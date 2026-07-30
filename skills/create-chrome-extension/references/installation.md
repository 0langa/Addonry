# Installation

## Preferred hands-off path

After all implementation gates pass:

1. Confirm extension directory is durable and outside plugin caches/temp.
2. Confirm user's earlier restart authorization still applies.
3. Inspect available browser state for visible active downloads, calls, or risky work.
4. Warn that unsaved forms, calls, and downloads cannot be guaranteed; give countdown.
5. Run guarded restart helper with `-AuthorizedRestart`.
6. Confirm helper state is `startup-scoped-load-confirmed`.
7. Use Chrome tooling to verify extension loaded, record ID when available, and run representative flow.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File <loaded-skill-directory>\scripts\restart-chrome-with-extension.ps1 `
  -ExtensionPath <durable-extension-directory> `
  -AuthorizedRestart
```

Add `-ProfileDirectory "<folder>"` only when intended normal profile is known. Add `-LaunchIfClosed` only after explicit authorization to open Chrome when it was closed.

Helper closes visible matching Chrome windows with `CloseMainWindow()`, waits for clean exit, never force-kills, starts Chrome with `--load-extension=<path> --restore-last-session`, and checks process command line. Session restore is requested, not guaranteed.

## Persistence truth

`--load-extension` proves extension was requested for that browser startup. Report it as `startup-scoped-load-confirmed`, not permanent profile installation. Keep using Addonry restart helper for later sessions/updates, use an Addonry-managed launcher that preserves flags, or complete one supported **Load unpacked** UI install.

Persistent UI path:

1. Open `chrome://extensions` in intended profile.
2. Enable Developer Mode.
3. Select **Load unpacked**.
4. Choose durable directory containing `manifest.json`.
5. Confirm extension card has no errors and record ID.
6. Pin toolbar action when relevant.
7. Run representative flow.

Chrome does not make `chrome://` links clickable by design. Browser-management UI/file chooser may require user action.

## Safe automation boundary

Use guarded restart or supported host Chrome UI automation. If both cannot finish requested persistence, ask user for one `Load unpacked` directory selection. Do not:

- edit Chrome profile databases;
- write enterprise force-install registry policies;
- use private `developerPrivate` APIs;
- copy extension into Chrome installation folders;
- attach raw remote debugging port to user's normal profile.
- force-kill Chrome when graceful close fails;
- launch Chrome when it was closed unless user authorized it.

## Updating unpacked extension

Keep same durable extension path. For command-line-loaded copy, guarded Chrome restart reloads it. For persistently UI-installed copy, use extension-card reload. Manifest, service-worker, and content-script changes require extension reload; content scripts also require target-page reload. Popup/options changes usually need only reopening page. Always rerun smoke.

## Completion states

- `installed-and-verified`: loaded in intended profile and final flow passed.
- `startup-scoped-load-confirmed`: process flag confirmed and browser-level smoke still required before installed-and-verified claim.
- `staged-browser-was-closed`: Chrome was closed and Addonry correctly did not open it without authorization.
- `implementation-verified-install-pending`: all isolated tests passed; one protected user action remains.
- `blocked`: implementation or test requirement failed.

Report exact state. Never equate helper launch proof with browser-level functional verification.
