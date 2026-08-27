# Cross-Browser Extension Architecture

## Target model

New projects target `chrome`, `firefox`, or `both`; default is `both`. Keep shared HTML, CSS, JavaScript, content scripts, permissions, and tests where browser behavior matches. Branch only at verified browser boundary.

For shared background logic, declare same file for each supported environment:

```json
"background": {
  "service_worker": "src/service-worker.js",
  "scripts": ["src/service-worker.js"]
}
```

Chrome package keeps `service_worker`. Firefox package keeps `scripts`. Background code must not depend on persistent globals because Chrome service workers can stop; Firefox event pages can also unload.

## Route by trigger

| Need | Portable surface |
| --- | --- |
| Toolbar click and page DOM | `activeTab` + `scripting.executeScript` after per-browser proof |
| Popup UI | `action.default_popup` |
| Automatic known-page behavior | narrow `content_scripts.matches` |
| Browser events | shared background file with dual declaration |
| Right-click action | `contextMenus` + background listener |
| Keyboard action | `commands` + background listener |
| Settings | `options_ui` + `storage` |
| Downloads | `downloads`, sanitized filenames, browser-specific behavior check |
| Cookies | `cookies` plus narrow host permissions |

## API rules

- Prefer portable WebExtension API subset.
- Firefox supports much Chrome-style `chrome.*` code, but support and async behavior still require compatibility check.
- Use local compatibility adapter or bundled WebExtension polyfill when promise/namespace behavior differs. Never fetch runtime code.
- Treat `side_panel`, `offscreen`, proxy configuration, request interception, and browser-specific UI as explicit single-browser design until both targets pass current compatibility research.
- Keep browser branching centralized; do not scatter user-agent checks.
- Record browser-specific limitations in `.addonry/project.json`.

## Manifest rules

- Use Manifest V3.
- Firefox target requires `browser_specific_settings.gecko.id` and explicit `data_collection_permissions`.
- Chrome target may use `minimum_chrome_version`; Firefox target may use `strict_min_version` inside Gecko settings.
- Keep executable JavaScript and WASM local.
- Avoid inline scripts, inline event handlers, `eval`, and `new Function`.
- Request least privilege and narrow hosts.

## Page boundaries

Content scripts run separately from page JavaScript. Use validated messages between content, popup, and background contexts. Treat DOM, frames, shadow roots, URLs, and network data as untrusted.

Use `textContent`, DOM construction, and URL parsing instead of untrusted `innerHTML`. Centralize selectors, tolerate missing nodes, bound observers, and disconnect them.

## Implementation style

Prefer dependency-free JavaScript for small utilities. Separate pure transforms from browser APIs. Add build tooling only when dependency or type complexity justifies it; packaging is not permission to add build complexity.
