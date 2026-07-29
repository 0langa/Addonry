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
  const popup = await openPopup();
  await popup.waitForSelector('[data-testid="ready"]');
  assert.equal(await popup.$eval('h1', (node) => node.textContent), manifest.name);
};
```

Harness provides actual Chrome, extension ID, parsed manifest, helpers, and Node strict assertion module. Tailor scenario to requested behavior. Avoid mocks at E2E layer.

`openPopup()` calls `chrome.action.openPopup()` from extension service worker. This tests popup UI but does not reproduce user gesture that grants `activeTab`. When shipped manifest uses `activeTab`, harness records limitation unless tailored scenario can prove real grant. Overall completion then requires toolbar click in installed daily Chrome through supported Chrome control or user, followed by observable result check. Never report generic popup pass as active-tab proof.

## Failure handling

- Reproduce before changing code.
- Preserve concise failure evidence without secrets.
- Fix root cause, rerun failed layer, then rerun full matrix.
- Treat flaky wait as test bug; wait for observable state, not arbitrary sleep.
- Explain environmental skips; do not count skipped live test as pass.

## Evidence record

Update `.addonry/project.json` with acceptance contract, permissions rationale, Chrome version, test commands, and final status. Harness writes `.addonry/verification.json`; keep it local with generated extension.
