# AIO Media Server Manager — UI context

This records the existing interface, not a redesign proposal. Source code is authoritative when implementation and this document differ; update this context when an intentional design change lands.

## Product and mode

The dashboard helps self-hosters install, connect and operate a media appliance. Application surfaces use Impeccable's **Operate** mode: clear status, predictable controls and task completion take priority. Marketing pages and documentation have their own purposes; do not apply dashboard layouts to them automatically.

## Existing visual identity

- Liquid-glass panels over an optional wallpaper, with light, dark and system themes. Preserve user-selected accent, wallpaper and glass settings.
- `frontend/src/style.css` owns shared tokens and controls. `frontend/src/glass.js` adjusts opacity, blur and depth at runtime; `frontend/src/visualsProfile.js` synchronizes visual preferences with the profile API.
- Figtree with system fallbacks is the shared typeface. `--font-mono` intentionally aliases the same font; do not introduce another typeface for code or controls as incidental polish.
- Home, Catalog and Settings are the main navigation destinations. Preserve the centered header navigation and existing responsive behavior; use the first-run wizard as the form-control reference.

## Token reference

Values below describe current defaults, not replacements for CSS variables or runtime preferences.

| Purpose | Existing source/default |
| --- | --- |
| Dark / light base | `--bg-base`: `#090d1f` / `#e6eeff` |
| Dark / light primary | `--color-primary`: `#5aa2ff` / `#0a6cff` |
| Text hierarchy | `--text-main`, `--text-muted`, `--text-dim`, `--text-heading` |
| Status | `--color-success`, `--color-warning`, `--color-danger`, `--color-info` and their background/foreground tokens |
| Type scale | `--text-kicker` through `--text-display`, in rem |
| Glass / tile / control radius | `--radius-glass`: 26px; `--radius-tile`: 18px; `--radius-control`: 999px |
| Glass defaults | Alpha 0.5, blur 28px, depth 1; wallpaper blur 12px in `glass.js` |

Reuse tokens rather than hardcoding these values in components. Check both themes and contrast over actual wallpapers; no blanket accessibility compliance is claimed here.

## Controls, copy and behavior

- Reuse `.ui-input`, `.ui-btn`, `.ui-btn-primary`, `.ui-btn-ghost` and `.ui-switch`. Shared control changes belong in the shared stylesheet, not isolated scoped overrides.
- Home grid panels share a 1rem inset and the existing glass surface, including greeting and search. Grid snap and handle transitions use 240ms with the same ease-out curve; active pointer movement stays immediate and reduced-motion disables these transitions. Grid geometry and interaction handlers remain owned by `HomeGrid.vue` and `homeGrid.js`.
- Display size is a browser-local preference (85%, 90%, 100%, 110%; default 100%). It scales the fluid root font and Home-grid row heights/gaps without rewriting saved grid coordinates. Touch controls retain their minimum targets and mobile input text stays at least 16px. Theme presets and profile sync do not change it.
- Follow Vue 3 and existing component/composable conventions. This is not a React/Tailwind project.
- Preserve vue-i18n usage. `frontend/src/i18n/index.js` and `frontend/src/i18n/locales/table.js` define the existing English, Dutch, German and French localization approach.
- Keep labels task-focused and errors actionable. Explain technical details only when users need them to choose or recover.
- Represent loading, empty, success and failure states honestly. Never show success before the operation succeeds or reveal secrets in diagnostics.
- Use semantic controls, accessible names, visible keyboard focus and status cues beyond color. Preserve keyboard operation and avoid unnecessary motion; verify behavior rather than assuming it.

## Verification and scope

- Ordinary refinement preserves product identity, behavior and content outside the request. A replacement visual direction requires an explicit redesign scope.
- Inspect changed surfaces on desktop and mobile, in relevant themes, with a bounded review/fix/confirmation pass. Check overflow and long translated labels.
- Follow `docs/testing.md` for unit tests, build and Playwright journeys. Existing header checks cover widths from 320px to 1440px; passing geometry checks does not prove remote-font delivery or all accessibility requirements.
- `docs/screenshots/light/` and `docs/screenshots/dark/` are reference captures. Check freshness against current components and tokens before treating them as definitive.
