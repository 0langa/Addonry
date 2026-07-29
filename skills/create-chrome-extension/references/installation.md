# Installation

## Preferred path

After all implementation gates pass:

1. Open `chrome://extensions` in user's intended Chrome profile.
2. Enable Developer Mode.
3. Select **Load unpacked**.
4. Choose generated extension directory containing `manifest.json`.
5. Confirm extension card shows no errors and record ID.
6. Pin extension if it has toolbar action.
7. Run representative flow in installed copy.

Chrome does not make `chrome://` links clickable by design. Browser-management UI/file chooser may require user action even when page testing is automated.

## Safe automation boundary

Try supported host Chrome UI automation first. If blocked, ask user for one `Load unpacked` directory selection. Do not:

- edit Chrome profile databases;
- write enterprise force-install registry policies;
- use private `developerPrivate` APIs;
- copy extension into Chrome installation folders;
- attach raw remote debugging port to user's normal profile.

## Updating unpacked extension

Manifest, service worker, and content script changes require extension reload; content scripts also require target-page reload. Popup/options page changes usually need only reopening page. Use reload button on extension card, then rerun smoke.

## Completion states

- `installed-and-verified`: loaded in intended profile and final flow passed.
- `implementation-verified-install-pending`: all isolated tests passed; one protected user action remains.
- `blocked`: implementation or test requirement failed.

Report exact state. Restart Chrome only when evidence requires it; unpacked install normally does not.
