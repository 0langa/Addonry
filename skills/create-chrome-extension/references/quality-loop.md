# Acceptance-Driven Quality Loop

## Purpose

Addonry uses deterministic accounting around agent implementation work. Agent interprets request and repairs code; controller decides whether current contract has current proof. It never asks model to score its own confidence.

`100%` means every criterion in confirmed `.addonry/contract.json` passed against current source. It does not mean natural-language intent received mathematical proof. Make contract observable, atomic, and user-visible before implementation.

## Contract

Scaffolder creates draft `.addonry/contract.json`. After grouped intake, replace draft criteria and mark contract confirmed:

```json
{
  "schemaVersion": 1,
  "status": "confirmed",
  "confirmedAt": "2026-08-27T00:00:00+00:00",
  "requestSummary": "Toolbar popup extracts visible PDF links in both browsers.",
  "browserTargets": ["chrome", "firefox"],
  "packagingRequested": true,
  "qualityPolicy": {
    "requireZeroWarnings": true,
    "stallThreshold": 3
  },
  "acceptedWarnings": [],
  "criteria": [
    {
      "id": "REQ-001",
      "kind": "behavior",
      "requirement": "Extract visible PDF links from active page.",
      "acceptance": "Both browser scenarios assert normalized unique links in page order.",
      "appliesTo": ["chrome", "firefox"],
      "proof": {
        "implementation": ["src/popup.js"],
        "tests": ["tests/e2e.cjs", "tests/firefox_e2e.py"],
        "evidence": ["static-validation", "chrome-e2e", "firefox-e2e", "package"]
      }
    }
  ]
}
```

Criterion rules:

- Stable ID: `REQ-001` or higher-width numeric equivalent.
- `kind`: `behavior`, `constraint`, `quality`, or `package`.
- `appliesTo`: non-empty subset of confirmed targets.
- Runtime implementation and test paths must exist inside extension root; implementation cannot point to metadata, tests, or artifacts.
- Browser behavior must map canonical `tests/e2e.cjs` or `tests/firefox_e2e.py` and corresponding evidence kind.
- Packaging choice and package evidence must agree.
- Accepted validator warning needs exact code plus concrete rationale. Default policy requires zero warnings.

## Scenario proof

Browser scenario reports criterion only after every relevant assertion succeeds.

Chrome:

```javascript
exports.run = async ({ openPopup, assert }) => {
  const popup = await openPopup();
  await popup.waitForSelector('[data-testid="results"]');
  assert.deepEqual(await popup.$$eval('a', (nodes) => nodes.map((node) => node.href)), expected);
  return { criteriaPassed: ['REQ-001'] };
};
```

Firefox:

```python
def run(context):
    driver = context["driver"]
    # Perform representative behavior and assertions.
    assert observed == expected
    return {"criteriaPassed": ["REQ-001"]}
```

Never return criterion ID before assertion. Generic popup visibility cannot prove feature behavior.

## Commands

Cheap assessment:

```powershell
python skills/create-chrome-extension/scripts/quality_loop.py assess <extension-path>
```

Full cycle:

```powershell
python skills/create-chrome-extension/scripts/quality_loop.py cycle <extension-path>
```

Full cycle uses fixed Addonry commands only. It validates contract/paths, runs release-ready static checks, JavaScript/Python syntax, discovered `tests/unit` tests, stale/missing requested browser gates, final-ready validation, requested package refresh, independent ZIP/hash validation, and final traceability accounting. Contract cannot inject shell commands.

Record proven external blocker:

```powershell
python skills/create-chrome-extension/scripts/quality_loop.py block <extension-path> `
  --code <lower-case-code> `
  --reason "<specific external blocker>"
```

Use `block` only after reproducing unavailable authority, authentication, browser/tool, protected UI, or platform constraint. Code/test failures remain `repair-required`.

## Agent loop

1. Run `cycle`.
2. Read `.addonry/quality-report.json`; start with first lowest-layer finding.
3. Reproduce/fix implementation, test, mapping, or environment gap.
4. Rerun focused failing gate.
5. Rerun `cycle`; never reuse evidence after source change.
6. At `strategy-change-required`, stop identical retries, isolate failure, change diagnosis/implementation strategy, then continue.
7. Finish only at `passed`, coverage `100.0`, empty findings, current browser proof for every target, and current package proof when requested.

## Durable outputs

- `.addonry/quality-loop.json`: iteration, repeat count, failure fingerprint, status, next action, bounded history.
- `.addonry/quality-report.json`: source/contract digests, traceability rows, gate inventory, findings, coverage.
- `.addonry/project.json` `qualityLoop`: compact current status pointer.

Source digest excludes metadata and regenerable caches/artifacts. Runtime source, manifest, and tests remain source-digest-bound. Confirmed contract has separate digest embedded in browser and package evidence. Any relevant source/test or acceptance-contract change invalidates prior proof.

## Status meanings

- `passed`: every criterion and hard gate passed; zero findings.
- `repair-required`: autonomous source/test/contract/evidence repair remains.
- `strategy-change-required`: unchanged source, contract, and failure fingerprint repeated at threshold.
- `blocked`: explicitly proven external condition prevents progress.

Never map `repair-required`, `strategy-change-required`, or `blocked` to finished. Never treat percentage as override for hard finding.
