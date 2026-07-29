from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "skills" / "create-chrome-extension" / "scripts"
sys.path.insert(0, str(TOOLS))

from generate_icons import PNG_SIGNATURE, generate_icons, parse_hex_color  # noqa: E402
from scaffold_extension import DEFAULT_OUTPUT_ROOT, scaffold  # noqa: E402
from validate_extension import validate_extension  # noqa: E402


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
    def test_default_output_stays_under_plugin_root(self) -> None:
        self.assertEqual(DEFAULT_OUTPUT_ROOT, ROOT / "generated")

    def test_scaffold_passes_static_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = scaffold("tab-helper", "Tab Helper", "Keeps current tab visible.", Path(temporary))
            findings = validate_extension(target)
            self.assertEqual([item for item in findings if item.level == "error"], [])
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_version"], 3)
            self.assertTrue((target / "tests" / "e2e.cjs").is_file())
            self.assertTrue((target / ".addonry" / "project.json").is_file())

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


if __name__ == "__main__":
    unittest.main()
