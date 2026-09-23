# Contributing

Thanks for helping improve AIO Media Server Manager.

## Development setup

- Python 3.11+
- [Poetry](https://python-poetry.org/)
- Node.js 18+ (frontend)

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
cp .env.example .env
poetry install
cd frontend && npm ci && cd ..
```

Run the API:

```bash
poetry run python main.py
```

Run the dashboard (optional, Vite proxy to the API):

```bash
cd frontend && npm run dev
```

## Checks before opening a PR

```bash
poetry run pytest
poetry run ruff check core api applications tests
cd frontend && npm run build
```

Optional: `pre-commit install` to run Ruff and basic file checks on commit.

## Project rules

- One AIO manager, many **managed processes** — do not add per-application Docker Compose services.
- No Debrid functionality (Real-Debrid, Zurg, Riven, mounts, caches).
- Application-specific logic belongs in `applications/` plugins, not in `core/`.
- Do not log or return secrets in API responses.
- Never delete media libraries in uninstall/backup paths.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [ROADMAP.md](ROADMAP.md) for the intended design.

## Pull requests

- Keep changes focused and describe *why* in the PR body.
- Add or update tests when you change behaviour.
- Squash merge is preferred.
