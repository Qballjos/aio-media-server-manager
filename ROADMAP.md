# Development Roadmap

Aligned with [PROMPT.md](PROMPT.md). Phases follow the methodology defined in §37.

---

## Phase 1: Architecture & Foundation

* [x] Research DUMB Architecture
* [x] Define Target Architecture & Deployment Modes
* [x] Initialize project structure (Python, FastAPI, Frontend framework)
* [x] Implement Core Process Supervisor (Start, Stop, Restart, Zombie reaping)
* [x] Implement Storage & Permission abstractions (PUID/PGID, Config paths, Hardlink checks)

---

## Phase 2: MVP Core Applications & Installer

Per PROMPT.md §37 Phase 3 — MVP stack only: manager, dashboard, catalog, process manager, installer, storage configuration, and the seven core applications below.

* [x] Implement Generic App Installer:
  * [x] Multi-architecture detection (`x86_64`, `ARM64`, `ARMv7` where upstream supports it)
  * [x] GitHub release scraper & binary extractor (`.tar.gz`, `.zip`, `.deb`)
  * [x] Hash / checksum validation
* [x] Extend installer for additional upstream formats (Python apps, Node apps, official `.deb` packages)
* [x] Application Catalog & Manifest System:
  * [x] Application metadata, tier definitions (Core, Recommended, Optional, Experimental)
  * [x] Dependency graph resolution
  * [x] ARM64 availability indicator per application
* [x] Port Manager & Conflict Detection:
  * [x] Registry of active and requested application ports
  * [x] Automatic collision detection and alternative port recommendation
* [x] Manager Authentication (**required before dashboard/API exposure**):
  * [x] Local admin account (created during first-run wizard or initial setup)
  * [x] bcrypt password hashing and JWT session management
  * [x] CSRF protection on state-changing requests
  * [x] API rate limiting
  * [x] No anonymous access to management endpoints
* [x] Build Application Plugins for **MVP Core Stack**:
  * [x] **Prowlarr** (Indexer manager)
  * [x] **Sonarr** (TV automation)
  * [x] **Radarr** (Movie automation)
  * [x] **SABnzbd** (Usenet downloader — NZBGet deferred to Phase 4)
  * [x] **qBittorrent** (BitTorrent downloader — normal WebUI/API)
  * [x] **Jellyfin** (Media server — Plex deferred to Phase 4)
  * [x] **Seerr** (Request management)
* [x] Web Dashboard MVP:
  * [x] Real-time service status, health, version, and uptime per application
  * [x] Process controls (Start / Stop / Restart / Open WebUI)
  * [x] Subprocess log inspector (console modal with real-time stream)

---

## Phase 3: Automatic Integration Engine & First-Run Wizard

* [x] Encrypted Secret Storage for application credentials (Fernet, filesystem permissions, masked UI fields)
* [x] Develop Automatic Integration Engine via APIs:
  * **Core wiring (automatic at install):**
    * [x] Configure categories (`sonarr`, `radarr`, `anime`, `lidarr`) and complete/incomplete/transcode folders
    * [x] Register download clients inside Sonarr, Radarr, and Lidarr
    * [x] Register Sonarr/Radarr/Lidarr in Prowlarr with automatic indexer synchronization
    * [x] Link Seerr to Sonarr, Radarr, and Jellyfin
    * [x] Configure root folders (TV, anime, movies, music, books) and media-server libraries
  * **Sensible defaults only (not full TRaSH tuning):**
    * [x] Basic naming templates and quality profile placeholders
  * **Deferred to Phase 4 optimization tools (not duplicated by the integration engine):**
    * TRaSH Guides quality profiles and custom formats → **Recyclarr**
    * Advanced profile management → **Profilarr**
    * *Arr ecosystem optimization → **NeutArr**
* [x] Guided 12-Step First-Run Wizard (PROMPT.md §26):
  1. Welcome
  2. Platform detection
  3. Storage configuration (with hardlink validation warnings)
  4. User / permissions (PUID / PGID)
  5. Download clients (SABnzbd, qBittorrent)
  6. VPN (optional — full implementation in Phase 5; wizard allows skip / configure later)
  7. *Arr selection (Prowlarr, Sonarr, Radarr)
  8. Media server (Jellyfin)
  9. Request system (Seerr)
  10. Recommended tools (preview selections — installed in Phase 4)
  11. Review
  12. Install (real-time progress display)
* [x] Crash Loop Detection & Resilience:
  * [x] Detection of repeated process failures (≥5 crashes in 10 mins)
  * [x] Backoff scheduling, halt auto-restart, and UI alert states
* [x] Centralized Live Log Viewer:
  * [x] WebSocket log streaming (all logs and per-application)
  * [x] Search, error filtering, download, and automatic credential/secret redaction

---

## Phase 4: Extended Applications, Updates & Backups

Per PROMPT.md §37 Phase 4.

* [x] MVP-deferred core applications:
  * **Plex** (media server — can run concurrently with Jellyfin on shared media library)
  * **NZBGet** (alternative Usenet client — user choice alongside or instead of SABnzbd)
* [x] Recommended & Optional Application Plugins:
  * **Bazarr** (Subtitles)
  * **Unpackerr** (Archive extraction)
  * **Recyclarr** (TRaSH Guides synchronization)
  * **Profilarr** (Profile management)
  * **NeutArr** (Automation optimizer)
  * **Extended *Arr:** Lidarr, Mylar3
  * **Maintenance:** Cleanuparr, Maintainerr, Tautulli
  * **Optional catalog entries** (implement when upstream APIs are stable): Autobrr, Kometa
* [x] Extend integration engine for Phase 4 apps:
  * Bazarr ↔ Sonarr/Radarr library pairing
  * Post-install hooks for Recyclarr, Profilarr, and NeutArr
  * Plex and NZBGet wiring into existing download/indexer/request flows
* [x] Safe Application Updater:
  * Pre-update snapshot of configuration and database
  * Automated post-update health check validation
  * Automatic rollback to prior version on startup failure
* [x] Centralized Backup & Restore System:
  * Automated and manual backups of manager config, application config, API credentials, and databases
  * Excludes media, torrent payloads, temp files, and large caches
  * Configurable local backup path, retention (keep last N), and scheduled backups
* [x] Application Uninstallation Workflow:
  * Clean binary removal with optional configuration/data purge
  * Explicit confirmation required; never delete media without user confirmation

---

## Phase 5: Advanced Features & Packaging

Per PROMPT.md §37 Phase 5.

* [x] VPN Integration for qBittorrent:
  * Isolated network namespace / routing table for torrent traffic only (Usenet bypasses VPN)
  * WireGuard / OpenVPN runner with PrivadoVPN pre-configuration
  * Generic provider abstraction: Mullvad, Proton VPN, AirVPN, IVPN, custom configs
  * Kill switch, DNS leak protection, connection monitoring, automatic reconnect
  * Dashboard warning if qBittorrent runs unprotected when VPN enforcement is enabled
* [x] Hardware Transcoding Auto-Detection:
  * Automatic probe for Intel Quick Sync, AMD, NVIDIA, and VAAPI (`/dev/dri`)
  * Dynamic configuration of Jellyfin and Plex hardware acceleration (graceful fallback when unavailable)
* [x] Advanced System Monitoring:
  * Per-core CPU, RAM, disk I/O, network throughput, and hardware temperatures
  * Enhanced per-application resource metrics on the dashboard
* [x] Reverse Proxy Readiness (optional — not mandatory for operation):
  * Trusted proxy header support for Traefik, Caddy, and Nginx
  * Manager continues to work via `http://server-ip:port` without a reverse proxy
* [x] Deployment Packaging:
  * **Mode A:** Single all-in-one Dockerfile plus optional compose file for the **one AIO container only** — not per-application containers
  * **Mode B:** Native Linux / LXC deployment with systemd unit file and built-in supervisor fallback when systemd is unavailable
  * **Mode C:** Unraid Community Applications template, Synology Container Manager guide, TrueNAS SCALE app definition
