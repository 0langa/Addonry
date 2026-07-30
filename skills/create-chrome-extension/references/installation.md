# Installation

## Choose install target first

After all implementation gates pass:

1. Confirm extension directory is durable and outside plugin caches/temp.
2. Detect browser product and major version.
3. Choose persistent normal Chrome or isolated automated test browser.
4. Use browser-level inspection to verify extension ID, enabled state, source path, and representative behavior.

## Normal Google Chrome

Google removed `--load-extension` support from official branded Chrome starting in Chrome 137. For Chrome 137+, closing and relaunching normal Chrome with that flag does not load extension.

Supported persistent path:

1. Open `chrome://extensions` in intended normal profile.
2. Enable Developer Mode.
3. Select **Load unpacked**.
4. Choose durable directory containing `manifest.json`.
5. Confirm extension card has no errors and record ID.
6. Pin toolbar action when relevant.
7. Run representative flow.

Chrome does not make `chrome://` links clickable by design. Browser-management UI/file chooser may require user action.

If host tooling cannot control protected extension-management UI, report `implementation-verified-install-pending` and exact durable directory. Do not claim installed.

## Isolated automated browser

Chromium and Chrome for Testing retain command-line unpacked-extension loading. Use them for E2E and optionally as separately managed utility profiles. They do not install extension into user's normal Chrome profile.

Run guarded helper only after product/version preflight:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File <loaded-skill-directory>\scripts\restart-chrome-with-extension.ps1 `
  -ExtensionPath <durable-extension-directory> `
  -PlanOnly
```

If preflight permits path, rerun with explicit authorization parameters. Add `-ProfileDirectory "<folder>"` only when intended isolated profile is known. Add `-LaunchIfClosed` only after explicit authorization to open browser when closed.

Helper refuses Google Chrome 137+ before closing or launching anything. For supported browsers it closes matching windows with `CloseMainWindow()`, waits for clean exit, never force-kills, requests session restore, starts with `--load-extension`, and checks process command line. Session restore is requested, not guaranteed.

`load-flag-observed-browser-verification-required` means only process command line contained flag. It is not installed/loaded proof. Browser-level verification remains mandatory.

## Safe automation boundary

Use supported host Chrome UI automation for normal-profile install, or isolated-browser automation for testing. If protected UI prevents persistent install, ask user for one `Load unpacked` directory selection. Do not:

- edit Chrome profile databases;
- write enterprise force-install registry policies;
- use private `developerPrivate` APIs;
- disable `DisableLoadExtensionCommandLineSwitch` or another browser security feature;
- copy extension into Chrome installation folders;
- attach raw remote debugging port to user's normal profile.
- force-kill Chrome when graceful close fails;
- launch Chrome when it was closed unless user authorized it.

## Updating unpacked extension

Keep same durable extension path. For persistently UI-installed copy, use extension-card reload. For supported isolated command-line test profile, relaunch it. Manifest, service-worker, and content-script changes require extension reload; content scripts also require target-page reload. Popup/options changes usually need only reopening page. Always rerun smoke.

## Completion states

- `installed-and-verified`: loaded in intended profile and final flow passed.
- `blocked-branded-chrome-load-extension-unsupported`: helper detected Google Chrome 137+ and changed no browser process.
- `load-flag-observed-browser-verification-required`: supported browser process contains flag, but browser-level load is unverified.
- `staged-browser-was-closed`: Chrome was closed and Addonry correctly did not open it without authorization.
- `implementation-verified-install-pending`: all isolated tests passed; one protected user action remains.
- `blocked`: implementation or test requirement failed.

Report exact state. Never equate launch arguments or process flags with extension registration.
