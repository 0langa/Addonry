# Acceptance-Driven Quality Loop Plan

Status: preconfirmed, implemented, and verified on 2026-08-27.

## Outcome

Addonry must convert confirmed user intent into a machine-readable contract, repeatedly assess current extension against deterministic gates, preserve iteration state, direct repairs, and finish only when every required criterion has current proof. Natural-language intent is not mathematically provable; `100% match` means every criterion in confirmed acceptance contract is mapped to implementation, exercised by declared proof, and passed against current source digest.

## Non-negotiable boundaries

- Preserve manual-only activation on Claude, Codex, and Kimi.
- Agent owns implementation and repair decisions; deterministic controller owns pass/fail accounting.
- Never edit evidence or digests to force success.
- Any source change invalidates browser and package proof.
- Any confirmed contract change invalidates browser and package proof even when runtime source stays unchanged.
- Chrome proof never satisfies Firefox; Firefox proof never satisfies Chrome.
- Missing tools, permissions, authentication, or protected UI become explicit blockers, never success.
- Signing, publication, Git operations, and normal-profile browser mutation remain separately authorized actions.
- Quality scores are diagnostic only. One failed hard gate prevents completion.

## Durable state

Each generated extension gains:

- `.addonry/contract.json`: confirmed request summary, targets, packaging choice, quality policy, and atomic acceptance criteria.
- `.addonry/quality-loop.json`: current iteration, source/contract digests, failure fingerprint, repeat count, status, next action, and bounded history.
- `.addonry/quality-report.json`: traceability matrix, proof inventory, request coverage, findings, and final verdict.

Each criterion contains stable ID, requirement, observable acceptance statement, browser scope, implementation paths, test paths, and required evidence kinds. Supported evidence kinds are `static-validation`, `chrome-e2e`, `firefox-e2e`, and `package`.

## Loop

1. Validate confirmed contract and project/target consistency.
2. Verify every proof path stays inside extension root and exists.
3. Run release-ready static validation with zero unresolved warnings when policy requires it.
4. Run JavaScript/Python syntax checks and discovered local unit tests.
5. Run tailored Chrome and Firefox browser gates requested by contract.
6. Require each browser scenario to return IDs it proved after assertions.
7. Run final-ready source-bound browser validation.
8. When packaging requested, create or refresh deterministic target ZIPs and revalidate hashes, target coverage, layout, and source digest.
9. Build criterion-by-criterion traceability report.
10. If any hard finding remains, record repair verdict and repeat after agent changes implementation/tests/contract.
11. If identical source, contract, and failure fingerprint repeat three times, require strategy change instead of blind retry.
12. Finish only with status `passed`, 100% required-criterion coverage, zero findings, and current proof.

## Commands

```powershell
python skills/create-chrome-extension/scripts/quality_loop.py assess <extension-path>
python skills/create-chrome-extension/scripts/quality_loop.py cycle <extension-path>
python skills/create-chrome-extension/scripts/quality_loop.py block <extension-path> --code <code> --reason "<reason>"
```

`assess` performs non-browser deterministic accounting and writes state/report. `cycle` runs full requested gate sequence, including isolated browser verification and requested local package refresh. Agent invokes `cycle`, repairs reported gaps, and invokes it again until passed or externally blocked.

## Implementation sequence

1. Add contract/state/report schemas and quality-loop engine.
2. Scaffold draft contract and initial loop state.
3. Capture `scenarioResult.criteriaPassed` in both browser evidence formats.
4. Add criterion proof checks, stale-proof checks, package revalidation, and stall detection.
5. Add full-cycle orchestration with safe fixed commands only; never execute arbitrary contract commands.
6. Make final-ready validator accept confirmed contract criteria as acceptance source while retaining legacy metadata compatibility.
7. Update canonical skill to require contract confirmation, loop execution, repairs, and final report.
8. Add deterministic unit/regression tests and committed quality-loop fixture.
9. Demonstrate intentional failure, repair, current Chrome/Firefox evidence, deterministic packages, and final 100% report.
10. Reconcile docs and Forge-generated provider surfaces from observed proof.

## Completion gates

- Scaffold creates valid draft contract and resumable initial state.
- Invalid, empty, contradictory, escaping, or unmapped contract fails closed.
- Missing criterion evidence prevents pass even when generic browser checks pass.
- Source change makes prior browser/package evidence stale.
- Repeated identical failure triggers strategy-change state.
- Broken fixture produces actionable criterion-level findings.
- Repaired fixture reaches `passed` with 100% traceability for Chrome and Firefox.
- Requested packages match verified source and pass independent hash/layout checks.
- Existing Chrome-only and cross-browser validation remain green.
- Full repository suite, structural validator, command mirror, Forge sync, syntax, and diff checks pass.

## Truthful stop states

- `passed`: all hard gates and every confirmed criterion passed against current source.
- `repair-required`: code, test, mapping, or evidence gap can be repaired autonomously.
- `strategy-change-required`: same unchanged failure repeated at configured threshold.
- `blocked`: external authority, authentication, browser/tool availability, or proven platform constraint prevents progress.

No iteration budget, percentage score, or agent confidence may convert incomplete work into `passed`.

## Delivered evidence

- Iteration 1 rejected fixture with `contract-missing`.
- Iteration 2 accepted repaired contract/cheap gates but rejected stale browser/package evidence and missing criterion IDs.
- Iteration 3 exposed real digest bug: Firefox regenerated `__pycache__`, making evidence immediately stale. Digest rules were repaired and regression-tested.
- Iteration 4 ran real Chrome and Firefox gates, rebuilt packages, and reached `passed` with `2/2` criteria, `100.0` coverage, and zero findings.
- Iterations 5-6 re-assessed same source successfully; iteration 7 refreshed Chrome, Firefox, and package evidence after contract-digest binding and passed again.
- Chrome `151.0.7922.174` passed tailored scenario, extension registration, diagnostics, and Chrome DevTools MCP evidence with `REQ-001` reported after assertions.
- Firefox `154.0.1` passed `web-ext lint`, temporary installation, tailored scenario, registration, cleanup, and `REQ-001` reporting.
- Chrome and Firefox package reports match source digest and independently validated ZIP layout/hash checks.
- Regression suite covers full success, missing criterion proof, stale browser/package proof, path escape, bytecode-cache stability, mutation during assessment, repeated-failure strategy change, external blocker state, and browser-proof reuse.
- Browser and package reports bind both source digest and confirmed-contract digest, preventing old proof reuse after requirement changes.
- Current repository suite passed `41` tests; repository validator passed `34` required files and `3` provider manifests; Python, Node, PowerShell, command-mirror, final-ready, MCP wrapper, Forge drift, and diff checks passed.
- Manual-only activation, provider generation, and no-sign/no-publish boundaries remain intact.
