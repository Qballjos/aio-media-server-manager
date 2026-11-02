# Frontend

Vue 3 + Vite dashboard for AIO Media Server Manager.

The default way to test the appliance (wizard, catalog installs, Open UI) is the Linux Docker image from the repository root:

```bash
./scripts/test-env.sh up
```

Then open **http://127.0.0.1:8080**. FastAPI serves `frontend/dist` from that image.

Use Vite only when you want live reload of the dashboard. The container must already be on port 8080. Do not start a host Poetry API for catalog testing.

```bash
npm ci
npm run dev      # http://127.0.0.1:5173 — proxies /api and /health to the container
npm run build    # production assets → dist/ (also built inside the Docker image)
```

Routes are hash-based so refresh keeps the screen: `#/home`, `#/catalog`, and `#/settings/` plus `account`, `visuals`, `system`, `updates`, `backups`, `network`, `notifications`, `usenet`, `homepage`, or `diagnostics`. Catalog search and filters live in the query string.

| Module | Role |
|--------|------|
| `App.vue` | Shell: header, auth gate, polling |
| `HomepagePanel.vue` | Home grid |
| `homeGrid.js` | Widget sizes and the phone, tablet, and desktop layouts |
| `CatalogView.vue` | Catalog grid |
| `WizardPanel.vue` | First-run wizard |
| `SettingsPanel.vue` | Settings sections listed above |
| `themes.js` / `theme.js` | Wallpaper, glass, and dark / light / system preference |
| `branding.js` | Title, accent color, and custom image URLs from `/api/branding` |
| `api.js` | Shared fetch helper (CSRF, bearer token, JSON vs binary, FastAPI errors) |
| `style.css` | Shared `ui-*` controls and theme CSS variables |

See the repository [README](../README.md) and [docs/USAGE.md](../docs/USAGE.md).

## Browser journeys and component boundaries

`npm test` runs Node behavior tests; `npm run test:e2e` runs desktop and mobile
Chromium journeys. Build first and install the pinned Chromium with
`npx --no-install playwright install chromium`. See [verification](../docs/testing.md)
for Python setup, isolation, artifacts and what the fake service adapters cover.

Settings delegates notification forms to `settings/NotificationSettings.vue` and
backup forms to `settings/BackupSettings.vue`. `composables/useBackups.js` owns the
backup job polling, so switching sections does not cancel a running operation.
`composables/useHomeCalendar.js` owns calendar state, grouping and navigation;
Home keeps that state alive as the layout changes. Scoped page styles live in
`settingsPanel.css` and `homepagePanel.css`; settings form/backup styles sit with
the corresponding section components.

## App-wide styling and typography

`src/main.js` loads **style.css first, then dashboard.css**, once for the entire
application. `style.css` owns design tokens (colors, sizes, spacing and typefaces)
and shared `ui-*` controls. `dashboard.css` styles the shell, header, catalog and
shared modal surfaces. Vue components and the extracted page stylesheets add
scoped rules for their own screen; those rules should reuse the shared tokens.

All application text uses `--font-sans`: **Figtree**, with a common system-font
fallback if the web font is unavailable. Form controls and code elements inherit
that family. `--font-mono` and `.font-mono` are compatibility names and now use
the same family. Define typography centrally rather than adding a new font to an
individual page. Figtree is requested by `index.html`; font sizes and weights
can still differ by role.

The header uses equal flexible side columns around the three page links, so
their center is the center of the full header, independently of the logo,
updates and account controls. The Home layout button is in the right-hand tools
group. At widths up to 1100 px, the page links occupy a separate centered row.
The header is in normal document flow and scrolls away; it is not sticky.

Theme, accent and glass preferences update shared CSS variables through
`theme.js`, `branding.js` and `glass.js`. They change appearance without selecting
a different typeface. Screen-specific styles belong with their component; shared
controls and typography belong in the app-wide stylesheets.
