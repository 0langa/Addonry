# Intake and Scope

## Goal

Convert user's idea into a testable acceptance contract before implementation. Ask about product behavior, not implementation trivia.

## Intake sequence

1. Restate utility in one sentence.
2. Inspect available browser/tool state and any supplied target page.
3. Identify missing observable decisions.
4. Group questions into one batch where possible.
5. State defaults agent will choose.
6. Confirm acceptance contract before sensitive or destructive behavior.

## Question bank

Use only relevant questions:

- What exact action starts workflow?
- Which desktop browsers: Chrome, Firefox, or both?
- Which websites or URL patterns are in scope?
- Should it affect current tab, current window, or every window?
- What data should be collected, transformed, copied, downloaded, or stored?
- How should duplicates, missing values, pagination, frames, or dynamic content behave?
- What output format and destination are expected?
- Should data persist between browser sessions?
- Does it need logged-in state, cookies, downloads, clipboard, history, or broad tab access?
- What visible feedback confirms success or failure?
- Which representative example can become E2E fixture?
- Is target persistent normal browser profile or isolated automated test browser?
- For normal Chrome, can user perform one protected **Load unpacked** directory selection if host automation cannot?
- For a supported isolated browser only: may Addonry gracefully relaunch it, and may it launch when currently closed?

## Default product choices

- Personal local use only.
- No Web Store or GitHub publication.
- Generated in durable personal storage outside provider/plugin cache.
- Preferred Windows root: `%USERPROFILE%\source\repos\browser-extensions`; fallback: `%USERPROFILE%\browser-extensions`.
- Desktop Chrome and Firefox unless user chooses one target.
- Persistent normal Chrome is preferred; Chrome 137+ may require one user **Load unpacked** action.
- Toolbar action for on-demand utilities.
- Current tab only unless user names broader scope.
- Preserve order and avoid duplicates for extracted items.
- Local storage only; no telemetry or remote backend.
- Clear success/error feedback.

## Acceptance contract template

```text
Trigger:
Scope:
Normal behavior:
Edge behavior:
Output/storage:
Sensitive access:
Install target:
Browser targets:
Package requested:
Protected install action:
Done when:
```

## Complexity calibration

Low: one API, one action, limited UI, no authentication. Build directly after brief contract.

Medium: target-page DOM, multiple contexts, downloads, optional permissions, or sensitive import/export. Inspect first and add tailored fixtures/E2E.

High: credential vaults, traffic interception across all sites, adversarial blocking, cryptographic security boundary, large synchronization backend, or store publication. Downscope to narrow personal helper or decline. Local packaging is not store publication.
