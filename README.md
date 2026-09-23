# AIO Media Server Manager

<p align="center">
  <img src="logo-aio-media-manager.png" alt="AIO Media Server Manager" width="160" />
</p>

<p align="center">
  <strong>One appliance. Many processes. No per-app Docker stack. No Debrid.</strong>
</p>

[![CI](https://github.com/Qballjos/aio-media-server-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/Qballjos/aio-media-server-manager/actions/workflows/ci.yml)
[![GHCR](https://img.shields.io/badge/GHCR-aio--media--server--manager-blue)](https://github.com/Qballjos/aio-media-server-manager/pkgs/container/aio-media-server-manager)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A self-hosted manager for a complete Usenet + BitTorrent media stack. You run **one container** (or one systemd service). It installs, configures, supervises, and wires Sonarr, download clients, Jellyfin/Plex, and the rest as processes inside that appliance.

Inspired by DUMB’s process-supervision model, with **zero Debrid functionality**.

---

## Screenshots

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="Dashboard with application icons, ports, and install actions" width="900" />
</p>

<p align="center"><em>Dashboard — catalog, ports, lifecycle, and app icons in one UI.</em></p>

<p align="center">
  <img src="docs/screenshots/login.png" alt="Sign-in screen with AIO Media Manager logo" width="900" />
</p>

<p align="center"><em>First-run setup and sign-in use the same branded manager UI.</em></p>

---

## Key features

- **Single appliance:** no Compose file per *Arr app. Docker is only the wrapper.
- **Process supervisor:** start/stop/restart, crash-loop detection, log tails, graceful shutdown.
- **Catalog installers:** GitHub releases, official binaries (Jellyfin, Plex), and PyPI apps.
- **Automatic wiring:** indexers, download clients, and Seerr hooked up after install.
- **Storage model:** `config`, `downloads`, and `media` with `PUID`/`PGID` and hardlink checks.
- **VPN for torrents only:** qBittorrent in a netns; Usenet stays off the VPN.
- **Hardware transcoding:** VAAPI / QSV / NVIDIA when the host exposes devices.
- **Cloudflare Tunnel:** optional remotely-managed `cloudflared` to the manager UI.
- **Management UI:** Vue 3 dashboard (app logos, health, updates, backups, uninstall).

---

## Application stack

| Role | Apps |
|------|------|
| Indexers | Prowlarr |
| Automation | Sonarr, Radarr, Lidarr, Readarr, Whisparr, Mylar3 |
| Downloaders | SABnzbd, NZBGet, qBittorrent |
| Media | Jellyfin, Plex (can share the same libraries) |
| Requests | Seerr |
| Subtitles / extract | Bazarr, Unpackerr |
| Profiles / cleanup | Recyclarr, Profilarr, NeutArr, Cleanuparr |
| Library / stats | Maintainerr, Kometa, Tautulli, Autobrr, Huntarr |

---

## Documentation

- [Installation](docs/INSTALL.md)
- [Docker](deploy/DOCKER.md) · [Linux / LXC](deploy/LINUX.md) · [Unraid](deploy/UNRAID.md) · [Synology](deploy/SYNOLOGY.md) · [TrueNAS](deploy/TRUENAS.md) · [Cloudflare Tunnel](deploy/CLOUDFLARE.md)
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

Image tags: `latest` (main), `sha-<git>`, and semver when you push `v*` tags. Multi-arch: `linux/amd64` and `linux/arm64`.

---

## Quick start (development)

### Prerequisites

- Python 3.11+
- Poetry
- Node.js 22 (dashboard)

### Setup

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
cp .env.example .env
poetry install
cd frontend && npm ci && npm run build && cd ..
poetry run python main.py
```

Manager UI: `http://localhost:8080`  
OpenAPI: `http://localhost:8080/docs`

For a live dashboard during UI work, run `npm run dev` in `frontend/` as well.

---

## License

[MIT](LICENSE)
