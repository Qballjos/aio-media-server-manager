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

When the process is up, open `http://<host>:8080` and follow [Usage](USAGE.md). After `docker compose pull`, recreate the container so published WebUI ports and the Python 3.13 child runtime (Bazarr) match the current image.

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

The manager UI listens on **8080**. Child applications bind in the same container. Compose, the Synology project file, Unraid XML, and the Docker run example publish their WebUI ports on the host so **Open UI** on the dashboard works (`http://<host>:8989` for Sonarr, and so on). Host networking is an alternative if you prefer not to map each port. An older compose file that only mapped `8080` will leave child UIs unreachable until you copy the current `ports:` list and recreate.

| Application | Default port |
|-------------|--------------|
| Manager UI | 8080 |
| qBittorrent | 8081 |
| Shelfmark | 8084 |
| SABnzbd | 8085 |
| Jellyfin | 8096 |
| Flaresolverr | 8191 |
| Bazarr | 6767 |
| NZBGet | 6789 |
| Profilarr | 6868 |
| Lidarr | 8686 |
| Sonarr | 8989 |
| Radarr | 7878 |
| Prowlarr | 9696 |
| Seerr | 5055 |
| Grimmory | 6060 |
| NeutArr | 9705 |
| Recyclarr | 19001 |
| Plex | 32400 |

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
