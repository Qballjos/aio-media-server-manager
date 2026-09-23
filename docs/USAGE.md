# Usage

This guide covers what you do after the appliance is running. Installation and host paths are in [INSTALL.md](INSTALL.md).

## 1. Create the administrator

The first visit to `http://<host>:8080` requires a local admin account. That username and password protect the **manager dashboard and API only** at this step. They are stored as a bcrypt hash for the manager, and an encrypted copy is kept so compatible applications can use the same local login.

Password rules: at least 8 characters, at most 72 bytes (bcrypt limit).

## 2. First-run wizard

After sign-in, a 9-step wizard runs until you finish it or choose **Skip for now**.

| Step | You choose |
|------|------------|
| 1 | Media, download, and config directories (same `/data` parent for hardlinks) |
| 2 | `PUID` / `PGID` (pre-filled from the host / compose user) |
| 3 | Download clients (SABnzbd, NZBGet, qBittorrent) |
| 4 | VPN: none, PrivadoVPN-style isolation, or a custom WireGuard / OpenVPN path |
| 5 | *Arr apps: Prowlarr, Sonarr, Radarr, Lidarr |
| 6 | Media servers: Jellyfin and/or Plex (optional Plex claim token) |
| 7 | Requests (Seerr) |
| 8 | Recommended tools (Bazarr and Flaresolverr selected by default) |
| 9 | Review, then save and install |

qBittorrent username and password in the wizard may be left blank. Blank fields reuse the manager admin login.

**Skip** opens the dashboard without installing anything. You can install applications later from the catalog.

## 3. Catalog dashboard

The dashboard lists every catalog application.

- Filter by **category**
- Sort by **popularity** or **A–Z**
- **Search** by name
- **?** opens that application's official wiki or documentation
- **Download & Install** fetches the upstream binary and starts the process when it is a daemon
- Installed apps expose Start, Stop, Restart, Open UI, Logs, Update, and Uninstall

Wiring (indexers, download clients, libraries) runs after relevant apps are installed and healthy.

## 4. Shared local login

When you create the admin (and again on later successful logins), the manager stores the username and password in the encrypted secret store and applies them to applications that support a **local user**:

- Sonarr, Radarr, Lidarr, Prowlarr
- SABnzbd, NZBGet, qBittorrent
- Bazarr
- Jellyfin (a matching local Jellyfin user)

These remain separate accounts inside each product. They are created to **match** the manager credentials; signing into the manager does not SSO into those UIs.

**Not shared:**

- **Plex** — Plex account or claim token
- **Seerr** — typically Jellyfin or Plex sign-in
- Tools with no web login (Unpackerr, Recyclarr, Flaresolverr, and similar)

Open **Open UI** on each app the first time to confirm that product's own setup finished (especially Jellyfin and Plex).

## 5. VPN and remote access

- Place a WireGuard or OpenVPN profile under the config VPN directory and enable VPN in the wizard or environment. Only **qBittorrent** and **Prowlarr** are tunneled. Usenet clients stay on the normal network.
- Optional [Cloudflare Tunnel](../deploy/CLOUDFLARE.md) runs `cloudflared` inside this appliance.

## 6. Backups and updates

Use the dashboard to update an application (snapshot, health check, rollback on failure) and to run configuration backups. Media libraries and torrent payloads are never deleted by uninstall or backup jobs.
