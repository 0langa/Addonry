# Addonry

Addonry is a manual-only plugin that turns a plain-language request into a finished personal Chrome extension. It targets Codex, Claude Code, and Kimi Code from one Forge-managed source.

Invoke Addonry through provider's manual skill syntax, describe browser utility, answer its up-front product questions, then leave implementation decisions to agent. Addonry owns feasibility research, Manifest V3 design, code, permissions, tests, real-Chrome verification, and best-effort installation.

| Provider | Manual invocation |
| --- | --- |
| Codex | `$addonry:create-chrome-extension Build ...` |
| Claude Code | `/addonry:create-chrome-extension Build ...` |
| Kimi Code | `/addonry:create-chrome-extension Build ...` |

Hard manual-only flags intentionally prevent plain prose such as `Use Addonry ...` from activating hidden skill. This keeps unrelated Chrome work isolated. After invocation, normal prose requirements follow command.

## Scope

Good fits include page-specific helpers, link extraction, one-click tab actions, formatters, lightweight download helpers, and narrowly scoped cookie import/export utilities. Addonry downscopes or refuses password managers, stealth or policy bypasses, credential harvesting, and other work whose security or complexity exceeds a personal convenience extension.

Generated extensions live under `generated/<slug>/`. That directory is ignored by Git: generated projects remain local and are never committed or published unless explicitly requested.

## Manual-only contract

- Codex: `agents/openai.yaml` disables implicit skill invocation.
- Claude Code and Kimi Code: only namespaced slash command is exposed; no model-invocable skill is registered.
- No plugin agent is registered for automatic delegation.
- Bundled MCP tools remain host-visible while the plugin is enabled because current plugin hosts start declared MCP servers eagerly. Addonry instructions permit their use only after explicit invocation.

## Components

- `skills/create-chrome-extension/`: intake, architecture, security, testing, and installation workflow.
- `addonry-chrome-devtools`: pinned Chrome DevTools MCP runtime with usage statistics disabled and an isolated Chrome profile by default.
- Deterministic helpers: extension scaffold, icon generation, static validation, and real-Chrome Puppeteer verification.
- Provider manifests generated from `forge.yaml` by Plugin Forge.

## Development checks

```powershell
python -m unittest discover -s tests -v
python scripts/validate_repository.py
node --check skills/create-chrome-extension/scripts/verify_extension.cjs
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-chrome-devtools-mcp.ps1 -SelfTest
node scripts/smoke_chrome_devtools_mcp.cjs
```

Large reusable runtime data and npm caches use mounted `agent-devstorage`: `fast-primary` first, then `bulk-secondary`, under `shared-cache\Addonry\cache`. Source stays in this repository. Without a participating drive, runtime falls back to `%LOCALAPPDATA%\Addonry\runtime`.

## Provider development load

```powershell
claude --plugin-dir .
forge install --provider all --mode link
kimi
```

After marketplace release, install `addonry@0langas-plugins`, start new provider session, and use matching manual invocation above. Exact marketplace commands are verified during release and recorded here before handoff.
