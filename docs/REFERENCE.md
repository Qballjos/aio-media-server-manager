# Advanced: ports and settings

[Beginner guide](INSTALL.md) · [Advanced](ADVANCED.md)

## Ports {#ports}

The manager UI uses **8080**. Child apps listen inside the same container. Compose and NAS templates publish those ports on the host so **Open UI** works (`http://YOUR-IP:8989` for Sonarr, and so on). Host networking is an alternative if you prefer not to map each port.

| Application | Default port |
|-------------|--------------|
| <img src="__AIO_ASSET__/assets/logo-aio-media-manager.png" alt="" class="aio-app-icon" /> Manager UI | 8080 |
| <img src="__AIO_ASSET__/assets/app-icons/qbittorrent.svg" alt="" class="aio-app-icon" /> qBittorrent | 8081 |
| <img src="__AIO_ASSET__/assets/app-icons/shelfmark.png" alt="" class="aio-app-icon" /> Shelfmark | 8084 |
| <img src="__AIO_ASSET__/assets/app-icons/sabnzbd.svg" alt="" class="aio-app-icon" /> SABnzbd | 8085 |
| <img src="__AIO_ASSET__/assets/app-icons/jellyfin.svg" alt="" class="aio-app-icon" /> Jellyfin | 8096 |
| <img src="__AIO_ASSET__/assets/app-icons/flaresolverr.png" alt="" class="aio-app-icon" /> Flaresolverr | 8191 (x86_64 only) |
| <img src="__AIO_ASSET__/assets/app-icons/bazarr.svg" alt="" class="aio-app-icon" /> Bazarr | 6767 |
| <img src="__AIO_ASSET__/assets/app-icons/nzbget.svg" alt="" class="aio-app-icon" /> NZBGet | 6789 |
| <img src="__AIO_ASSET__/assets/app-icons/lidarr.svg" alt="" class="aio-app-icon" /> Lidarr | 8686 |
| <img src="__AIO_ASSET__/assets/app-icons/sonarr.svg" alt="" class="aio-app-icon" /> Sonarr | 8989 |
| <img src="__AIO_ASSET__/assets/app-icons/radarr.svg" alt="" class="aio-app-icon" /> Radarr | 7878 |
| <img src="__AIO_ASSET__/assets/app-icons/prowlarr.svg" alt="" class="aio-app-icon" /> Prowlarr | 9696 |
| <img src="__AIO_ASSET__/assets/app-icons/seerr.svg" alt="" class="aio-app-icon" /> Seerr | 5055 |
| <img src="__AIO_ASSET__/assets/app-icons/grimmory.svg" alt="" class="aio-app-icon" /> Grimmory | 6060 |
| <img src="__AIO_ASSET__/assets/app-icons/neutarr.svg" alt="" class="aio-app-icon" /> NeutArr | 9705 |
| <img src="__AIO_ASSET__/assets/app-icons/cleanuparr.svg" alt="" class="aio-app-icon" /> Cleanuparr | 11011 |
| <img src="__AIO_ASSET__/assets/app-icons/recyclarr.svg" alt="" class="aio-app-icon" /> Recyclarr | none (CLI only) |
| <img src="__AIO_ASSET__/assets/app-icons/plex.svg" alt="" class="aio-app-icon" /> Plex | 32400 |

## Common environment variables

Copy [`.env.example`](../.env.example) for native installs. Many of these can also be set later in **Settings**.

| Variable | Purpose |
|----------|---------|
| `PUID` / `PGID` | User the apps run as (match folder ownership) |
| `TZ` / `AMM_TIMEZONE` | Timezone for logs and schedules |
| `AMM_DOWNLOAD_DIR` / `AMM_MEDIA_DIR` | Paths inside the container (change host mounts in compose) |
| `GITHUB_TOKEN` | Optional; higher GitHub API limits for updates |
| `AMM_CLOUDFLARE_TUNNEL_*` | Optional remote tunnel (`cloudflared` starts after apps on boot) |
| `AMM_VPN_*` | Optional VPN for qBittorrent, Prowlarr, and Flaresolverr (they wait for the tunnel; local DNS cache for those apps) |
| `AMM_SECURE_COOKIES` | Set to `true` when the manager is served over HTTPS; default `false` for LAN HTTP. |
| `AMM_PREFLIGHT_MIN_FREE_MB` | Minimum free MiB required on storage paths before installation/update; default `512`. |
| `AMM_BACKUP_RECOVERY_TOKEN` | Optional operator recovery secret of at least 32 characters, only before a working admin account. Remove after recovery; see the security guide. |

- [Installation checks, external backups and recovery](operations.md)
- [Sessions, HTTPS and emergency recovery](security-operations.md)
