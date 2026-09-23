# Frontend

Vue 3 + Vite dashboard for AIO Media Server Manager.

```bash
npm ci
npm run dev      # development server (proxies API)
npm run build    # production assets → dist/
```

FastAPI serves `frontend/dist` in production. Shared buttons, fields, and the Settings debug switch are defined in `src/style.css` (`ui-*` classes) so they match the first-run wizard.

See the repository [README](../README.md) and [docs/USAGE.md](../docs/USAGE.md).
