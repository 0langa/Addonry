# Packaging

## Boundary

Packaging creates local delivery artifacts. It does not install, sign, upload, publish, or update store listing.

Run only after release-ready source validation:

```powershell
python <loaded-skill-directory>\scripts\package_extension.py `
  <extension-path> `
  --target both
```

Use `--target chrome`, `--target firefox`, or project-configured `auto`. Existing artifacts block overwrite unless user requested regeneration and `--overwrite` is supplied.

## Output

Default output directory: `<extension-path>\artifacts`.

Package names:

```text
<slug>-<version>-chrome.zip
<slug>-<version>-firefox.zip
```

`.addonry/package-report.json` records source digest, browser targets, paths, byte sizes, file counts, and SHA-256 values. `signed` and `published` remain false.

## Content rules

- `manifest.json` must be archive root entry.
- Chrome package removes Firefox-only manifest metadata and background scripts.
- Firefox package removes Chrome-only service worker, fixed key, and minimum Chrome version.
- Exclude `.addonry`, tests, source-control state, dependencies, caches, prior artifacts, build output, docs, and local environment files.
- Refuse secret-like filenames, private keys, symlinks, path escapes, and `KEEP`-protected output.
- Sort files and normalize ZIP timestamps/permissions for byte-identical rebuilds.

## Distribution boundary

Chrome Web Store accepts ZIP and signs delivered Chrome package. Normal Firefox Release/Beta requires Mozilla-signed XPI. Store credentials, signing, declarations, screenshots, listing changes, and publication need separate explicit request and fresh authorization.
