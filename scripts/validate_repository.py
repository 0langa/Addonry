#!/usr/bin/env python3
"""Run deterministic structural checks for Addonry plugin repository."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_OR_GENERATED_PATH_PARTS = frozenset(
    {".git", ".recall", ".venv", "__pycache__", "build", "dist", "generated", "node_modules"}
)
TEXT_SOURCE_SUFFIXES = frozenset({".md", ".json", ".yaml", ".yml", ".py", ".ps1", ".js", ".cjs"})
REQUIRED_FILES = (
    "forge.yaml",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "kimi.plugin.json",
    ".mcp.json",
    ".codex-mcp.json",
    "skills/create-chrome-extension/SKILL.md",
    "skills/create-chrome-extension/agents/openai.yaml",
    "skills/create-chrome-extension/scripts/restart-chrome-with-extension.ps1",
    "commands/create-chrome-extension.md",
    "scripts/start-chrome-devtools-mcp.ps1",
    "scripts/smoke_chrome_devtools_mcp.cjs",
    "scripts/sync_manual_command.py",
    "tests/fixtures/active-tab-smoke/manifest.json",
    "tests/fixtures/active-tab-smoke/tests/e2e.cjs",
)


def is_source_text_file(path: Path) -> bool:
    """Keep local runtime state and generated dependencies out of source checks."""
    return path.is_file() and not (LOCAL_OR_GENERATED_PATH_PARTS & set(path.parts)) and path.suffix.lower() in TEXT_SOURCE_SUFFIXES


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    text_files = [
        path
        for path in ROOT.rglob("*")
        if is_source_text_file(path)
    ]
    placeholder_token = "TO" + "DO"
    for path in text_files:
        text = path.read_text(encoding="utf-8")
        if f"[{placeholder_token}:" in text or re.search(rf"\b{placeholder_token}\b", text):
            errors.append(f"placeholder remains: {path.relative_to(ROOT)}")

    manifests: list[dict[str, object]] = []
    for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "kimi.plugin.json"):
        path = ROOT / relative
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("root is not object")
                manifests.append(payload)
            except (json.JSONDecodeError, ValueError) as error:
                errors.append(f"invalid JSON {relative}: {error}")
    identities = {(item.get("name"), item.get("version")) for item in manifests}
    forge_text = (ROOT / "forge.yaml").read_text(encoding="utf-8")
    version_match = re.search(r"(?m)^version:\s*([^\s]+)$", forge_text)
    expected_version = version_match.group(1) if version_match else None
    if identities and identities != {("addonry", expected_version)}:
        errors.append(f"provider identity drift: {sorted(map(str, identities))}")

    expected_provider_surfaces = {
        ".claude-plugin/plugin.json": {"commands": "./commands", "mcpServers": "./.mcp.json"},
        ".codex-plugin/plugin.json": {"skills": "./skills/", "mcpServers": "./.codex-mcp.json"},
        "kimi.plugin.json": {"skills": "./skills/", "commands": "./commands/"},
    }
    for relative, expected in expected_provider_surfaces.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            if payload.get(key) != value:
                errors.append(f"provider surface drift: {relative} {key} must be {value!r}")

    skill_path = ROOT / "skills/create-chrome-extension/SKILL.md"
    if skill_path.is_file():
        skill = skill_path.read_text(encoding="utf-8")
        frontmatter = re.match(r"\A---\s*\n(?P<content>.*?)\n---(?:\s*\n|\Z)", skill, re.DOTALL)
        if frontmatter is None or not re.search(
            r"(?m)^disableModelInvocation:\s*true\s*$", frontmatter.group("content")
        ):
            errors.append("manual-only Kimi policy missing")
        for reference in re.findall(r"\]\((references/[^)]+)\)", skill):
            if not (skill_path.parent / reference).is_file():
                errors.append(f"missing skill reference: {reference}")

    command_sync = subprocess.run(
        ["python", "scripts/sync_manual_command.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if command_sync.returncode:
        errors.append(command_sync.stdout.strip() or command_sync.stderr.strip() or "manual surface drift")

    openai_path = ROOT / "skills/create-chrome-extension/agents/openai.yaml"
    if openai_path.is_file() and "allow_implicit_invocation: false" not in openai_path.read_text(encoding="utf-8"):
        errors.append("manual-only Codex policy missing")

    for relative in (".mcp.json", ".codex-mcp.json", "kimi.plugin.json"):
        mcp_path = ROOT / relative
        if mcp_path.is_file():
            mcp_text = mcp_path.read_text(encoding="utf-8")
            if "start-chrome-devtools-mcp.ps1" not in mcp_text:
                errors.append(f"{relative} does not use Addonry runtime wrapper")
            if "Test-Path" not in mcp_text or "Addonry plugin root not found" not in mcp_text:
                errors.append(f"{relative} does not verify selected plugin root")
    wrapper = ROOT / "scripts/start-chrome-devtools-mcp.ps1"
    if wrapper.is_file():
        wrapper_text = wrapper.read_text(encoding="utf-8")
        if "1.6.0" not in wrapper_text or "@latest" in wrapper_text:
            errors.append("Chrome DevTools MCP runtime is not immutably pinned")
        if "CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS" not in wrapper_text:
            errors.append("Chrome DevTools MCP usage-statistics opt-out missing")
        if "routing.log" not in wrapper_text or "--no-audit" not in wrapper_text:
            errors.append("Chrome DevTools MCP runtime install lacks reproducible storage hygiene")

    verifier = ROOT / "skills/create-chrome-extension/scripts/verify_extension.cjs"
    if verifier.is_file():
        verifier_text = verifier.read_text(encoding="utf-8")
        for required_token in ("browser.extensions()", "triggerAction", "extensionRegistration", "cleanupWarnings"):
            if required_token not in verifier_text:
                errors.append(f"extension verifier missing final-evidence behavior: {required_token}")

    validator = ROOT / "skills/create-chrome-extension/scripts/validate_extension.py"
    if validator.is_file() and "--final-ready" not in validator.read_text(encoding="utf-8"):
        errors.append("extension validator lacks final-ready evidence gate")

    restart_helper = ROOT / "skills/create-chrome-extension/scripts/restart-chrome-with-extension.ps1"
    if restart_helper.is_file():
        helper_text = restart_helper.read_text(encoding="utf-8")
        if "Stop-Process" in helper_text or "taskkill" in helper_text.lower():
            errors.append("Chrome restart helper contains force-termination primitive")
        for required_token in (
            "CloseMainWindow",
            "--load-extension=",
            "--restore-last-session",
            "AuthorizedRestart",
            "blocked-branded-chrome-load-extension-unsupported",
            "Google Chrome 137+ ignores --load-extension",
        ):
            if required_token not in helper_text:
                errors.append(f"Chrome restart helper missing safety behavior: {required_token}")

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    if not re.search(r"(?m)^generated/$", gitignore):
        errors.append("generated output is not ignored")
    tracked = subprocess.run(
        ["git", "ls-files", "generated"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tracked:
        errors.append(f"generated extension files are tracked: {tracked}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"Repository validation failed with {len(errors)} error(s).")
        return 1
    print(f"Repository validation passed: {len(REQUIRED_FILES)} required files, {len(manifests)} provider manifests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
