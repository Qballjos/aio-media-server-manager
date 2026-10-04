# Cloudflare Tunnel

Reach AIO (and optional apps like Sonarr or Jellyfin) from the internet **without opening ports** on your router.

How it works in plain terms: a small program (`cloudflared`) runs **inside AIO**, dials out to Cloudflare, and Cloudflare serves `https://your-name.yourdomain.com`. Your home firewall stays closed to inbound traffic.

**Do not** install a second Cloudflare Docker container or `cloudflared` service on the same host for the same tunnel — AIO already runs it.

Official Cloudflare help: [Create a tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/) · [Tunnel token](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/remote-tunnel-permissions/#get-the-tunnel-token).

Your LAN UI at `http://YOUR-SERVER-IP:8080` still works when the tunnel is off.

---

## What you need

- A domain whose DNS is on Cloudflare
- Permission to create tunnels (**Networking → Tunnels**)
- AIO already installed and through first-run setup

---

## Step 1 — Create the tunnel

1. Sign in at [dash.cloudflare.com](https://dash.cloudflare.com/).
2. Open **Networking → Tunnels**  
   (some accounts still show **Zero Trust → Networks → Tunnels** — same place).
3. **Create a tunnel** → connector type **Cloudflared**.
4. Name it clearly, e.g. `aio-media-manager`.
5. **Create Tunnel**.

---

## Step 2 — Copy only the token

Cloudflare shows install commands for Docker, Windows, etc. **Do not run those on your NAS.** You only need the token string.

1. Stay on the tunnel setup / **Overview** page.
2. Pick any OS so a command appears (or later: tunnel → **Overview** → **Add a replica**).
3. You will see something like:

   ```bash
   cloudflared service install eyJhIjoiNWFiNGU5Z...very-long...
   ```

4. Copy **only** the part that starts with `eyJ` (long JWT-style string).  
   Treat it like a password — anyone with it can run your tunnel.

**Lost the token?** Tunnel → **Overview** → **Add a replica** → copy `eyJ…` again.  
**Leaked?** Use **Refresh token**, paste the new one into AIO, Save.

---

## Step 3 — Publish hostnames (so Open UI works remotely)

Cloudflare only serves **HTTPS on port 443**. You cannot open `https://media.example.com:8989`.  
Each app needs its own hostname, e.g. `https://sonarr.example.com`, routed to `http://127.0.0.1:8989` **inside** the AIO container.

### Easiest: do it in AIO

After the tunnel token is saved (Step 4):

1. **Settings → Network → Public subdomains**
2. Set **Public app domain** to your zone (e.g. `example.com` or `example.co.uk`).
3. Create a [Cloudflare API token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/) with:
   - **Account** → **Cloudflare Tunnel** → **Edit**
   - **Zone** → **DNS** → **Edit** (limit to your zone)
4. Paste that API token under **Public subdomains**  
   (this is **not** the `eyJ…` connector token).
5. Toggle **Expose** per app, edit subdomains if you like, **Save**, then **Publish to Cloudflare**.

AIO writes tunnel routes and creates proxied DNS names. Day to day you can stay in AIO instead of the Cloudflare dashboard.

### Or: publish routes by hand in Cloudflare

**Networking → Tunnels** → your tunnel → **Routes** → **Published application**.

At least the manager: `media.example.com` → `http://127.0.0.1:8080`.

| Hostname | Points to (inside AIO) |
|----------|-------------------------|
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

More ports: [Install → Ports](../docs/INSTALL.md#ports).

**Important:** published hostnames are on the public internet until you add [Cloudflare Access](CLOUDFLARE_ACCESS.md). Prefer Access (or very strong app passwords) for Sonarr, Radarr, qBittorrent, and the AIO manager itself.

**Publish behaviour (short version)**

- AIO only changes routes it published (or that you enable now). Hand-made dashboard routes you never published from AIO stay put.
- Turning an app off and publishing again removes its tunnel route; the DNS name may remain (then you get a tunnel 404).
- Changing an app’s listen port updates the tunnel target when an API token is saved.
- At home, `http://nas-ip:8080` still opens apps as `http://nas-ip:port` even if a public domain is set.

---

## Step 4 — Paste the token into AIO

1. Open `http://YOUR-SERVER-IP:8080`.
2. **Settings → Network → Cloudflare Tunnel**
3. Turn **Enable tunnel** on, paste the `eyJ…` token, Save.
4. Status should show **Enabled**, **Token saved**, **Tunnel up**, **cloudflared ready**.  
   The header **CF** pill turns green/blue when healthy.

Stuck on **Tunnel down**? Check cloudflared logs in Catalog/Diagnostics, outbound access to Cloudflare (port **7844**), and that nothing else is using the same token.

---

## Optional: token file on disk (SSH / Compose)

Handy for env-driven installs. Paths are on the **host** side of `/config`:

| Platform | Folder for `tunnel.token` |
|----------|---------------------------|
| Generic Linux | `/opt/aio-media-manager/config/cloudflare/` |
| Unraid | `/mnt/user/appdata/aio-media-manager/cloudflare/` |
| Synology | `/volume1/docker/aio-media-manager/config/cloudflare/` |

```bash
ssh user@host
CONFIG=/opt/aio-media-manager/config
sudo mkdir -p "$CONFIG/cloudflare"
sudo tee "$CONFIG/cloudflare/tunnel.token" >/dev/null <<'EOF'
eyJ...paste-token...
EOF
sudo chmod 600 "$CONFIG/cloudflare/tunnel.token"
sudo chown "${PUID:-1000}:${PGID:-1000}" "$CONFIG/cloudflare/tunnel.token"
```

Then enable in Settings, or set and recreate:

```bash
AMM_CLOUDFLARE_TUNNEL_ENABLED=true
AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE=/config/cloudflare/tunnel.token
```

Keep a **single** AIO service in Compose — no separate `cloudflare/cloudflared` container.

---

## Native Linux (no Docker)

Install the `cloudflared` binary if you are not on the GHCR image, but **do not** run `cloudflared service install` — AIO starts the process:

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared
```

Enable the tunnel in Settings (or env) and start `aio-media-manager.service`.

---

## Check that it works

1. Cloudflare: tunnel status **Healthy**
2. AIO: Settings → Network → tunnel **connected**
3. From mobile data (or another network): open `https://media.example.com` (your hostname)
4. Optional API check (does not return the token): `GET /api/cloudflare/tunnel/status`

---

## Trusted reverse-proxy IPs

**Settings → Network → Trusted reverse-proxy IPs** (`AMM_TRUSTED_PROXIES`).

This tells AIO which nearby proxies may send `X-Forwarded-*` headers (real client IP and https vs http).

| Your setup | What to put |
|------------|-------------|
| LAN only | **Leave empty** |
| Cloudflare Tunnel only (token in AIO) | **Leave empty** — AIO already trusts local `cloudflared` |
| nginx / Caddy / Traefik in front of AIO | That proxy’s IP (as AIO sees it), e.g. `172.17.0.1` |

This is **not** a list of Cloudflare’s public edge IPs. With a tunnel, traffic arrives from local `cloudflared`.  
Do not set `*` unless you understand spoofing risk. Restart the container after changing this field.

Access login gate: [CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md) — trusted proxies do not replace Access.

---

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Not connected | Full `eyJ…` pasted; only one `cloudflared` using that token |
| 502 on hostname | Service must be `http://127.0.0.1:PORT` inside AIO, not a LAN IP |
| Open UI fails over tunnel | Publish `https://app.your.domain`; set **Public app domain**; do not expect `:8989` on the manager hostname |
| Works on LAN, not remotely | Outbound firewall / port **7844**; DNS and tunnel route |
| Odd login/cookies | Leave trusted proxies empty for tunnel-only |
| Token field empty after save | Normal — stored on disk, never shown again |

---

## Quick checklist

1. Create tunnel in Cloudflare.
2. Copy `eyJ…` — do **not** run Cloudflare’s installer on the NAS.
3. Paste token in AIO → enable tunnel → Save.
4. Publish hostnames (AIO **Public subdomains** or dashboard routes).
5. Leave trusted proxies empty unless you also run nginx/Caddy in front.
6. Confirm Healthy / connected, then open the HTTPS URL.
7. Lock it down with [Cloudflare Access](CLOUDFLARE_ACCESS.md).
