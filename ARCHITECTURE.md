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

This is explicitly **not** a Docker Compose generator. The manager is the container/appliance itself. A optional `docker-compose.yml` may exist only to deploy the **single AIO container** — never one container per managed application.

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
* **Centralized Backups:** DUMB lacks an automated configuration backup/rollback engine. We build automatic pre-update backups, scheduled backups, and rollback on failure.

---

## 3. Target Platforms & Hardware Considerations

### 3.1 Primary Target Environments

* **Synology NAS (DSM):** Strict permission models, restricted root access, lack of native user-space systemd. Mode A (Single Docker Container) is the primary path.
* **Unraid:** FUSE filesystem (`/mnt/user/`) with cache pooling. Docker templates (Mode C) mapping `PUID`/`PGID` and paths are standard.
* **TrueNAS SCALE:** ZFS ACL datasets, container runtime. Mode A (Single Docker container / App) ensures compatibility.
* **Generic Linux / Proxmox LXC / Debian / Ubuntu:** Can run Mode A (Docker) or Mode B (Native Python service with systemd or built-in supervisor).

Platform-specific assumptions are avoided. Storage, networking, and permissions are accessed through abstraction layers in `core/storage.py` and `core/network_manager.py`.

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
* An optional `docker-compose.yml` deploys this **one container only**. It is not a multi-service compose stack for individual applications.

### Mode B — Native Linux / LXC

The manager runs directly as a Python application on Debian, Ubuntu, Proxmox LXC, or other supported Linux environments. Applications run as native child processes supervised by the built-in asyncio supervisor.

**systemd integration (when available):**

* A `aio-media-manager.service` unit runs the manager as a system service.
* The manager's internal supervisor handles all child application processes — individual systemd units per application are not required.
* On platforms without systemd (some NAS environments, minimal LXC), the built-in supervisor operates standalone with no external dependency.

**Process ownership:**

* All supervised applications run under the configured `PUID`/`PGID`.
* The manager drops privileges before spawning child processes where the host permits.

### Mode C — NAS-Specific Templates

Specialized deployment wrappers around Mode A:

* Unraid Community Applications XML template with user-configurable paths and UID/GID.
* Synology Container Manager project template with NAS filesystem mounts.
* TrueNAS SCALE catalog app definition with dataset mounts.

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
│   ├── network_manager.py      # Platform-agnostic networking & port abstraction
│   ├── installer.py            # Architecture-aware binary downloader & extractor
│   ├── updater.py              # Update manager (backup -> extract -> healthcheck -> rollback)
│   ├── health_monitor.py       # Health checks & state transitions
│   ├── port_manager.py         # Port registry, collision detection & auto-assignment
│   ├── vpn_manager.py          # WireGuard/OpenVPN runner & kill switch for qBittorrent
│   ├── backup_manager.py       # Scheduled/manual configuration & SQLite DB backup
│   ├── secret_manager.py       # Fernet-encrypted credential storage
│   └── auth.py                 # Admin auth (password hashing, JWT, CSRF, rate limiting)
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
│       ├── health.py           # Health endpoints (public liveness only)
│       ├── system.py           # System info, storage checks, processes
│       ├── applications.py     # App lifecycle (start, stop, restart, update, logs)
│       ├── catalog.py          # App catalog listing & installation requests
│       ├── wizard.py           # First-run setup wizard endpoints
│       ├── backups.py          # Backup & restore operations
│       └── auth.py             # Login, sessions, secret management
└── frontend/                   # Vue 3 + Vite management dashboard
```

### 5.2 Application Plugin Contract

Each application module defines — the core must not hard-code application-specific logic:

* **metadata** — name, description, upstream repo, tier, category, default port, supported architectures
* **installation** — download method, extract path, dependency checks
* **configuration** — config/data/log directory layout, environment variables
* **lifecycle** — start command, stop signal, working directory, user/group
* **health** — HTTP/API endpoint, startup timeout, health poll interval
* **updates** — version detection, release source, rollback support
* **integrations** — API capabilities consumed and provided by the integration engine

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

Each supervised application carries: command, arguments, environment, working directory, config/data/log directories, user/group, restart policy, health check, startup timeout, and shutdown timeout.

---

## 7. Storage, Hardlinks & Permissions

### 7.1 Parameterized Storage

No hardcoded paths. All paths are resolved from environment variables or `amm_config.json`:

* `config_dir` (default `/config`)
* `download_dir` (default `/downloads`)
* `media_dir` (default `/media`)
* `cache_dir` (default `/cache`, optional)

The first-run wizard prompts the user to define these paths. Examples across platforms:

| Platform | Media | Downloads |
|----------|-------|-----------|
| Unraid | `/mnt/user/media` | `/mnt/user/downloads` |
| Synology | `/volume1/media` | `/volume1/downloads` |
| TrueNAS | `/mnt/tank/media` | `/mnt/tank/downloads` |
| Generic | `/media` | `/downloads` |

### 7.2 Hardlink & Atomic Move Verification

* Instant atomic moves between download completion and media library require hardlink support.
* On startup and during wizard setup, the manager creates a temporary probe file in `download_dir` and attempts `os.link()` into `media_dir`.
* If cross-filesystem boundaries or network mounts prevent hardlinking, the UI warns that file copies will temporarily double disk usage and that torrent seeding may be affected.
* Detects filesystem type via `/proc/mounts` (Linux) or `statfs` (macOS).

### 7.3 Permissions (PUID / PGID)

* All supervised processes run under the configured `PUID` and `PGID` (default 1000:1000, validated > 0 to avoid root execution).
* Ownership is applied idempotently on startup, skipping files that already match ownership to prevent I/O bottlenecks on large media arrays.
* Goal: downloads writable by download clients, media writable by *Arr apps, media readable by Jellyfin/Plex, no unnecessary root permissions.

---

## 8. Application Catalog & Manifest System

Applications are organized into clear tiers and categories:

* **Categories:** Downloading, Automation (*Arr), Indexers, Subtitles, Media Servers, Requests, Optimization, Maintenance.
* **Tiers:**
  * **Core (MVP):** Prowlarr, Sonarr, Radarr, SABnzbd, qBittorrent, Jellyfin, Seerr.
  * **Core (Phase 4):** Plex, NZBGet — same tier, added after MVP validation.
  * **Recommended:** Bazarr, Unpackerr, Recyclarr, Profilarr, NeutArr.
  * **Optional:** Lidarr, Readarr, Whisparr, Mylar3, Autobrr, Cleanuparr, Maintainerr, Tautulli, Kometa.
  * **Experimental:** Huntarr and other tools with less stable APIs or maintenance.
* **Client Flexibility:** The user selects SABnzbd and/or NZBGet for Usenet, and Jellyfin and/or Plex (both can share the same media library concurrently).

Each catalog entry carries: name, description, upstream project, GitHub repository, current/installed version, supported architectures, installation method, required dependencies, default port, configuration directory, data directory, health endpoint, update mechanism, and API integration capabilities.

---

## 9. Installation & Update Safety

### 9.1 Installation Methods

The installer detects architecture, operating system, libc, and available dependencies, then selects the correct upstream release. Supported mechanisms (per application manifest):

* GitHub releases (`.tar.gz`, `.zip`) — primary method for *Arr apps and qBittorrent
* Official `.deb` packages
* Official standalone binaries
* Python applications (venv + pip from upstream)
* Node applications (official release bundles)

Always prefer official upstream releases. Never create unofficial forks unless absolutely necessary.

### 9.2 Safe Update Workflow

1. Stop application process.
2. Create timestamped snapshot of configuration and database in `{config_dir}/backups/{name}`.
3. Download and verify new binary (checksum validation).
4. Swap binary and launch service.
5. Poll health check endpoint.
6. If health check fails within timeout: automatically restore backup, revert binary, restart previous version, and notify dashboard.

Every application exposes: current version, installed version, update availability, update action, and rollback where feasible.

---

## 10. Automatic Integration Engine

Eliminates repetitive manual configuration across the stack. The user should not manually create API connections, download client entries, or synchronize indexers across five applications.

### 10.1 Core Integration (Phase 3 — automatic at install)

* **Categories & Paths:** Configures `sonarr` and `radarr` download categories in SABnzbd and qBittorrent (NZBGet and Plex wiring added in Phase 4).
* **Download Clients:** Connects Sonarr and Radarr to SABnzbd and qBittorrent via generated API keys stored in the secret manager.
* **Indexer Synchronization:** Registers Sonarr and Radarr as applications in Prowlarr with automatic tag and category mapping.
* **Request System:** Registers Sonarr, Radarr, and Jellyfin inside Seerr (Plex added in Phase 4).
* **Root Folders & Download Handling:** Sets media root folders and enables completed download handling with hardlink-aware paths where the storage layout permits.

### 10.2 Sensible Defaults (Phase 3)

* Basic naming templates and quality profile placeholders applied so the stack is functional immediately after install.
* These are starting points, not full TRaSH Guides tuning.

### 10.3 Deep Configuration (Phase 4 — delegated to optimization tools)

The integration engine does **not** duplicate what dedicated tools do better:

| Concern | Handled by |
|---------|------------|
| TRaSH Guides quality profiles & custom formats | **Recyclarr** |
| Advanced profile tuning & sync | **Profilarr** |
| *Arr ecosystem optimization | **NeutArr** |
| Full TRaSH naming conventions | **Recyclarr** |
| Subtitle library pairing | **Bazarr** (auto-wired on install) |
| Archive extraction | **Unpackerr** |

Post-install hooks trigger Recyclarr/Profilarr/NeutArr initial sync after the user enables them from the catalog.

---

## 11. Optional VPN for Torrents (PrivadoVPN & Generic Providers)

```
Internet
   │
   ├── Usenet (SABnzbd/NZBGet)
   │      └── normal network (no VPN)
   │
   └── Torrent (qBittorrent)
          └── VPN tunnel (optional)
                 └── Internet
```

* **Scope:** Only qBittorrent traffic is routed through the VPN; Usenet and general traffic bypass the VPN.
* **Provider Abstraction:** WireGuard-first architecture (with OpenVPN fallback). Initial pre-configuration for **PrivadoVPN** (researched at implementation time — not hard-coded). Generic support for Mullvad, Proton VPN, AirVPN, IVPN, and custom configs.
* **Kill Switch & Isolation:** If the VPN tunnel disconnects, qBittorrent network traffic is immediately blocked to prevent IP/DNS leaks.
* **Dashboard Telemetry:** Displays tunnel status, public IP check, reconnect state, and warns if qBittorrent is running unprotected when VPN enforcement is enabled.

---

## 12. Security, Authentication & Secret Management

Management APIs must never be exposed anonymously.

* **Manager Authentication (Phase 2):** Built-in local admin account with bcrypt password hashing and JWT sessions. Created during the first-run wizard or initial setup.
* **CSRF Protection:** State-changing API requests require valid CSRF tokens when using cookie-based sessions.
* **Rate Limiting:** Login and sensitive API endpoints are rate-limited to prevent brute-force attacks.
* **Secret Storage (Phase 3):** Sensitive credentials (API keys, passwords, VPN configs) are stored encrypted via Fernet using a machine-derived key. Filesystem permissions restrict access to the manager process only.
* **Masking & Redaction:** Credentials are masked in UI responses and redacted from log outputs. Secrets are never included in API responses unless explicitly required for copy-to-clipboard flows (masked by default).
* **Port Conflict Detection:** Pre-flight port checks prevent startup crashes by auto-detecting conflicts and suggesting alternatives.

---

## 13. Centralized Backup & Restore

Separate from per-update snapshots (§9.2), the backup manager provides ongoing configuration protection:

**Backed up:**

* Manager configuration (`amm_config.json`, environment overrides)
* Application configuration directories
* API credentials and integration state (from secret manager)
* Application database files (SQLite, etc.)

**Never backed up:**

* Downloaded media, torrent payloads, temporary files, large caches

**User-configurable:**

* Local backup destination path
* Retention policy (keep last N backups)
* Scheduled backup interval (manual trigger also supported)

Restore operations validate backup integrity before applying. Restore is available per-application or for the full manager state.

---

## 14. Centralized Log Viewer

All supervised application stdout/stderr is captured to `{config_dir}/logs/{app}/` and buffered in memory ring buffers for live access.

* **Scope:** All logs combined, or filtered per application.
* **Live streaming:** WebSocket feed for real-time tailing.
* **Search & filter:** Text search and error-level filtering.
* **Download:** Export log files from the UI.
* **Redaction:** Automatic scrubbing of API keys, passwords, and tokens before display or export.

---

## 15. Application Uninstallation

Applications are individually removable from the catalog/dashboard:

```
Remove Lidarr?
  [ ] Remove application binary
  [ ] Remove configuration
  [ ] Remove data
```

* Media files are **never** deleted during uninstall regardless of selections.
* Deleting configuration or data requires explicit checkbox confirmation.
* Running processes are stopped gracefully before file removal.
* Integration references (e.g. Prowlarr app entry, Seerr server link) are cleaned up automatically.

---

## 16. Reverse Proxy Readiness

A reverse proxy is **not required**. The manager and all application WebUIs are accessible via `http://server-ip:port` out of the box.

The architecture supports optional future reverse proxy integration (Phase 5):

* Trusted proxy header parsing (`X-Forwarded-For`, `X-Forwarded-Proto`) for Traefik, Caddy, and Nginx.
* Configurable base URL / subpath prefix for the manager UI.
* No hard dependency on any specific proxy product.

---

## 17. First-Run Wizard

12-step guided setup (PROMPT.md §26):

| Step | Content |
|------|---------|
| 1 | Welcome |
| 2 | Platform detection |
| 3 | Storage configuration (media, downloads, config, optional cache) |
| 4 | User / permissions (PUID, PGID) |
| 5 | Download clients (SABnzbd, qBittorrent) |
| 6 | VPN (optional — skip or configure later; full VPN in Phase 5) |
| 7 | *Arr selection (Prowlarr, Sonarr, Radarr, optional Lidarr/Readarr preview) |
| 8 | Media server (Jellyfin; Plex available after Phase 4) |
| 9 | Request system (Seerr) |
| 10 | Recommended tools (Bazarr, Unpackerr, Recyclarr, Profilarr, NeutArr — installed in Phase 4) |
| 11 | Review (summary of all selections and storage layout warnings) |
| 12 | Install (real-time progress: install → configure → health check per application) |

On completion the wizard creates the admin account (if not already set), persists configuration, installs selected applications, runs the integration engine, and redirects to the dashboard.

---

## 18. Management Dashboard

Vue 3 + Vite responsive UI backed by FastAPI.

**System panel:**

* CPU (per-core in Phase 5), RAM, disk usage per mount, network I/O, uptime, temperature where available.

**Applications panel (per service):**

* Status, version, uptime, CPU, RAM, health state, update availability.
* Actions: Open WebUI, Start, Stop, Restart, Update, Logs, Configure, Uninstall.

**Additional views:**

* Application catalog browser (enable/disable modular services by tier).
* Centralized live log viewer (§14).
* Backup management (§13).
* VPN status (Phase 5).
* Storage layout and hardlink status (§7.2).
