# Contributing

Thank you for contributing to AIO Media Server Manager.

## Development setup

- Python 3.11 or newer
- [Poetry](https://python-poetry.org/)
- Node.js 22 (dashboard)

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
cp .env.example .env
poetry install
cd frontend && npm ci && cd ..
```

API:

```bash
poetry run python main.py
```

Dashboard with Vite (optional; proxies API requests):

```bash
cd frontend && npm run dev
```

## Checks before a pull request

```bash
poetry run pytest
poetry run ruff check core api applications tests
cd frontend && npm run build
```

Optional: `pre-commit install` for Ruff and basic file checks on commit.

## Project rules

- One manager, many **managed processes**. Do not add per-application Docker Compose services.
- No Debrid functionality (Real-Debrid, Zurg, Riven, mounts, caches).
- The catalog stays **17 applications**. VueTorrent is a qBittorrent WebUI option, not a catalog app.
- Application-specific behaviour lives in `applications/` plugins, not in `core/`.
- Do not log or return secrets in API responses.
- Never delete media libraries in uninstall or backup paths.
- Shared form controls live in `frontend/src/style.css` (`.ui-input`, `.ui-btn`, `.ui-btn-primary`, `.ui-btn-ghost`, `.ui-switch`). Match the first-run wizard; do not restyle inputs only in a scoped SFC.
- When you add env vars, ports, or Settings behaviour, update `.env.example`, Compose/templates (`docker-compose.yml`, `deploy/synology/`, `deploy/unraid.xml`), and `docs/` / `deploy/*.md` in the same change.

Report vulnerabilities through [GitHub private advisories](https://github.com/Qballjos/aio-media-server-manager/security/advisories/new), not public issues.

## Pull requests

- Keep the change focused and explain *why* in the PR body.
- Add or update tests when behaviour changes.
- Squash merge is preferred.
