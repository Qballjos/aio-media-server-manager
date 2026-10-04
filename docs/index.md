# AIO Media Server Manager

One app that runs your whole media stack — downloads, automation, and streaming — from a single dashboard.

You do **not** install Sonarr, Radarr, qBittorrent, and friends as separate containers. You install **this** once. It starts and manages those tools for you.

## Who this is for

- You want a media server at home (NAS, Unraid, Linux box, etc.)
- You would rather not wire up a big Docker Compose file by hand
- You want one place to see status, start apps, and open each web UI

## What you get

| Piece | What it does |
|-------|----------------|
| **Dashboard** | Overview of every app, quick links, health |
| ***Arr apps** | Find and organize TV, movies, music, subtitles |
| **Download clients** | Torrents and Usenet (when you enable them) |
| **Players / requests** | Jellyfin, Plex, Seerr, and similar — when you turn them on |
| **Optional VPN** | WireGuard or OpenVPN for the download path |
| **Optional Cloudflare** | Reach apps from outside your home with HTTPS |

## Pick a path

| I want to… | Start here |
|------------|------------|
| Install for the first time | [Install](INSTALL.md) |
| Learn the UI after it is running | [Using the dashboard](USAGE.md) |
| Run with Docker | [Docker](deploy/DOCKER.md) |
| Install on Unraid | [Unraid](deploy/UNRAID.md) |
| Install on Synology | [Synology](deploy/SYNOLOGY.md) |
| Install on TrueNAS | [TrueNAS](deploy/TRUENAS.md) |
| Install without Docker (Linux / LXC) | [Linux](deploy/LINUX.md) |
| Share apps on the internet safely | [Cloudflare Tunnel](deploy/CLOUDFLARE.md) → [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md) |

## The one rule that matters

**One AIO install = one container (or one native install).**  
Do not add separate Sonarr/Radarr/qBittorrent containers next to it. That fights this design and usually breaks networking or duplicates config.

## Source and image

- Code: [GitHub](https://github.com/Qballjos/aio-media-server-manager)
- Docker image: `ghcr.io/qballjos/aio-media-server-manager:latest`
