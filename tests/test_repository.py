from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
        self.assertIn("disable-model-invocation: true", skill)
        self.assertIn("disableModelInvocation: true", skill)

    def test_provider_specific_mcp_roots(self) -> None:
        codex_manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(codex_manifest["mcpServers"], "./.codex-mcp.json")
        codex_mcp = json.loads((ROOT / ".codex-mcp.json").read_text(encoding="utf-8"))
        claude_mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        kimi = json.loads((ROOT / "kimi.plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(codex_mcp["mcpServers"]["addonry-chrome-devtools"]["cwd"], "./")
        self.assertEqual(claude_mcp["mcpServers"]["addonry-chrome-devtools"]["cwd"], "${CLAUDE_PLUGIN_ROOT}")
        self.assertEqual(kimi["mcpServers"]["addonry-chrome-devtools"]["cwd"], "./")


if __name__ == "__main__":
    unittest.main()
