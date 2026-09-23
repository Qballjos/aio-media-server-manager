# Installation

AIO Media Server Manager is **one appliance**. The manager and every *Arr app, downloader, and media server run as supervised processes inside it. Do not deploy a Compose service or NAS app per application.

**Published image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Architectures:** `linux/amd64`, `linux/arm64`

## Platform guides

| Platform | Guide |
|----------|--------|
| Docker / Compose (recommended) | [deploy/DOCKER.md](../deploy/DOCKER.md) |
| Native Linux / LXC / systemd | [deploy/LINUX.md](../deploy/LINUX.md) |
| Unraid | [deploy/UNRAID.md](../deploy/UNRAID.md) |
| Synology DSM (Container Manager) | [deploy/SYNOLOGY.md](../deploy/SYNOLOGY.md) |
| TrueNAS SCALE | [deploy/TRUENAS.md](../deploy/TRUENAS.md) |
| Cloudflare Tunnel (optional) | [deploy/CLOUDFLARE.md](../deploy/CLOUDFLARE.md) |

When the process is up, open `http://<host>:8080` and follow [Usage](USAGE.md).

## Host directories

SSH into the host and create the bind mounts. Keep **downloads and media in one host folder** (same filesystem, and on btrfs the same subvolume) so *Arr can hardlink instead of copy.

```bash
ssh user@host

sudo mkdir -p /path/to/config /path/to/data/downloads /path/to/data/media /path/to/config/vpn
sudo chown -R "$PUID:$PGID" /path/to/config /path/to/data
id   # use this if you do not yet know PUID/PGID
```

The appliance then creates library layout inside those mounts, for example:

- `media/{tv,movies,anime,music,books}`
- `downloads/{complete,incomplete,torrents}/…`
- `cache/transcode/{jellyfin,plex}`

Those paths are wired into Sonarr, Radarr, Lidarr, download clients, Jellyfin, and Plex.

## Requirements

- Disk for **config**, **downloads**, and **media**
- Media-user UID/GID (`id`) mapped as `PUID` / `PGID`
- Optional: `/dev/dri` or NVIDIA devices for hardware transcoding
- Optional: `NET_ADMIN` (or a privileged container) plus a WireGuard or OpenVPN profile if torrent traffic should use a VPN

## Ports

The manager UI listens on **8080**. Child applications bind inside the same appliance. Publish the ports you need, or run with host networking.

| Application | Default port |
|-------------|--------------|
| Manager UI | 8080 |
| qBittorrent | 8081 |
| Shelfmark | 8084 |
| SABnzbd | 8085 |
| Jellyfin | 8096 |
| Tautulli | 8181 |
| Flaresolverr | 8191 |
| Maintainerr | 6246 |
| Bazarr | 6767 |
| NZBGet | 6789 |
| Profilarr | 6868 |
| Autobrr | 7474 |
| Lidarr | 8686 |
| Sonarr | 8989 |
| Radarr | 7878 |
| Prowlarr | 9696 |
| Seerr | 5055 |
| Grimmory | 6060 |
| NeutArr | 9705 |
| Cleanuparr | 11083 |
| Plex | 32400 |

Unpackerr, Recyclarr, Kometa, and Mylar3 use the ports shown on their catalog cards.

## Development clone

Use a git checkout only when changing the code. Production should use the GHCR image or a tagged release.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
cp .env.example .env
poetry install
cd frontend && npm ci && npm run build && cd ..
poetry run python main.py
```
