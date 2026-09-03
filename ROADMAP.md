# Development Roadmap

## Phase 1: Architecture & Foundation
* [x] Research DUMB Architecture
* [x] Define Target Architecture & Deployment Modes
* [x] Initialize project structure (Python, FastAPI, Frontend framework)
* [x] Implement Core Process Supervisor (Start, Stop, Restart, Zombie reaping)
* [x] Implement Storage & Permission abstractions (PUID/PGID, Config paths, Hardlink checks)

---

## Phase 2: MVP Core Applications & Installer
* [x] Implement Generic App Installer:
  * [x] Multi-architecture detection (`x86_64`, `ARM64`)
  * [x] GitHub release scraper & binary extractor (`.tar.gz`, `.zip`, `.deb`)
  * [x] Hash / checksum validation
* [ ] Application Catalog & Manifest System:
  * Application metadata, tier definitions (Core, Recommended, Optional, Experimental)
  * Dependency graph resolution
* [ ] Port Manager & Conflict Detection:
  * Registry of active and requested application ports
  * Automatic collision detection and alternative port recommendation
* [ ] Build Application Plugins for Core Stack:
  * **Prowlarr** (Indexer manager)
  * **Sonarr** (TV automation)
  * **Radarr** (Movie automation)
  * **SABnzbd** & **NZBGet** (Usenet downloaders — user choice)
  * **qBittorrent** (BitTorrent downloader)
  * **Jellyfin** & **Plex** (Media servers — support either or both concurrently)
  * **Seerr** (Request management)
* [ ] Web Dashboard MVP:
  * Real-time service status, health checks, and process controls (Start / Stop / Restart)
  * Subprocess log inspector

---

## Phase 3: Automatic Integration Engine & First-Run Wizard
* [ ] Develop Automatic Integration Engine via APIs:
  * Configure categories (`sonarr`, `radarr`) in SABnzbd, NZBGet, and qBittorrent
  * Register download clients inside Sonarr and Radarr
  * Register Sonarr/Radarr applications in Prowlarr with automatic indexer synchronization
  * Link Seerr to Sonarr, Radarr, and Jellyfin/Plex
* [ ] Guided 12-Step First-Run Wizard:
  * Storage path setup & hardlink validation
  * PUID/PGID and permissions configuration
  * Interactive selection of download clients, *Arrs, media servers, and optimization tools
  * Real-time installation progress display
* [ ] Crash Loop Detection & Resilience:
  * Detection of repeated process failures (≥5 crashes in 10 mins)
  * Backoff scheduling & UI alert states
* [ ] Centralized Live Log Viewer:
  * WebSocket log streaming
  * Search, error filtering, and automatic credential/secret redaction

---

## Phase 4: Extended Tools, Updates & Backups
* [ ] Build Recommended & Optional Application Plugins:
  * **Bazarr** (Subtitles)
  * **Unpackerr** (Archive extraction)
  * **Recyclarr** (TRaSH guides synchronization)
  * **Profilarr** (Profile management)
  * **NeutArr** (Automation optimizer)
  * **Extended *Arr**: Lidarr, Readarr, Whisparr
  * **Maintenance Tools**: Cleanuparr, Maintainerr, Tautulli
* [ ] Safe Application Updater:
  * Pre-update snapshot of configuration and database
  * Automated post-update health check validation
  * Automatic rollback to prior version on startup failure
* [ ] Centralized Backup & Restore System:
  * Automated and manual backups of configuration, API keys, and databases
  * Retention policy management (keep last N backups)
* [ ] Secret Management & Manager Authentication:
  * Local admin account with bcrypt password hashing and JWT sessions
  * Encrypted credential storage (Fernet)
* [ ] Application Uninstallation Workflow:
  * Clean binary removal with optional configuration/data purge (safeguards against deleting media)

---

## Phase 5: Advanced Features & Packaging
* [ ] VPN Integration for qBittorrent:
  * Isolated network namespace / routing table for torrent traffic
  * WireGuard / OpenVPN runner with PrivadoVPN pre-configuration and generic provider support
  * Kill switch and DNS leak protection
* [ ] Hardware Transcoding Auto-Detection:
  * Automatic probe for Intel QuickSync, AMD, NVIDIA, and VAAPI (`/dev/dri`)
  * Dynamic configuration of Jellyfin and Plex hardware acceleration
* [ ] Advanced System Monitoring:
  * Per-core CPU, RAM, disk I/O, network throughput, and hardware temperatures
* [ ] Reverse Proxy Readiness:
  * Trusted proxy header support (Traefik, Caddy, Nginx)
* [ ] Deployment Packaging:
  * Mode A: Single all-in-one Dockerfile and docker-compose deployment
  * Mode C: Unraid Community Applications template & Synology Container Manager guide
