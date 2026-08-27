from __future__ import annotations

import json
import os
import subprocess
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "skills" / "create-chrome-extension" / "scripts"
sys.path.insert(0, str(TOOLS))

from generate_icons import PNG_SIGNATURE, generate_icons, parse_hex_color  # noqa: E402
from package_extension import package_extension  # noqa: E402
from quality_loop import assess_quality, cycle_quality, record_blocker  # noqa: E402
from scaffold_extension import default_output_root, resolve_output_root, scaffold  # noqa: E402
from validate_extension import contract_digest, source_digest, validate_extension  # noqa: E402


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
            self.assertEqual(default_output_root(home), home / "source" / "repos" / "browser-extensions")

    def test_default_output_falls_back_to_personal_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            self.assertEqual(default_output_root(home), home / "browser-extensions")

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
            self.assertEqual(manifest["background"]["service_worker"], "src/service-worker.js")
            self.assertEqual(manifest["background"]["scripts"], ["src/service-worker.js"])
            self.assertRegex(manifest["browser_specific_settings"]["gecko"]["id"], r"^\{[0-9a-f-]{36}\}$")
            self.assertEqual(
                manifest["browser_specific_settings"]["gecko"]["data_collection_permissions"]["required"],
                ["none"],
            )
            self.assertTrue((target / "tests" / "e2e.cjs").is_file())
            self.assertTrue((target / "tests" / "firefox_e2e.py").is_file())
            self.assertTrue((target / ".addonry" / "project.json").is_file())
            self.assertTrue((target / ".addonry" / "contract.json").is_file())
            self.assertTrue((target / ".addonry" / "quality-loop.json").is_file())
            readme = (target / "README.md").read_text(encoding="utf-8")
            self.assertIn("Targets: Chrome, Firefox", readme)
            self.assertIn("about:debugging", readme)
            project = json.loads((target / ".addonry" / "project.json").read_text(encoding="utf-8"))
            contract = json.loads((target / ".addonry" / "contract.json").read_text(encoding="utf-8"))
            self.assertEqual(project["schemaVersion"], 3)
            self.assertEqual(project["browsers"], ["chrome", "firefox"])
            self.assertEqual(project["qualityLoop"]["status"], "not-run")
            self.assertEqual(contract["status"], "draft")
            self.assertEqual(contract["browserTargets"], ["chrome", "firefox"])

    def test_scaffold_can_target_each_browser_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            chrome = scaffold("chrome-only", "Chrome Only", "Chrome target.", output, browser="chrome")
            firefox = scaffold("firefox-only", "Firefox Only", "Firefox target.", output, browser="firefox")
            chrome_manifest = json.loads((chrome / "manifest.json").read_text(encoding="utf-8"))
            firefox_manifest = json.loads((firefox / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("service_worker", chrome_manifest["background"])
            self.assertNotIn("scripts", chrome_manifest["background"])
            self.assertNotIn("browser_specific_settings", chrome_manifest)
            self.assertIn("scripts", firefox_manifest["background"])
            self.assertNotIn("service_worker", firefox_manifest["background"])
            self.assertIn("browser_specific_settings", firefox_manifest)
            self.assertFalse((chrome / "tests" / "firefox_e2e.py").exists())
            self.assertTrue((firefox / "tests" / "firefox_e2e.py").is_file())

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
            root = scaffold("verified", "Verified", "Verified extension.", Path(temporary), browser="chrome")
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
            root = scaffold("verified", "Verified", "Verified extension.", Path(temporary), browser="chrome")
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

    def test_firefox_target_requires_portable_manifest_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_version": 3,
                        "name": "Firefox Gap",
                        "version": "1.0.0",
                        "background": {"service_worker": "worker.js"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "worker.js").write_text("", encoding="utf-8")
            codes = {item.code for item in validate_extension(root, target="firefox")}
            self.assertIn("firefox-background-missing", codes)
            self.assertIn("firefox-settings-missing", codes)


class QualityLoopTests(unittest.TestCase):
    def _write_browser_evidence(self, target: Path, *, chrome_criteria: list[str] | None = None) -> None:
        digest = source_digest(target)
        contract_sha = contract_digest(target)
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        chrome_evidence = {
            "status": "passed",
            "sourceSha256": digest,
            "contractSha256": contract_sha,
            "scenario": str((target / "tests" / "e2e.cjs").resolve()),
            "scenarioResult": {"criteriaPassed": chrome_criteria if chrome_criteria is not None else ["REQ-001"]},
            "consoleErrors": [],
            "pageErrors": [],
            "workerErrors": [],
            "limitations": [],
            "cleanupWarnings": [],
            "chromeDevtoolsMcp": {"status": "passed"},
            "extensionRegistration": {
                "id": "abcdefghijklmnopabcdefghijklmnop",
                "name": manifest["name"],
                "version": manifest["version"],
                "path": str(target.resolve()),
                "enabled": True,
            },
        }
        firefox_evidence = {
            "status": "passed",
            "sourceSha256": digest,
            "contractSha256": contract_sha,
            "scenario": str((target / "tests" / "firefox_e2e.py").resolve()),
            "scenarioResult": {"criteriaPassed": ["REQ-001"]},
            "lint": {"status": "passed"},
            "consoleErrors": [],
            "pageErrors": [],
            "backgroundErrors": [],
            "limitations": [],
            "cleanupWarnings": [],
            "extensionRegistration": {
                "id": manifest["browser_specific_settings"]["gecko"]["id"],
                "name": manifest["name"],
                "version": manifest["version"],
                "path": str(target.resolve()),
                "enabled": True,
                "temporary": True,
            },
        }
        (target / ".addonry" / "verification.json").write_text(json.dumps(chrome_evidence), encoding="utf-8")
        (target / ".addonry" / "firefox-verification.json").write_text(json.dumps(firefox_evidence), encoding="utf-8")

    def _ready_project(self, output: Path, *, packaging: bool = True) -> Path:
        target = scaffold("quality-tool", "Quality Tool", "Proves one shared behavior.", output)
        (target / "src" / "popup.html").write_text(
            '<!doctype html><title>Quality Tool</title><p data-testid="ready">ready</p><script src="popup.js"></script>',
            encoding="utf-8",
        )
        (target / "src" / "popup.js").write_text(
            "document.querySelector('[data-testid=ready]').dataset.initialized = 'true';\n",
            encoding="utf-8",
        )
        (target / "tests" / "e2e.cjs").write_text(
            "exports.run = async ({ openPopup, assert }) => {\n"
            "  const popup = await openPopup();\n"
            "  await popup.waitForSelector('[data-testid=ready][data-initialized=true]');\n"
            "  assert.ok(true);\n"
            "  return { criteriaPassed: ['REQ-001'] };\n"
            "};\n",
            encoding="utf-8",
        )
        (target / "tests" / "firefox_e2e.py").write_text(
            "def run(context):\n"
            "    context['driver'].get(context['extension_origin'] + '/src/popup.html')\n"
            "    assert context['driver'].find_element('css selector', '[data-testid=ready]').text == 'ready'\n"
            "    return {'criteriaPassed': ['REQ-001']}\n",
            encoding="utf-8",
        )
        project_path = target / ".addonry" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["status"] = "implemented"
        project["acceptance"] = {}
        project_path.write_text(json.dumps(project), encoding="utf-8")
        contract = {
            "schemaVersion": 1,
            "status": "confirmed",
            "confirmedAt": "2026-08-27T00:00:00+00:00",
            "requestSummary": "Shared popup initializes in Chrome and Firefox.",
            "browserTargets": ["chrome", "firefox"],
            "packagingRequested": packaging,
            "qualityPolicy": {"requireZeroWarnings": True, "stallThreshold": 3},
            "acceptedWarnings": [],
            "criteria": [
                {
                    "id": "REQ-001",
                    "kind": "behavior",
                    "requirement": "Popup initializes in both requested browsers.",
                    "acceptance": "Initialized marker is observable in Chrome and Firefox.",
                    "appliesTo": ["chrome", "firefox"],
                    "proof": {
                        "implementation": ["src/popup.js"],
                        "tests": ["tests/e2e.cjs", "tests/firefox_e2e.py"],
                        "evidence": [
                            "static-validation",
                            "chrome-e2e",
                            "firefox-e2e",
                            *( ["package"] if packaging else [] ),
                        ],
                    },
                }
            ],
        }
        (target / ".addonry" / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
        self._write_browser_evidence(target)
        if packaging:
            package_extension(target)
        return target

    def test_confirmed_contract_can_replace_legacy_acceptance_map(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary), packaging=False)
            codes = {item.code for item in validate_extension(target, release_ready=True)}
            self.assertNotIn("acceptance-missing", codes)

    def test_complete_current_proof_reaches_100_percent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary))
            report = assess_quality(target)
            self.assertEqual(report["status"], "passed", report["findings"])
            self.assertEqual(report["coverage"], {"passed": 1, "total": 1, "percent": 100.0})
            self.assertTrue((target / ".addonry" / "quality-report.json").is_file())
            self.assertEqual(json.loads((target / ".addonry" / "quality-loop.json").read_text(encoding="utf-8"))["status"], "passed")

    def test_missing_browser_criterion_proof_fails_despite_generic_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary))
            self._write_browser_evidence(target, chrome_criteria=[])
            report = assess_quality(target)
            codes = {item["code"] for item in report["findings"]}
            self.assertEqual(report["status"], "repair-required")
            self.assertIn("criterion-proof-incomplete", codes)

    def test_source_change_invalidates_browser_and_package_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary))
            (target / "src" / "popup.js").write_text("document.body.dataset.changed = 'true';\n", encoding="utf-8")
            codes = {item["code"] for item in assess_quality(target)["findings"]}
            self.assertIn("chrome-evidence-stale", codes)
            self.assertIn("firefox-evidence-stale", codes)
            self.assertIn("package-report-stale", codes)

    def test_contract_change_invalidates_browser_and_package_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary))
            contract_path = target / ".addonry" / "contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["criteria"][0]["acceptance"] = "Changed acceptance requires new proof."
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            codes = {item["code"] for item in assess_quality(target)["findings"]}
            self.assertIn("chrome-evidence-contract-stale", codes)
            self.assertIn("firefox-evidence-contract-stale", codes)
            self.assertIn("package-report-contract-stale", codes)

    def test_python_bytecode_cache_does_not_invalidate_source_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary))
            before = source_digest(target)
            cache = target / "tests" / "__pycache__"
            cache.mkdir()
            (cache / "firefox_e2e.cpython-314.pyc").write_bytes(b"regenerable-bytecode")
            self.assertEqual(source_digest(target), before)
            self.assertEqual(assess_quality(target)["status"], "passed")

    def test_source_mutation_during_assessment_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary))
            mutated = False

            def runner(command, cwd, timeout):
                nonlocal mutated
                if not mutated:
                    with (target / "src" / "popup.js").open("a", encoding="utf-8") as stream:
                        stream.write("\n// changed during test gate\n")
                    mutated = True
                return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout)

            report = assess_quality(target, runner=runner)
            codes = {item["code"] for item in report["findings"]}
            self.assertIn("source-changed-during-assessment", codes)
            self.assertNotEqual(report["status"], "passed")

    def test_contract_path_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary))
            contract_path = target / ".addonry" / "contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["criteria"][0]["proof"]["implementation"] = ["../outside.js"]
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            codes = {item["code"] for item in assess_quality(target)["findings"]}
            self.assertIn("criterion-path-escape", codes)

    def test_unchanged_failure_requires_strategy_change_at_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = scaffold("stalled", "Stalled", "Draft contract remains incomplete.", Path(temporary))
            self.assertEqual(assess_quality(target)["status"], "repair-required")
            self.assertEqual(assess_quality(target)["status"], "repair-required")
            third = assess_quality(target)
            self.assertEqual(third["status"], "strategy-change-required")
            self.assertEqual(third["repeatCount"], 3)

    def test_external_blocker_is_recorded_without_success_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary))
            report = record_blocker(target, "firefox-auth-required", "Representative site requires unavailable login.")
            self.assertEqual(report["status"], "blocked")
            self.assertIn("Resolve documented external blocker", report["nextAction"])

    def test_cycle_reuses_current_browser_proof_without_browser_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._ready_project(Path(temporary))
            commands: list[list[str]] = []

            def runner(command, cwd, timeout):
                commands.append(list(command))
                self.assertNotEqual(Path(command[0]).name.lower(), "powershell.exe")
                return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout)

            report = cycle_quality(target, runner=runner)
            self.assertEqual(report["status"], "passed", report["findings"])
            self.assertTrue(commands)


class PackagingTests(unittest.TestCase):
    def _implemented_project(self, root: Path) -> Path:
        target = scaffold("portable-tool", "Portable Tool", "Works in both browsers.", root)
        (target / "src" / "popup.html").write_text(
            '<!doctype html><title>Portable Tool</title><script src="popup.js"></script>',
            encoding="utf-8",
        )
        (target / "tests" / "e2e.cjs").write_text(
            "exports.run = async ({ assert }) => { assert.ok(true); };\n",
            encoding="utf-8",
        )
        (target / "tests" / "firefox_e2e.py").write_text(
            "def run(context):\n    assert context['addon_id']\n    return {}\n",
            encoding="utf-8",
        )
        project_path = target / ".addonry" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project.update({"status": "implemented", "acceptance": {"popup": "opens"}})
        project_path.write_text(json.dumps(project), encoding="utf-8")
        return target

    def test_packages_target_specific_manifests_without_development_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._implemented_project(Path(temporary))
            report = package_extension(target)
            self.assertEqual(report["targets"], ["chrome", "firefox"])
            self.assertFalse(report["signed"])
            for row in report["packages"]:
                with zipfile.ZipFile(row["path"], "r") as archive:
                    names = archive.namelist()
                    self.assertEqual(names[0], "manifest.json")
                    self.assertFalse(any(name.startswith("tests/") for name in names))
                    self.assertFalse(any(name.startswith(".addonry/") for name in names))
                    manifest = json.loads(archive.read("manifest.json"))
                    if row["browser"] == "chrome":
                        self.assertIn("service_worker", manifest["background"])
                        self.assertNotIn("scripts", manifest["background"])
                        self.assertNotIn("browser_specific_settings", manifest)
                    else:
                        self.assertIn("scripts", manifest["background"])
                        self.assertNotIn("service_worker", manifest["background"])
                        self.assertIn("browser_specific_settings", manifest)

    def test_repeated_package_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._implemented_project(Path(temporary))
            first = package_extension(target)
            first_hashes = {row["browser"]: row["sha256"] for row in first["packages"]}
            second = package_extension(target, overwrite=True)
            second_hashes = {row["browser"]: row["sha256"] for row in second["packages"]}
            self.assertEqual(first_hashes, second_hashes)

    def test_refuses_sensitive_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._implemented_project(Path(temporary))
            (target / "client-secret.pem").write_text("not-a-real-secret", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sensitive filename"):
                package_extension(target)


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
