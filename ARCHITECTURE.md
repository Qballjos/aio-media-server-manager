# AIO Media Server Manager — Architecture

## 1. Project Vision

The AIO Media Server Manager is a self-hosted appliance that manages a complete Usenet + torrent media stack without relying on a separate Docker container per application. The user installs one management layer; the manager installs, configures, supervises, integrates, and maintains everything else.

**Core Principle:**

```
Host
└── AIO Media Manager (one process / one container)
      ├── Prowlarr     (managed process)
      ├── Sonarr       (managed process)
      ├── Radarr       (managed process)
      ├── SABnzbd      (managed process)
      ├── qBittorrent  (managed process)
      ├── Jellyfin     (managed process)
      ├── Seerr        (managed process)
      └── ...
```

This is explicitly **not** a Docker Compose generator. The manager is the container/appliance itself.
There is **zero Debrid functionality** (no Real-Debrid, AllDebrid, Premiumize, Zurg, Riven, Decypharr, Debrid mounts, or Debrid caching). The focus is entirely on conventional Usenet and BitTorrent.

---

## 2. DUMB Architecture Analysis & Adaptation

### 2.1 What DUMB Does Well (Concepts to Adopt)
* **Custom Process Supervisor:** Python-based process manager to supervise child processes, intercept signals (SIGTERM/SIGINT/SIGCHLD), reap zombie processes, and restart failed applications.
* **Direct Binary Management:** Downloads, extracts, and updates raw binaries (e.g. GitHub releases, `.tar.gz`) directly into local application directories rather than pulling separate Docker images.
* **Unified Health Monitoring & Metrics:** Integrates health checks, process polling, and restarts natively within the manager.
* **Declarative Configuration & Auto-Wiring:** Centralized configuration that automatically wires services together (e.g. injecting download clients and indexers into *Arr apps via REST API).
* **Unified Logging:** Interleaved streaming of subprocess stdout/stderr to disk and in-memory ring buffers.

### 2.2 What DUMB Does Poorly (Areas to Improve)
* **Debrid Tight Coupling:** DUMB is fundamentally built around Debrid workflows. We completely eliminate Debrid.
* **Hardcoded App Deployment:** DUMB bakes specific application paths into core scripts. We use a modular plugin/manifest system (`applications/` and `integrations/`).
* **Rigid Storage Assumptions:** DUMB assumes specific mount points (`/mnt/`). We implement fully parameterized, user-defined paths (`config_dir`, `download_dir`, `media_dir`, `cache_dir`).
* **Missing Application Catalog & Tiers:** DUMB lacks categorization. We introduce clear tiers: Core, Recommended, Optional, and Experimental.
* **Lack of Guided First-Run Wizard:** DUMB requires manual environment/config file tweaking. We provide a guided first-run setup wizard.
* **Secret Management & Security:** Credentials must not be stored in plaintext in the frontend or exposed in logs. We introduce encrypted secret management and authenticated UI/API.
* **Centralized Backups:** DUMB lacks an automated configuration backup/rollback engine. We build automatic pre-update backups and rollback on failure.

---

## 3. Target Platforms & Hardware Considerations

### 3.1 Primary Target Environments
* **Synology NAS (DSM):** Strict permission models, restricted root access, lack of native user-space systemd. Mode A (Single Docker Container) is the primary path.
* **Unraid:** FUSE filesystem (`/mnt/user/`) with cache pooling. Docker templates (Mode C) mapping `PUID`/`PGID` and paths are standard.
* **TrueNAS SCALE:** ZFS ACL datasets, container runtime. Mode A (Single Docker container / App) ensures compatibility.
* **Generic Linux / Proxmox LXC / Debian / Ubuntu:** Can run Mode A (Docker) or Mode B (Native Python service with systemd or built-in supervisor).

### 3.2 Low Overhead & Resource Philosophy
Many users run on low-power NAS hardware (limited RAM: 4–16GB, low-power CPUs).
* **Zero Heavy Middleware:** No Kubernetes, no Redis, no RabbitMQ, no Elasticsearch.
* **Asynchronous Core:** Single async event loop (FastAPI + asyncio process supervisor) with negligible CPU idle footprint.

### 3.3 ARM64 & Multi-Architecture First
NAS systems frequently use ARM64 processors.
* The manager core supports both `x86_64` and `ARM64`.
* Every application plugin declares its supported architectures (`x86_64`, `arm64`, `armv7`).
* The UI clearly indicates whether an application supports ARM64 or is unavailable upstream.

---

## 4. Deployment Modes

### Mode A — Single Docker Container (Primary / Recommended)
The entire manager and all supervised applications run inside a single privileged Docker container.
* Volumes mapped: `/config`, `/downloads`, `/media`, optional `/cache`.
* Host exposes the manager UI port (e.g. `8080`) and forwarded application WebUI ports.

### Mode B — Native Linux / LXC
The manager runs directly as a Python application (managed by systemd or run as a standalone service). Applications run as native child processes.

### Mode C — NAS-Specific Templates
Specialized deployment wrappers around Mode A:
* Unraid Community Applications XML template.
* Synology Container Manager project / compose template.
* TrueNAS SCALE catalog app definition.

---

## 5. Core Architectural Components

### 5.1 System Structure
```
aio-media-manager/
├── main.py                     # Unified entrypoint
├── core/
│   ├── settings.py             # Pydantic BaseSettings (env + amm_config.json)
│   ├── logging_config.py       # colorlog + rotating file handler
│   ├── supervisor.py           # Async process supervisor & zombie reaper
│   ├── storage.py              # Storage validation, hardlinks, FS detection, permissions
│   ├── installer.py            # Architecture-aware binary downloader & extractor
│   ├── updater.py              # Update manager (backup -> extract -> healthcheck -> rollback)
│   ├── health_monitor.py       # Health checks & state transitions
│   ├── port_manager.py         # Port registry, collision detection & auto-assignment
│   ├── vpn_manager.py          # WireGuard/OpenVPN runner & kill switch for qBittorrent
│   ├── backup_manager.py       # Scheduled/manual configuration & SQLite DB backup
│   ├── secret_manager.py       # Fernet-encrypted credential storage
│   └── auth.py                 # Admin auth (password hashing, JWT sessions)
├── applications/
│   ├── base.py                 # BaseApplication abstract plugin class
│   ├── catalog.py              # Catalog manifest registry (tiers, categories, metadata)
│   ├── prowlarr/
│   ├── sonarr/
│   ├── radarr/
│   ├── sabnzbd/
│   ├── nzbget/
│   ├── qbittorrent/
│   ├── jellyfin/
│   ├── plex/
│   ├── seerr/
│   ├── bazarr/
│   ├── unpackerr/
│   ├── recyclarr/
│   ├── profilarr/
│   └── neutarr/
├── integrations/
│   ├── base.py                 # BaseIntegration engine
│   ├── prowlarr_sync.py        # Automatic Prowlarr -> Sonarr/Radarr indexer sync
│   ├── download_client_sync.py # SABnzbd/NZBGet/qBittorrent -> *Arr download client injection
│   └── seerr_sync.py           # Seerr -> Sonarr/Radarr/Jellyfin/Plex registration
├── api/
│   ├── app.py                  # FastAPI application factory
│   └── routers/
│       ├── health.py           # Health endpoints
│       ├── system.py           # System info, storage checks, processes
│       ├── applications.py     # App lifecycle (start, stop, restart, update, logs)
│       ├── catalog.py          # App catalog listing & installation requests
│       ├── wizard.py           # First-run setup wizard endpoints
│       └── auth.py             # Login, sessions, secret management
└── frontend/                   # Vue 3 + Vite management dashboard
```

---

## 6. Process Supervisor & Lifecycle Engine

The `ProcessSupervisor` is an asyncio-based singleton responsible for all supervised applications:
* **Async Spawning:** Uses `asyncio.create_subprocess_exec` with separate pipes for stdout/stderr.
* **Zombie Reaping:** Registers a `SIGCHLD` handler invoking `os.waitpid(-1, os.WNOHANG)` to avoid defunct zombie processes.
* **Graceful Termination:** Sends `SIGTERM`, waits up to a configurable timeout (default 10s), then escalates to `SIGKILL`. Shuts down processes in reverse dependency order on system exit.
* **Crash Loop Protection:** If an application crashes 5 times within a rolling 10-minute window, auto-restart is halted and the process is marked as `CRASH_LOOP` to prevent CPU thrashing.
* **Exponential Backoff:** Retries restart at 2s, 4s, 8s, 16s, 32s intervals.
* **Health States:**
  `STOPPED`, `STARTING`, `RUNNING`, `HEALTHY`, `UNHEALTHY`, `FAILED`, `CRASH_LOOP`, `INSTALLING`, `UPDATING`.

---

## 7. Storage, Hardlinks & Permissions

### 7.1 Parameterized Storage
No hardcoded paths. All paths are resolved from environment variables or `amm_config.json`:
* `config_dir` (default `/config`)
* `download_dir` (default `/downloads`)
* `media_dir` (default `/media`)
* `cache_dir` (default `/cache`, optional)

### 7.2 Hardlink & Atomic Move Verification
* Instant atomic moves between download completion and media library require hardlink support.
* On startup and during wizard setup, the manager creates a temporary probe file in `download_dir` and attempts `os.link()` into `media_dir`.
* If cross-filesystem boundaries or network mounts prevent hardlinking, the system issues a warning in the UI explaining that file copies will temporarily double disk usage.
* Detects filesystem type via `/proc/mounts` (Linux) or `statfs` (macOS).

### 7.3 Permissions (PUID / PGID)
* All supervised processes run under the configured `PUID` and `PGID` (default 1000:1000, validated > 0 to avoid root execution).
* Ownership is applied idempotently on startup, skipping files that already match ownership to prevent I/O bottlenecks on large media arrays.

---

## 8. Application Catalog & Manifest System

Applications are organized into clear tiers and categories:
* **Categories:** Downloading, Automation (*Arr), Indexers, Subtitles, Media Servers, Requests, Optimization, Maintenance.
* **Tiers:**
  * **Core:** Prowlarr, Sonarr, Radarr, SABnzbd/NZBGet, qBittorrent, Jellyfin/Plex, Seerr.
  * **Recommended:** Bazarr, Unpackerr, Recyclarr, Profilarr, NeutArr.
  * **Optional:** Lidarr, Readarr, Whisparr, Mylar3, Autobrr, Cleanuparr, Maintainerr, Tautulli, Kometa.
  * **Experimental:** Emerging tools or community scripts.
* **Client Flexibility:** The user selects SABnzbd OR NZBGet (or both) for Usenet, and Jellyfin OR Plex (or both simultaneously sharing the media library).

---

## 9. Binary Installation & Update Safety

* **Binary Installer:** Detects architecture (`x86_64`, `arm64`) and OS/libc, pulls official GitHub release assets or packages, validates checksums, and extracts into `{config_dir}/apps/{name}`.
* **Safe Update Workflow:**
  1. Stop application process.
  2. Create timestamped snapshot of configuration and database in `{config_dir}/backups/{name}`.
  3. Download and verify new binary.
  4. Swap binary and launch service.
  5. Poll health check endpoint.
  6. If health check fails within timeout: automatically restore backup, revert binary, restart previous version, and notify dashboard.

---

## 10. Automatic Integration Engine

Eliminates repetitive manual configuration across the stack:
* **Categories & Paths:** Configures `sonarr` and `radarr` download categories in SABnzbd, NZBGet, and qBittorrent.
* **Download Clients:** Connects Sonarr and Radarr to SABnzbd/NZBGet and qBittorrent via generated API keys.
* **Indexer Synchronization:** Registers Sonarr and Radarr as applications in Prowlarr with automatic tag and category mapping.
* **Request System:** Registers Sonarr, Radarr, and Jellyfin/Plex instances inside Seerr.
* **Subtitles:** Pairs Bazarr with Sonarr and Radarr libraries.

---

## 11. Optional VPN for Torrents (PrivadoVPN & Generic Providers)

* **Scope:** Only qBittorrent traffic is routed through the VPN; Usenet and general traffic bypass the VPN.
* **Provider Abstraction:** WireGuard-first architecture (with OpenVPN fallback). Initial pre-configuration for **PrivadoVPN**, with generic support for Mullvad, ProtonVPN, AirVPN, and custom configs.
* **Kill Switch & Isolation:** If the VPN tunnel disconnects, qBittorrent network traffic is immediately blocked to prevent IP/DNS leaks.
* **Dashboard Telemetry:** Displays tunnel status, public IP check, and warns if qBittorrent is running unprotected.

---

## 12. Security, Authentication & Secret Management

* **Manager Authentication:** Built-in local admin account with bcrypt password hashing and JWT sessions.
* **Secret Storage:** Sensitive credentials (API keys, passwords, VPN configs) are stored encrypted via Fernet using a machine-derived key.
* **Masking & Redaction:** Credentials are masked in UI responses and redacted from log outputs.
* **Port Conflict Detection:** Pre-flight port checks prevent startup crashes by auto-detecting conflicts and suggesting alternatives.

---

## 13. First-Run Wizard & Management Dashboard

* **Guided First-Run Wizard:** 12-step flow covering platform detection, storage paths, PUID/PGID, download client selection, VPN setup, *Arr tools, media servers, recommended optimization tools, admin account creation, and automated installation with real-time progress.
* **Modern Web Dashboard:** Vue 3 + Vite responsive UI with:
  * System overview (CPU, RAM, disk breakdown per mount, network I/O, uptime, temperatures).
  * Per-application control (start, stop, restart, update, logs, config, uninstall).
  * Centralized live log viewer with search, filtering, and download.
  * Application catalog browser for enabling/disabling modular services.
