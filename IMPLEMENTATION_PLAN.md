# Cross-Browser And Packaging Implementation Plan

Status: preconfirmed by user, then implemented and verified on 2026-08-27.

## Confirmed outcome

Deliver Addonry support for personal desktop Chrome and Firefox extensions plus deterministic local packaging when user requests it. Preserve manual-only activation and current safety boundaries.

## Confirmed decisions

- Target values: `chrome`, `firefox`, `both`; new scaffold default: `both`.
- Source model: one shared MV3 project and one root development manifest.
- Background model: same script declared as Chrome service worker and Firefox background script.
- API model: portable WebExtension subset by default; browser-specific APIs require explicit target check and documented limitation.
- Firefox identity: stable generated GUID stored in manifest; AMO data collection defaults to `required: ["none"]` unless feature contract says otherwise.
- Public surface: retain `create-chrome-extension` command for compatibility; broaden instructions and descriptions to browser extensions.
- Packaging: separate Chrome and Firefox ZIPs, deterministic ordering/timestamps, manifest at root, SHA-256 report.
- Artifact scope: runtime files only. Exclude `.addonry`, `tests`, `.git`, `artifacts`, caches, logs, local environment files, and credentials.
- Distribution: no signing, store upload, publication, Git commit, or release without separate explicit request.
- Evidence: Chrome evidence cannot satisfy Firefox gate; Firefox evidence cannot satisfy Chrome gate.

## Execution sequence

1. Update scaffold and project metadata.
2. Extend validator with target-aware manifest and evidence rules.
3. Add deterministic package builder and package report.
4. Add Firefox lint/temporary-install verification helper.
5. Update canonical skill, references, README, command mirror, and provider metadata.
6. Add regression tests for targets, manifests, package contents, determinism, and evidence separation.
7. Run focused tests, full unit suite, repository validator, syntax checks, Forge compile/sync, and available browser smokes.
8. Update this file and `ROADMAP.md` only from observed results.

## Completion gates

- Scaffolded `both` project passes target-aware static validation.
- Chrome-only and Firefox-only scaffolds omit unsupported target requirements.
- Packaging produces valid target ZIPs twice with identical SHA-256 values.
- Package contains no excluded development paths or sensitive filename classes.
- Firefox package passes `web-ext lint` when tool is available.
- Existing Chrome fixture and current Chrome validation remain green.
- Manual-only provider surfaces remain disabled for implicit invocation.
- Forge-generated manifests show no drift.

## Expected files

- `skills/create-chrome-extension/scripts/scaffold_extension.py`
- `skills/create-chrome-extension/scripts/validate_extension.py`
- `skills/create-chrome-extension/scripts/package_extension.py`
- `skills/create-chrome-extension/scripts/verify-firefox-extension.ps1`
- `skills/create-chrome-extension/references/cross-browser-architecture.md`
- `skills/create-chrome-extension/references/packaging.md`
- canonical skill, README, tests, Forge source, generated provider manifests

## Stop conditions

Pause only for credential use, store submission, browser-profile mutation outside isolated test profile, destructive migration of existing generated projects, or platform behavior disproving planned architecture.

## Delivered evidence

- `41` current repository tests passed, including original cross-browser/packaging gates and added quality-loop regressions.
- Both committed fixtures passed final-ready validation with zero errors and warnings.
- Chrome cross-browser and active-tab live smokes passed on Chrome `151.0.7922.174`, including Chrome DevTools MCP evidence.
- Firefox temporary-install smoke and `web-ext lint` passed on Firefox `154.0.1`.
- Chrome and Firefox packages passed target validation and deterministic-package coverage; live package reports recorded SHA-256 and runtime inventory.
- Repository validator passed `27` required files and `3` generated provider manifests.
- Canonical manual command mirror matched, Plugin Forge sync reported no drift, and `git diff --check` passed after documentation reconciliation.
- Signing, store upload, publication, commit, tag, and release were intentionally not performed.
