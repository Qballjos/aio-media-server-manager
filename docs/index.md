# AIO Media Server Manager

**One Linux appliance for a complete Usenet and BitTorrent media stack.**

Install, supervise, and wire every application as a process inside a single container (or native Linux service) — not a Compose file per app.

<p align="center">
  <img src="screenshots/dashboard.png" alt="Catalog dashboard" width="820" />
</p>

## Start here

| Guide | When to read it |
|-------|-----------------|
| [Installation](INSTALL.md) | Host folders, ports, and which platform guide to follow |
| [Usage](USAGE.md) | First-run wizard, Home, Catalog, Auto-Wire, Settings |
| [Docker](deploy/DOCKER.md) | Recommended deployment |

## Platforms

| Platform | Guide |
|----------|--------|
| Docker / Compose | [DOCKER.md](deploy/DOCKER.md) |
| Native Linux / LXC | [LINUX.md](deploy/LINUX.md) |
| Unraid | [UNRAID.md](deploy/UNRAID.md) |
| Synology | [SYNOLOGY.md](deploy/SYNOLOGY.md) |
| TrueNAS SCALE | [TRUENAS.md](deploy/TRUENAS.md) |

## Remote access

| Topic | Guide |
|-------|--------|
| Cloudflare Tunnel | [CLOUDFLARE.md](deploy/CLOUDFLARE.md) |
| Cloudflare Access (login gate) | [CLOUDFLARE_ACCESS.md](deploy/CLOUDFLARE_ACCESS.md) |

## Project links

- [GitHub repository](https://github.com/Qballjos/aio-media-server-manager)
- [Container image (GHCR)](https://github.com/Qballjos/aio-media-server-manager/pkgs/container/aio-media-server-manager)
- [Contributing](https://github.com/Qballjos/aio-media-server-manager/blob/main/CONTRIBUTING.md)
- [Security advisories](https://github.com/Qballjos/aio-media-server-manager/security/advisories/new)

Published image: `ghcr.io/qballjos/aio-media-server-manager:latest` (`linux/amd64`, `linux/arm64`).
