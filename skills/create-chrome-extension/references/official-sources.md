# Official Sources

Checked 2026-08-27. Re-open relevant primary page whenever current behavior matters.

## Chrome Extensions

- Overview and tutorials: https://developer.chrome.com/docs/extensions/
- Hello World, load unpacked, reload rules: https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world
- Manifest V3: https://developer.chrome.com/docs/extensions/develop/migrate/what-is-mv3
- Service workers: https://developer.chrome.com/docs/extensions/develop/migrate/to-service-workers
- Permissions: https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions
- Security: https://developer.chrome.com/docs/extensions/develop/security-privacy/stay-secure
- E2E testing: https://developer.chrome.com/docs/extensions/how-to/test/end-to-end-testing
- Puppeteer extension testing: https://developer.chrome.com/docs/extensions/how-to/test/puppeteer
- Puppeteer `Browser.installExtension()` and registration APIs: https://pptr.dev/api/puppeteer.browser.installextension
- Puppeteer `Extension.triggerAction()` and extension metadata: https://pptr.dev/api/puppeteer.extension
- ChromeDriver load-extension option: https://developer.chrome.com/docs/chromedriver/extensions
- Self-hosting and installation restrictions: https://developer.chrome.com/docs/extensions/how-to/distribute
- Windows external installation restrictions: https://developer.chrome.com/docs/extensions/how-to/distribute/install-extensions
- API reference: https://developer.chrome.com/docs/extensions/reference/api

## Chromium startup behavior

- Chrome Extensions announcement: official Chrome 137+ removes `--load-extension`: https://groups.google.com/a/chromium.org/g/chromium-extensions/c/1-g8EFx2BBY
- Chromium feature definition for branded Chrome: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/extensions/common/extension_features.cc
- Startup browser creator and `--restore-last-session`: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/browser/ui/startup/startup_browser_creator.cc
- Chrome 136 remote-debugging restrictions for default data directory: https://developer.chrome.com/blog/remote-debugging-port
- DevTools Protocol Extensions domain (`loadUnpacked`, testing-only constraints): https://chromedevtools.github.io/devtools-protocol/tot/Extensions/

For branded Google Chrome 137+, do not use `--load-extension`. Do not disable feature gate. Chromium and Chrome for Testing retain flag for development. Treat supported-browser process flags as launch evidence only, never registration or permanent installation proof.

## Chrome DevTools MCP

- Official repository and setup: https://github.com/ChromeDevTools/chrome-devtools-mcp
- Published package (current pinned version check): https://www.npmjs.com/package/chrome-devtools-mcp

Use repository README for current Node/Chrome requirements, client configuration, runtime flags, auto-connect behavior, and security warning for remote debugging.

## Firefox WebExtensions

- Cross-browser design: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Build_a_cross_browser_extension
- Chrome incompatibilities: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Chrome_incompatibilities
- MV3 background compatibility: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/background
- Gecko identity and data declarations: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/browser_specific_settings
- `web-ext` development and build: https://extensionworkshop.com/documentation/develop/getting-started-with-web-ext/
- Signing and distribution: https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/
- Selenium Firefox add-on installation/context API: https://www.selenium.dev/selenium/docs/api/py/selenium_webdriver_firefox/selenium.webdriver.firefox.webdriver.html
- Selenium Manager cache/config: https://www.selenium.dev/documentation/selenium_manager/

## Packaging and distribution

- Chrome ZIP preparation: https://developer.chrome.com/docs/webstore/prepare
- Chrome distribution restrictions: https://developer.chrome.com/docs/extensions/how-to/distribute
- Firefox packaging with `web-ext build`: https://extensionworkshop.com/documentation/develop/getting-started-with-web-ext/

## Provider plugin docs

- Codex plugins: https://developers.openai.com/plugins/build/plugins
- Codex skills: https://developers.openai.com/plugins/build/skills
- Claude Code plugins: https://code.claude.com/docs/en/plugins
- Claude Code plugin reference: https://code.claude.com/docs/en/plugins-reference
- Claude Code skills: https://code.claude.com/docs/en/skills
- Kimi Code plugins: https://www.kimi.com/code/docs/en/kimi-code-cli/customization/plugins
- Kimi Code skills: https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html
- Kimi Code MCP: https://www.kimi.com/code/docs/en/kimi-code-cli/customization/mcp.html
