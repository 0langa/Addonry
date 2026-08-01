# Changelog

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
