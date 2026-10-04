# Cloudflare Tunnel token (manual)

Use a **remotely managed Cloudflare Tunnel** so you can reach AIO Media Server Manager (and optional child apps) from the internet **without opening ports** on your router. `cloudflared` runs **inside this appliance** — do not install a second Cloudflare Docker/systemd service on the same host for the same tunnel.

Official Cloudflare docs: [Create a tunnel (dashboard)](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/) · [Tunnel token](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/remote-tunnel-permissions/#get-the-tunnel-token).

The LAN UI stays available at `http://<server-ip>:8080` even when the tunnel is off.

---

## What you need

- A domain on Cloudflare (DNS managed by Cloudflare).
- A Cloudflare account that can create tunnels (**Networking → Tunnels**).
- AIO Media Server Manager already running (wizard finished). The GHCR image includes `cloudflared`.

---

## 1. Create the tunnel

1. Sign in at [dash.cloudflare.com](https://dash.cloudflare.com/).
2. Open **Networking → Tunnels**  
   (some accounts still show **Zero Trust → Networks → Tunnels** — same idea).
3. Select **Create a tunnel**.
4. Choose **Cloudflared** as the connector type.
5. Name it something clear, for example `aio-media-manager`.
6. Select **Create Tunnel**.

---

## 2. Copy the tunnel token (do not run Cloudflare’s installer)

Cloudflare shows an install command for Docker, Windows, macOS, or Linux. **Do not run that command on your NAS** if AIO will supervise `cloudflared`.

1. Stay on the tunnel setup / **Overview** page.
2. Select an OS (any is fine) so the install command appears, **or** open the tunnel later → **Overview** → **Add a replica**.
3. Copy the whole command into a text editor. It looks like:

   ```bash
   cloudflared service install eyJhIjoiNWFiNGU5Z...very-long...
   ```

   or for Docker:

   ```bash
   docker run ... cloudflare/cloudflared:latest tunnel --no-autoupdate run --token eyJhIjoiNWFiNGU5Z...
   ```

4. Copy **only** the token: the long string that starts with `eyJ` (JWT-style).  
   That is what you paste into AIO. Treat it like a password — anyone with it can run your tunnel.

To recover a token later: **Networking → Tunnels** → your tunnel → **Overview** → **Add a replica** → copy `eyJ…` from the command again.  
To replace a leaked token: use **Refresh token** on that page, then paste the new `eyJ…` into AIO and Save.

---

## 3. Publish hostnames (routes)

Catalog **Open UI** cannot use `http://media.example.com:8989` behind the tunnel (Cloudflare only serves HTTPS on 443). Links must be **`https://<subdomain>.<your-domain>`** with a published route to `http://127.0.0.1:<port>` inside the container.

### Recommended: Settings → Network → Public subdomains

After the tunnel connector token is saved (section 4):

1. Set **Public app domain** to your zone (e.g. `example.com`).
2. Create a [Cloudflare API token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/) with:
   - **Account** → **Cloudflare Tunnel** → **Edit**
   - **Zone** → **DNS** → **Edit** (scope to your zone)
3. Paste that API token under **Public subdomains** (this is **not** the `eyJ…` connector token).
4. Toggle **Expose** for each app, edit the subdomain if you want (e.g. `watch` instead of `jellyfin`), then **Save subdomains**.
5. Select **Publish to Cloudflare** — AIO writes the tunnel ingress rules and creates proxied DNS CNAMEs.

You only need the Cloudflare dashboard for the initial tunnel; day-to-day hostnames can stay in AIO.

### Manual (dashboard) alternative

1. Open **Networking → Tunnels** → your tunnel → **Routes** → **Add route** → **Published application**.
2. Add at least the manager: `media.example.com` → `http://127.0.0.1:8080`.
3. Add one hostname per app (service = localhost inside the container):

   | Hostname | Service |
   |----------|---------|
   | `jellyfin.example.com` | `http://127.0.0.1:8096` |
   | `sonarr.example.com` | `http://127.0.0.1:8989` |
   | `radarr.example.com` | `http://127.0.0.1:7878` |
   | `prowlarr.example.com` | `http://127.0.0.1:9696` |
   | `seerr.example.com` | `http://127.0.0.1:5055` |
   | `qbittorrent.example.com` | `http://127.0.0.1:8081` |
   | `sabnzbd.example.com` | `http://127.0.0.1:8085` |
   | `bazarr.example.com` | `http://127.0.0.1:6767` |
   | `lidarr.example.com` | `http://127.0.0.1:8686` |
   | `plex.example.com` | `http://127.0.0.1:32400` |

   Full default ports: [docs/INSTALL.md](../docs/INSTALL.md#ports).

**Security:** published hostnames are reachable from the internet unless you add Cloudflare Access.  
Household walkthrough: **[CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md)**. Prefer Access (or at least strong app logins) for Sonarr/Radarr/Seerr/qBittorrent.

**Publish behaviour notes**

- AIO only changes tunnel routes it previously published (or that you enable now). Manual dashboard routes you never published from AIO stay intact.
- Disabling an app and publishing again removes its tunnel route; the DNS CNAME is left in place (requests then hit the tunnel catch-all / 404).
- Changing an exposed app’s listen port (Catalog → app settings) automatically rewrites the tunnel service URL and recreates its DNS CNAME when a Cloudflare API token is saved.
- Set **Public app domain** to the full zone for multi-part TLDs (e.g. `example.co.uk`). Auto-derive understands common suffixes like `co.uk` / `com.au`.
- LAN use of the manager (`http://nas-ip:8080`) still opens apps as `http://nas-ip:port` even when Public app domain is set.

---

## 4. Put the token into AIO (recommended: Settings UI)

1. Open the manager on the LAN: `http://<server-ip>:8080`.
2. Go to **Settings → Network**.
3. Under **Cloudflare Tunnel**:
   - Turn **Enable tunnel** on.
   - Paste the `eyJ…` token into **Tunnel token** (leave blank later to keep the stored token — it is never shown again).
   - Save.
4. Check the status chips: **Enabled**, **Token saved**, **Tunnel up**, **cloudflared ready**.  
   The header also shows a **CF** pill when the tunnel is enabled (green/blue when up, red when down).

If the status stays **Tunnel down** / **Connecting…**, open Catalog → cloudflared logs (or Diagnostics), confirm the host can reach Cloudflare on outbound **7844**, and that you did not start a second `cloudflared` with the same token elsewhere.

---

## 5. Optional: store the token on disk over SSH

Useful for Compose/env-driven installs. Paths are on the **host** bind-mount for `/config`:

| Platform | Host folder for the token file |
|----------|--------------------------------|
| Generic / Linux | `/opt/aio-media-manager/config/cloudflare/` (or your `/config` mount) |
| Unraid | `/mnt/user/appdata/aio-media-manager/cloudflare/` |
| Synology | `/volume1/docker/aio-media-manager/config/cloudflare/` |

```bash
ssh user@host
# adjust CONFIG to your /config mount
CONFIG=/opt/aio-media-manager/config
sudo mkdir -p "$CONFIG/cloudflare"
sudo tee "$CONFIG/cloudflare/tunnel.token" >/dev/null <<'EOF'
eyJ...paste-token...
EOF
sudo chmod 600 "$CONFIG/cloudflare/tunnel.token"
sudo chown "${PUID:-1000}:${PGID:-1000}" "$CONFIG/cloudflare/tunnel.token"
```

Then either enable in **Settings → Network**, or set env and recreate the container:

```bash
AMM_CLOUDFLARE_TUNNEL_ENABLED=true
AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE=/config/cloudflare/tunnel.token
```

You can also pass `AMM_CLOUDFLARE_TUNNEL_TOKEN` once; the manager writes it to the token file and starts:

`cloudflared tunnel --no-autoupdate run --token-file …`

---

## 6. Docker Compose reminder

Keep a **single** `aio-media-manager` service. Example:

```yaml
environment:
  AMM_CLOUDFLARE_TUNNEL_ENABLED: "true"
  AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE: /config/cloudflare/tunnel.token
```

Do **not** add a separate `cloudflare/cloudflared` service for this tunnel.

---

## 7. Native Linux (non-Docker)

Install the `cloudflared` binary on the host if you are not using the GHCR image, but **do not** run `cloudflared service install` — AIO supervises the process:

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared
```

Point `.env` at the token file, enable the tunnel in Settings (or env), start `aio-media-manager.service`.

---

## 8. Check that it works

1. In Cloudflare: **Networking → Tunnels** → tunnel status **Healthy**.
2. In AIO: **Settings → Network** → Tunnel **connected**.
3. From a phone off Wi‑Fi (or another network), open `https://media.example.com` (your published hostname).
4. API (no token returned): `GET /api/cloudflare/tunnel/status`.

---

## Trusted reverse-proxy IPs

**Settings → Network → Trusted reverse-proxy IPs** (env: `AMM_TRUSTED_PROXIES`).

This tells the manager which TCP peers are allowed to send `X-Forwarded-*` / `Forwarded` headers. Uvicorn then uses those headers for the real client IP and scheme (http vs https).

### Default: leave it empty

| Setup | What to put in the field |
|-------|---------------------------|
| LAN only (`http://192.168.x.x:8080`) | **Empty** |
| Cloudflare Tunnel only (token in AIO) | **Empty** — when the tunnel is enabled, AIO already trusts `127.0.0.1` automatically (that is where `cloudflared` connects inside the container) |
| Your own reverse proxy in front of AIO (nginx, Caddy, Traefik, NPM on the NAS/LAN) | The **proxy’s IP as AIO sees it** (often `172.x` Docker bridge, or the NAS LAN IP), comma-separated CIDRs allowed |

Examples:

```text
172.17.0.1
10.0.0.5,172.16.0.0/12
```

### What it is not

- **Not** a list of Cloudflare public edge IPs. With a tunnel you do not need those; traffic arrives from local `cloudflared`.
- **Not** required to “turn on” the tunnel. The tunnel token + Enable switch are enough.
- **Not** something to set to `*` unless you understand the risk: any client could spoof `X-Forwarded-For` and look like another IP.

### When you might fill it in

1. You put **nginx/Caddy** on the host (or another container) that proxies to `http://aio:8080`.
2. That proxy sets `X-Forwarded-For` / `X-Forwarded-Proto`.
3. You want correct client IPs in logs and correct HTTPS awareness behind that proxy.

Then list only that proxy’s address(es). **Restart the container** after changing this field (or `AMM_TRUSTED_PROXIES`) — proxy trust is applied when the manager process starts.

### Cloudflare Tunnel + Access

See **[CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md)** for a step-by-step Access setup (email one-time PIN, policies, which hostnames to protect). Trusted proxies do not replace Access.

---

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Token rejected / not connected | Pasted the full `eyJ…` string with no spaces/newlines; only one `cloudflared` using that token |
| Hostname 502 / error | Published service is `http://127.0.0.1:<port>` (inside the appliance), not `http://192.168.x.x` |
| Catalog Open UI fails over tunnel | Publish `https://<app>.your.domain` routes; set **Public app domain**; do not expect `:8989` on the manager hostname |
| Works on LAN, not via tunnel | Outbound firewall blocking Cloudflare (port **7844**); tunnel route hostname/DNS |
| Login / cookies odd behind tunnel | Leave **Trusted reverse-proxy IPs** empty for tunnel-only; do not set `*` |
| Wrong client IP behind nginx/Caddy | Add that proxy’s IP/CIDR to Trusted reverse-proxy IPs |
| Token field empty after save | Expected — token is stored on disk and never shown again; status still shows **token present** |

---

## Quick checklist

1. Create tunnel in Cloudflare (**Networking → Tunnels**).
2. Copy `eyJ…` from the install command — **do not** run Cloudflare’s installer on the NAS.
3. Add published route: `your.host` → `http://127.0.0.1:8080`.
4. Paste token in AIO **Settings → Network**, enable tunnel, Save.
5. Leave **Trusted reverse-proxy IPs** empty unless you also run nginx/Caddy in front of AIO.
6. Confirm **connected** / **Healthy**, then open the public HTTPS hostname.
7. Put Cloudflare Access in front of published apps — [CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md).
