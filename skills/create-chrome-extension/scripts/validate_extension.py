#!/usr/bin/env python3
"""Validate a personal unpacked Chrome extension before browser testing."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,3}$")
INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>\s*\S", re.IGNORECASE | re.DOTALL)
REMOTE_SCRIPT_RE = re.compile(r"<script[^>]+\bsrc\s*=\s*['\"]https?://", re.IGNORECASE)
INLINE_HANDLER_RE = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
# Match direct dynamic-code calls, not Puppeteer helpers such as `$eval(...)`.
EVAL_RE = re.compile(r"(?<![$\w])(?:eval\s*\(|new\s+Function\s*\()")
REMOTE_CODE_RE = re.compile(r"(?:import\s*\(|importScripts\s*\()[^\n]{0,200}https?://", re.IGNORECASE)
SECRET_RE = re.compile(r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"][^'\"]{8,}")
HIGH_RISK_PERMISSIONS = {"cookies", "debugger", "history", "management", "nativeMessaging", "proxy", "tabs", "webRequest", "webRequestBlocking"}


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str
    path: str | None = None


def _manifest_paths(manifest: dict[str, Any]) -> Iterable[str]:
    icons = manifest.get("icons", {})
    if isinstance(icons, dict):
        yield from (value for value in icons.values() if isinstance(value, str))

    action = manifest.get("action", {})
    if isinstance(action, dict):
        popup = action.get("default_popup")
        if isinstance(popup, str):
            yield popup
        action_icons = action.get("default_icon", {})
        if isinstance(action_icons, str):
            yield action_icons
        elif isinstance(action_icons, dict):
            yield from (value for value in action_icons.values() if isinstance(value, str))

    background = manifest.get("background", {})
    if isinstance(background, dict) and isinstance(background.get("service_worker"), str):
        yield background["service_worker"]

    for key in ("options_page", "devtools_page"):
        if isinstance(manifest.get(key), str):
            yield manifest[key]
    options_ui = manifest.get("options_ui", {})
    if isinstance(options_ui, dict) and isinstance(options_ui.get("page"), str):
        yield options_ui["page"]
    side_panel = manifest.get("side_panel", {})
    if isinstance(side_panel, dict) and isinstance(side_panel.get("default_path"), str):
        yield side_panel["default_path"]

    for script in manifest.get("content_scripts", []):
        if isinstance(script, dict):
            for key in ("js", "css"):
                values = script.get(key, [])
                if isinstance(values, list):
                    yield from (value for value in values if isinstance(value, str))


def validate_extension(root: Path, *, release_ready: bool = False) -> list[Finding]:
    root = root.expanduser().resolve()
    findings: list[Finding] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return [Finding("error", "manifest-missing", "manifest.json is missing", str(manifest_path))]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [Finding("error", "manifest-invalid", f"manifest.json cannot be parsed: {error}", str(manifest_path))]
    if not isinstance(manifest, dict):
        return [Finding("error", "manifest-shape", "manifest root must be an object", str(manifest_path))]

    if manifest.get("manifest_version") != 3:
        findings.append(Finding("error", "manifest-version", "manifest_version must be 3", "manifest.json"))
    for field in ("name", "version"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            findings.append(Finding("error", f"missing-{field}", f"{field} must be a non-empty string", "manifest.json"))
    if isinstance(manifest.get("version"), str) and not VERSION_RE.fullmatch(manifest["version"]):
        findings.append(Finding("error", "invalid-version", "version must contain one to four dot-separated integers", "manifest.json"))

    for referenced in sorted(set(_manifest_paths(manifest))):
        normalized = referenced.replace("\\", "/")
        candidate = (root / normalized).resolve()
        try:
            inside = candidate.is_relative_to(root)
        except AttributeError:  # pragma: no cover - Python < 3.9 compatibility
            inside = str(candidate).startswith(str(root))
        if not inside:
            findings.append(Finding("error", "path-escape", f"manifest path escapes extension root: {referenced}", "manifest.json"))
        elif "*" not in referenced and not candidate.is_file():
            findings.append(Finding("error", "referenced-file-missing", f"manifest references missing file: {referenced}", "manifest.json"))

    permissions = set(value for value in manifest.get("permissions", []) if isinstance(value, str))
    host_permissions = set(value for value in manifest.get("host_permissions", []) if isinstance(value, str))
    for permission in sorted(permissions & HIGH_RISK_PERMISSIONS):
        findings.append(Finding("warning", "high-risk-permission", f"permission requires explicit acceptance rationale: {permission}", "manifest.json"))
    if "<all_urls>" in host_permissions:
        findings.append(Finding("warning", "broad-host-access", "<all_urls> requires explicit scope rationale", "manifest.json"))

    csp = manifest.get("content_security_policy")
    csp_text = json.dumps(csp) if csp is not None else ""
    if "'unsafe-eval'" in csp_text:
        findings.append(Finding("error", "unsafe-eval-csp", "extension CSP permits unsafe-eval", "manifest.json"))
    if isinstance(manifest.get("update_url"), str):
        findings.append(Finding("warning", "update-url", "personal unpacked extension should not need update_url", "manifest.json"))

    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in {"node_modules", ".git"} for part in path.parts):
            continue
        suffix = path.suffix.lower()
        if suffix not in {".js", ".mjs", ".cjs", ".html", ".htm"}:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            findings.append(Finding("error", "non-utf8-source", "source file is not UTF-8", relative))
            continue
        if suffix in {".html", ".htm"}:
            if REMOTE_SCRIPT_RE.search(text):
                findings.append(Finding("error", "remote-script", "remote script source is forbidden in Manifest V3", relative))
            if INLINE_SCRIPT_RE.search(text):
                findings.append(Finding("error", "inline-script", "inline executable script violates extension CSP", relative))
            if INLINE_HANDLER_RE.search(text):
                findings.append(Finding("error", "inline-handler", "inline event handlers violate extension CSP", relative))
        else:
            if EVAL_RE.search(text):
                findings.append(Finding("error", "dynamic-code", "eval/new Function is forbidden", relative))
            if REMOTE_CODE_RE.search(text):
                findings.append(Finding("error", "remote-code", "remote executable code import is forbidden", relative))
        if SECRET_RE.search(text):
            findings.append(Finding("error", "embedded-secret", "possible embedded credential found", relative))

    if release_ready:
        project_path = root / ".addonry" / "project.json"
        if not project_path.is_file():
            findings.append(Finding("error", "project-metadata-missing", "release-ready validation requires .addonry/project.json", ".addonry/project.json"))
        else:
            try:
                project = json.loads(project_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                findings.append(Finding("error", "project-metadata-invalid", f"project metadata cannot be parsed: {error}", ".addonry/project.json"))
            else:
                if not isinstance(project, dict) or project.get("status") == "scaffolded":
                    findings.append(Finding("error", "scaffold-status", "project status must move beyond scaffolded before final verification", ".addonry/project.json"))
                if not isinstance(project, dict) or not isinstance(project.get("acceptance"), dict) or not project["acceptance"]:
                    findings.append(Finding("error", "acceptance-missing", "record concrete acceptance criteria before final verification", ".addonry/project.json"))

        starter_popup = "Ready. Replace this scaffold with requested workflow."
        for path in root.rglob("*.html"):
            if path.is_file() and starter_popup in path.read_text(encoding="utf-8"):
                findings.append(Finding("error", "starter-ui", "starter popup remains unchanged", path.relative_to(root).as_posix()))
        starter_scenario = Path(__file__).resolve().parent.parent / "assets" / "starter" / "e2e.cjs"
        scenario_path = root / "tests" / "e2e.cjs"
        if starter_scenario.is_file() and scenario_path.is_file() and scenario_path.read_bytes() == starter_scenario.read_bytes():
            findings.append(Finding("error", "starter-e2e", "tailor tests/e2e.cjs to requested behavior", "tests/e2e.cjs"))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extension_path", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--release-ready", action="store_true")
    args = parser.parse_args()
    findings = validate_extension(args.extension_path, release_ready=args.release_ready)
    errors = [finding for finding in findings if finding.level == "error"]
    payload = {
        "extension": str(args.extension_path.expanduser().resolve()),
        "errors": len(errors),
        "warnings": sum(finding.level == "warning" for finding in findings),
        "findings": [asdict(finding) for finding in findings],
    }
    if args.as_json:
        print(json.dumps(payload, indent=2))
    else:
        for finding in findings:
            location = f" ({finding.path})" if finding.path else ""
            print(f"{finding.level.upper()} {finding.code}: {finding.message}{location}")
        print(f"Validation: {payload['errors']} error(s), {payload['warnings']} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
