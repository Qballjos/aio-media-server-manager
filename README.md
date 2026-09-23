# AIO Media Server Manager

[![CI](https://github.com/Qballjos/aio-media-server-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/Qballjos/aio-media-server-manager/actions/workflows/ci.yml)
[![GHCR](https://img.shields.io/badge/GHCR-aio--media--server--manager-blue)](https://github.com/Qballjos/aio-media-server-manager/pkgs/container/aio-media-server-manager)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A self-hosted, all-in-one appliance that manages a complete media stack (Usenet/Torrents, *Arr ecosystem, media servers) without a separate Docker container for each application.

Inspired by the process supervision and declarative concepts of DUMB, with **zero Debrid functionality**, built for conventional Usenet and BitTorrent automation.

---

## Key Features

- **Single container / appliance model:** managed applications run as supervised processes in one environment.
- **Async process supervisor:** restart backoff, crash-loop detection, zombie reaping, graceful shutdown.
- **Storage and permissions:** parameterized paths, hardlink checks, `PUID`/`PGID` enforcement.
- **Application plugins:** install, health, lifecycle, and catalog metadata per app.
- **Automatic integration:** wires download clients, indexers, and request tools.
- **Updates, backups, and uninstall:** snapshot/rollback updates, config backups, media-safe uninstall.
- **Management UI:** Vue 3 + Vite dashboard backed by FastAPI.

---

## Application stack

- **Downloaders:** SABnzbd, NZBGet, qBittorrent
- **Automation and indexers:** Prowlarr, Sonarr, Radarr, Lidarr, Readarr, Whisparr
- **Subtitles and extraction:** Bazarr, Unpackerr
- **Optimization:** Recyclarr, Profilarr, NeutArr
- **Media servers:** Jellyfin, Plex (can share the same libraries)
- **Requests:** Seerr

---

## Documentation

- [Installation](docs/INSTALL.md)
- [Docker](deploy/DOCKER.md) · [Linux / LXC](deploy/LINUX.md) · [Unraid](deploy/UNRAID.md) · [Synology](deploy/SYNOLOGY.md) · [TrueNAS](deploy/TRUENAS.md)
- [Architecture](ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)
- [Contributing](CONTRIBUTING.md)

---

## Install (Docker)

Over SSH, create the bind-mount folders first (see [docs/INSTALL.md](docs/INSTALL.md)), then:

```bash
sudo mkdir -p /opt/aio-media-manager/{config,downloads,media}
docker pull ghcr.io/qballjos/aio-media-server-manager:latest
docker compose up -d
```

Or from this repo: `docker compose pull && docker compose up -d`. Then open `http://localhost:8080`.

Image tags: `latest` (main), `sha-<git>`, and semver when you push `v*` tags. See [docs/INSTALL.md](docs/INSTALL.md) for Unraid, Synology, TrueNAS, and native Linux.

---

## Quick start (development)

### Prerequisites

- Python 3.11+
- Poetry
- Node.js 18+ (dashboard)

### Setup

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
cp .env.example .env
poetry install
cd frontend && npm ci && npm run build && cd ..
poetry run python main.py
```

API: `http://localhost:8080`  
OpenAPI: `http://localhost:8080/docs`

For a live dashboard during UI work, run `npm run dev` in `frontend/` as well.

---

## License

[MIT](LICENSE)
