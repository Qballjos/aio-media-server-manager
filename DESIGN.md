# AIO Media Server Manager — UI context

This records the existing interface, not a redesign proposal. Source code is authoritative when implementation and this document differ; update this context when an intentional design change lands.

## Product and mode

The dashboard helps self-hosters install, connect and operate a media appliance. Application surfaces use Impeccable's **Operate** mode: clear status, predictable controls and task completion take priority. Marketing pages and documentation have their own purposes; do not apply dashboard layouts to them automatically.

## Existing visual identity

- The app separates translucent navigation and controls from quiet content surfaces over a user-selected wallpaper. Light, dark and system themes share the same component hierarchy. Preserve saved accent, wallpaper and glass settings.
- `frontend/src/style.css` owns shared tokens and controls. `frontend/src/glass.js` adjusts opacity, blur and depth at runtime; `frontend/src/visualsProfile.js` synchronizes visual preferences with the profile API.
- Figtree with system fallbacks is the shared typeface for the web app and documentation site. `--font-mono` intentionally aliases the same font; do not introduce another typeface for code or controls as incidental polish.
- Logo-only mode uses the Logo asset. The title-and-icon header uses the Header icon asset. The saved brand title is still the logo’s accessible name and the browser title.
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

## Material and screen rules

- Use `.glass-pill` for top navigation and launcher chrome, `.glass-chrome` for side navigation, and `.glass-popover` for menus and `.glass-dialog` for modal dialogs. They share the reflection, rim and blur rules in `frontend/src/dashboard.css`. Menus use a dense fill to protect readability. Dialogs use one translucent surface with a lit rim above a theme-aware dim layer.
- Use `.material-content` for page bodies and the shared `.glass-card` content treatment for Home widgets, sign-in and the wizard. The content fill comes from the theme base and its opacity stays independent of glass tuning. Avoid applying backdrop blur to nested content sections.
- Raise active navigation with a neutral fill and shadow. Use the user accent for links and visible keyboard focus. Semantic status colours stay independent. The dock keeps its light and dark tile faces, coloured status dots and pointer-only hover magnification.
- Catalog opens on My apps when installed apps exist. Discover remains available and owns the featured carousel. Keep search global and category and status navigation in one place, including the mobile filter control.
- Settings separates its glass navigation from the form surface. Mobile uses the existing section picker. Administrator and media-account Appearance both preview the active theme, wallpaper and material using the same classes as the live UI.
- Glass presets set existing opacity, blur and depth values. Matching values select Clear, Balanced or Tinted. Other values appear as Custom. Changing glass keeps the current colour mode, wallpaper, wallpaper blur and accent. Existing profile values stay valid. Manual glass controls and custom accent colour are under Advanced.

## Controls, copy and behavior

- Reuse `.ui-input`, `.ui-btn`, `.ui-btn-primary`, `.ui-btn-ghost` and `.ui-switch`. Shared control changes belong in the shared stylesheet, not isolated scoped overrides.
- Ordinary buttons and select triggers use quiet, compact surfaces. Primary actions use denser neutral glass and a reflection. Selected controls use neutral relief, and keyboard focus keeps a distinct indicator. Align adjacent controls to the shared button height and keep touch targets at least 44px where used on mobile. Shared button styles and accent tokens live in `frontend/src/style.css`.
- Home grid panels share a 1rem inset. The greeting and search wrappers are transparent. Home search uses a single Liquid Glass surface on the field itself. The Home search field lifts slightly when focused, with no colour change or outline around the field. The wrapper stays transparent and reduced motion makes the lift immediate. Catalog search and sorting sit directly on the content panel. Grid snap and handle transitions use 240ms with the same ease-out curve; active pointer movement stays immediate and reduced-motion disables these transitions. Grid geometry and interaction handlers remain owned by `HomeGrid.vue` and `homeGrid.js`.
- For active or keyboard-focused Home widgets, use a slight lift with a neutral rim and shadow. Keep individual control focus indicators visible.
- When a fixed-size widget has more items than fit, use native scrolling as the default way to browse them. Use horizontal scrolling for Home widgets that present items side by side, including one-item-at-a-time rails. Support mouse or trackpad scrolling, touch swipes, and keyboard scrolling. Give users a visible cue when more items are available. Use scroll snap when a widget presents one full item at a time.
- Display size is a browser-local preference (85%, 90%, 100%, 110%; default 100%). It scales the fluid root font and Home-grid row heights/gaps without rewriting saved grid coordinates. Touch controls retain their minimum targets and mobile input text stays at least 16px. Theme presets and profile sync do not change it.
- Dropdowns use the shared `UiSelect.vue` trigger and glass popover, including the mobile Settings section picker. Avoid native select menus for app settings and filters. Calendar events use neutral surfaces with source/availability colors confined to the left marker and time text. Media type stays available to assistive technology without a visible Film or Series badge. Day cells use neutral borders and backgrounds. The selected day sits visually above its neighbors with a 2px lift, a neutral glass surface with blur and reflected light, a pronounced top highlight and layered soft shadows; the day number indicates today/selection.
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
