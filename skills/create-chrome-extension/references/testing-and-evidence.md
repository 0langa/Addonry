# Testing and Evidence

## Required matrix

| Layer | Evidence |
| --- | --- |
| Static | manifest parses, paths exist, MV3/CSP/security checks pass, starter markers removed, acceptance metadata complete |
| Syntax | every shipped JS file parses |
| Unit | pure transforms and edge cases pass |
| Chrome E2E | unpacked extension loaded into real Chrome and tailored JavaScript scenario passes |
| Firefox E2E | target package temporarily installed into real Firefox and tailored Python scenario passes |
| Background | restart/recovery tested when state matters in each requested browser |
| DevTools MCP | representative live page inspected; console/network/DOM evidence clean; Chrome evidence only |
| Install | each requested daily browser performs user flow, or protected manual action is identified |
| Package | target ZIP layout, manifest, exclusions, SHA-256, and reproducibility pass when packaging requested |
| Traceability | every confirmed criterion maps implementation/test paths to current proof and final report reaches 100% with no findings |

## Fixture strategy

For page-specific features, create deterministic local fixture capturing needed DOM states without copying sensitive content. Cover normal, empty, malformed, duplicate, delayed/dynamic, and permission-denied cases that matter. Use live site as additional smoke, not sole test oracle.

## E2E scenario contract

Generated `tests/e2e.cjs` exports `run(context)`:

```javascript
exports.run = async ({ browser, extensionId, manifest, openPopup, getServiceWorker, assert }) => {
  const targetPage = await browser.newPage();
  await targetPage.goto('https://example.com/');
  const popup = await openPopup(targetPage);
  await popup.waitForSelector('[data-testid="ready"]');
  assert.equal(await popup.$eval('h1', (node) => node.textContent), manifest.name);
  return { criteriaPassed: ['REQ-001'] };
};
```

Harness provides actual Chrome, verified extension registration, parsed manifest, toolbar-action helpers, and Node strict assertion module. Tailor scenario to requested behavior. Avoid mocks at E2E layer. Report criterion ID only after every mapped assertion succeeds.

`openPopup(targetPage)` uses Puppeteer's extension toolbar-action API and grants `activeTab` to target page. `triggerAction(targetPage)` handles toolbar actions without popup. When shipped manifest uses `activeTab`, harness records limitation unless tailored scenario invokes one helper with representative page and asserts resulting behavior. `openPopup()` without target page tests popup UI only.

After harness pass, run `validate_extension.py <path> --final-ready`. Gate rejects generic scenario, stale source digest, missing browser-registration or MCP evidence, cleanup warnings, and unresolved limitations.

## Firefox scenario contract

Generated `tests/firefox_e2e.py` defines `run(context)`:

```python
def run(context):
    driver = context["driver"]
    driver.get(context["extension_origin"] + "/src/popup.html")
    heading = driver.find_element("css selector", "h1")
    assert heading.text == context["manifest"]["name"]
    return {"limitations": [], "criteriaPassed": ["REQ-001"]}
```

Context includes real Selenium Firefox driver, installed add-on ID, temporary UUID/origin, Firefox-target manifest, explicit wait helper, and run artifact directory. Tailor scenario to requested behavior. If feature uses `activeTab`, return `activeTabProven: true` only after representative Firefox action flow proves grant-dependent behavior.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File <loaded-skill-directory>\scripts\verify-firefox-extension.ps1 `
  -ExtensionPath <extension-path> `
  -ScenarioPath <extension-path>\tests\firefox_e2e.py
```

Helper runs pinned `web-ext` lint, packages Firefox target without publication, launches isolated real Firefox through pinned Selenium, installs unsigned XPI temporarily, verifies Gecko ID/UUID, runs scenario, uninstalls add-on, closes browser, and writes `.addonry/firefox-verification.json`.

## Quality-loop gate

After tailored tests exist, run `quality_loop.py cycle <extension-path>`. Controller runs fixed commands only; contract cannot inject shell. It writes criterion traceability, source/contract digests, proof inventory, failure fingerprint, repair status, and bounded history. Repair first finding and repeat. `strategy-change-required` means identical unchanged failure reached threshold; isolate and change strategy. Only `passed` with 100% coverage and empty findings permits completion claim. See [quality-loop.md](quality-loop.md).

## Failure handling

- Reproduce before changing code.
- Preserve concise failure evidence without secrets.
- Fix root cause, rerun failed layer, then rerun full matrix.
- Treat flaky wait as test bug; wait for observable state, not arbitrary sleep.
- Explain environmental skips; do not count skipped live test as pass.

## Evidence record

Update `.addonry/project.json` with permissions rationale, requested browsers, browser versions, commands, and final status. Confirmed criteria live in `.addonry/contract.json`; controller writes `.addonry/quality-loop.json` and `.addonry/quality-report.json`. Chrome harness writes `.addonry/verification.json`; Firefox harness writes `.addonry/firefox-verification.json`. Keep evidence local with generated extension.
