from __future__ import annotations

import json
import os
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "skills" / "create-chrome-extension" / "scripts"
sys.path.insert(0, str(TOOLS))

from generate_icons import PNG_SIGNATURE, generate_icons, parse_hex_color  # noqa: E402
from scaffold_extension import default_output_root, resolve_output_root, scaffold  # noqa: E402
from validate_extension import source_digest, validate_extension  # noqa: E402


class IconTests(unittest.TestCase):
    def test_generates_expected_png_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = generate_icons(Path(temporary), "#123456")
            self.assertEqual([path.name for path in paths], ["icon16.png", "icon32.png", "icon48.png", "icon128.png"])
            for path in paths:
                payload = path.read_bytes()
                self.assertTrue(payload.startswith(PNG_SIGNATURE))
                width, height = struct.unpack(">II", payload[16:24])
                expected = int(path.stem.removeprefix("icon"))
                self.assertEqual((width, height), (expected, expected))

    def test_rejects_invalid_color(self) -> None:
        with self.assertRaises(ValueError):
            parse_hex_color("#123")


class ScaffoldTests(unittest.TestCase):
    def test_default_output_prefers_personal_source_repos(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / "source" / "repos").mkdir(parents=True)
            self.assertEqual(default_output_root(home), home / "source" / "repos" / "chrome-extensions")

    def test_default_output_falls_back_to_personal_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            self.assertEqual(default_output_root(home), home / "chrome-extensions")

    def test_environment_output_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configured = Path(temporary) / "custom"
            with patch.dict(os.environ, {"ADDONRY_OUTPUT_ROOT": str(configured)}):
                self.assertEqual(resolve_output_root(None), configured.resolve())

    def test_scaffold_passes_static_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = scaffold("tab-helper", "Tab Helper", "Keeps current tab visible.", Path(temporary))
            findings = validate_extension(target)
            self.assertEqual([item for item in findings if item.level == "error"], [])
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_version"], 3)
            self.assertTrue((target / "tests" / "e2e.cjs").is_file())
            self.assertTrue((target / ".addonry" / "project.json").is_file())
            readme = (target / "README.md").read_text(encoding="utf-8")
            self.assertIn("Google Chrome 137+", readme)
            self.assertIn("--final-ready", readme)
            self.assertNotIn("Use Addonry's guarded Chrome restart helper when authorized", readme)

    def test_scaffold_fails_release_ready_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = scaffold("unfinished", "Unfinished", "Still starter content.", Path(temporary))
            codes = {item.code for item in validate_extension(target, release_ready=True)}
            self.assertTrue({"scaffold-status", "acceptance-missing", "starter-ui", "starter-e2e"} <= codes)

    def test_refuses_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scaffold("same", "Same", "First.", Path(temporary))
            with self.assertRaises(FileExistsError):
                scaffold("same", "Same", "Second.", Path(temporary))

    def test_rejects_unsafe_slug(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                scaffold("../escape", "Escape", "Unsafe.", Path(temporary))


class ValidatorTests(unittest.TestCase):
    def test_detects_missing_file_and_remote_script(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_version": 3,
                        "name": "Broken",
                        "version": "1.0.0",
                        "action": {"default_popup": "missing.html"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "bad.html").write_text('<script src="https://example.com/app.js"></script>', encoding="utf-8")
            codes = {item.code for item in validate_extension(root)}
            self.assertIn("referenced-file-missing", codes)
            self.assertIn("remote-script", codes)

    def test_warns_on_sensitive_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_version": 3,
                        "name": "Cookie Tool",
                        "version": "1.0.0",
                        "permissions": ["cookies"],
                        "host_permissions": ["<all_urls>"],
                    }
                ),
                encoding="utf-8",
            )
            codes = {item.code for item in validate_extension(root)}
            self.assertIn("high-risk-permission", codes)
            self.assertIn("broad-host-access", codes)

    def test_checks_optional_permissions_content_matches_and_manifest_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_version": 3,
                        "name": "Broad Tool",
                        "version": "1.0.0",
                        "optional_permissions": ["cookies"],
                        "content_scripts": [{"matches": ["*://*/*"], "js": ["content.js"]}],
                        "web_accessible_resources": [{"resources": ["missing.js"], "matches": ["https://example.com/*"]}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "content.js").write_text("export const ready = true;", encoding="utf-8")
            codes = {item.code for item in validate_extension(root)}
            self.assertIn("high-risk-permission", codes)
            self.assertIn("broad-host-access", codes)
            self.assertIn("referenced-file-missing", codes)

    def test_detects_static_remote_import_and_secret_in_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(
                json.dumps({"manifest_version": 3, "name": "Unsafe", "version": "1.0.0"}),
                encoding="utf-8",
            )
            (root / "module.js").write_text("import helper from 'https://example.com/helper.js';", encoding="utf-8")
            (root / "settings.json").write_text('{"api_key": "1234567890abcdef"}', encoding="utf-8")
            codes = {item.code for item in validate_extension(root)}
            self.assertIn("remote-code", codes)
            self.assertIn("embedded-secret", codes)

    def test_malformed_permission_fields_return_findings_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_version": 3,
                        "name": "Malformed",
                        "version": "1.0.0",
                        "permissions": None,
                        "content_scripts": None,
                    }
                ),
                encoding="utf-8",
            )
            codes = {item.code for item in validate_extension(root)}
            self.assertIn("invalid-permission-list", codes)
            self.assertIn("invalid-manifest-list", codes)

    def test_final_ready_rejects_stale_browser_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = scaffold("verified", "Verified", "Verified extension.", Path(temporary))
            (root / "src" / "popup.html").write_text("<!doctype html><title>Verified</title><script src=\"popup.js\"></script>", encoding="utf-8")
            (root / "tests" / "e2e.cjs").write_text("exports.run = async ({ assert }) => { assert.ok(true); };\n", encoding="utf-8")
            project_path = root / ".addonry" / "project.json"
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project["status"] = "implemented"
            project["acceptance"] = {"popup": "opens"}
            project_path.write_text(json.dumps(project), encoding="utf-8")
            evidence = {
                "status": "passed",
                "sourceSha256": source_digest(root),
                "scenario": str(root / "tests" / "e2e.cjs"),
                "limitations": [],
                "cleanupWarnings": [],
                "chromeDevtoolsMcp": {"status": "passed"},
                "extensionRegistration": {
                    "id": "abcdefghijklmnopabcdefghijklmnop",
                    "name": "Verified",
                    "version": "0.1.0",
                    "path": str(root),
                    "enabled": True,
                },
            }
            verification_path = root / ".addonry" / "verification.json"
            verification_path.write_text(json.dumps(evidence), encoding="utf-8")
            self.assertEqual([item for item in validate_extension(root, final_ready=True) if item.level == "error"], [])

            (root / "src" / "popup.js").write_text("document.body.dataset.changed = 'true';", encoding="utf-8")
            codes = {item.code for item in validate_extension(root, final_ready=True)}
            self.assertIn("verification-stale", codes)

    def test_final_ready_rejects_mismatched_registration_and_browser_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = scaffold("verified", "Verified", "Verified extension.", Path(temporary))
            (root / "src" / "popup.html").write_text("<!doctype html><title>Verified</title><script src=\"popup.js\"></script>", encoding="utf-8")
            (root / "tests" / "e2e.cjs").write_text("exports.run = async ({ assert }) => { assert.ok(true); };\n", encoding="utf-8")
            project_path = root / ".addonry" / "project.json"
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project.update({"status": "implemented", "acceptance": {"popup": "opens"}})
            project_path.write_text(json.dumps(project), encoding="utf-8")
            evidence = {
                "status": "passed",
                "sourceSha256": source_digest(root),
                "scenario": str(root / "other-e2e.cjs"),
                "consoleErrors": ["boom"],
                "pageErrors": [],
                "workerErrors": [],
                "limitations": [],
                "cleanupWarnings": [],
                "chromeDevtoolsMcp": {"status": "passed"},
                "extensionRegistration": {
                    "id": "not-an-extension-id",
                    "name": "Wrong",
                    "version": "9.9.9",
                    "path": str(root.parent),
                    "enabled": True,
                },
            }
            (root / ".addonry" / "verification.json").write_text(json.dumps(evidence), encoding="utf-8")
            codes = {item.code for item in validate_extension(root, final_ready=True)}
            self.assertIn("verification-scenario-mismatch", codes)
            self.assertIn("extension-registration-mismatch", codes)
            self.assertIn("browser-errors-present", codes)


@unittest.skipUnless(sys.platform == "win32", "PowerShell helper is Windows-specific")
class ChromeRestartHelperTests(unittest.TestCase):
    def test_plan_only_fails_closed_for_unsupported_branded_chrome(self) -> None:
        chrome_candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        chrome = next((path for path in chrome_candidates if path.is_file()), None)
        if chrome is None:
            self.skipTest("Google Chrome is not installed")

        with tempfile.TemporaryDirectory() as temporary:
            extension = Path(temporary) / "extension"
            extension.mkdir()
            (extension / "manifest.json").write_text(
                json.dumps({"manifest_version": 3, "name": "Plan Test", "version": "1.0.0"}),
                encoding="utf-8",
            )
            helper = TOOLS / "restart-chrome-with-extension.ps1"
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(helper),
                    "-ExtensionPath",
                    str(extension),
                    "-ChromePath",
                    str(chrome),
                    "-PlanOnly",
                    "-AllowVolatilePath",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            major = int(report["browserVersion"].split(".", 1)[0])
            if report["browserProduct"] == "Google Chrome" and major >= 137:
                self.assertEqual(report["state"], "blocked-branded-chrome-load-extension-unsupported")
                self.assertEqual(report["persistence"], "not-installed")
                self.assertFalse(report["sessionRestoreRequested"])
                self.assertEqual(report["launchArguments"], [])
            else:
                self.assertEqual(report["state"], "plan-only")
                self.assertEqual(report["persistence"], "unknown-until-browser-verified")
                self.assertTrue(report["sessionRestoreRequested"])
                self.assertIn("--restore-last-session", report["launchArguments"])


if __name__ == "__main__":
    unittest.main()
