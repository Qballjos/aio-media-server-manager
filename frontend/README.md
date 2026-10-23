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
