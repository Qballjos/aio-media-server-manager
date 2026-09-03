# AIO Media Server Manager

A self-hosted, all-in-one appliance designed to manage a complete media stack (Usenet/Torrents, *Arr ecosystem, Media Servers) without relying on a separate Docker container for each individual application.

Inspired by the process supervision and declarative concepts of DUMB, with **zero Debrid functionality** and built specifically for conventional Usenet and BitTorrent automation.

---

## Key Features

- **Single Container / Appliance Model:** All managed applications run as monitored subprocesses within a single environment rather than managing a web of separate containers.
- **Async Process Supervisor:** Python-based process lifecycle management with automatic restart backoff, crash-loop detection, zombie process reaping, and graceful shutdown.
- **Storage & Permission Abstraction:** Parameterized storage layout, cross-filesystem hardlink verification (essential for instant atomic file moves), filesystem type detection, and idempotent `PUID`/`PGID` permission enforcement.
- **Application Plugin Architecture:** Modular plugin manifests for each application covering installation, execution, health polling, and integration.
- **Automated Integration Engine:** Auto-wires categories, indexers, download clients, and media servers across the entire stack.
- **Torrent VPN Isolation:** Dedicated WireGuard/OpenVPN tunnel and kill switch for BitTorrent traffic (PrivadoVPN pre-configured, generic providers supported).
- **Modern Management UI:** Fast dashboard built with Vue 3 + Vite, backed by FastAPI.

---

## Planned Application Stack

- **Downloaders:** SABnzbd, NZBGet, qBittorrent
- **Automation & Indexers:** Prowlarr, Sonarr, Radarr, Lidarr, Readarr
- **Subtitles & Extraction:** Bazarr, Unpackerr
- **Optimization:** Recyclarr, Profilarr, NeutArr
- **Media Servers:** Jellyfin, Plex (can run concurrently sharing media libraries)
- **Requests:** Seerr

---

## Documentation

- [Architecture Blueprint](ARCHITECTURE.md)
- [Development Roadmap](ROADMAP.md)

---

## Quick Start (Development)

### Prerequisites

- Python 3.11+
- Poetry
- Node.js 18+ (for frontend dashboard)

### Setup & Run

1. Clone the repository:
   ```bash
   git clone https://github.com/Qballjos/aio-media-server-manager.git
   cd aio-media-server-manager
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your desired paths and PUID/PGID
   ```

3. Install dependencies:
   ```bash
   poetry install
   ```

4. Start the backend:
   ```bash
   poetry run python main.py
   ```
   The API will be available at `http://localhost:8080` (API Docs at `/docs`).

---

## License

MIT License
