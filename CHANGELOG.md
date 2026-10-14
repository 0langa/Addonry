# Changelog

## [0.3.2] - 2026-10-14

- Keep Claude Code from starting the manual-only workflow on its own: the command and the canonical skill now set `disable-model-invocation: true`, so only `/addonry:create-chrome-extension` runs it.
- Validate the project slug before packaging, so a crafted slug in `.addonry/project.json` can no longer write the ZIP outside `artifacts/`.
- Update the Firefox verifier's runtime to web-ext 10.7.0 and force shell-quote 1.11.0, which clears the image-size and critical shell-quote advisories. The node-forge advisory (GHSA-86w9-cpqp-85rv) stays open until a patched release exists; `web-ext lint`, the only command the verifier runs, never loads it.

## [0.3.1] - 2026-09-09

- Keep MCP and browser-verifier runtime packages local, and preserve the user's npm, uv, and Selenium cache settings.
- Preserve LF checkout bytes for evidence-bound test fixtures so Windows line-ending conversion does not invalidate recorded source and contract hashes.

## [0.3.0] - 2026-08-27

- Added confirmed request contracts, persistent iteration state, criterion-to-proof traceability, autonomous gate cycling, stall detection, and honest external-blocker recording.
- Bound Chrome, Firefox, and package evidence to acceptance-contract/source digests and criterion IDs; fixed source digests to ignore regenerable Python bytecode caches.
- Added shared desktop Chrome and Firefox MV3 scaffolding with target-aware validation and per-browser evidence gates.
- Added real Firefox temporary-install verification through Selenium plus target-specific `web-ext lint`.
- Added deterministic, unsigned Chrome and Firefox ZIP packaging with SHA-256 reports, source binding, runtime-only inventories, and sensitive-file refusal.
- Kept existing Chrome verification green while updating pinned Puppeteer and hardening active-tab fixture cleanup and action timeouts.

## [0.2.1] - 2026-08-05

- Enforced Kimi's native manual-only skill gate with `disableModelInvocation: true`, so Addonry remains manual-only on every provider, backed by repository validation and regression coverage.
- Made generated-provider validation self-contained, verifying provider-surface paths without cross-repository CI access.
- Excluded local runtime state and generated dependencies from repository source validation.

## [0.2.0] - 2026-08-01

- Added source-bound `--final-ready` gate requiring passed tailored Chrome E2E, extension registration, MCP evidence, clean cleanup, and no unresolved limitations.
- Added real toolbar-action and `activeTab` verification through Puppeteer extension APIs, backed by local HTTP fixture and CI smoke.
- Expanded validator coverage for optional/high-risk permissions, broad host patterns, manifest resources, remote static imports, malformed lists, and secrets in non-JavaScript text files.
- Made Chrome test-profile cleanup retryable and truthfully reported without overwriting primary test result.
- Corrected scaffold installation instructions for branded Chrome 137+ and hardened MCP plugin-root resolution across Codex, Claude Code, and Kimi Code.
- Added external devstorage routing logs and quieter pinned npm installs.
- Reduced canonical skill below evaluator truncation limit while preserving detailed references; standard PluginEval reached Gold with trigger F1 1.0 and no anti-patterns.

## 0.1.4 - 2026-07-30

- Blocked obsolete `--load-extension` path for branded Chrome 137+ before changing browser processes.
- Replaced false installation inference with supported **Load unpacked** guidance and explicit install-pending state.

## 0.1.0 - 2026-07-29

- Initial manual-only Codex, Claude Code, and Kimi Code plugin release.
- Added autonomous Manifest V3 workflow, Chrome DevTools MCP integration, scaffolding, validation, and real-Chrome E2E harness.
