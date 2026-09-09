from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = (
    ROOT / "scripts/start-chrome-devtools-mcp.ps1",
    ROOT / "skills/create-chrome-extension/scripts/verify-extension.ps1",
    ROOT / "skills/create-chrome-extension/scripts/verify-firefox-extension.ps1",
)
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell runtime paths")
class RuntimePathTests(unittest.TestCase):
    def test_each_helper_resolves_local_runtime_and_preserves_cache_settings(self) -> None:
        # Evaluate just the real resolver, without starting a browser or installing packages.
        command = r"""$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:ADDONRY_TEST_SCRIPT, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$resolver = $ast.Find({param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Get-AddonryRuntimeRoot'
}, $true)
if (-not $resolver) { throw 'Runtime resolver not found' }
. ([scriptblock]::Create($resolver.Extent.Text))
Get-AddonryRuntimeRoot
"""
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary) / "local-app-data"
            env = dict(os.environ, LOCALAPPDATA=str(local), PLUGIN_DATA=str(Path(temporary) / "provider-data"))
            env.pop("ADDONRY_RUNTIME_ROOT", None)
            for script in SCRIPTS:
                with self.subTest(script=script.name):
                    env["ADDONRY_TEST_SCRIPT"] = str(script)
                    result = subprocess.run(
                        [POWERSHELL, "-NoProfile", "-Command", command],
                        env=env, capture_output=True, text=True, check=True,
                    )
                    self.assertEqual(Path(result.stdout.strip()), local / "Addonry" / "runtime")
                    text = script.read_text(encoding="utf-8")
                    for variable in ("NPM_CONFIG_CACHE", "UV_CACHE_DIR", "SE_CACHE_PATH"):
                        self.assertNotIn(f"$env:{variable} =", text)
                    env["ADDONRY_RUNTIME_ROOT"] = str(Path(temporary) / "explicit-local-runtime")
                    result = subprocess.run(
                        [POWERSHELL, "-NoProfile", "-Command", command],
                        env=env, capture_output=True, text=True, check=True,
                    )
                    self.assertEqual(Path(result.stdout.strip()), Path(env.pop("ADDONRY_RUNTIME_ROOT")))

    @unittest.skipUnless(shutil.which("node"), "Node.js launcher fixture")
    def test_cached_mcp_self_test_uses_local_package_without_redirecting_npm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary) / "local-app-data"
            runtime = local / "Addonry" / "runtime"
            package = runtime / "chrome-devtools-mcp-1.6.0" / "node_modules" / "chrome-devtools-mcp"
            entry = package / "build" / "src" / "bin" / "chrome-devtools-mcp.js"
            entry.parent.mkdir(parents=True)
            (package / "package.json").write_text('{"version":"1.6.0"}', encoding="utf-8")
            entry.write_text(
                'console.log(JSON.stringify({args:process.argv.slice(2),cache:process.env.NPM_CONFIG_CACHE}));',
                encoding="utf-8",
            )
            cache = str(Path(temporary) / "existing-npm-cache")
            env = dict(os.environ, LOCALAPPDATA=str(local), NPM_CONFIG_CACHE=cache)
            env.pop("ADDONRY_RUNTIME_ROOT", None)
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS[0]), "-SelfTest"],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertEqual(json.loads(result.stdout), {"args": ["--version"], "cache": cache})
            self.assertFalse((runtime / "npm-cache").exists())


if __name__ == "__main__":
    unittest.main()
