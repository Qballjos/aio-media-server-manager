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
- No Debrid functionality or cloud remotes.
- The catalog stays **16 applications**. VueTorrent is a qBittorrent WebUI option, not a catalog app. Hide an entry from the catalog and wizard when the host architecture is unsupported; do not install a default “wrong-arch” build.
- The appliance image must not install Flaresolverr’s Chromium/Xvfb stack on `linux/arm64`. Shared runtimes (Python 3.13, Node 22, JRE, MariaDB, ffmpeg) stay on both published architectures.
- Application-specific behaviour lives in `applications/` plugins, not in `core/`.
- Do not log or return secrets in API responses.
- Never delete media libraries in uninstall or backup paths.
- Shared form controls live in `frontend/src/style.css` (`.ui-input`, `.ui-btn`, `.ui-btn-primary`, `.ui-btn-ghost`, `.ui-switch`). Match the first-run wizard; do not restyle inputs only in a scoped SFC.
- When you add env vars, ports, or Settings behaviour, update `.env.example`, Compose/templates (`docker-compose.yml`, `compose.test.yml`, `compose.gpu.yml`, `deploy/synology/`, `deploy/unraid.xml`), and `docs/` / `deploy/*.md` in the same change.

## Updates and runtime pins

Agents and Dependabot often treat “not on the newest version” as a bug. In this project it is often intentional:

**Catalog apps** (Sonarr, Radarr, Seerr, …) are updated by the operator (dashboard **Update**) or by Settings update schedules. Those schedules default to **Off**. AIO does not silently bump child apps in CI or on image rebuild. Seeing an older installed app version is expected until someone applies an update.

**Pinned runtimes in the appliance image / CI:**

| Runtime | Pin | Reason |
|---|---|---|
| Node (frontend build + Seerr) | **22** LTS | Seerr declares `engines.node: ^22.19.0`. The image copies Node from `node:22-bookworm-slim`. Do **not** merge Dependabot bumps to Node 24/25/26 until Seerr’s engines allow it (Node 26 also broke `corepack` in our Dockerfile). |
| Manager Python | **3.14** | Appliance API process |
| Child Python | **3.13** | Bazarr / SABnzbd / Shelfmark (`AMM_CHILD_PYTHON` / `/opt/python3.13`) |
| JRE | **25** | Grimmory |

**Frontend majors:** treat `vue-router` 5.x as a deliberate migration, not an auto-merge.

**Out of catalog (do not add without an explicit product decision):** analytics frontends, unpack helpers, library automation extras, and tracker automation tools outside the 16 catalog apps. A local-only trailer manager may be considered later (never a Docker child container).

Report vulnerabilities through [GitHub private advisories](https://github.com/Qballjos/aio-media-server-manager/security/advisories/new), not public issues.

## Pull requests

- Keep the change focused and explain *why* in the PR body.
- Add or update tests when behaviour changes.
- Squash merge is preferred.
