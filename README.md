# AIO Media Server Manager

[![CI](https://github.com/Qballjos/aio-media-server-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/Qballjos/aio-media-server-manager/actions/workflows/ci.yml)
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

- [Architecture](ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)
- [Contributing](CONTRIBUTING.md)
- [Deployment](deploy/README.md)

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
