# AIO Media Server Manager

**TV Thuis:** connect your Android / Google TV launcher with a one-use pairing link from
**Settings → Account → TV connections**. See [pairing and API details](docs/tv-thuis.md).

<p align="center">
  <img src="logo-aio-media-manager.png" alt="AIO Media Server Manager" width="128" />
</p>

<p align="center">
  <strong>One install for your whole home media stack.</strong><br />
  Sonarr, Radarr, download clients, and players run inside a single appliance — not a container per app.
</p>

<p align="center">
  <a href="https://qballjos.github.io/aio-media-server-manager/"><img src="https://img.shields.io/badge/docs-GitHub%20Pages-0F6FFF?logo=gitbook&logoColor=white" alt="Docs"></a>
  <a href="https://github.com/Qballjos/aio-media-server-manager/actions/workflows/ci.yml"><img src="https://github.com/Qballjos/aio-media-server-manager/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Qballjos/aio-media-server-manager/pkgs/container/aio-media-server-manager"><img src="https://img.shields.io/badge/GHCR-aio--media--server--manager-0F6FFF" alt="GHCR"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-2ea44f.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/arch-amd64%20%7C%20arm64-informational" alt="linux/amd64 and linux/arm64">
  <img src="https://img.shields.io/badge/vibe%20coded-yes-ff69b4" alt="Vibe coded">
  <a href="https://www.paypal.com/donate/?business=P8CTXW8ER3PBY&amp;no_recurring=0&amp;item_name=Sponsor+My+Next+Bug&amp;currency_code=EUR"><img src="https://img.shields.io/badge/Donate-PayPal-00457C?logo=paypal&amp;logoColor=white" alt="Donate with PayPal"></a>
  <a href="https://ko-fi.com/qballjos"><img src="https://img.shields.io/badge/Ko--fi-qballjos-FF5E5B?logo=kofi&amp;logoColor=white" alt="Donate on Ko-fi"></a>
</p>

You run **one** Docker container (or one native Linux service). AIO installs the apps you choose, starts them, wires folders and APIs together, and gives you one web dashboard. There is no per-app Compose stack and no Debrid functionality.

**This project was vibe coded** — built with AI pair-programming in Cursor, guided by a human who wanted one appliance instead of a Compose novel. Expect a fast-moving stack; issues and PRs are welcome when something feels off.

🤖 AI writes some code. I break it. We fix it together.

Can’t spare a few bucks? Drop a star on GitHub instead. It feeds the ego, and that’s almost as good.

---

## Screenshots

Light is on the left, dark is on the right. Visuals, catalog app settings, and the other Settings sections are in the [usage guide](docs/USAGE.md#screens).

<p align="center">
  <img src="docs/screenshots/light/login.png" alt="Administrator sign-in, light theme" width="440" />
  <img src="docs/screenshots/dark/login.png" alt="Administrator sign-in, dark theme" width="440" />
</p>

<p align="center"><em>Sign-in.</em></p>

<p align="center">
  <img src="docs/screenshots/light/dashboard.png" alt="Home before any applications are installed, light theme" width="440" />
  <img src="docs/screenshots/dark/dashboard.png" alt="Home before any applications are installed, dark theme" width="440" />
</p>

<p align="center"><em>Home — before any apps with a WebUI are installed.</em></p>

<p align="center">
  <img src="docs/screenshots/light/catalog.png" alt="Catalog with application cards and install controls, light theme" width="440" />
  <img src="docs/screenshots/dark/catalog.png" alt="Catalog with application cards and install controls, dark theme" width="440" />
</p>

<p align="center"><em>Catalog — search, filters, and install for each app.</em></p>

<p align="center">
  <img src="docs/screenshots/light/settings.png" alt="Settings account page, light theme" width="440" />
  <img src="docs/screenshots/dark/settings.png" alt="Settings account page, dark theme" width="440" />
</p>

<p align="center"><em>Settings — account. The other sections are in the usage guide.</em></p>

---

## Why this exists

Most *Arr setups turn into a long Compose file: one container for Sonarr, one for Radarr, one for qBittorrent, and so on. This project treats the stack as **one appliance** you install once.

| You get | You do not get |
|---------|----------------|
| One image, one process tree | A generator of per-app containers |
| Automatic wiring between indexers, downloaders, and libraries | Debrid services or cloud remotes |
| A first-run wizard for the apps you actually want | A second Docker network per service |
| `linux/amd64` and `linux/arm64` (NAS-friendly) | Kubernetes or extra brokers |

---

## Features

**Lifecycle.** Start, stop, restart, crash-loop detection, leftover-process reclaim, log tails, and graceful shutdown. Uninstall stops the process, then removes its install tree.

**Install and catalog.** GitHub releases, official binaries (Jellyfin, Plex), and PyPI applications. The catalog and first-run wizard only list applications that support the host CPU architecture (Flaresolverr is x86_64-only).

**First-run wizard.** Choose *Arr apps, download clients (including Usenet provider fields), media servers, VPN, an optional Cloudflare Tunnel, and recommended tools. The tunnel and the VPN start as soon as the wizard finishes. On later boots the dashboard answers while apps start in the background: VPN first (torrent apps wait for a live handshake), then download clients, then the rest, Cloudflare Tunnel last. Persist paths and credentials, then install. Administrator setup requires an email address.

**Shared local login.** The manager admin username, email, and password are applied to apps that support a local account (*Arr, download clients, Bazarr, Jellyfin). Seerr's admin is created by signing in with that Jellyfin account (or the claimed Plex token), and its first-run wizard is completed for you. Plex still uses a Plex account.

**Automatic wiring.** After an app is healthy — or when you click **Auto-Wire** — the manager configures categories, root folders, download clients in Sonarr/Radarr, Prowlarr sync, Seerr, Bazarr pairing, and starter configs for Recyclarr and NeutArr. Settings → Usenet holds the Usenet provider (server, port, SSL, login, connections) and sends it to SABnzbd and NZBGet; NZB indexers are added in Prowlarr. Prowlarr also gets a starter set of public indexers (1337x, The Pirate Bay, YTS, Nyaa.si, LimeTorrents, Knaben) with seed settings (ratio 1, 48 hours, season packs 7 days), and FlareSolverr is attached to the ones Cloudflare blocks. Remove any you do not want; they are not added back.

**Home.** A grid with its own layout on phone, tablet, and desktop: greeting, search, calendar, downloading, recently added, requests, trending, now playing, storage, server, and needs attention, plus an app dock. Recently added and Trending keep loading as you scroll (Jellyfin recently added walks the library; Plex stays on its latest 20). The Server card shows the host's network traffic when `/sys` is mounted read-only at `/host/sys`. Arrange widgets with the layout control on the Home tab. The dock is shown or hidden under **Settings → Homepage**. Widget diagnostics live under **Settings → Diagnostics** (empty tiles explained; API keys never shown).

**Visuals.** Dark / light / system theme, accent color, wallpaper, custom header title, and replaceable header icon, login logo, and favicon under **Settings → Visuals**.

**Notifications.** Settings → Notifications sends Discord and email when an app crash-loops, the VPN or Cloudflare tunnel drops, an update is available, or a disk passes 90% full, and again when it recovers.

**Operations.** `config` / `downloads` / `media` with `PUID` / `PGID` and hardlink checks. Optional WireGuard or OpenVPN isolation for qBittorrent, Prowlarr, and Flaresolverr (Usenet stays off the tunnel), with a local DNS cache for those apps so brief tunnel DNS failures do not take Prowlarr indexers offline. Optional VAAPI / QSV / NVIDIA transcoding. Optional Cloudflare Tunnel (`cloudflared` inside this appliance; starts after apps on boot). Configuration backups with verify, per-app restore, and a schedule.

**Open UI.** Each catalog card opens `http://<host>:<app-port>`. On the LAN, apps with a local login (Sonarr, Radarr, Lidarr, Prowlarr, qBittorrent, SABnzbd, Bazarr, Seerr) open already signed in as the manager admin: the manager signs in server-side and hands the session to your browser. Jellyfin, Plex, and NZBGet keep their own login, and so does every app on public subdomains. Compose and the NAS templates publish those ports; host networking is an alternative. qBittorrent uses [VueTorrent](https://github.com/VueTorrent/VueTorrent) by default (same port and WebAPI). Catalog → qBittorrent → Settings can switch to the stock WebUI or **Update VueTorrent** (re-downloads the latest UI zip; not part of Catalog app updates). Catalog → NeutArr → Settings shows NeutArr's first-run setup token while `/config/neutarr/.setup-token` exists. NeutArr removes that file after account creation.

---

## Application catalog

Sixteen applications are defined. Install only what you select. Entries that cannot run on the current architecture are omitted from the catalog and the wizard.

| Role | Applications |
|------|----------------|
| Indexers | Prowlarr, Flaresolverr (x86_64) |
| Automation | Sonarr, Radarr, Lidarr |
| Downloaders | SABnzbd, NZBGet, qBittorrent (VueTorrent WebUI by default) |
| Media servers | Jellyfin, Plex (may share the same libraries) |
| Requests | Seerr, Shelfmark |
| Books | Grimmory |
| Subtitles | Bazarr |
| Profiles | Recyclarr, NeutArr |

Each catalog card includes a help control that opens that project's official documentation.

---

## Documentation

**Start here:** [qballjos.github.io/aio-media-server-manager](https://qballjos.github.io/aio-media-server-manager/)  
(Plain-language guides, published from this repo with GitHub Pages.)

| Guide | What it covers |
|-------|----------------|
| [Install](docs/INSTALL.md) | Folders, ports, which platform guide to open |
| [Using the dashboard](docs/USAGE.md) | First run, Home, Settings, Open UI, updates |
| [Docker](deploy/DOCKER.md) | Recommended way to run AIO |
| [Linux](deploy/LINUX.md) · [Unraid](deploy/UNRAID.md) · [Synology](deploy/SYNOLOGY.md) · [TrueNAS](deploy/TRUENAS.md) | Platform-specific steps |
| [Cloudflare Tunnel](deploy/CLOUDFLARE.md) | Remote HTTPS without opening router ports |
| [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md) | Login gate on those public URLs |
| [Contributing](CONTRIBUTING.md) | Development workflow |

Local preview: `bash scripts/prepare-docs-site.sh && pip install -r requirements-docs.txt && mkdocs serve`

---

## Install

Create the library folders in your home (downloads and media as children of **one** folder so hardlinks work and the file manager can see them), clone this repo for the compose file, then start the published image.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
mkdir -p "$HOME/aio-media-manager/downloads" "$HOME/aio-media-manager/media" config backups
docker compose pull
docker compose up -d
```

Open `http://<host>:8080`. Create the administrator (username, email, password), complete the stack wizard, then use Catalog for anything you skipped.

That compose file mounts `./config`, `./backups`, and `$HOME/aio-media-manager` as `/data`, and host `/sys` read-only at `/host/sys` so Home's Server card counts the host's network cards. `PUID` and `PGID` in the file default to `1000` — set them to the output of `id` before the first start. A plain `docker run`, NAS layouts, and `/opt` paths are in the platform guides.

Image tags: `latest` (main), `sha-<git>`, and semver when a `v*` tag is pushed. Architectures: `linux/amd64`, `linux/arm64`. The manager runs on Python 3.14. Child runtimes on both architectures: Python 3.13 (Bazarr / SABnzbd), Python 3.14 (Shelfmark), Node 22 (Seerr), JRE 25 and MariaDB (Grimmory), jellyfin-ffmpeg (Jellyfin HW) plus stock ffmpeg (Plex / tools), git (Recyclarr). Chromium/Xvfb ship only on `linux/amd64` for Flaresolverr. After a pull, **recreate** the container so new port mappings and runtimes take effect. That updates AIO. Sonarr, Seerr, and the other apps update from **Settings → Updates** (schedules default to off).

Full steps: [docs/INSTALL.md](docs/INSTALL.md) · [deploy/DOCKER.md](deploy/DOCKER.md).

---

## Development

The appliance is a **Linux container**. Catalog installs (Sonarr, Jellyfin, qBittorrent-nox, Flaresolverr, and others) are Linux binaries. Do not run the manager natively on macOS or Windows to test installs.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
./scripts/test-env.sh up
```

Open **http://127.0.0.1:8080**. Data for this run is under `.docker-test/` (gitignored). Stop with `./scripts/test-env.sh down`. Remove `.docker-test/` to wipe test config and libraries.

| URL | Purpose |
|-----|---------|
| http://127.0.0.1:8080 | Manager UI (dashboard built into the image) |
| http://127.0.0.1:8080/docs | OpenAPI |

Optional live Vue reload (API still in Docker): `cd frontend && npm ci && npm run dev`, then use **http://127.0.0.1:5173**. Unit tests: `poetry run pytest`. Full workflow: [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📌 Intended Use & Disclaimer

### What This Project Is For
This project is designed solely as a self-hosting management tool and deployment stack to help users automate, configure, and manage personal media servers and lab infrastructure. It is intended for:
* Managing personal digital libraries and media legally owned by the user (e.g., home videos, family photos, public domain content, or personal physical backups).
* Streamlining local network setup, container management, and server administration for home lab enthusiasts.

### What This Project Is NOT For
* **Not for illegal downloading or piracy:** This repository does not host, provide, or distribute copyrighted content, nor is it designed to encourage copyright infringement.
* **Not a license or legal shield:** Using this software stack to acquire, download, stream, or distribute unauthorized copyrighted material violates copyright laws in most jurisdictions. Users are solely responsible for ensuring their usage complies with all local, state, and international laws.

---

## Security

Report vulnerabilities through [GitHub private advisories](https://github.com/Qballjos/aio-media-server-manager/security/advisories/new), not public issues.

---

## License

[MIT](LICENSE)

## Homey dashboard integration

Homey can pair with AIO using a five-minute, one-use code from **Settings → Homey connections**. Each connection gets its own revocable, read-only dashboard credential. No admin password, TV credential or media-server key is exported. The companion Homey app shows server status, Now playing and Recently added widgets. See [Homey protocol and setup](docs/homey.md).
