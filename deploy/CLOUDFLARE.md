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

## Step 3 — Paste the connector token into AIO

1. Open `http://YOUR-SERVER-IP:8080`.
2. **Settings → Network → Cloudflare Tunnel**
3. Turn **Enable tunnel** on, paste the `eyJ…` token, Save.
4. Status should show **Enabled**, **Token saved**, **Tunnel up**, **cloudflared ready**.  
   The header **CF** pill turns green/blue when healthy.

Stuck on **Tunnel down**? Check cloudflared logs in Catalog/Diagnostics, outbound access to Cloudflare (port **7844**), and that nothing else is using the same token.

---

## Step 4 — Publish applications (so Open UI works remotely)

Cloudflare only serves **HTTPS on port 443**. You cannot open `https://media.example.com:8989`.  
Each app needs its own **public hostname**, e.g. `https://sonarr.example.com`, mapped to `http://127.0.0.1:8989` **inside** the AIO container.

In Cloudflare’s model these are **[Published applications](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/#2a-publish-an-application)** (hostname → service). That is **not** the same as private-network Tunnel **routes** (CIDR / private hostname / WAN routes).

### Recommended: Published application in the Cloudflare dashboard

When you add a published application in the dashboard, Cloudflare also creates the proxied DNS **CNAME** to `<tunnel-id>.cfargotunnel.com` for you ([routing docs](https://developers.cloudflare.com/tunnel/concepts/routing/)).

1. **Networking → Tunnels** → your tunnel → **Routes** → **Add route** → **Published application**
2. Subdomain + domain (e.g. `sonarr` + `example.com`)
3. **Service URL:** `http://127.0.0.1:PORT` (see table below — must be localhost inside AIO, not a LAN IP)
4. Save

At least publish the manager: `media.example.com` → `http://127.0.0.1:8080`.

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

Then in AIO: **Settings → Network → Public subdomains** — set **Public app domain**, toggle the same labels, **Save**. That only aligns Catalog **Open UI** links; it does not call Cloudflare.

### Optional: publish via Cloudflare API from AIO

Same outcome as the dashboard path, using Cloudflare’s [Tunnel API get-started](https://developers.cloudflare.com/tunnel/get-started/) steps (PUT tunnel **ingress** configuration + Zone DNS CNAME). Useful if you want AIO to keep ingress in sync when you change listen ports.

Create the API token the way Cloudflare documents ([Create API token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)) — do **not** invent a shortcut path:

1. In the [Cloudflare dashboard](https://dash.cloudflare.com/), go to **My Profile → API Tokens** for a user token. For an Account Token, go to **Manage Account → Account API Tokens**.
2. Select **Create Token**.
3. Pick a template or **Create Custom Token**. Start from the **Edit zone DNS** template (Cloudflare’s own example), then adjust:
   - Name it something clear (e.g. `AIO Media publish`).
   - Keep **Zone → DNS → Edit**, and under **Zone Resources** limit the token to **your** zone (not All zones).
   - Add **Account → Cloudflare Tunnel → Edit** (required to update published-application ingress). Scope **Account Resources** to your account.
   - Recommended: also **Zone → Zone → Read** so AIO can resolve the zone by name.
4. **Continue to summary** → **Create Token**. Copy the secret once (shown only once).

Paste that token under **Public subdomains** (this is **not** the `eyJ…` connector token). Toggle **Expose**, **Save**, then **Publish via API (advanced)**.

API calls need DNS write plus a tunnel-connector write permission ([`DNS Write`](https://developers.cloudflare.com/fundamentals/api/reference/permissions/) and one of `Cloudflare Tunnel Write` / `Cloudflare One Connector: cloudflared Write` / `Cloudflare One Connectors Write`).

AIO only rewrites ingress hostnames it manages (or that you enable now). Hand-made dashboard published applications you never published from AIO stay put. Turning an app off and publishing again removes that ingress hostname; the DNS name may remain (then you get a tunnel 404). Changing a listen port updates the **service URL** in ingress; the DNS CNAME still targets the tunnel id.

**Important:** published hostnames are on the public internet until you add [Cloudflare Access](CLOUDFLARE_ACCESS.md). Prefer Access (or very strong app passwords) for Sonarr, Radarr, qBittorrent, and the AIO manager itself.

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
| Open UI fails over tunnel | Add a Published application for `https://app.your.domain`; set **Public app domain** in AIO; do not expect `:8989` on the manager hostname |
| Works on LAN, not remotely | Outbound firewall / port **7844**; DNS CNAME to `<tunnel-id>.cfargotunnel.com` and published application ingress |
| Odd login/cookies | Leave trusted proxies empty for tunnel-only |
| Token field empty after save | Normal — stored on disk, never shown again |

---

## Quick checklist

1. Create tunnel in Cloudflare.
2. Copy `eyJ…` — do **not** run Cloudflare’s installer on the NAS.
3. Paste token in AIO → enable tunnel → Save.
4. Add **Published applications** in Cloudflare (hostname → `http://127.0.0.1:PORT`); optionally align Open UI labels under AIO **Public subdomains**.
5. Leave trusted proxies empty unless you also run nginx/Caddy in front.
6. Confirm Healthy / connected, then open the HTTPS URL.
7. Lock it down with [Cloudflare Access](CLOUDFLARE_ACCESS.md).
