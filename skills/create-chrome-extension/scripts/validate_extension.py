#!/usr/bin/env python3
"""Validate a personal Chrome/Firefox extension before browser testing or packaging."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from browser_targets import TARGET_CHOICES, project_browsers, validate_firefox_id

VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,3}$")
INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>\s*\S", re.IGNORECASE | re.DOTALL)
REMOTE_SCRIPT_RE = re.compile(r"<script[^>]+\bsrc\s*=\s*['\"]https?://", re.IGNORECASE)
INLINE_HANDLER_RE = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
# Match direct dynamic-code calls, not Puppeteer helpers such as `$eval(...)`.
EVAL_RE = re.compile(r"(?<![$\w])(?:eval|Function)\s*\(")
REMOTE_CODE_RE = re.compile(r"(?:import\s*\(|importScripts\s*\()[^\n]{0,200}https?://", re.IGNORECASE)
STATIC_REMOTE_IMPORT_RE = re.compile(
    r"(?:^|[;\n])\s*(?:import|export)\s+(?:[^;\n]*?\s+from\s+)?['\"]https?://",
    re.IGNORECASE,
)
SECRET_RE = re.compile(r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)['\"]?\s*[:=]\s*['\"][^'\"]{8,}")
HIGH_RISK_PERMISSIONS = {"cookies", "debugger", "history", "management", "nativeMessaging", "proxy", "tabs", "webRequest", "webRequestBlocking"}
BROAD_HOST_PATTERNS = {"<all_urls>", "*://*/*", "http://*/*", "https://*/*"}
TEXT_SOURCE_SUFFIXES = {".js", ".mjs", ".cjs", ".html", ".htm", ".json", ".css", ".txt", ".yaml", ".yml"}
IGNORED_DIGEST_DIRECTORIES = {".addonry", ".git", "__pycache__", "artifacts", "node_modules", "web-ext-artifacts"}


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str
    path: str | None = None


def _confirmed_contract_has_criteria(root: Path) -> bool:
    """Allow quality-loop contract to replace legacy project.acceptance map."""
    contract_path = root / ".addonry" / "contract.json"
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(contract, dict)
        and contract.get("status") == "confirmed"
        and isinstance(contract.get("criteria"), list)
        and bool(contract["criteria"])
    )


def contract_digest(root: Path) -> str | None:
    """Hash confirmed acceptance contract independently from runtime source."""
    contract_path = root.expanduser().resolve() / ".addonry" / "contract.json"
    if not _confirmed_contract_has_criteria(root.expanduser().resolve()):
        return None
    return hashlib.sha256(contract_path.read_bytes()).hexdigest()


def source_digest(root: Path) -> str:
    """Match verifier digest so stale browser evidence can be rejected."""
    root = root.expanduser().resolve()
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not any(part in IGNORED_DIGEST_DIRECTORIES for part in path.relative_to(root).parts)
    )
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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
    if isinstance(background, dict):
        if isinstance(background.get("service_worker"), str):
            yield background["service_worker"]
        scripts = background.get("scripts", [])
        if isinstance(scripts, list):
            yield from (value for value in scripts if isinstance(value, str))

    for key in ("options_page", "devtools_page"):
        if isinstance(manifest.get(key), str):
            yield manifest[key]
    options_ui = manifest.get("options_ui", {})
    if isinstance(options_ui, dict) and isinstance(options_ui.get("page"), str):
        yield options_ui["page"]
    side_panel = manifest.get("side_panel", {})
    if isinstance(side_panel, dict) and isinstance(side_panel.get("default_path"), str):
        yield side_panel["default_path"]

    overrides = manifest.get("chrome_url_overrides", {})
    if isinstance(overrides, dict):
        yield from (value for value in overrides.values() if isinstance(value, str))

    sandbox = manifest.get("sandbox", {})
    if isinstance(sandbox, dict):
        pages = sandbox.get("pages", [])
        if isinstance(pages, list):
            yield from (value for value in pages if isinstance(value, str))

    web_resources = manifest.get("web_accessible_resources", [])
    for resource in (web_resources if isinstance(web_resources, list) else []):
        if isinstance(resource, dict):
            values = resource.get("resources", [])
            if isinstance(values, list):
                yield from (value for value in values if isinstance(value, str))

    rules = manifest.get("declarative_net_request", {})
    if isinstance(rules, dict):
        rule_resources = rules.get("rule_resources", [])
        for resource in (rule_resources if isinstance(rule_resources, list) else []):
            if isinstance(resource, dict) and isinstance(resource.get("path"), str):
                yield resource["path"]

    content_scripts = manifest.get("content_scripts", [])
    for script in (content_scripts if isinstance(content_scripts, list) else []):
        if isinstance(script, dict):
            for key in ("js", "css"):
                values = script.get(key, [])
                if isinstance(values, list):
                    yield from (value for value in values if isinstance(value, str))


def validate_extension(
    root: Path,
    *,
    release_ready: bool = False,
    final_ready: bool = False,
    target: str = "auto",
) -> list[Finding]:
    root = root.expanduser().resolve()
    release_ready = release_ready or final_ready
    browsers = project_browsers(root, target)
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

    background = manifest.get("background")
    if background is not None and not isinstance(background, dict):
        findings.append(Finding("error", "invalid-background", "background must be an object", "manifest.json"))
    elif isinstance(background, dict):
        if "chrome" in browsers and not isinstance(background.get("service_worker"), str):
            findings.append(Finding("error", "chrome-background-missing", "Chrome target requires background.service_worker", "manifest.json"))
        scripts = background.get("scripts")
        if "firefox" in browsers and (
            not isinstance(scripts, list)
            or not scripts
            or any(not isinstance(item, str) for item in scripts)
        ):
            findings.append(Finding("error", "firefox-background-missing", "Firefox target requires non-empty background.scripts", "manifest.json"))

    if "firefox" in browsers:
        browser_settings = manifest.get("browser_specific_settings")
        gecko = browser_settings.get("gecko") if isinstance(browser_settings, dict) else None
        if not isinstance(gecko, dict):
            findings.append(Finding("error", "firefox-settings-missing", "Firefox target requires browser_specific_settings.gecko", "manifest.json"))
        else:
            firefox_id = gecko.get("id")
            try:
                validate_firefox_id(firefox_id if isinstance(firefox_id, str) else "")
            except ValueError:
                findings.append(Finding("error", "firefox-id-invalid", "Firefox target requires valid Gecko extension ID", "manifest.json"))
            collection = gecko.get("data_collection_permissions")
            required_collection = collection.get("required") if isinstance(collection, dict) else None
            if (
                not isinstance(required_collection, list)
                or not required_collection
                or any(not isinstance(item, str) for item in required_collection)
            ):
                findings.append(Finding("error", "firefox-data-collection-missing", "Firefox target requires explicit Gecko data collection declaration", "manifest.json"))
            elif "none" in required_collection and len(required_collection) != 1:
                findings.append(Finding("error", "firefox-data-collection-invalid", "Firefox data collection value 'none' cannot be combined with other values", "manifest.json"))

        if "side_panel" in manifest:
            findings.append(Finding("error", "firefox-side-panel-unsupported", "Firefox target cannot use Chrome side_panel manifest key; design a portable UI", "manifest.json"))

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

    permission_fields = ("permissions", "optional_permissions", "host_permissions", "optional_host_permissions")
    for field in permission_fields:
        value = manifest.get(field, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            findings.append(Finding("error", "invalid-permission-list", f"{field} must be an array of strings", "manifest.json"))

    for field in ("content_scripts", "web_accessible_resources"):
        if field in manifest and not isinstance(manifest[field], list):
            findings.append(Finding("error", "invalid-manifest-list", f"{field} must be an array", "manifest.json"))

    permissions = {
        value
        for key in ("permissions", "optional_permissions")
        for value in (manifest.get(key, []) if isinstance(manifest.get(key, []), list) else [])
        if isinstance(value, str)
    }
    host_patterns = {
        value
        for key in ("host_permissions", "optional_host_permissions")
        for value in (manifest.get(key, []) if isinstance(manifest.get(key, []), list) else [])
        if isinstance(value, str)
    }
    content_scripts = manifest.get("content_scripts", [])
    for script in (content_scripts if isinstance(content_scripts, list) else []):
        if isinstance(script, dict):
            matches = script.get("matches", [])
            if not isinstance(matches, list) or any(not isinstance(item, str) for item in matches):
                findings.append(Finding("error", "invalid-content-script-matches", "content_scripts.matches must be an array of strings", "manifest.json"))
            else:
                host_patterns.update(matches)

    for permission in sorted(permissions & HIGH_RISK_PERMISSIONS):
        findings.append(Finding("warning", "high-risk-permission", f"permission requires explicit acceptance rationale: {permission}", "manifest.json"))
    for pattern in sorted(host_patterns & BROAD_HOST_PATTERNS):
        findings.append(Finding("warning", "broad-host-access", f"{pattern} requires explicit scope rationale", "manifest.json"))

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
        if suffix not in TEXT_SOURCE_SUFFIXES and path.name != ".env":
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
        elif suffix in {".js", ".mjs", ".cjs"}:
            if EVAL_RE.search(text):
                findings.append(Finding("error", "dynamic-code", "eval/new Function is forbidden", relative))
            if REMOTE_CODE_RE.search(text) or STATIC_REMOTE_IMPORT_RE.search(text):
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
                legacy_acceptance = (
                    isinstance(project, dict)
                    and isinstance(project.get("acceptance"), dict)
                    and bool(project["acceptance"])
                )
                if not legacy_acceptance and not _confirmed_contract_has_criteria(root):
                    findings.append(Finding("error", "acceptance-missing", "record concrete acceptance criteria before final verification", ".addonry/project.json"))

        starter_popup = "Ready. Replace this scaffold with requested workflow."
        for path in root.rglob("*.html"):
            if path.is_file() and starter_popup in path.read_text(encoding="utf-8"):
                findings.append(Finding("error", "starter-ui", "starter popup remains unchanged", path.relative_to(root).as_posix()))
        starter_scenario = Path(__file__).resolve().parent.parent / "assets" / "starter" / "e2e.cjs"
        scenario_path = root / "tests" / "e2e.cjs"
        if starter_scenario.is_file() and scenario_path.is_file() and scenario_path.read_bytes() == starter_scenario.read_bytes():
            findings.append(Finding("error", "starter-e2e", "tailor tests/e2e.cjs to requested behavior", "tests/e2e.cjs"))
        if not scenario_path.is_file() or "exports.run" not in scenario_path.read_text(encoding="utf-8"):
            findings.append(Finding("error", "e2e-contract", "tests/e2e.cjs must export run(context)", "tests/e2e.cjs"))
        if "firefox" in browsers:
            firefox_starter = Path(__file__).resolve().parent.parent / "assets" / "starter" / "firefox_e2e.py"
            firefox_scenario = root / "tests" / "firefox_e2e.py"
            if not firefox_scenario.is_file() or "def run(" not in firefox_scenario.read_text(encoding="utf-8"):
                findings.append(Finding("error", "firefox-e2e-contract", "tests/firefox_e2e.py must define run(context)", "tests/firefox_e2e.py"))
            elif firefox_starter.is_file() and firefox_scenario.read_bytes() == firefox_starter.read_bytes():
                findings.append(Finding("error", "starter-firefox-e2e", "tailor tests/firefox_e2e.py to requested behavior", "tests/firefox_e2e.py"))

    if final_ready and "chrome" in browsers:
        verification_path = root / ".addonry" / "verification.json"
        if not verification_path.is_file():
            findings.append(Finding("error", "verification-missing", "final-ready validation requires .addonry/verification.json", ".addonry/verification.json"))
        else:
            try:
                verification = json.loads(verification_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                findings.append(Finding("error", "verification-invalid", f"verification evidence cannot be parsed: {error}", ".addonry/verification.json"))
            else:
                if not isinstance(verification, dict) or verification.get("status") != "passed":
                    findings.append(Finding("error", "verification-not-passed", "latest real-Chrome verification must have passed", ".addonry/verification.json"))
                if not isinstance(verification, dict) or verification.get("sourceSha256") != source_digest(root):
                    findings.append(Finding("error", "verification-stale", "verification digest does not match current extension source", ".addonry/verification.json"))
                expected_contract_sha = contract_digest(root)
                if expected_contract_sha is not None and (
                    not isinstance(verification, dict)
                    or verification.get("contractSha256") != expected_contract_sha
                ):
                    findings.append(Finding("error", "verification-contract-stale", "verification does not match current acceptance contract", ".addonry/verification.json"))
                if not isinstance(verification, dict) or verification.get("scenario") == "generic-popup":
                    findings.append(Finding("error", "verification-generic", "final evidence must use tailored E2E scenario", ".addonry/verification.json"))
                elif isinstance(verification, dict):
                    scenario = verification.get("scenario")
                    expected_scenario = (root / "tests" / "e2e.cjs").resolve()
                    if not isinstance(scenario, str) or Path(scenario).expanduser().resolve() != expected_scenario:
                        findings.append(Finding("error", "verification-scenario-mismatch", "verification must use this extension's tests/e2e.cjs", ".addonry/verification.json"))
                mcp = verification.get("chromeDevtoolsMcp", {}) if isinstance(verification, dict) else {}
                if not isinstance(mcp, dict) or mcp.get("status") != "passed":
                    findings.append(Finding("error", "mcp-verification-missing", "Chrome DevTools MCP evidence must have passed", ".addonry/verification.json"))
                limitations = verification.get("limitations", []) if isinstance(verification, dict) else []
                if not isinstance(limitations, list) or limitations:
                    findings.append(Finding("error", "verification-limitations", "resolve E2E limitations before final-ready claim", ".addonry/verification.json"))
                cleanup_warnings = verification.get("cleanupWarnings", []) if isinstance(verification, dict) else []
                if not isinstance(cleanup_warnings, list) or cleanup_warnings:
                    findings.append(Finding("error", "verification-cleanup", "rerun after resolving E2E cleanup warnings", ".addonry/verification.json"))
                registration = verification.get("extensionRegistration", {}) if isinstance(verification, dict) else {}
                required_registration = {"id", "name", "version", "path", "enabled"}
                if not isinstance(registration, dict) or not required_registration <= set(registration) or registration.get("enabled") is not True:
                    findings.append(Finding("error", "extension-registration-missing", "browser registration evidence is incomplete", ".addonry/verification.json"))
                elif (
                    not isinstance(registration.get("id"), str)
                    or re.fullmatch(r"[a-p]{32}", registration["id"]) is None
                    or registration.get("name") != manifest.get("name")
                    or registration.get("version") != manifest.get("version")
                    or not isinstance(registration.get("path"), str)
                    or Path(registration["path"]).expanduser().resolve() != root
                ):
                    findings.append(Finding("error", "extension-registration-mismatch", "browser registration does not match current extension identity and source path", ".addonry/verification.json"))
                for field in ("consoleErrors", "pageErrors", "workerErrors"):
                    errors = verification.get(field, []) if isinstance(verification, dict) else []
                    if not isinstance(errors, list) or errors:
                        findings.append(Finding("error", "browser-errors-present", f"verification contains unresolved {field}", ".addonry/verification.json"))

    if final_ready and "firefox" in browsers:
        verification_path = root / ".addonry" / "firefox-verification.json"
        if not verification_path.is_file():
            findings.append(Finding("error", "firefox-verification-missing", "final-ready validation requires Firefox evidence", ".addonry/firefox-verification.json"))
        else:
            try:
                verification = json.loads(verification_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                findings.append(Finding("error", "firefox-verification-invalid", f"Firefox evidence cannot be parsed: {error}", ".addonry/firefox-verification.json"))
            else:
                if not isinstance(verification, dict) or verification.get("status") != "passed":
                    findings.append(Finding("error", "firefox-verification-not-passed", "latest real-Firefox verification must have passed", ".addonry/firefox-verification.json"))
                if not isinstance(verification, dict) or verification.get("sourceSha256") != source_digest(root):
                    findings.append(Finding("error", "firefox-verification-stale", "Firefox evidence digest does not match current extension source", ".addonry/firefox-verification.json"))
                expected_contract_sha = contract_digest(root)
                if expected_contract_sha is not None and (
                    not isinstance(verification, dict)
                    or verification.get("contractSha256") != expected_contract_sha
                ):
                    findings.append(Finding("error", "firefox-verification-contract-stale", "Firefox evidence does not match current acceptance contract", ".addonry/firefox-verification.json"))
                lint = verification.get("lint", {}) if isinstance(verification, dict) else {}
                if not isinstance(lint, dict) or lint.get("status") != "passed":
                    findings.append(Finding("error", "firefox-lint-missing", "Firefox web-ext lint must pass", ".addonry/firefox-verification.json"))
                registration = verification.get("extensionRegistration", {}) if isinstance(verification, dict) else {}
                if (
                    not isinstance(registration, dict)
                    or registration.get("enabled") is not True
                    or not isinstance(registration.get("id"), str)
                    or registration.get("name") != manifest.get("name")
                    or registration.get("version") != manifest.get("version")
                    or registration.get("temporary") is not True
                ):
                    findings.append(Finding("error", "firefox-registration-mismatch", "Firefox temporary registration does not match current extension", ".addonry/firefox-verification.json"))
                limitations = verification.get("limitations", []) if isinstance(verification, dict) else []
                if not isinstance(limitations, list) or limitations:
                    findings.append(Finding("error", "firefox-verification-limitations", "resolve Firefox verification limitations before final-ready claim", ".addonry/firefox-verification.json"))
                cleanup_warnings = verification.get("cleanupWarnings", []) if isinstance(verification, dict) else []
                if not isinstance(cleanup_warnings, list) or cleanup_warnings:
                    findings.append(Finding("error", "firefox-verification-cleanup", "resolve Firefox cleanup warnings before final-ready claim", ".addonry/firefox-verification.json"))
                for field in ("consoleErrors", "pageErrors", "backgroundErrors"):
                    errors = verification.get(field, []) if isinstance(verification, dict) else []
                    if not isinstance(errors, list) or errors:
                        findings.append(Finding("error", "firefox-errors-present", f"Firefox verification contains unresolved {field}", ".addonry/firefox-verification.json"))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extension_path", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--release-ready", action="store_true")
    parser.add_argument("--final-ready", action="store_true")
    parser.add_argument("--browser-target", choices=("auto",) + TARGET_CHOICES, default="auto")
    args = parser.parse_args()
    findings = validate_extension(
        args.extension_path,
        release_ready=args.release_ready,
        final_ready=args.final_ready,
        target=args.browser_target,
    )
    errors = [finding for finding in findings if finding.level == "error"]
    payload = {
        "extension": str(args.extension_path.expanduser().resolve()),
        "browsers": list(project_browsers(args.extension_path.expanduser().resolve(), args.browser_target)),
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
