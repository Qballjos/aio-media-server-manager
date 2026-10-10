# Using the dashboard

This guide is for after AIO is installed and you can open the web UI.

!!! success "Goal"
    Enable only the apps you need, finish each app’s own setup, and use **Open UI** whenever you want that tool’s screen.

Default address on your home network:

```text
http://YOUR-SERVER-IP:8080
```

Replace the IP (and port, if you changed it).

---

## First time

1. Create your **admin** account when prompted.
2. Glance at **Settings** — paths, timezone, and basic options.
3. On the home dashboard, enable only the apps you actually want (Sonarr, Radarr, a download client, a media player, etc.).
4. Wait until each app shows as **running**, then use **Open UI** to finish that app’s own setup wizard.

You do not need every app. Start small (for example Radarr + one download client + Jellyfin), then add more later.

---

## The home dashboard

Think of it as a control panel for the whole stack:

| You see… | Meaning |
|----------|---------|
| App cards | Each tool AIO can run |
| Status (running / stopped / error) | Whether that process is up |
| **Open UI** | Opens that app’s web interface |
| Quick actions | Start / stop / restart (where available) |

LAN **Open UI** usually looks like `http://YOUR-SERVER-IP:8989` (example for Sonarr).  
If you set up Cloudflare public hostnames, **Open UI** can instead use `https://sonarr.yourdomain.com` — see [Cloudflare Tunnel](deploy/CLOUDFLARE.md).

---

## Typical setup order

Do this once per new install. Exact menus differ slightly per app, but the order stays the same.

### 1. Download client first

Enable **qBittorrent**, **SABnzbd**, or another client you use.

- Complete its setup (folders, speed limits, login).
- Note its URL and API/password — *Arr apps will need them.

Downloads should land under your shared **downloads** folder (the path you mounted as data).

### 2. Indexers (Prowlarr)

Enable **Prowlarr** if you use indexers.

- Add your indexers there.
- Sync or connect Sonarr/Radarr/Lidarr to Prowlarr so you do not paste the same indexer into every app.

### 3. Libraries (*Arr)

Enable **Sonarr** (TV), **Radarr** (movies), **Lidarr** (music), **Bazarr** (subtitles) as needed.

In each app:

1. Set **root folders** to your media paths (TV, movies, etc.).
2. Add the **download client** you configured above.
3. Connect **Prowlarr** (or add indexers).
4. Pick a quality profile you are happy with.

Keep **downloads** and **media** on the same volume/share so completed files can **hardlink** instead of copying (saves disk space and time).

### 4. Streaming / requests

Enable **Jellyfin**, **Plex**, and **Seerr** as needed.

- Point libraries at the same media folders Sonarr, Radarr, and Lidarr use.
- Seerr talks to Sonarr and Radarr so household members can request titles.
- Seerr's admin account and first-run wizard are completed for you using the shared login (through Jellyfin, or a claimed Plex).
- On the LAN, **Open UI** opens Sonarr, Radarr, Lidarr, Prowlarr, qBittorrent, SABnzbd, Bazarr, and Seerr already signed in with the manager account. Jellyfin, Plex, and NZBGet ask for the same username and password themselves.

### 5. Optional extras

VPN, Cloudflare Tunnel, Recyclarr, NeutArr, and backups — turn these on when you need them. None are required for a basic home setup.

#### NeutArr first-run setup token

The first time NeutArr starts, before it has an account, it asks for a one-time setup token.

1. Wait until NeutArr shows as **running**.
2. Open **Catalog → NeutArr → Settings**.
3. Copy **First-run setup token** and paste it into NeutArr's setup screen.

That value is the file `/config/neutarr/.setup-token` inside the appliance (the host folder mounted as `/config`). NeutArr deletes the file after the account is created, and the Settings field goes empty. Until NeutArr has started, the field stays empty.

---

## Opening each app’s UI

| Situation | What to use |
|-----------|-------------|
| At home on Wi‑Fi | **Open UI** → `http://IP:PORT` |
| Away from home with Cloudflare | **Open UI** → `https://subdomain.yourdomain.com` |
| You changed the WebUI port in Settings | AIO updates published routes; recreate/restart if LAN links look wrong |

If **Open UI** fails:

- Is the app **running** on the dashboard?
- Are you on the same network (for LAN links)?
- For HTTPS links: is the tunnel connected and was **Publish** successful? ([Cloudflare guide](deploy/CLOUDFLARE.md))

---

## Settings you will actually use

Names in the UI may be short labels; here is what they mean in practice.

| Area | Why it matters |
|------|----------------|
| **Paths / data** | Where downloads and media live |
| **WebUI port** | Host port for the AIO dashboard (and related LAN links) |
| **VPN** | Optional; usually for download traffic |
| **Public / Cloudflare** | Base domain + subdomains for remote HTTPS access |
| **Backups** | Export config so you can recover after a disk mishap |
| **Support share** | Temporary remote help — leave **off** unless you are debugging with someone you trust |

After changing important network or port settings, give apps a moment to reload — or restart AIO if links still look stale.

---

## Backups

- Use the built-in backup feature when you have a setup you like.
- Also back up the **config** folder on the host (and the backups mount if you use one).
- Media files are separate — back those up with your normal NAS/disk strategy.

---

## Updating apps vs updating AIO

| What | How |
|------|-----|
| **AIO itself** (dashboard + supervisor) | Pull a new Docker image and **recreate** the container ([Install](INSTALL.md)) |
| **Child apps** (Sonarr, etc.) | Use whatever update path AIO exposes for that app, or recreate after an image that bundles newer versions |

Read release notes on GitHub if something major changed.

---

## Common snags

| Problem | Try this |
|---------|----------|
| Blank or login loop on an app | Clear site data for that URL; confirm the app is running |
| NeutArr asks for a setup token | **Catalog → NeutArr → Settings** after NeutArr is running. The token is removed once the NeutArr account exists |
| Permission errors writing files | Host folder owner must match the container user (`PUID`/`PGID`) |
| Sonarr imports but duplicates files | Downloads and media must share one filesystem for hardlinks |
| Works at home, not on phone data | Need Tunnel (+ ideally Access); LAN IPs are not reachable from mobile data |
| Two Sonarrs fighting | Remove any extra Sonarr container; only AIO should run it |

---

## Next steps

- New install checklist: [Install](INSTALL.md)  
- Remote access: [Cloudflare Tunnel](deploy/CLOUDFLARE.md)  
- Lock the door on public URLs: [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md)
