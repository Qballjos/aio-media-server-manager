# Contributing

Thank you for contributing to AIO Media Server Manager.

## Run the appliance (default)

Docker is the default way to test the wizard, catalog installs, Open UI, and Auto-Wire. The image is Linux (`linux/amd64` or `linux/arm64`). macOS and Windows hosts only provide Docker Desktop; they are not a native install target.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
./scripts/test-env.sh up
```

Open **http://127.0.0.1:8080**. Volumes live in `.docker-test/` (gitignored). Logs: `./scripts/test-env.sh logs`. Stop: `./scripts/test-env.sh down`. Stopping does not delete `.docker-test/`; remove that directory to wipe test data.

Optional live dashboard (proxies `/api` and `/health` to the container on port 8080):

```bash
cd frontend && npm ci && npm run dev
```

Then use **http://127.0.0.1:5173**, not a host `poetry run` API.

If you need Intel/AMD transcoding on a Linux host that has `/dev/dri`, add `compose.gpu.yml` to a production compose command (see [deploy/DOCKER.md](deploy/DOCKER.md)). The test script does not map `/dev/dri`.

## Unit tests and lint (host)

Python 3.11+ with [Poetry](https://python-poetry.org/), and Node.js 22 for the dashboard build:

```bash
poetry install
cd frontend && npm ci && cd ..
poetry run pytest
poetry run ruff check core api applications tests
cd frontend && npm run build
```

Optional: `pre-commit install` for Ruff and basic file checks on commit.

Do not use `poetry run python main.py` on macOS or Windows to exercise catalog installs. That path is for native Linux / LXC only ([deploy/LINUX.md](deploy/LINUX.md)).

## Project rules

- One manager, many **managed processes**. Do not add per-application Docker Compose services.
- No Debrid functionality (Real-Debrid, Zurg, Riven, mounts, caches).
- The catalog stays **17 applications**. VueTorrent is a qBittorrent WebUI option, not a catalog app. Hide an entry from the catalog and wizard when the host architecture is unsupported; do not install a default “wrong-arch” build.
- The appliance image must not install Flaresolverr’s Chromium/Xvfb stack on `linux/arm64`. Shared runtimes (Python 3.13, Node 22, JRE, MariaDB, ffmpeg) stay on both published architectures.
- Application-specific behaviour lives in `applications/` plugins, not in `core/`.
- Do not log or return secrets in API responses.
- Never delete media libraries in uninstall or backup paths.
- Shared form controls live in `frontend/src/style.css` (`.ui-input`, `.ui-btn`, `.ui-btn-primary`, `.ui-btn-ghost`, `.ui-switch`). Match the first-run wizard; do not restyle inputs only in a scoped SFC.
- When you add env vars, ports, or Settings behaviour, update `.env.example`, Compose/templates (`docker-compose.yml`, `compose.test.yml`, `compose.gpu.yml`, `deploy/synology/`, `deploy/unraid.xml`), and `docs/` / `deploy/*.md` in the same change.

Report vulnerabilities through [GitHub private advisories](https://github.com/Qballjos/aio-media-server-manager/security/advisories/new), not public issues.

## Pull requests

- Keep the change focused and explain *why* in the PR body.
- Add or update tests when behaviour changes.
- Squash merge is preferred.
