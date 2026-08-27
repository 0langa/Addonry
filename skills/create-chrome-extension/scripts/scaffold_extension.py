#!/usr/bin/env python3
"""Create a dependency-free Manifest V3 project in durable personal storage."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from browser_targets import TARGET_CHOICES, browsers_for_choice, validate_firefox_id
from generate_icons import generate_icons

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def default_output_root(home: Path | None = None) -> Path:
    """Choose storage that survives plugin upgrades and cache cleanup."""
    user_home = (home or Path.home()).expanduser().resolve()
    source_repos = user_home / "source" / "repos"
    if source_repos.is_dir():
        return source_repos / "browser-extensions"
    return user_home / "browser-extensions"


DEFAULT_OUTPUT_ROOT = default_output_root()


def resolve_output_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    configured = os.environ.get("ADDONRY_OUTPUT_ROOT")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_OUTPUT_ROOT


def scaffold(
    slug: str,
    name: str,
    description: str,
    output_root: Path,
    color: str = "#7C3AED",
    browser: str = "both",
    firefox_id: str | None = None,
) -> Path:
    if not SLUG_RE.fullmatch(slug):
        raise ValueError("slug must use lower-case letters, digits, and single hyphens")
    if not name.strip() or not description.strip():
        raise ValueError("name and description are required")
    browsers = browsers_for_choice(browser)
    if "firefox" in browsers:
        firefox_id = validate_firefox_id(firefox_id) if firefox_id else "{" + str(uuid.uuid4()) + "}"

    output_root = output_root.expanduser().resolve()
    target = (output_root / slug).resolve()
    if target.parent != output_root:
        raise ValueError("resolved target escaped output root")
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")

    source_dir = target / "src"
    tests_dir = target / "tests"
    metadata_dir = target / ".addonry"
    for directory in (source_dir, tests_dir, metadata_dir):
        directory.mkdir(parents=True, exist_ok=False)

    starter = Path(__file__).resolve().parent.parent / "assets" / "starter"
    for source_name, destination_name in (
        ("popup.html", "popup.html"),
        ("popup.css", "popup.css"),
        ("popup.js", "popup.js"),
        ("service-worker.js", "service-worker.js"),
    ):
        text = (starter / source_name).read_text(encoding="utf-8").replace("__EXTENSION_NAME__", name)
        (source_dir / destination_name).write_text(text, encoding="utf-8", newline="\n")
    shutil.copyfile(starter / "e2e.cjs", tests_dir / "e2e.cjs")
    if "firefox" in browsers:
        shutil.copyfile(starter / "firefox_e2e.py", tests_dir / "firefox_e2e.py")

    icon_paths = generate_icons(target / "icons", color)
    icons = {str(size): f"icons/icon{size}.png" for size in (16, 32, 48, 128)}
    background: dict[str, object] = {}
    if "chrome" in browsers:
        background["service_worker"] = "src/service-worker.js"
    if "firefox" in browsers:
        background["scripts"] = ["src/service-worker.js"]
    manifest: dict[str, object] = {
        "manifest_version": 3,
        "name": name,
        "version": "0.1.0",
        "description": description,
        "icons": icons,
        "action": {
            "default_title": name,
            "default_popup": "src/popup.html",
            "default_icon": icons,
        },
        "background": background,
    }
    if "firefox" in browsers:
        manifest["browser_specific_settings"] = {
            "gecko": {
                "id": firefox_id,
                "data_collection_permissions": {"required": ["none"]},
            }
        }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")

    created_at = datetime.now(UTC).isoformat()
    contract = {
        "schemaVersion": 1,
        "status": "draft",
        "confirmedAt": None,
        "requestSummary": description,
        "browserTargets": list(browsers),
        "packagingRequested": False,
        "qualityPolicy": {"requireZeroWarnings": True, "stallThreshold": 3},
        "acceptedWarnings": [],
        "criteria": [],
    }
    (metadata_dir / "contract.json").write_text(
        json.dumps(contract, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    loop_state = {
        "schemaVersion": 1,
        "status": "not-run",
        "iteration": 0,
        "repeatCount": 0,
        "stallThreshold": 3,
        "nextAction": "Confirm atomic acceptance criteria before implementation.",
        "report": ".addonry/quality-report.json",
        "updatedAt": created_at,
        "history": [],
    }
    (metadata_dir / "quality-loop.json").write_text(
        json.dumps(loop_state, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    project = {
        "schemaVersion": 3,
        "slug": slug,
        "name": name,
        "createdAt": created_at,
        "status": "scaffolded",
        "acceptance": {},
        "browsers": list(browsers),
        "architecture": {"manifestVersion": 3, "buildStep": False, "sharedSource": True},
        "permissions": [],
        "verification": {target: {"status": "not-run"} for target in browsers},
        "installation": {target: {"status": "not-installed"} for target in browsers},
        "packaging": {"status": "not-packaged", "targets": list(browsers)},
        "qualityLoop": {
            "status": "not-run",
            "contract": ".addonry/contract.json",
            "state": ".addonry/quality-loop.json",
            "report": ".addonry/quality-report.json",
        },
    }
    (metadata_dir / "project.json").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8", newline="\n")

    readme = f"""# {name}

{description}

Personal browser extension generated by Addonry in durable user storage.

Targets: {", ".join(browser.title() for browser in browsers)}.

## Install or update

For Chrome, open `chrome://extensions`, enable Developer Mode, choose
**Load unpacked**, and select this directory. For Firefox development, use
`about:debugging` > **This Firefox** > **Load Temporary Add-on** and select
`manifest.json`. Normal Firefox installation requires Mozilla signing.

## Verify

Run Addonry target-aware validation and each requested browser's verification
gate before use. Packaging remains separate from installation and publication.
"""
    (target / "README.md").write_text(readme, encoding="utf-8", newline="\n")

    if len(icon_paths) != 4:
        raise RuntimeError("icon generation did not produce expected files")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--color", default="#7C3AED")
    parser.add_argument("--browser", choices=TARGET_CHOICES, default="both")
    parser.add_argument("--firefox-id")
    args = parser.parse_args()

    try:
        target = scaffold(
            args.slug,
            args.name,
            args.description,
            resolve_output_root(args.output_root),
            args.color,
            args.browser,
            args.firefox_id,
        )
    except (ValueError, FileExistsError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({"status": "created", "path": str(target)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
