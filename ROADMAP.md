# Addonry Roadmap

Status: milestones 1-3.5 implemented and verified on 2026-08-27. Milestone 4 remains future work. Code, tests, and executable evidence outrank this file.

## Product direction

Addonry builds small personal Manifest V3 extensions for desktop Chrome and Firefox from one shared project. It remains manual-only, asks product questions before implementation, uses least privilege, verifies each requested browser, and reports installation and packaging state without treating one as proof of another.

## Milestone 1: cross-browser project model

- [x] Accept `chrome`, `firefox`, or `both`; default new projects to `both`.
- [x] Generate shared source with Chrome service-worker and Firefox background-script declarations.
- [x] Generate stable Firefox extension ID and explicit data-collection declaration.
- [x] Store requested browser targets and per-browser state in `.addonry/project.json`.
- [x] Preserve current `create-chrome-extension` manual command as compatibility surface.

Exit gate: fresh scaffold passes static validation for both browser targets.

## Milestone 2: browser-specific verification

- [x] Keep tailored Chrome E2E plus Chrome DevTools MCP evidence.
- [x] Add Firefox manifest lint and real temporary-install smoke.
- [x] Bind final-ready evidence to source digest and requested browser targets.
- [x] Refuse `verified` or `installed` claims when evidence exists for only one requested browser.

Exit gate: fixture passes Chrome and Firefox target checks, with honest blocker state when local browser tooling is unavailable.

## Milestone 3: deterministic packaging

- [x] Build target-specific runtime trees from shared source.
- [x] Exclude tests, metadata, source-control state, credentials, and prior artifacts.
- [x] Write ZIP with `manifest.json` at archive root.
- [x] Produce SHA-256, file inventory, source digest, target, and version report.
- [x] Rebuild identical source into byte-identical package.

Exit gate: both packages validate, contain no forbidden paths, and reproduce identical hashes.

## Milestone 3.5: acceptance-driven quality loop

- [x] Generate draft request contract and persistent iteration state.
- [x] Require atomic criterion mappings to runtime source, tests, targets, and proof kinds.
- [x] Capture criterion IDs from real Chrome and Firefox scenarios after assertions.
- [x] Reassess static, syntax, unit, browser, final-ready, and package gates until all pass.
- [x] Invalidate stale browser/package evidence after source changes.
- [x] Detect unchanged retry stalls and preserve explicit external blocker state.
- [x] Produce 100% traceability report with zero hard findings before completion claim.

Exit gate: deliberately broken cross-browser fixture fails with actionable gaps, then repaired fixture reaches live `passed` status with 100% current criterion proof and deterministic packages.

## Milestone 4: optional distribution

- [ ] Add Chrome Web Store upload preparation.
- [ ] Add Mozilla AMO signing preparation for listed or unlisted distribution.
- [ ] Keep credentials outside project and artifacts.
- [ ] Require explicit user request immediately before signing, upload, publication, or update.

This milestone is not part of local packaging. Store accounts, credentials, declarations, screenshots, review, and publication remain separate external gates.

## Long-term targets

- Firefox Android compatibility as separate target.
- Edge compatibility using Chromium target where behavior matches.
- API compatibility catalog for browser-specific features.
- Migration support for existing Chrome-only Addonry projects.
