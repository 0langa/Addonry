# Changelog

## [Unreleased]

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
