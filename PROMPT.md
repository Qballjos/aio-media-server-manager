Project: AIO Media Server Manager – DUMB-inspired, No Debrid

Role

You are a senior Linux systems architect, application developer and DevOps engineer.

I want you to design and build a self-hosted All-In-One Media Server Manager, inspired by the architecture and user experience of the current DUMB project.

Before writing code, you MUST study the current DUMB project architecture, repository and documentation.

Reference:

* DUMB GitHub: https://github.com/I-am-PUID-0/DUMB
* DUMB documentation/repository: https://github.com/I-am-PUID-0/DUMB_docs

Do NOT assume that DUMB is a Docker Compose orchestrator.

Understand how DUMB actually works:

* central controller
* managed applications/services
* application installation
* process management
* configuration management
* lifecycle management
* health checks
* updates
* logs
* service discovery
* automatic integration between applications
* embedded/accessed web interfaces

The goal is to build a DUMB-like media appliance, but specifically designed for normal Usenet + torrent users and without any Debrid functionality.

⸻

1. Fundamental concept

The product should be an AIO Media Server Manager, not a Docker Compose generator.

The user installs this software on a NAS/home server and the application becomes the central management layer for the entire media stack.

The manager should:

* install applications
* download the correct application versions
* install/update binaries
* create configuration directories
* create required users/groups
* configure applications
* start/stop/restart applications
* monitor application health
* monitor processes
* manage logs
* perform upgrades
* recover failed services
* configure networking
* configure application integrations
* expose links to application web interfaces
* maintain application dependencies
* provide a unified dashboard

Applications should normally run as managed processes inside the AIO environment, rather than every application becoming a separate Docker container.

This is one of the most important architectural requirements.

Docker

Docker may be used as a single deployment wrapper for the entire AIO manager.

For example:

Host
  └── AIO Media Manager container
        ├── Sonarr
        ├── Radarr
        ├── Prowlarr
        ├── SABnzbd
        ├── qBittorrent
        ├── Jellyfin
        ├── Seerr
        └── other managed services

Do NOT create:

Docker container → Sonarr
Docker container → Radarr
Docker container → Prowlarr
Docker container → SABnzbd
Docker container → qBittorrent
etc.

The AIO manager itself is the container/appliance.

When running natively in an LXC/Linux environment, the same applications should run as managed native processes/services.

⸻

2. Target platforms

The primary target is home NAS/server hardware, not cloud infrastructure.

The project should be designed specifically for platforms such as:

* Synology NAS
* Unraid
* TrueNAS SCALE
* TrueNAS
* generic Linux servers
* Debian
* Ubuntu
* Proxmox LXC
* potentially other Linux-based NAS systems

The architecture must be portable.

Do not build the application around one specific platform.

Important

Many users of these systems have:

* large HDD arrays
* SSD/NVMe cache
* shared media folders
* shared download folders
* custom UID/GID permissions
* limited RAM
* limited CPU
* no desire to manually maintain dozens of containers

The product should therefore have very low overhead.

⸻

3. Deployment modes

Design the system around multiple deployment modes.

Mode A – Single Docker container

The preferred generic deployment method.

Example:

AIO Manager
    ↓
one Docker container
    ↓
all managed applications

Persistent storage should be configurable.

Example:

/config
/downloads
/media
/data
/logs

The manager must NOT require Docker Compose for every application.

⸻

Mode B – Native Linux / LXC

The manager should also be capable of running directly inside:

* Debian
* Ubuntu
* Proxmox LXC
* other supported Linux environments

Applications then run as native processes/services.

The manager should have its own service/process supervisor if systemd is unavailable.

If systemd is available, support using systemd where appropriate.

⸻

Mode C – NAS-specific deployment

Investigate the best way to support:

Synology

Potential deployment through:

* Docker/Container Manager
* single AIO container
* NAS filesystem mounts

Unraid

Potential deployment through:

* Docker
* Unraid template
* user-configurable paths
* correct UID/GID handling

TrueNAS SCALE

Potential deployment through:

* Docker/Apps where appropriate
* single AIO container
* dataset mounts

Do not make platform-specific assumptions.

Create an abstraction layer for storage, networking and permissions.

⸻

4. No Debrid

This project must have:

ZERO DEBRID FUNCTIONALITY

Do not implement:

* Real-Debrid
* AllDebrid
* Premiumize
* Zurg
* Riven
* Decypharr
* Debrid mounts
* Debrid caching
* Debrid download workflows

The system should be designed around conventional:

* Usenet
* BitTorrent

downloads.

⸻

5. Download clients

Usenet

Support one of:

SABnzbd

or

NZBGet

The user should be able to select which one they want.

The manager should:

* install it
* configure it
* start it
* monitor it
* configure categories
* configure download directories
* configure post-processing
* connect it to Sonarr/Radarr
* expose its web interface

The architecture should allow adding another Usenet client later without redesigning the entire system.

⸻

6. Torrents

Use:

qBittorrent

qBittorrent must be the primary torrent client.

It should use its normal WebUI/API.

The manager should:

* install qBittorrent
* configure it
* configure download locations
* configure categories
* configure authentication
* configure Sonarr/Radarr integration
* monitor its health
* expose its WebUI

The user specifically wants the normal qBittorrent interface and does not want a custom torrent engine.

⸻

7. Optional VPN for torrents

Torrent traffic should optionally be routed through:

PrivadoVPN

The VPN must be optional.

Usenet traffic should NOT automatically be forced through the VPN.

Desired architecture:

Internet
   │
   ├── Usenet
   │      └── normal network
   │
   └── Torrent
          └── qBittorrent
                 └── VPN
                        └── Internet

The VPN implementation must include:

* configurable VPN
* connection monitoring
* kill switch
* DNS leak protection
* torrent traffic isolation
* automatic reconnect
* clear VPN status
* warning if qBittorrent is running without the VPN when VPN enforcement is enabled

Before implementation, research the current PrivadoVPN Linux support and available WireGuard/OpenVPN configuration options.

Do not hard-code assumptions about PrivadoVPN.

The VPN layer should ideally be abstracted so additional providers can be supported later.

Potential future providers:

* Mullvad
* Proton VPN
* AirVPN
* IVPN

⸻

8. *Arr ecosystem

The manager should support the complete *Arr ecosystem.

Core:

* Prowlarr
* Sonarr
* Radarr

Optional:

* Lidarr
* Readarr
* Whisparr
* Mylar3
* other actively maintained *Arr-compatible applications

The manager should understand that these applications are not isolated.

It should automatically configure:

Prowlarr
   ↓
Sonarr
Radarr
Lidarr
etc.

When possible, the manager should automatically:

* create API connections
* configure download clients
* configure categories
* configure root folders
* configure indexers
* synchronize indexers
* configure quality profiles
* configure naming
* configure download handling

The user should not have to manually configure the same integration five times.

⸻

9. Media automation tools

Include first-class support for:

Bazarr

Subtitle management.

Unpackerr

Automatic archive extraction.

Recyclarr

Synchronisation of TRaSH Guides configurations.

Profilarr

Quality/profile management.

NeutArr

Automation/optimization around the *Arr ecosystem.

Investigate the current versions, APIs and recommended integration methods before implementation.

These applications should be optional modules.

⸻

10. Additional optional applications

Design the architecture so applications can be enabled/disabled individually.

Potential modules:

* Autobrr
* Cleanuparr
* Maintainerr
* Tautulli
* Kometa
* Huntarr if still actively maintained and appropriate
* other useful media-management tools

Do not blindly install everything.

The UI should distinguish:

Core

Required for the selected setup.

Recommended

Strongly recommended tools.

Optional

Additional functionality.

Experimental

Applications that may have less stable APIs or maintenance.

⸻

11. Media servers

The user should be able to select:

Jellyfin

Plex

Both

The manager should install and configure the selected media server(s).

Example:

[x] Jellyfin
[ ] Plex

or:

[x] Jellyfin
[x] Plex

Both must be able to use the same media library.

The manager should configure:

* media paths
* permissions
* hardware transcoding where possible
* service startup
* health monitoring
* updates
* WebUI links

The architecture must support hardware acceleration where the host exposes it.

Examples:

* Intel Quick Sync
* AMD
* NVIDIA
* VAAPI
* /dev/dri

Do not assume hardware acceleration is available.

Detect it automatically.

⸻

12. Seerr

Support:

Seerr

Seerr should be treated as the primary request interface.

Example workflow:

User
  ↓
Seerr
  ↓
Sonarr / Radarr
  ↓
Prowlarr
  ↓
SABnzbd / NZBGet / qBittorrent
  ↓
Media library
  ↓
Jellyfin / Plex

The manager should automatically configure the required connections.

⸻

13. Storage architecture

Storage is extremely important.

Do NOT hard-code paths.

The first-run wizard should ask the user to define:

Media

Example:

/media

or:

/mnt/user/media

Downloads

Example:

/downloads

Configuration

Example:

/config

Temporary/cache storage

Optional:

/cache

The manager should understand that different NAS platforms use different storage layouts.

Examples:

Unraid:

/mnt/user/media
/mnt/user/downloads

Synology:

/volume1/media
/volume1/downloads

TrueNAS:

/mnt/tank/media
/mnt/tank/downloads

The user should be able to choose arbitrary paths.

⸻

14. Hardlinks and atomic moves

The manager should detect whether downloads and media are located on the same filesystem.

Where possible:

* use hardlinks
* avoid unnecessary copying
* preserve seeding
* avoid duplicate disk usage

The UI should warn the user when their storage layout prevents hardlinking.

Example:

Downloads:
/data/downloads
Media:
/data/media

Good.

But:

Downloads:
/disk1/downloads
Media:
/disk2/media

May require copying.

Explain this clearly in the UI.

⸻

15. Permissions

The manager must handle:

* UID
* GID
* umask
* file ownership
* shared groups
* read/write permissions

Do not assume UID 1000.

The installer should detect the environment and allow the user to configure:

PUID
PGID

The goal is:

* downloads writable by download clients
* media writable by *Arr applications
* media readable by Jellyfin/Plex
* no unnecessary root permissions

Avoid running every application as root unless technically required.

⸻

16. Central management dashboard

Build a modern web UI.

The dashboard should show:

System

* CPU
* RAM
* disk usage
* network
* uptime
* temperature where available

Applications

For each service:

Sonarr        ● Running
Radarr        ● Running
Prowlarr      ● Running
SABnzbd       ● Running
qBittorrent   ● Running
Jellyfin      ● Running
Seerr         ● Running

Show:

* status
* version
* uptime
* CPU
* RAM
* health
* update availability

Provide buttons:

* Open
* Start
* Stop
* Restart
* Update
* Logs
* Configure
* Uninstall

⸻

17. Application catalog

Create an application catalog.

Example:

Downloading

* SABnzbd
* NZBGet
* qBittorrent

Automation

* Sonarr
* Radarr
* Lidarr
* Readarr
* Whisparr

Indexers

* Prowlarr

Subtitles

* Bazarr

Media

* Jellyfin
* Plex

Requests

* Seerr

Optimization

* Recyclarr
* Profilarr
* NeutArr

Maintenance

* Unpackerr
* Cleanuparr
* Maintainerr
* Tautulli

Each application should have metadata such as:

* name
* description
* upstream project
* GitHub repository
* current version
* supported architectures
* installation method
* required dependencies
* default port
* configuration directory
* data directory
* health endpoint
* update mechanism
* API integration capabilities

This should be defined through a modular application manifest system.

⸻

18. Architecture

Use a modular architecture.

Suggested:

aio-manager/
├── core/
│   ├── service_manager
│   ├── process_manager
│   ├── installer
│   ├── updater
│   ├── health_manager
│   ├── config_manager
│   ├── storage_manager
│   ├── permission_manager
│   └── network_manager
│
├── integrations/
│   ├── sonarr
│   ├── radarr
│   ├── prowlarr
│   ├── sabnzbd
│   ├── nzbget
│   ├── qbittorrent
│   ├── jellyfin
│   ├── plex
│   └── seerr
│
├── applications/
│   ├── sonarr
│   ├── radarr
│   ├── prowlarr
│   ├── sabnzbd
│   ├── qbittorrent
│   └── ...
│
├── frontend/
│
└── installer/

Applications must be plugins/modules rather than hard-coded into the core.

⸻

19. Application installation

Do not assume every application has the same installation method.

The installer should support:

GitHub releases

Download:

* AMD64
* ARM64
* ARMv7 where applicable

Debian packages

Official binaries

Python applications

Node applications

Other supported upstream distribution mechanisms

Always prefer official upstream releases.

Do not create unofficial forks unless absolutely necessary.

The installer should detect:

architecture
operating system
libc
available dependencies

and select the correct release.

⸻

20. Updates

Every application should support:

* current version
* installed version
* update available
* update
* rollback where feasible

Before updating:

1. Stop service.
2. Backup configuration.
3. Download new version.
4. Validate download.
5. Install.
6. Start service.
7. Run health check.
8. If health check fails, attempt rollback.

Never blindly replace a working installation.

⸻

21. Backups

Provide centralized backup management.

Back up:

* manager configuration
* application configuration
* API credentials
* database files where applicable
* integration configuration

Do NOT back up:

* downloaded media
* temporary files
* torrent payloads
* large caches

Allow the user to configure:

* local backup path
* retention
* scheduled backups

⸻

22. Secrets

Never store passwords/API keys in plaintext in frontend configuration.

Implement a proper secret/configuration system.

At minimum:

* protected configuration storage
* filesystem permissions
* masked UI fields
* never expose credentials in logs
* never expose credentials through API responses unnecessarily

⸻

23. Process management

This is critical.

The manager needs a reliable process supervisor.

Each application should have:

* command
* arguments
* environment
* working directory
* config directory
* data directory
* log directory
* user/group
* restart policy
* health check
* startup timeout
* shutdown timeout

Example:

Application:
    Sonarr
Command:
    /opt/sonarr/Sonarr
User:
    media
Config:
    /config/sonarr
Logs:
    /logs/sonarr
Health:
    HTTP API
Restart:
    on failure

The manager must be able to recover from crashed applications.

⸻

24. Health monitoring

Every application should have a health state:

* Running
* Starting
* Healthy
* Unhealthy
* Stopped
* Failed
* Updating
* Installing

Use appropriate health checks.

Prefer:

* HTTP health endpoint
* API endpoint
* process status

rather than simply checking whether a process exists.

⸻

25. Automatic configuration

One of the biggest advantages over manually building a media stack should be automatic integration.

Example:

The user installs:

Prowlarr
Sonarr
Radarr
SABnzbd
qBittorrent

The manager should automatically create:

SABnzbd

Categories:

sonarr
radarr

qBittorrent

Categories:

sonarr
radarr

Sonarr

Download clients:

SABnzbd
qBittorrent

Radarr

Download clients:

SABnzbd
qBittorrent

Prowlarr

Indexer connections to:

Sonarr
Radarr

The user should only need to provide credentials/API keys when required.

⸻

26. First-run wizard

Create a professional first-run setup.

Step 1:

Welcome

Step 2:

Platform detection

Step 3:

Storage configuration

Step 4:

User/permissions

Step 5:

Download clients
[x] SABnzbd
[ ] NZBGet
[x] qBittorrent

Step 6:

VPN
[ ] None
[x] PrivadoVPN

Step 7:

*Arr
[x] Prowlarr
[x] Sonarr
[x] Radarr
[ ] Lidarr
[ ] Readarr

Step 8:

Media server
[x] Jellyfin
[ ] Plex

Step 9:

Request system
[x] Seerr

Step 10:

Recommended tools
[x] Bazarr
[x] Unpackerr
[x] Recyclarr
[x] Profilarr
[x] NeutArr

Step 11:

Review

Step 12:

Install

The manager should then install and configure everything automatically.

⸻

27. Installation progress

Show detailed progress:

Installing Prowlarr       ✓
Installing Sonarr         ✓
Installing Radarr         ✓
Installing SABnzbd        ✓
Installing qBittorrent    ✓
Configuring Prowlarr     ✓
Configuring Sonarr       ✓
Configuring Radarr       ✓
Configuring SABnzbd      ✓
Configuring qBittorrent  ✓
Running health checks    ✓

At the end:

Media stack successfully installed.

⸻

28. Ports

Do not hard-code ports blindly.

Every application should have:

* default port
* configurable port
* conflict detection

The manager should detect:

Port already in use

and offer:

Use another port

The UI should provide direct links to every application.

⸻

29. Reverse proxy

Do NOT make a reverse proxy mandatory.

The manager should work entirely through:

http://server-ip:port

But design the architecture so reverse proxy support can later be added.

Potential future support:

* Traefik
* Caddy
* Nginx

⸻

30. Security

The manager itself should have authentication.

At minimum:

* local admin account
* password hashing
* session management
* CSRF protection
* secure API
* rate limiting
* secure secret handling

Do not expose management APIs anonymously.

⸻

31. Architecture must support ARM64

This is extremely important because NAS systems commonly use ARM processors.

Support where upstream applications permit:

* x86_64
* ARM64

The manager itself should ideally support both.

Do not assume every application supports ARM64.

The UI should clearly show:

ARM64: Supported

or:

ARM64: Not available from upstream

⸻

32. Resource awareness

This is intended for NAS hardware.

Avoid unnecessarily heavy technologies.

Do not introduce:

* Kubernetes
* Kubernetes operators
* microservices
* Redis
* RabbitMQ
* Elasticsearch

unless there is a very strong architectural reason.

The manager should remain lightweight.

⸻

33. Failure recovery

The manager should be resilient.

If:

Sonarr crashes

the manager should:

1. Detect failure.
2. Record the failure.
3. Restart Sonarr.
4. Verify health.
5. Notify the UI.

If repeated failures occur:

5 crashes within 10 minutes

stop restarting indefinitely and mark:

Crash loop detected

This prevents runaway resource usage.

⸻

34. Logs

Provide a centralized log viewer.

Allow:

* all logs
* per application
* live logs
* search
* download logs
* error filtering

Never expose secrets in logs.

⸻

35. Uninstall

Applications must be removable.

For example:

Remove Lidarr?

Options:

[ ] Remove application
[ ] Remove configuration
[ ] Remove data

Never delete media without an explicit confirmation.

⸻

36. Important architectural principle

The application manager must NOT become another giant monolithic hard-coded media application.

The core should know:

"How to install and manage applications."

It should NOT contain all application-specific logic.

Application modules should define:

metadata
installation
configuration
lifecycle
health
updates
integrations

This makes it possible to add new applications later.

⸻

37. Development methodology

Do NOT immediately start writing thousands of lines of code.

First perform an architecture phase.

Phase 1 – Research

Study:

* current DUMB architecture
* DUMB process management
* DUMB application definitions
* DUMB installation system
* DUMB configuration system
* DUMB update mechanism
* DUMB Proxmox/LXC implementation
* how DUMB handles managed services

Also research current official documentation/APIs for:

* Sonarr
* Radarr
* Prowlarr
* SABnzbd
* NZBGet
* qBittorrent
* Jellyfin
* Plex
* Seerr
* Bazarr
* Recyclarr
* Profilarr
* NeutArr
* Unpackerr
* PrivadoVPN

Prefer official documentation and upstream repositories.

Phase 2 – Architecture document

Before coding, create:

ARCHITECTURE.md

It must explain:

* system architecture
* deployment modes
* process manager
* installer
* application plugin system
* storage system
* permissions
* networking
* VPN architecture
* configuration system
* secret management
* update system
* health monitoring
* backup system
* frontend/backend architecture

Phase 3 – MVP

Build only:

* manager
* dashboard
* application catalog
* process manager
* installer
* storage configuration
* Prowlarr
* Sonarr
* Radarr
* SABnzbd
* qBittorrent
* Jellyfin
* Seerr

Then implement automatic integration.

Phase 4

Add:

* Plex
* NZBGet
* Bazarr
* Unpackerr
* Recyclarr
* Profilarr
* NeutArr

Phase 5

Add:

* VPN
* additional *Arr applications
* maintenance applications
* backup system
* advanced monitoring

⸻

38. Important: don’t copy DUMB blindly

The goal is:

Inspired by DUMB

NOT:

Clone DUMB

Analyze what DUMB does well and reproduce the useful architectural concepts.

Do not copy code unless the license explicitly permits it and doing so is appropriate.

Improve the architecture where appropriate.

⸻

39. User experience goal

The final experience should feel like installing an appliance.

The user should ideally be able to go from:

"I have a new NAS"

to:

"My complete media server is running"

with as little manual configuration as possible.

The user should NOT need to understand:

* Docker networking
* container-to-container networking
* manually creating API connections
* manually creating download client entries
* manually synchronizing indexers
* manually configuring every *Arr application

The manager should handle these things.

⸻

40. Final product vision

The final product should essentially be:

“DUMB for traditional Usenet + Torrents”

without:

* Debrid
* Real-Debrid
* Zurg
* Riven
* Decypharr
* custom torrent downloader
* custom Usenet downloader

Instead use mature existing applications:

SABnzbd / NZBGet
         +
    qBittorrent
         +
      Prowlarr
         +
  Sonarr / Radarr
         +
Bazarr / Unpackerr
         +

Recyclarr / Profilarr / NeutArr
+
Jellyfin / Plex
+
Seerr

The AIO manager is responsible for making all of these applications work together.

⸻

41. First task

Do NOT start implementing the application yet.

First:

1. Research the current DUMB architecture.
2. Research how its managed services are installed and executed.
3. Compare that architecture with the requirements above.
4. Identify what should be copied conceptually.
5. Identify what should be improved.
6. Identify technical limitations on Synology, Unraid and TrueNAS.
7. Propose the final architecture.
8. Create ARCHITECTURE.md.
9. Create a development roadmap.
10. Only after that ask for approval to begin implementation.

The architecture must prioritize:

simplicity
reliability
low resource usage
NAS compatibility
automatic configuration
easy updates
recoverability
security
modularity

The most important design principle is:

One AIO manager, many managed applications — not many Docker containers managed by another Docker manager.