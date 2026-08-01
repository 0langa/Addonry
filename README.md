# Addonry

Addonry is a manual-only plugin that turns a plain-language request into a tested personal Chrome extension plus truthful installation state. It targets Codex, Claude Code, and Kimi Code from one Forge-managed source.

Invoke Addonry through provider's manual skill syntax, describe browser utility, answer its up-front product questions, then leave implementation decisions to agent. Addonry owns feasibility research, Manifest V3 design, code, permissions, tests, real-Chrome verification, and best-effort installation.

| Provider | Manual invocation |
| --- | --- |
| Codex | `$addonry:create-chrome-extension Build ...` |
| Claude Code | `/addonry:create-chrome-extension Build ...` |
| Kimi Code | `/addonry:create-chrome-extension Build ...` |
| Kimi Code 0.29.x Windows fallback | `/skill:create-chrome-extension Build ...` |

Hard manual-only flags intentionally prevent plain prose such as `Use Addonry ...` from activating hidden skill. This keeps unrelated Chrome work isolated. After invocation, normal prose requirements follow command.

## Scope

Good fits include page-specific helpers, link extraction, one-click tab actions, formatters, lightweight download helpers, and narrowly scoped cookie import/export utilities. Addonry downscopes or refuses password managers, stealth or policy bypasses, credential harvesting, and other work whose security or complexity exceeds a personal convenience extension.

Generated extensions live in durable personal storage outside provider caches. On Windows, Addonry prefers `%USERPROFILE%\source\repos\chrome-extensions\<slug>` when `source\repos` exists, otherwise `%USERPROFILE%\chrome-extensions\<slug>`. `ADDONRY_OUTPUT_ROOT` overrides default. Generated projects remain local and are never committed or published unless explicitly requested.

## Manual-only contract

- Codex: `agents/openai.yaml` disables implicit skill invocation.
- Claude Code: only namespaced slash command is exposed; no model-invocable skill is registered.
- Kimi Code: namespaced slash command remains canonical. Manual-only `/skill:create-chrome-extension` fallback covers Kimi 0.29.x Windows builds that install plugins but omit plugin commands from command registry.
- No plugin agent is registered for automatic delegation.
- Bundled MCP tools remain host-visible while the plugin is enabled because current plugin hosts start declared MCP servers eagerly. Addonry instructions permit their use only after explicit invocation.

## Components

- `skills/create-chrome-extension/`: intake, architecture, security, testing, and installation workflow.
- `addonry-chrome-devtools`: pinned Chrome DevTools MCP runtime with usage statistics disabled and an isolated Chrome profile by default.
- Deterministic helpers: durable extension scaffold, icon generation, security/static validation, real-Chrome Puppeteer toolbar-action verification, source-bound final evidence gate, and fail-closed browser load preflight.
- Provider manifests generated from `forge.yaml` by Plugin Forge.

## Development checks

```powershell
python -m unittest discover -s tests -v
python scripts/validate_repository.py
node --check skills/create-chrome-extension/scripts/verify_extension.cjs
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-chrome-devtools-mcp.ps1 -SelfTest
node scripts/smoke_chrome_devtools_mcp.cjs
powershell -NoProfile -ExecutionPolicy Bypass -File skills/create-chrome-extension/scripts/verify-extension.ps1 `
  -ExtensionPath tests/fixtures/active-tab-smoke `
  -ScenarioPath tests/fixtures/active-tab-smoke/tests/e2e.cjs
python skills/create-chrome-extension/scripts/validate_extension.py tests/fixtures/active-tab-smoke --final-ready
```

Official Google Chrome 137+ ignores `--load-extension`. Addonry therefore uses Chrome's supported **Developer Mode** > **Load unpacked** flow for persistent normal-profile installation. Protected browser UI may require one user directory selection. Guarded helper refuses unsupported branded Chrome before changing any process; supported isolated Chromium/Chrome for Testing flows still require browser-level verification.

Large reusable runtime data and npm caches use mounted `agent-devstorage`: `fast-primary` first, then `bulk-secondary`, under `shared-cache\Addonry\cache`. Source stays in this repository. Without a participating drive, runtime reports fallback and uses `%LOCALAPPDATA%\Addonry\runtime`. FAT32 bulk-secondary storage is supported but first dependency install/module load can be slow; fast-primary remains preferred.

## Provider development load

```powershell
claude --plugin-dir .
forge install --provider all --mode link
kimi
```

After marketplace release, install `addonry@0langas-plugins`, start new provider session, and use matching manual invocation above. Exact marketplace commands are verified during release and recorded here before handoff.
