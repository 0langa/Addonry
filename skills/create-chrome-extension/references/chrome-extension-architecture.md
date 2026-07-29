# Chrome Extension Architecture

## Route by trigger

| Need | Preferred surface |
| --- | --- |
| User clicks toolbar button and page DOM is needed | `activeTab` + `scripting.executeScript` |
| Popup UI | `action.default_popup` |
| Runs automatically on known pages | narrow `content_scripts.matches` |
| Browser event handling | extension service worker |
| Right-click action | `contextMenus` + service worker |
| Keyboard action | `commands` + service worker |
| Settings | `options_ui` + `storage` |
| Downloads | `downloads` with sanitized filenames |
| Cookie access | `cookies` plus narrow host permissions |

## Manifest V3 baseline

- Use `manifest_version: 3`.
- Keep `name`, `version`, `description`, icons, action, background, and permissions limited to actual behavior.
- Package executable JavaScript and WASM locally. Do not fetch code for execution.
- Use extension CSP defaults; avoid inline scripts, inline event handlers, `eval`, and `new Function`.
- Set `minimum_chrome_version` only when implementation uses an API introduced after user's installed Chrome.

## Service worker rules

- Register event listeners synchronously at top level.
- Expect termination at any time.
- Persist required state in `chrome.storage`; never depend on global variables across events.
- Replace long timers with alarms when wake-up semantics matter.
- Return or await asynchronous message handling correctly.
- Keep DOM work in popup, content script, or justified offscreen document.

## Page boundaries

Content scripts run in isolated world. Use messages for communication with service worker. When page-world execution is necessary, keep injected function small, validate inputs/outputs, and avoid exposing extension internals.

Treat page DOM and network data as untrusted:

- use `textContent`, DOM construction, and URL parsing instead of untrusted `innerHTML`;
- validate message `type`, payload shape, sender tab/origin, and expected response;
- centralize selectors and tolerate missing nodes;
- observe dynamic pages with bounded `MutationObserver`, then disconnect;
- inspect frames/shadow roots explicitly rather than assuming main document.

## Permissions

Request least privilege. Prefer `activeTab` for click-triggered current-page access. Prefer optional permissions when core function can run without them. Narrow hosts to required schemes/domains and explain high-impact access.

Common high-impact permissions needing explicit justification: `cookies`, `history`, `management`, `nativeMessaging`, `debugger`, broad `tabs` access, and `<all_urls>` host access.

## Storage and exports

- Version stored schema.
- Validate imported data before mutation.
- Use atomic replace pattern: parse -> validate -> backup -> apply -> verify.
- Bound retained history and object sizes.
- Do not store secrets unless feature explicitly requires them and user accepts risk.

## Implementation style

Prefer dependency-free JavaScript for small utilities. Separate pure transforms from Chrome API calls so logic is unit-testable. Add TypeScript/build tooling only when type complexity or bundled dependencies justify operational cost.
