# Installation

AIO Media Server Manager is **one appliance**: the manager plus every *Arr app, downloader, and media server run as supervised processes. Do not deploy a Compose stack or NAS app per application.

Published image: `ghcr.io/qballjos/aio-media-server-manager:latest` (`linux/amd64` and `linux/arm64`).

| Platform | Guide |
|----------|--------|
| Docker / Compose | [deploy/DOCKER.md](../deploy/DOCKER.md) |
| Native Linux / LXC / systemd | [deploy/LINUX.md](../deploy/LINUX.md) |
| Unraid | [deploy/UNRAID.md](../deploy/UNRAID.md) |
| Synology DSM (Container Manager project) | [deploy/SYNOLOGY.md](../deploy/SYNOLOGY.md) |
| TrueNAS SCALE | [deploy/TRUENAS.md](../deploy/TRUENAS.md) |
| Cloudflare Tunnel (optional) | [deploy/CLOUDFLARE.md](../deploy/CLOUDFLARE.md) |

After the process is running, open `http://<host>:8080` and complete the first-run wizard.

## Create folders over SSH

SSH into the host first, then create the three bind-mount directories (adjust the paths for your NAS). Same filesystem for downloads and media is recommended so hardlinks work.

```bash
ssh user@host

sudo mkdir -p /path/to/config /path/to/downloads /path/to/media /path/to/config/vpn
sudo chown -R "$PUID:$PGID" /path/to/config /path/to/downloads /path/to/media
# If you do not know PUID/PGID yet:
id
```

Platform path examples and full commands: [Docker](../deploy/DOCKER.md), [Linux](../deploy/LINUX.md), [Unraid](../deploy/UNRAID.md), [Synology](../deploy/SYNOLOGY.md), [TrueNAS](../deploy/TRUENAS.md).

The appliance then creates library subfolders inside those mounts (`media/{tv,movies,anime,music,books}`, `downloads/{complete,incomplete,torrents}/…`, `cache/transcode/{jellyfin,plex}`) and wires them into Sonarr, Radarr, Lidarr, download clients, Jellyfin, and Plex.

## What you need

- Storage for **config**, **downloads**, and **media** (same filesystem recommended so hardlinks work).
- A media user UID/GID (`id`) for `PUID` / `PGID`.
- Optional: `/dev/dri` (or NVIDIA devices) for hardware transcoding.
- Optional: `NET_ADMIN` / privileged container and a WireGuard or OpenVPN profile for qBittorrent-only VPN.

## Ports

The manager UI is **8080**. Child apps bind inside the same appliance (Sonarr 8989, Radarr 7878, Prowlarr 9696, qBittorrent 8081, SABnzbd 8085, Jellyfin 8096, Seerr 5055, Plex 32400, and others). Publish those ports, or run the container with host networking.

## Development clone

Use this only if you are changing the code. Production installs should use the GHCR image or a tagged release.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
cp .env.example .env
poetry install
cd frontend && npm ci && npm run build && cd ..
poetry run python main.py
```
