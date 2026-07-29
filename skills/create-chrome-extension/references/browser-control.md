# Browser Control

## Default mode

Bundled `addonry-chrome-devtools` server launches current stable Chrome with temporary isolated profile. Usage statistics and update checks are disabled. Use this mode for target-page inspection, reproducible diagnostics, console/network evidence, screenshots, and privacy-safe testing.

Expected MCP runtime is pinned in `scripts/start-chrome-devtools-mcp.ps1`. If tools are missing, check provider MCP status and run wrapper `-SelfTest`; then reload plugin/new session. Do not silently substitute web search for live target inspection.

## Tool workflow

Discover current tool names rather than assuming stale schema. Use capabilities equivalent to:

1. list/select/open page;
2. semantic snapshot;
3. click/type/upload when user flow needs it;
4. evaluate focused JavaScript for DOM facts only;
5. inspect console and network;
6. capture screenshot for visual evidence.

Prefer semantic snapshot and direct page state over coordinate clicks. Use JavaScript evaluation for facts unavailable through snapshot, not as replacement for user-facing interaction tests.

## Authenticated daily Chrome

Use isolated browser unless task truly needs existing login. Chrome 144+ can expose explicit remote-debugging permission through `chrome://inspect/#remote-debugging`; wrapper supports `ADDONRY_CHROME_MODE=auto-connect` on next provider session.

Auto-connect requires user to enable debugging and accept Chrome dialog. It grants MCP access to open windows in selected profile. Before requesting it:

- explain access scope;
- ask user to close unrelated sensitive tabs;
- avoid reading cookies, storage, passwords, profile files, or unrelated pages;
- disable remote debugging when finished.

`browser-url` mode exists for dedicated test Chrome only. Set both `ADDONRY_CHROME_MODE=browser-url` and `ADDONRY_CHROME_BROWSER_URL=http://127.0.0.1:<port>` before session. A raw debugging port lets any local process control browser, so never use normal profile and never leave port open after work.

## Final installation UI

If host offers user-Chrome control (for example Codex Chrome capability), use it for `chrome://extensions` and toolbar pinning after extension passes isolated tests. Chrome DevTools MCP remains primary diagnostic tool. Protected browser UI may still require one user confirmation.
