# Usage

This guide covers what you do after the appliance is running. Installation and host paths are in [INSTALL.md](INSTALL.md).

## 1. Create the administrator

The first visit to `http://<host>:8080` requires a local admin account: **username, email, and password**. The account protects the manager dashboard and API. Credentials are stored as a bcrypt hash, and an encrypted copy is kept so compatible applications (and **Seerr**) can use the same local identity.

Password rules: at least 8 characters, at most 72 bytes (bcrypt limit). You can change username, email, and password later under **Settings → Account** (current password required).

## 2. First-run wizard

After sign-in, a 9-step wizard runs until you finish it or choose **Skip for now**. Skip is a short save; the dashboard opens even if the API is busy with an install.

| Step | You choose |
|------|------------|
| 1 | Media, download, and config directories (same `/data` parent for hardlinks) |
| 2 | `PUID` / `PGID` (pre-filled from the host / compose user) |
| 3 | Download clients (SABnzbd, NZBGet, qBittorrent). Usenet host, port, SSL, username, password, and connections are saved for SABnzbd/NZBGet. qBittorrent username/password may be blank to reuse the manager admin login |
| 4 | VPN: none, PrivadoVPN-style isolation, or a custom WireGuard / OpenVPN profile (upload, paste, or path) |
| 5 | *Arr apps: Prowlarr, Sonarr, Radarr, Lidarr |
| 6 | Media servers: Jellyfin and/or Plex (optional Plex claim token) |
| 7 | Requests (Seerr) |
| 8 | Recommended tools (Bazarr and Flaresolverr on by default; Recyclarr, Profilarr, NeutArr, Grimmory, Shelfmark optional) |
| 9 | Review, then save and install |

**Finish** persists settings and queues catalog installs. Wiring (indexers, download clients, libraries, Seerr, Recyclarr sync) runs **after each app is installed and answers its health check**, not during the Finish request. Apps that are not installed or not running are skipped so *Arr is not pointed at a dead downloader. You can run the same wiring later with **Auto-Wire** on the catalog.

**Skip** opens the household homepage without installing anything. You can install applications later from **Catalog**.

## 3. Household homepage

After the wizard, **Home** is the front page for watching and requesting. It reuses the manager login (no extra household accounts). There are no start/stop/install controls here.

- **Launcher** lists installed apps that have a WebUI. Recyclarr is omitted (CLI only). Stopped apps still appear dimmed.
- **Coming up** is a real calendar of Sonarr/Radarr airings: a full month on wide screens, the current week on phones.
- **Downloading** uses SABnzbd, NZBGet, and/or qBittorrent queues.
- **Recently added** uses Jellyfin and/or Plex. AMM tries the manager login first. You can also paste a Jellyfin API key under **Settings → Integrations** (or Catalog → Jellyfin → Settings). Create the key in Jellyfin Dashboard → API Keys.
- **Search** talks to Seerr when it is running (Request button). AMM reads `apiKey` from Seerr’s `settings.json` after Seerr’s first setup. Without Seerr, search falls back to Sonarr/Radarr lookup only.
- **Widget debug** on Home (or `?debug=1`) shows why a widget is empty: not installed, stopped, missing API key, HTTP error, timeout, or an empty API result. Keys are never shown.

Empty widgets stay hidden until debug is on. **Catalog** is still the admin dashboard for install, process controls, logs, and Auto-Wire.

## 4. Catalog dashboard

The dashboard lists the **17** catalog applications (installed vs available counts are separate).

- Filter by **status** and **category**
- Sort by **popularity** or **A–Z**
- **Search** by name
- **?** opens that application's official wiki or documentation
- **Health** (header) opens host CPU/RAM/disk graphs plus per-application CPU and memory (including child processes)
- **Download & Install** fetches the upstream binary and starts the process when it is a daemon
- Installed apps: **Start** or **Stop**, **Open UI**, and **More** (Restart, Logs, Settings, Update, Uninstall).
- **Auto-Wire** (header) re-runs integration after apps are healthy: download clients in Sonarr/Radarr (qBittorrent and SABnzbd when installed), Prowlarr, Seerr, Bazarr, and a Recyclarr `sync` when Recyclarr is installed.
- Catalog **Settings** on a card changes the listen **port** (persisted, running apps are restarted) and **start with the manager**. Config/install paths are shown read-only. Bind mounts still change in compose, not here.
- Cards show **Update available** when a scheduled or manual check found a newer GitHub release. Manual **Update** still uses snapshot → install → health check → rollback.

**Open UI** uses `http://<host>:<app-port>` (for example Sonarr `8989`). That only works if the appliance compose/template publishes those ports, or the container uses host networking. Recreate the container after pulling an image that added port mappings. Recyclarr has no WebUI.

qBittorrent on localhost is allowed without the WebUI login prompt. **Open UI** from another LAN machine uses the manager username and password (seeded into `qBittorrent.conf` before start). Restart qBittorrent once after upgrading if an older run already created a temporary WebUI password.

**VueTorrent:** Catalog → qBittorrent → Settings → **VueTorrent WebUI** downloads the latest [VueTorrent](https://github.com/VueTorrent/VueTorrent) zip and sets qBittorrent’s alternative WebUI folder (quoted absolute path, readable by PUID/PGID). Same listen port (`8081` by default) and the same WebAPI, so *Arr download clients keep working. Turn the switch off to return to the stock WebUI; the files stay on disk so you can enable it again without another download. If Open UI fails after enabling, turn VueTorrent off, save (qBittorrent restarts on the stock UI), then enable it again.

Bazarr runs on the bundled **Python 3.13** interpreter (not the manager’s 3.14), with Pillow and the rest of its requirements. Rebuild/recreate the image if Bazarr previously failed with `PIL` / `ModuleNotFoundError`. Form login uses the manager username and password (YAML stores a SHA-256 of the password; type the same plaintext you used in the wizard).

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

Recyclarr is a one-shot CLI. Auto-Wire and **Sync** on the catalog card run `recyclarr sync --config recyclarr.yml` with `RECYCLARR_CONFIG_DIR` (Recyclarr 8 dropped `--app-data`). It writes an official Recyclarr v8 / [TRaSH Guides](https://trash-guides.info/) `recyclarr.yml`: HD WEB-1080p, Anime Remux-1080p, and HD Bluray+WEB by default. 4K profiles are opt-in.

**Catalog → Recyclarr → Settings** toggles profiles, Plex/Jellyfin naming, YAML edit, and restore defaults. Custom YAML is kept until you restore defaults. Last-sync details appear on the debug share when diagnostics are on.

## 6. VPN and remote access

- Upload or paste a WireGuard (`.conf`) or OpenVPN (`.ovpn`) profile in the wizard or **Settings → VPN**. It is written under `/config/vpn/` (`wg0.conf` or `client.ovpn`) with mode `600`. You can still point at an existing path. **qBittorrent**, **Prowlarr**, and **Flaresolverr** are tunneled. Usenet clients stay on the normal network.
- Optional [Cloudflare Tunnel](../deploy/CLOUDFLARE.md) can be toggled from **Settings → Remote access** or `AMM_CLOUDFLARE_TUNNEL_*`. `cloudflared` runs inside this appliance.

## 7. Backups and updates

**Settings → Backups** lists configuration archives (config, secrets, databases — never media). You can set retention, backup now, restore, or delete.

**Catalog Update** on a card always runs snapshot → install → health check → rollback.

**Settings → Updates** schedules GitHub checks (off / daily / weekly / monthly) and optionally applies them (off = notify only, same as check, or a separate cadence). Time of day uses the host timezone from **Settings → General**. The job skips apps that are not installed or in a crash loop, respects `GITHUB_TOKEN` / Settings → GitHub, and pauses while the wizard is open or an install is running. Last check / last apply timestamps appear on the dashboard and in Settings.

## 8. Settings

The **Settings** nav item is the admin page for the appliance (separate from per-app catalog cards). Bind mounts and the manager listen address stay in compose/env.

| Section | What it does |
|---------|----------------|
| Account | Username, email, password (current password required) |
| General | Timezone, log level; manager bind host/port is shown read-only |
| Updates | Check/apply schedules and Check now |
| Storage | Architecture, CPU, memory, disk, filesystem format (read-only) |
| Permissions | PUID / PGID — saving restarts running child processes |
| Backups | Retention, backup now, restore, delete |
| VPN | Enable, protocol, upload/paste config, path, kill switch |
| Remote access | Cloudflare Tunnel on/off, token (write-only), trusted proxy IPs |
| GitHub | Optional token for rate limits (not shown again after save) |
| Debug | Error ring + time-limited share URL (`/debug/{token}`) |

Do not leave debug sharing on after you finish a support conversation.

Inputs and buttons across login, wizard, catalog, and Settings use the same control styles as the first-run wizard.
