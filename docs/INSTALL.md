# Installation

AIO Media Server Manager is **one appliance**. The manager and every *Arr app, downloader, and media server run as supervised processes inside it. Do not deploy a Compose service or NAS app per application.

**Published image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Architectures:** `linux/amd64`, `linux/arm64`

The ARM64 image does not install Chromium, Xvfb, or fonts-liberation. Flaresolverr is x86_64-only and is hidden on ARM hosts. Shared runtimes stay on both architectures: Python 3.13 (Bazarr / SABnzbd), Node 22 (Seerr), JRE 25 and MariaDB (Grimmory), ffmpeg (Jellyfin / Plex).

## Platform guides

| Platform | Guide |
|----------|--------|
| Docker / Compose (recommended) | [deploy/DOCKER.md](../deploy/DOCKER.md) |
| Native Linux / LXC / systemd | [deploy/LINUX.md](../deploy/LINUX.md) |
| Unraid | [deploy/UNRAID.md](../deploy/UNRAID.md) |
| Synology DSM (Container Manager) | [deploy/SYNOLOGY.md](../deploy/SYNOLOGY.md) |
| TrueNAS SCALE | [deploy/TRUENAS.md](../deploy/TRUENAS.md) |
| Cloudflare Tunnel (optional) | [deploy/CLOUDFLARE.md](../deploy/CLOUDFLARE.md) |

When the process is up, open `http://<host>:8080` and follow [Usage](USAGE.md). After `docker compose pull`, recreate the container so published WebUI ports, the Python 3.13 child runtime (Bazarr), and Debian `unrar` (SABnzbd) match the current image.

## Host directories

SSH into the host and create the bind mounts. Keep **downloads and media in one folder under the login home** (same filesystem, and on btrfs the same subvolume) so *Arr can hardlink instead of copy and so the file manager can see the library.

```bash
ssh user@host

mkdir -p "$HOME/aio-media-manager/downloads" "$HOME/aio-media-manager/media"
sudo mkdir -p /path/to/config /path/to/config/vpn /path/to/backups
sudo chown -R "$PUID:$PGID" "$HOME/aio-media-manager" /path/to/config /path/to/backups
id   # use this if you do not yet know PUID/PGID
```

Mount `/path/to/backups` at `/backups` for configuration archives. Ideally it sits on a different disk or share than `config`. Without that mount, backups fall back to `/config/backups`.

The appliance then creates library layout inside those mounts, for example:

- `media/{tv,movies,anime,music,books}`
- `downloads/{complete,incomplete,torrents}/…`
- `cache/transcode/{jellyfin,plex}`

Those paths are wired into Sonarr, Radarr, Lidarr, download clients, Jellyfin, and Plex.

## Requirements

- **Config** — small; manager and application settings
- **Downloads and media** — sized for your library; keep them as siblings on one filesystem for hardlinks
- **Backups** — configuration archives (not media); map `/backups` if possible
- Media-user UID/GID (`id`) mapped as `PUID` / `PGID`
- Optional: `/dev/dri` or NVIDIA devices for hardware transcoding
- Optional: `NET_ADMIN` (or a privileged container) plus a WireGuard or OpenVPN profile if torrent traffic should use a VPN

## Ports

The manager UI listens on **8080**. Child applications bind in the same container. Compose, the Synology project file, Unraid XML, and the Docker run example publish their WebUI ports on the host so **Open UI** on the catalog works (`http://<host>:8989` for Sonarr, and so on). Host networking is an alternative if you prefer not to map each port. An older compose file that only mapped `8080` will leave child UIs unreachable until you copy the current `ports:` list and recreate.

| Application | Default port |
|-------------|--------------|
| Manager UI | 8080 |
| qBittorrent | 8081 |
| Shelfmark | 8084 |
| SABnzbd | 8085 |
| Jellyfin | 8096 |
| Flaresolverr | 8191 (x86_64 only; omitted on ARM64) |
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
| Recyclarr | none (CLI; not published on the host) |
| Plex | 32400 |

## Environment

Copy [`.env.example`](../.env.example) for a native install. Compose bind-mounts `$HOME/aio-media-manager` as `/data` and sets `PUID` / `PGID`, `TZ`, and the in-container `/data` paths. Values you change in **Settings** (timezone, log level, PUID, VPN, update schedules) persist in `/config/amm_config.json`. Environment variables still win when they are set in compose.

| Variable | Purpose |
|----------|---------|
| `PUID` / `PGID` | Child process user (also Settings → System) |
| `TZ` / `AMM_TIMEZONE` | Clock, logs, scheduled updates (also Settings → System) |
| `AMM_LOG_LEVEL` | Root log level |
| `AMM_DOWNLOAD_DIR` / `AMM_MEDIA_DIR` | Bind paths — change mounts in compose, not the UI |
| `AMM_API_HOST` / `AMM_API_PORT` | Manager listen address (compose/env only) |
| `GITHUB_TOKEN` | Optional; also Settings → Updates (not written back to compose) |
| `AMM_UPDATE_CHECK_SCHEDULE` | `off` / `daily` / `weekly` / `monthly` |
| `AMM_UPDATE_APPLY_SCHEDULE` | `off` / `same` / `daily` / `weekly` / `monthly` |
| `AMM_UPDATE_TIME` | `HH:MM` in the host timezone |
| `AMM_CLOUDFLARE_TUNNEL_*` | Optional tunnel; also Settings → Network |
| `AMM_VPN_*` | Optional VPN for qBittorrent, Prowlarr, and Flaresolverr; also Settings → Network |

## Development clone

Use a git checkout only when changing the code. **Run that checkout in Docker** so catalog installs get Linux binaries (same as production). Do not start the manager with Poetry on macOS or Windows for install/start testing.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
./scripts/test-env.sh up
```

Open `http://127.0.0.1:8080`. Stop with `./scripts/test-env.sh down`. Test data stays in `.docker-test/` until you delete that directory. Details: [Contributing](../CONTRIBUTING.md).

Native Linux / LXC without Docker is documented in [deploy/LINUX.md](../deploy/LINUX.md).
