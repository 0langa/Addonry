# Addonry

Addonry is a manual-only Codex, Claude Code, and Kimi Code plugin that turns an explicit request into a tested personal Manifest V3 extension for desktop Chrome, Firefox, or both. Current source also runs an acceptance-driven repair loop and creates deterministic unsigned ZIP packages when requested.

## Invoke

| Provider | Manual invocation |
| --- | --- |
| Codex | `$addonry:create-chrome-extension Build ...` |
| Claude Code | `/addonry:create-chrome-extension Build ...` |
| Kimi Code | `/addonry:create-chrome-extension Build ...` |
| Kimi Code 0.29.x Windows fallback | `/skill:create-chrome-extension Build ...` |

Command name remains `create-chrome-extension` for compatibility; workflow now asks for `chrome`, `firefox`, or `both`. Hard manual-only flags prevent unqualified prose from activating hidden workflow.

## Scope

Good fits: page helpers, link extraction, tab actions, formatters, focused downloads, and narrow cookie import/export. Addonry downscopes or refuses password managers, surveillance, credential theft, policy bypass, enterprise force-installation, broad traffic interception, and comparable high-assurance work.

Generated projects live outside provider caches. Windows default: `%USERPROFILE%\source\repos\browser-extensions\<slug>` when `source\repos` exists, otherwise `%USERPROFILE%\browser-extensions\<slug>`. `ADDONRY_OUTPUT_ROOT` overrides default. Generated projects stay local, untracked, unsigned, and unpublished unless user explicitly requests next action.

## Manual-only contract

- Codex: `agents/openai.yaml` disables implicit skill invocation.
- Claude Code: namespaced slash command only; no model-invocable skill.
- Kimi Code: `disableModelInvocation: true`; namespaced command plus documented 0.29.x fallback.
- No plugin agent exists for automatic delegation.
- Bundled Chrome DevTools MCP starts when plugin host enables it; workflow permits use only after explicit Addonry invocation.

## Cross-browser model

- Shared MV3 source and root development manifest.
- Chrome background service worker plus Firefox background script declaration when target is `both`.
- Stable Firefox Gecko ID and explicit AMO data-collection declaration.
- Target-aware static/final validation; Chrome evidence cannot satisfy Firefox gate.
- Real Chrome Puppeteer scenario plus Chrome DevTools MCP evidence.
- Real Firefox Selenium temporary-install scenario plus pinned `web-ext` lint.
- Browser-specific ZIP manifests generated without changing shared source.
- Confirmed request contract plus criterion-level current proof; confidence or generic browser pass cannot replace missing behavior evidence.

See [ROADMAP.md](ROADMAP.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), [QUALITY_LOOP_PLAN.md](QUALITY_LOOP_PLAN.md), [cross-browser architecture](skills/create-chrome-extension/references/cross-browser-architecture.md), [quality-loop contract](skills/create-chrome-extension/references/quality-loop.md), and [packaging contract](skills/create-chrome-extension/references/packaging.md).

## Scaffold

```powershell
python skills/create-chrome-extension/scripts/scaffold_extension.py `
  --slug tab-helper `
  --name "Tab Helper" `
  --description "Focused tab utility." `
  --browser both
```

## Verify

```powershell
python -m unittest discover -s tests -v
python scripts/validate_repository.py
python skills/create-chrome-extension/scripts/validate_extension.py <extension-path> --release-ready

powershell -NoProfile -ExecutionPolicy Bypass `
  -File skills/create-chrome-extension/scripts/verify-extension.ps1 `
  -ExtensionPath <extension-path> `
  -ScenarioPath <extension-path>\tests\e2e.cjs

powershell -NoProfile -ExecutionPolicy Bypass `
  -File skills/create-chrome-extension/scripts/verify-firefox-extension.ps1 `
  -ExtensionPath <extension-path> `
  -ScenarioPath <extension-path>\tests\firefox_e2e.py

python skills/create-chrome-extension/scripts/validate_extension.py <extension-path> --final-ready
```

Chrome final gate also needs representative Chrome DevTools MCP inspection. Firefox helper uses isolated profile and temporary unsigned install; it does not install into daily Firefox.

## Acceptance-driven quality loop

Scaffold creates draft `.addonry\contract.json`. After grouped intake, Addonry records confirmed atomic criteria, implementation/test mappings, requested browser evidence, warning policy, and packaging choice. Browser scenarios return each criterion ID through `criteriaPassed` only after mapped assertions pass.

```powershell
python skills/create-chrome-extension/scripts/quality_loop.py assess <extension-path>
python skills/create-chrome-extension/scripts/quality_loop.py cycle <extension-path>
```

`assess` runs contract/path accounting, release-ready static validation, syntax, discovered unit tests, current evidence checks, package revalidation, and traceability reporting. `cycle` additionally runs stale/missing requested browser gates and refreshes requested packages. Agent repairs first finding and repeats until `.addonry\quality-report.json` says `passed`, coverage is `100.0`, and findings are empty.

Same unchanged failure at configured threshold becomes `strategy-change-required`. Proven external blocker can be recorded without success claim:

```powershell
python skills/create-chrome-extension/scripts/quality_loop.py block <extension-path> `
  --code <lower-case-code> `
  --reason "<specific reproduced blocker>"
```

## Package

```powershell
python skills/create-chrome-extension/scripts/package_extension.py `
  <extension-path> `
  --target both
```

Output: `<extension-path>\artifacts\<slug>-<version>-chrome.zip`, matching Firefox ZIP, and `.addonry\package-report.json` with SHA-256 values. Rebuild blocks existing artifact unless `--overwrite` is explicitly supplied. Packaging does not sign, install, upload, or publish.

Chrome Web Store signs Chrome distribution. Normal Firefox Release/Beta requires Mozilla-signed XPI. Those external actions need separate explicit request and credentials.

## Repository development checks

```powershell
python -m unittest discover -s tests -v
python scripts/validate_repository.py
python scripts/sync_manual_command.py
forge compile
forge sync
node --check skills/create-chrome-extension/scripts/verify_extension.cjs
python -c "from pathlib import Path; compile(Path('skills/create-chrome-extension/scripts/quality_loop.py').read_text(encoding='utf-8'), 'quality_loop.py', 'exec')"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-chrome-devtools-mcp.ps1 -SelfTest
node scripts/smoke_chrome_devtools_mcp.cjs
```

Large reusable browser/runtime output routes through mounted `agent-devstorage` selected by `DRIVE-IDENTITY.json`; source remains in repository. If no participating drive exists, helpers state fallback and use `%LOCALAPPDATA%\Addonry\runtime`.

## Provider development load

```powershell
claude --plugin-dir .
forge install --provider all --mode link
kimi
```

After marketplace release, install `addonry@0langas-plugins`, start new provider session, then use matching manual invocation.
