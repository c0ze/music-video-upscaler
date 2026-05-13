# Web Theme Toggle — Design Spec

- **Date**: 2026-05-11
- **Status**: Draft (pending user review)
- **Scope**: Add a light mode with a persistent theme toggle to the existing local web UI.

## Goal

Add a simple client-side theme toggle so the web UI supports both dark and light mode, remembers the user's last explicit choice, and uses the host system theme on first visit before any preference has been saved.

## Non-goals

- No server-side theme state.
- No per-panel or per-component theme controls.
- No third "auto" mode in the UI for v1. System theme is only the first-load default.
- No redesign of layout, information architecture, or job behavior.

## Chosen approach

Use a single stylesheet with CSS custom properties and switch themes by setting a `data-theme` attribute on the document root.

### Why this approach

The current UI already uses a token-style palette in `web/static/style.css`. Extending that pattern is the smallest and cleanest change:

- one stylesheet
- minimal DOM changes
- no server/API changes
- easy persistence via `localStorage`

Alternative approaches such as body classes or separate stylesheets add duplication without improving behavior.

## Behavior

### Initial load

On page load:

1. Read `localStorage` for a saved theme preference.
2. If a saved value exists (`light` or `dark`), apply it.
3. If no saved value exists, resolve the initial theme from `window.matchMedia("(prefers-color-scheme: dark)")`.

This means the first visit follows system theme. After the user toggles once, the saved explicit preference wins on future visits.

### Toggle behavior

- The UI exposes a single toggle control in the page header.
- Clicking it switches between explicit `light` and `dark`.
- The selected explicit value is written to `localStorage`.
- The page updates immediately without reload.

### Persistence

- Storage key should be specific to the app, e.g. `music-video-upscaler.theme`.
- Allowed values: `light`, `dark`.
- Invalid stored values are ignored and treated as "no saved preference".

## UI design

### Placement

Add the toggle to the top row near the page title so it is globally visible and does not interfere with job-specific controls.

### Control shape

Use a labeled button-style control, for example:

- label: `Theme`
- button text reflects the current resolved theme, such as `Light` or `Dark`

The control must remain keyboard accessible and visually obvious in both themes.

## Styling changes

Extend the existing token set so both themes fully cover:

- page background
- panel background
- borders
- primary text
- muted text
- form controls
- button surfaces
- progress track
- preview card surfaces
- log background
- health/error banner surface

The accent, success, and danger colors may remain close to the current palette as long as contrast remains readable in both modes.

## Accessibility and UX constraints

- Theme changes must not require page reload.
- The toggle must be keyboard reachable and use a clear accessible label.
- Contrast should remain readable in both themes for headings, body text, buttons, status pills, and progress text.
- No animation is required for the theme switch.

## Testing

Add or update lightweight static-surface coverage to verify:

1. `index.html` contains the theme control.
2. `app.js` contains theme bootstrap and persistence logic.
3. Existing static asset serving tests continue to pass.

Manual verification should confirm:

1. first load follows system theme when no saved value exists
2. toggling persists across reloads
3. both light and dark remain readable across the full page

## Implementation notes

- This is a frontend-only change in `web/static/index.html`, `web/static/style.css`, and `web/static/app.js`.
- No API routes, backend state, or job orchestration logic should change.
