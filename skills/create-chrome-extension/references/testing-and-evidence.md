# Testing and Evidence

## Required matrix

| Layer | Evidence |
| --- | --- |
| Static | manifest parses, paths exist, MV3/CSP/security checks pass, starter markers removed, acceptance metadata complete |
| Syntax | every shipped JS file parses |
| Unit | pure transforms and edge cases pass |
| E2E | unpacked extension loaded into real Chrome and tailored scenario passes |
| Service worker | restart/recovery tested when state matters |
| DevTools MCP | representative live page inspected; console/network/DOM evidence clean |
| Install | daily Chrome loaded copy performs user flow, or protected manual action identified |

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
};
```

Harness provides actual Chrome, verified extension registration, parsed manifest, toolbar-action helpers, and Node strict assertion module. Tailor scenario to requested behavior. Avoid mocks at E2E layer.

`openPopup(targetPage)` uses Puppeteer's extension toolbar-action API and grants `activeTab` to target page. `triggerAction(targetPage)` handles toolbar actions without popup. When shipped manifest uses `activeTab`, harness records limitation unless tailored scenario invokes one helper with representative page and asserts resulting behavior. `openPopup()` without target page tests popup UI only.

After harness pass, run `validate_extension.py <path> --final-ready`. Gate rejects generic scenario, stale source digest, missing browser-registration or MCP evidence, cleanup warnings, and unresolved limitations.

## Failure handling

- Reproduce before changing code.
- Preserve concise failure evidence without secrets.
- Fix root cause, rerun failed layer, then rerun full matrix.
- Treat flaky wait as test bug; wait for observable state, not arbitrary sleep.
- Explain environmental skips; do not count skipped live test as pass.

## Evidence record

Update `.addonry/project.json` with acceptance contract, permissions rationale, Chrome version, test commands, and final status. Harness writes `.addonry/verification.json`; keep it local with generated extension.
