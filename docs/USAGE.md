# Usage

This guide covers what you do after the appliance is running. Installation and host paths are in [INSTALL.md](INSTALL.md). To try a git checkout, use `./scripts/test-env.sh up` (Linux container), not a native macOS or Windows process.

## 1. Create the administrator

The first visit to `http://<host>:8080` requires a local admin account: **username, email, and password**. The account protects the manager dashboard and API. Credentials are stored as a bcrypt hash, and an encrypted copy is kept so compatible applications (and **Seerr**) can use the same local identity.

Password rules: at least 8 characters, at most 72 bytes (bcrypt limit). You can change username, email, and password later under **Settings → Account** (current password required).

## Install on a phone or tablet

The manager is a **progressive web app**. After you sign in, you can pin it like a native app:

- **iPhone / iPad:** Safari → Share → **Add to Home Screen**.
- **Android (Chrome):** menu → **Install app**. Chromium shows an **Install** control in the header when the browser allows it. HTTPS is required for that prompt (Cloudflare Tunnel or a reverse proxy). On `http://nas-ip:8080` use the browser menu if Install appears.
- **Settings → Account** repeats these steps.

The home-screen icon is named **AIO Media** and opens Home / Catalog / Settings without the browser chrome.

## 2. First-run wizard

After sign-in, a 9-step wizard runs until you finish it or choose **Skip for now**. Skip is a short save; Home opens even if the API is busy with an install.

| Step | You choose |
|------|------------|
| 1 | Media, download, and config directories (same `/data` parent for hardlinks) |
| 2 | `PUID` / `PGID` (pre-filled from the host / compose user) |
| 3 | Download clients (SABnzbd, NZBGet, qBittorrent). Usenet host, port, SSL, username, password, and connections are saved for SABnzbd/NZBGet. qBittorrent username/password may be blank to reuse the manager admin login |
| 4 | VPN: none, PrivadoVPN-style isolation, or a custom WireGuard / OpenVPN profile (upload, paste, or path) |
| 5 | *Arr apps: Prowlarr, Sonarr, Radarr, Lidarr |
| 6 | Media servers: Jellyfin and/or Plex (optional Plex claim token) |
| 7 | Requests (Seerr) |
| 8 | Recommended tools (Bazarr on by default; Flaresolverr on x86_64 by default; Recyclarr, Profilarr, NeutArr, Grimmory, Shelfmark optional) |
| 9 | Review, then save and install |

**Finish** stays on the wizard and shows per-app install progress until each selected catalog install finishes (or fails). **Open Home** leaves the wizard while remaining installs continue in the background. Wiring (indexers, download clients, libraries, Seerr, Recyclarr sync) runs **after each app is installed and answers its health check**, not during the Finish request. Apps that are not installed or not running are skipped so *Arr is not pointed at a dead downloader. You can run the same wiring later with **Auto-Wire** on Catalog. The wizard and catalog omit applications the host architecture cannot run.

**Skip** opens **Home** without installing anything. You can install applications later from **Catalog**.

## 3. Home

After the wizard, **Home** is the front page for watching and requesting (`#/home`). It reuses the manager login. There are no start/stop/install controls here.

- **Launcher** lists installed apps that have a WebUI, grouped by category. Recyclarr and Flaresolverr are omitted (no household UI). Stopped apps still appear dimmed. A crash loop or failed process gets a red border and an Unhealthy label.
- **Recently added** is a horizontal poster rail from Jellyfin and/or Plex. A whole season added together shows as one season tile instead of every episode.
- **Requests** is the same kind of rail from Seerr (who asked, with artwork).
- **Coming up** is a Sonarr/Radarr calendar (time, title, SxxExx) with month/week/day/list views, previous/next, and a TV/movies/not-downloaded filter. The default view follows the screen: list on phones, week on laptops, month on large displays. Green marks files that are already on disk.
- **Downloading** uses SABnzbd, NZBGet, and/or qBittorrent queues and shows progress plus speed. It polls every 3 seconds, separately from the rest of Home.
- Jellyfin recently-added art uses the shared local login or a key from **Settings → Homepage**. Create the key in Jellyfin Dashboard → API Keys. Plex uses the local token when present.
- **Search** talks to Seerr when it is running. Each result shows whether it is **Available**, **Partly available**, **Requested**, or **Not in library**, with a **Get it now** button that sends a Seerr request. The manager reads `apiKey` from Seerr’s `settings.json`; if that fails, paste the key from Seerr Settings → General under **Settings → Homepage** (or Catalog → Seerr → Settings). If Seerr is missing or rejects the key, search falls back to Sonarr/Radarr lookup and shows the Seerr error above the results.
- **Widget debug** in **Settings → Homepage** (or `#/home?debug=1`) shows why a widget is empty: not installed, stopped, missing API key, HTTP error, timeout, or an empty API result. Keys are never shown.

Empty widgets stay hidden until debug is on. **Catalog** is still the admin dashboard for install, process controls, logs, and Auto-Wire.

The dashboard uses hash URLs so you can bookmark or refresh without losing your place: `#/home`, `#/catalog`, `#/settings/backups`. A link such as `#/catalog?q=sonarr&status=active&cat=automation&sort=az` restores search, status/category filters, and sort. After login the hash is kept, so a shared Settings or Catalog link still opens the right screen. Log and backup downloads use the same signed-in session as the rest of the UI.

## 4. Catalog

The catalog lists up to **17** applications at `#/catalog` (installed vs available counts are separate). Entries that do not support the host CPU architecture are hidden — for example Flaresolverr on ARM64, which also keeps Chromium out of the ARM64 image.

- Filter by **status** and **category**
- Sort by **popularity** or **A–Z**
- **Search** by name
- **?** opens that application's official wiki or documentation
- **Health** opens host CPU/RAM/disk graphs plus per-app CPU and memory
- **Install** fetches the upstream binary and starts the process when it is a daemon
- Installed apps: **Start** or **Stop**, **Open UI**, and **More** (Restart, Logs, Settings, Update, Uninstall)
- **Auto-Wire** (header) re-runs integration after apps are healthy: download clients in Sonarr/Radarr (qBittorrent and SABnzbd when installed), Prowlarr, Seerr, Bazarr, and a Recyclarr `sync` when Recyclarr is installed
- Catalog **Settings** on a card changes the listen **port** (persisted; running apps are restarted) and **start with the manager**. Config/install paths are shown read-only. Bind mounts still change in compose, not here
- Cards show **Update available** when a scheduled or manual check found a newer GitHub release. Manual **Update** still uses snapshot → install → health check → rollback

Process status on Catalog refreshes about every 5 seconds while that page is open. Catalog metadata, update, and backup summaries refresh about every 30 seconds. Home widgets poll every 15 seconds; the manager keeps the last snapshot in memory for about 30 seconds and refreshes it in the background so the page does not wait on Sonarr, Radarr, Jellyfin, Plex, and Seerr each time. **Downloading** is live (about every 3 seconds) and is not served from that cache. Background polls pause when the browser tab is hidden and catch up when you return. **Sync Status** still reloads everything at once.

**Open UI** uses `http://<host>:<app-port>` (for example Sonarr `8989`). That only works if the appliance compose/template publishes those ports, or the container uses host networking. Recreate the container after pulling an image that added port mappings. Recyclarr has no WebUI.

qBittorrent on localhost is allowed without the WebUI login prompt. **Open UI** from another LAN machine uses the manager username and password (seeded into `qBittorrent.conf` before start). Restart qBittorrent once after upgrading if an older run already created a temporary WebUI password. Auto-Wire applies VPN-safe client defaults (encryption preferred, LSD off, high connection limits, unlimited ratio/seed time so Sonarr/Radarr/Lidarr own seeding).

**VueTorrent:** Catalog → qBittorrent → Settings → **VueTorrent WebUI** downloads the latest [VueTorrent](https://github.com/VueTorrent/VueTorrent) zip and sets qBittorrent’s alternative WebUI folder (quoted absolute path, readable by PUID/PGID). Same listen port (`8081` by default) and the same WebAPI, so *Arr download clients keep working. Turn the switch off to return to the stock WebUI; the files stay on disk so you can enable it again without another download. If Open UI fails after enabling, turn VueTorrent off, save (qBittorrent restarts on the stock UI), then enable it again.

Bazarr runs on the bundled **Python 3.13** interpreter (not the manager’s 3.14), with Pillow and the rest of its requirements. Recreate the container from a current image if Bazarr previously failed with `PIL` / `ModuleNotFoundError`. Form login uses the manager username and password (Bazarr stores an MD5 hex of the password in YAML; type the same plaintext you used in the wizard).

SABnzbd needs the non-free Debian `unrar` package (RAR 5). Recreate the appliance image if you still see **UNRAR version is 0.00**. Helpful warnings are off in the bootstrap `sabnzbd.ini`.

## 5. Shared local login

When you create the admin (and again on later successful logins or account changes), the manager stores the username, password, and email in the encrypted secret store and applies them to applications that support a **local user**:

- Sonarr, Radarr, Lidarr, Prowlarr
- SABnzbd, NZBGet, qBittorrent
- Bazarr
- Jellyfin (a matching local Jellyfin user)
- Seerr (local admin from the manager email when Seerr is chosen in the wizard)
- Profilarr (first local user, when the register API is available)

These remain separate accounts inside each product. They are created to **match** the manager credentials; signing into the manager does not SSO into those UIs.

**Not a second login (use these as intended):**

- **Recyclarr** — CLI only (no Open UI, no login, no background daemon). See below.
- **NeutArr** — LAN access bypass is on for RFC1918, so Open UI from your home network should not ask you to invent an account. It hunts missing/upgrade items through the *Arr APIs. Create a NeutArr user only if you expose it beyond the LAN.
- **Profilarr** — `AUTH=local` skips login on the local network. Dictionarry still has its own first-user screen if you open it from a non-local address; use the manager username and password there. Styling needs the Vite `static` (or `client`) tree next to the binary after install. Instances are pre-filled for Sonarr/Radarr (and Lidarr when installed).
- **Plex** — Plex account or claim token
- **Flaresolverr** — no web login

Open **Open UI** on each app the first time to confirm that product's own setup finished (especially Jellyfin and Plex).

### Recyclarr (TRaSH Guides)

Recyclarr is a one-shot CLI. Auto-Wire and **Sync** on the catalog card run `recyclarr sync --config recyclarr.yml` with `RECYCLARR_CONFIG_DIR` (Recyclarr 8 dropped `--app-data`). It clones TRaSH Guides with **git**, then writes one Recyclarr instance per Sonarr/Radarr URL (multiple names on the same URL are skipped). Default TRaSH profiles: HD WEB-1080p, Anime Remux-1080p, and HD Bluray+WEB. 4K profiles are opt-in.

**Catalog → Recyclarr → Settings** toggles profiles, Plex/Jellyfin naming, YAML edit, and restore defaults. Custom YAML is kept until you restore defaults. Last-sync details appear on the debug share when diagnostics are on.

## 6. VPN and remote access

- Upload or paste a WireGuard (`.conf`) or OpenVPN (`.ovpn`) profile in the wizard or **Settings → Network**. It is written under `/config/vpn/` (`wg0.conf` or `client.ovpn`) with mode `600`. You can still point at an existing path. **qBittorrent**, **Prowlarr**, and **Flaresolverr** are tunneled. Usenet clients stay on the normal network. While VPN is enabled, those apps cannot use the house WAN: traffic must leave through the tunnel, and they are stopped if the tunnel is down. The top bar shows a **VPN** pill next to the clock (green when the tunnel is up, red when it is down). DNS for those apps is `/etc/netns/amm-torrent/resolv.conf` (from the profile’s `DNS` line, otherwise `1.1.1.1`). Docker’s `127.0.0.11` resolver is not used inside the tunnel. On NAS kernels without a WireGuard module (common on Synology), `wg-quick` uses **wireguard-go** in userspace. OpenVPN needs `/dev/net/tun` (privileged compose already provides it).
- Optional [Cloudflare Tunnel](../deploy/CLOUDFLARE.md) can be toggled from **Settings → Network** or `AMM_CLOUDFLARE_TUNNEL_*`. `cloudflared` runs inside this appliance.

## 7. Backups and updates

**Settings → Backups** manages configuration archives: manager settings, secrets, app config and databases.

- **What is included:** everything under `/config` except install binaries (`apps/`), caches, logs, transcode folders, artwork caches (Jellyfin `metadata`, Plex `Media`/`Metadata`), the *Arr apps' own `Backups` folders and media files. SQLite databases (Sonarr, Radarr, Jellyfin, Plex, …) are copied with SQLite's online backup, so they are consistent even while apps run. There is no size limit; anything that could not be read is listed as a warning on the backup.
- **Where:** `/backups` when you map a volume there (the compose files do), otherwise `/config/backups`. Map `/backups` to a different disk or NAS share, or download backups regularly. Backups from the old `/config/backups` location still show up and can be restored.
- **Schedule:** automatic backups default to daily at 03:30 in the host timezone (before the 04:00 update window). You can switch to weekly or monthly, or turn them off. **Keep last N** applies to all backups. The dashboard shows when the last backup ran.
- **Verify** re-reads an archive and checks every file against the SHA-256 checksums in its manifest.
- **Restore** lets you pick everything or individual apps (plus "Manager settings & secrets"). The manager first verifies the archive and saves the current state as a *Before restore* backup. It then stops the affected apps, writes the files back (clearing stale SQLite `-wal`/`-shm` files), reloads secrets and settings, and starts the apps again. Restoring manager settings from another server can sign you out.
- **Download / Upload** moves archives off the box or onto a new server. Uploads must be `.tar.gz` backups; verify them before restoring.

**Catalog Update** on a card always runs stop → snapshot → install → health check → rollback. The last three pre-update snapshots per app are kept under `/backups/app-snapshots/<app>/`.

**Settings → Updates** schedules GitHub checks (off / daily / weekly / monthly) and optionally applies them (off = notify only, same as check, or a separate cadence). Time of day uses the host timezone from **Settings → System**. The job skips apps that are not installed or in a crash loop, respects `GITHUB_TOKEN` / Settings → Updates (GitHub token), and pauses while the wizard is open or an install is running. Last check / last apply timestamps appear on Catalog and in Settings.

## 8. Settings

The **Settings** nav item is the admin page for the appliance (separate from per-app catalog cards), at `#/settings/account` (and `#/settings/backups`, `#/settings/network`, …). Older hashes such as `#/settings/vpn` still redirect. Bind mounts and the manager listen address stay in compose/env.

| Section | What it does |
|---------|----------------|
| Account | Username, email, password (current password required) |
| System | Timezone, log level, PUID/PGID, host CPU/RAM, storage paths (read-only) |
| Updates | Catalog check/apply schedules, Check now, optional GitHub token |
| Backups | Schedule, retention, backup now, verify, per-app restore, download/upload, delete |
| Network | VPN (enable, protocol, config, kill switch) and Cloudflare Tunnel (token, trusted proxies) |
| Homepage | Jellyfin and Seerr API keys for Home widgets, plus widget debug |
| Diagnostics | Error ring and time-limited support share URL (`/debug/{token}`). Host dumps and `/api/system` process logs use the same switch; `curl` from localhost on the appliance always works. |

Do not leave the support share URL on after you finish a support conversation. Cloudflare Tunnel and VPN start only after first-run, so the wizard is LAN-only.

Inputs and buttons across login, wizard, catalog, and Settings use the same control styles as the first-run wizard.
