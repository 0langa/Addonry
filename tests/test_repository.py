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
        self.assertIn(
            "path: skills/create-chrome-extension/SKILL.md\n    providers:\n    - codex",
            forge,
        )
        self.assertIn(
            "path: commands/create-chrome-extension.md\n    providers:\n    - claude\n    - kimi",
            forge,
        )

    def test_provider_safe_mcp_root_resolution(self) -> None:
        codex_manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(codex_manifest["mcpServers"], "./.codex-mcp.json")
        codex_mcp = json.loads((ROOT / ".codex-mcp.json").read_text(encoding="utf-8"))
        claude_mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        kimi = json.loads((ROOT / "kimi.plugin.json").read_text(encoding="utf-8"))
        entries = [
            codex_mcp["mcpServers"]["addonry-chrome-devtools"],
            claude_mcp["mcpServers"]["addonry-chrome-devtools"],
            kimi["mcpServers"]["addonry-chrome-devtools"],
        ]
        for entry in entries:
            self.assertEqual(entry["cwd"], "./")
            resolver = entry["args"][-1]
            self.assertIn("CLAUDE_PLUGIN_ROOT", resolver)
            self.assertIn("KIMI_PLUGIN_ROOT", resolver)
            self.assertIn("PLUGIN_ROOT", resolver)
            self.assertIn("start-chrome-devtools-mcp.ps1", resolver)

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


if __name__ == "__main__":
    unittest.main()
