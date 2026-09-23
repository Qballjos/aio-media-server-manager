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

The dashboard lists the **17** catalog applications (installed vs available counts are separate).

- Filter by **status** and **category**
- Sort by **popularity** or **A–Z**
- **Search** by name
- **?** opens that application's official wiki or documentation
- **Download & Install** fetches the upstream binary and starts the process when it is a daemon
- Installed apps expose Start, Stop, Restart, Open UI, Logs, Update, and Uninstall

**Open UI** uses `http://<host>:<app-port>` (for example Sonarr `8989`). That only works if the appliance compose/template publishes those ports, or the container uses host networking. Recreate the container after pulling an image that added port mappings.

Wiring (indexers, download clients, libraries) runs after relevant apps are installed **and running**. Clients that are not installed or not healthy are skipped so Sonarr/Radarr are not pointed at a dead NZBGet/SABnzbd/qBittorrent. qBittorrent on localhost is allowed without the WebUI login prompt.

Bazarr runs on the bundled **Python 3.13** interpreter (not the manager’s 3.14), with Pillow and the rest of its requirements. Rebuild/recreate the image if Bazarr previously failed with `PIL` / `ModuleNotFoundError`.

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
- Tools with no web login (Recyclarr, Flaresolverr, and similar)

Open **Open UI** on each app the first time to confirm that product's own setup finished (especially Jellyfin and Plex).

## 5. VPN and remote access

- Place a WireGuard or OpenVPN profile under the config VPN directory and enable VPN in the wizard or environment. Only **qBittorrent** and **Prowlarr** are tunneled. Usenet clients stay on the normal network.
- Optional [Cloudflare Tunnel](../deploy/CLOUDFLARE.md) runs `cloudflared` inside this appliance.

## 6. Backups and updates

Use the dashboard to update an application (snapshot, health check, rollback on failure) and to run configuration backups. Media libraries and torrent payloads are never deleted by uninstall or backup jobs. There is no scheduled update checker yet — updates run when you click **Update** on a card.

## 7. Settings

The **Settings** nav item opens an admin page (separate from the catalog). Today it includes:

- **Error manager** — recent ERROR+ events from this process
- **Debug share URL** — a toggle. On creates a time-limited, secret-redacted report at `/debug/{token}` (24 hours). Off revokes it. Copy the URL only while the toggle is on.

Do not leave debug sharing on after you finish a support conversation.

Inputs and buttons across login, wizard, catalog, and Settings use the same control styles as the first-run wizard.
