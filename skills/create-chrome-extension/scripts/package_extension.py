#!/usr/bin/env python3
"""Build deterministic Chrome/Firefox ZIP packages from one Addonry project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from browser_targets import TARGET_CHOICES, browsers_for_choice, manifest_for_browser, project_browsers
from validate_extension import contract_digest, source_digest, validate_extension

EXCLUDED_DIRECTORIES = frozenset(
    {
        ".addonry",
        ".git",
        ".venv",
        "__pycache__",
        "artifacts",
        "build",
        "dist",
        "node_modules",
        "tests",
        "web-ext-artifacts",
    }
)
EXCLUDED_ROOT_FILES = frozenset(
    {
        ".gitignore",
        "IMPLEMENTATION_PLAN.md",
        "README.md",
        "ROADMAP.md",
    }
)
SENSITIVE_SUFFIXES = frozenset({".key", ".p12", ".pem", ".pfx"})
SENSITIVE_NAME_RE = re.compile(r"(?i)(?:^|[._-])(credential|password|private[-_]?key|secret|token)(?:[._-]|$)")
DETERMINISTIC_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _runtime_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"package input cannot contain symbolic link: {relative.as_posix()}")
        if not path.is_file() or relative.as_posix() == "manifest.json":
            continue
        if len(relative.parts) == 1 and path.name in EXCLUDED_ROOT_FILES:
            continue
        if path.name == ".env" or path.name.startswith(".env."):
            raise ValueError(f"refusing sensitive environment file: {relative.as_posix()}")
        if path.suffix.lower() in SENSITIVE_SUFFIXES or SENSITIVE_NAME_RE.search(path.name):
            raise ValueError(f"refusing sensitive filename: {relative.as_posix()}")
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"package input escapes extension root: {relative.as_posix()}")
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, DETERMINISTIC_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.flag_bits |= 0x800
    return info


def _write_package(
    root: Path,
    browser: str,
    manifest: dict[str, Any],
    runtime_files: list[Path],
    destination: Path,
) -> dict[str, Any]:
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=destination.stem + ".",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.writestr(_zip_info("manifest.json"), manifest_bytes)
            for path in runtime_files:
                name = path.relative_to(root).as_posix()
                archive.writestr(_zip_info(name), path.read_bytes())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    payload = destination.read_bytes()
    with zipfile.ZipFile(destination, "r") as archive:
        names = archive.namelist()
        if not names or names[0] != "manifest.json" or len(names) != len(set(names)):
            raise RuntimeError(f"invalid {browser} package layout")
        packaged_manifest = json.loads(archive.read("manifest.json"))
        if packaged_manifest != manifest:
            raise RuntimeError(f"{browser} package manifest mismatch")
        bad_parts = sorted(
            name
            for name in names
            if any(part in EXCLUDED_DIRECTORIES for part in Path(name).parts)
        )
        if bad_parts:
            raise RuntimeError(f"excluded path entered {browser} package: {bad_parts[0]}")
    return {
        "browser": browser,
        "path": str(destination),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "files": len(names),
    }


def package_extension(
    root: Path,
    *,
    target: str = "auto",
    output_dir: Path | None = None,
    overwrite: bool = False,
    record: bool = True,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    configured = project_browsers(root)
    requested = configured if target == "auto" else browsers_for_choice(target)
    unsupported = [browser for browser in requested if browser not in configured]
    if unsupported:
        raise ValueError(f"project is not configured for: {', '.join(unsupported)}")
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"manifest.json cannot be packaged: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json root must be an object")

    findings = []
    for browser in requested:
        findings.extend(validate_extension(root, release_ready=True, target=browser))
    errors = [finding for finding in findings if finding.level == "error"]
    if errors:
        first = errors[0]
        raise ValueError(f"validation failed [{first.code}]: {first.message}")

    project_path = root / ".addonry" / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    slug = project.get("slug") if isinstance(project, dict) else None
    if not isinstance(slug, str) or not slug:
        raise ValueError("project metadata requires slug")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("manifest requires version")

    destination_root = (output_dir or root / "artifacts").expanduser().resolve()
    if (destination_root / "KEEP").is_file():
        raise ValueError(f"KEEP blocks package output: {destination_root}")
    runtime_files = _runtime_files(root)
    package_rows = []
    for browser in requested:
        destination = destination_root / f"{slug}-{version}-{browser}.zip"
        if destination.exists() and not overwrite:
            raise FileExistsError(f"package already exists: {destination}")
        package_rows.append(
            _write_package(root, browser, manifest_for_browser(manifest, browser), runtime_files, destination)
        )

    report = {
        "schemaVersion": 1,
        "status": "packaged",
        "createdAt": datetime.now(UTC).isoformat(),
        "sourcePath": str(root),
        "sourceSha256": source_digest(root),
        "contractSha256": contract_digest(root),
        "version": version,
        "targets": list(requested),
        "packages": package_rows,
        "signed": False,
        "published": False,
    }
    if record:
        metadata_dir = root / ".addonry"
        metadata_dir.mkdir(exist_ok=True)
        report_path = metadata_dir / "package-report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
        if isinstance(project, dict):
            project["packaging"] = {
                "status": "packaged",
                "targets": list(requested),
                "report": str(report_path),
            }
            project_path.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extension_path", type=Path)
    parser.add_argument("--target", choices=("auto",) + TARGET_CHOICES, default="auto")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()
    try:
        report = package_extension(
            args.extension_path,
            target=args.target,
            output_dir=args.output_dir,
            overwrite=args.overwrite,
            record=not args.no_record,
        )
    except (FileExistsError, OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
