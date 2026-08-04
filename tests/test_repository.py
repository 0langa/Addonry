from __future__ import annotations

import json
import importlib.util
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATOR_SPEC = importlib.util.spec_from_file_location("addonry_repository_validator", ROOT / "scripts/validate_repository.py")
assert VALIDATOR_SPEC is not None and VALIDATOR_SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)


class RepositoryTests(unittest.TestCase):
    def test_repository_validator(self) -> None:
        result = subprocess.run(
            ["python", "scripts/validate_repository.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_automatic_agent_surface(self) -> None:
        forge = (ROOT / "forge.yaml").read_text(encoding="utf-8")
        self.assertIn("agents: []", forge)
        self.assertIn("allow_implicit_invocation: false", (ROOT / "skills/create-chrome-extension/agents/openai.yaml").read_text(encoding="utf-8"))
        skill = (ROOT / "skills/create-chrome-extension/SKILL.md").read_text(encoding="utf-8")
        frontmatter = re.match(r"\A---\s*\n(?P<content>.*?)\n---(?:\s*\n|\Z)", skill, re.DOTALL)
        self.assertIsNotNone(frontmatter)
        self.assertRegex(frontmatter.group("content"), r"(?m)^disableModelInvocation:\s*true\s*$")
        self.assertIn(
            "path: skills/create-chrome-extension/SKILL.md\n    providers:\n    - codex\n    - kimi",
            forge,
        )
        self.assertIn(
            "path: commands/create-chrome-extension.md\n    providers:\n    - claude\n    - kimi",
            forge,
        )

    def test_repository_validator_excludes_local_runtime_and_generated_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "docs" / "guide.md"
            runtime = root / ".recall" / "memory.json"
            dependency = root / "node_modules" / "package.json"
            generated = root / "generated" / "extension.json"
            for path in (source, runtime, dependency, generated):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("source", encoding="utf-8")

            self.assertTrue(VALIDATOR.is_source_text_file(source))
            self.assertFalse(VALIDATOR.is_source_text_file(runtime))
            self.assertFalse(VALIDATOR.is_source_text_file(dependency))
            self.assertFalse(VALIDATOR.is_source_text_file(generated))

    def test_provider_safe_mcp_root_resolution(self) -> None:
        codex_manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(codex_manifest["mcpServers"], "./.codex-mcp.json")
        codex_mcp = json.loads((ROOT / ".codex-mcp.json").read_text(encoding="utf-8"))
        claude_mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        kimi = json.loads((ROOT / "kimi.plugin.json").read_text(encoding="utf-8"))
        entries = [
            (codex_mcp["mcpServers"]["addonry-chrome-devtools"], "./"),
            (claude_mcp["mcpServers"]["addonry-chrome-devtools"], "${CLAUDE_PLUGIN_ROOT}"),
            (kimi["mcpServers"]["addonry-chrome-devtools"], "./"),
        ]
        for entry, expected_cwd in entries:
            self.assertEqual(entry["cwd"], expected_cwd)
            resolver = entry["args"][-1]
            self.assertIn("CLAUDE_PLUGIN_ROOT", resolver)
            self.assertIn("KIMI_PLUGIN_ROOT", resolver)
            self.assertIn("PLUGIN_ROOT", resolver)
            self.assertIn("start-chrome-devtools-mcp.ps1", resolver)
            self.assertIn("Test-Path", resolver)
            self.assertIn("Addonry plugin root not found", resolver)

    def test_runtime_uses_agent_devstorage_identity(self) -> None:
        for relative in (
            "scripts/start-chrome-devtools-mcp.ps1",
            "skills/create-chrome-extension/scripts/verify-extension.ps1",
        ):
            script = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("agent-devstorage", script)
            self.assertIn("DRIVE-IDENTITY.json", script)
            self.assertIn("shared-cache\\Addonry\\cache\\runtime", script)
            self.assertNotIn("AvailableFreeSpace", script)
            self.assertIn("routing.log", script)
            self.assertIn("external devstorage unavailable", script)

    def test_manual_trigger_eval_corpus_is_balanced_and_provider_native(self) -> None:
        cases = json.loads(
            (ROOT / "skills/create-chrome-extension/evals/trigger-evals.json").read_text(encoding="utf-8")
        )
        positive = [case for case in cases if case["should_trigger"] is True]
        negative = [case for case in cases if case["should_trigger"] is False]
        self.assertGreaterEqual(len(positive), 8)
        self.assertLessEqual(len(positive), 12)
        self.assertGreaterEqual(len(negative), 8)
        self.assertLessEqual(len(negative), 12)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        prefixes = ("$addonry:create-chrome-extension", "/addonry:create-chrome-extension", "/skill:create-chrome-extension")
        self.assertTrue(all(case["query"].startswith(prefixes) for case in positive))
        self.assertTrue(all(not case["query"].startswith(prefixes) for case in negative))
        self.assertTrue(any("C:\\work\\" in case["query"] for case in positive))


if __name__ == "__main__":
    unittest.main()
