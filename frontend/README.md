# Frontend

Vue 3 + Vite dashboard for AIO Media Server Manager.

The default way to test the appliance (wizard, catalog installs, Open UI) is the Linux Docker image: `./scripts/test-env.sh up` from the repo root, then **http://127.0.0.1:8080**. FastAPI serves `frontend/dist` from that image.

Use Vite only when you want live reload of the dashboard. The container must already be on port 8080 (`./scripts/test-env.sh up`). Do not start a host `poetry` API for catalog testing.

```bash
npm ci
npm run dev      # http://127.0.0.1:5173 — proxies /api and /health to the container
npm run build    # production assets → dist/ (also built inside the Docker image)
```

FastAPI serves `frontend/dist` in production. Hash routes (`#/home`, `#/catalog`, `#/settings/backups`) keep the screen after refresh; catalog search and filters live in the query string. `App.vue` is the shell (header, auth gate, polling). `CatalogView.vue` is the catalog grid, `HomepagePanel.vue` is the Home Dashboard, and `SettingsPanel.vue` is appliance settings. `src/api.js` is the shared fetch helper (CSRF, bearer token, JSON vs binary uploads, FastAPI error bodies). Shared buttons, fields, and switches live in `src/style.css` (`ui-*` classes) so they match the first-run wizard.

See the repository [README](../README.md) and [docs/USAGE.md](../docs/USAGE.md).
