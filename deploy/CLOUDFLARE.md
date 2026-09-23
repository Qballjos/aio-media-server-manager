# Cloudflare Tunnel

Optional inbound access without opening ports. `cloudflared` runs **inside the AIO appliance** as a supervised process — not a second Compose service.

The manager stays available at `http://server-ip:8080` even when the tunnel is off.

Prefer a [remotely managed tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/) and a tunnel token. Public hostnames are configured in the Cloudflare dashboard.

## Create the tunnel

1. In the [Cloudflare dashboard](https://dash.cloudflare.com/), open **Zero Trust → Networks → Tunnels** (or **Networking → Tunnels**).
2. **Create a tunnel** → choose **Cloudflared**.
3. Copy the **token** (`eyJ…`). Do not run Cloudflare’s extra Docker/systemd installer on the NAS if this appliance will run `cloudflared`.
4. Add a **published application**:
   - Hostname: `media.example.com` (your zone)
   - Service: `http://127.0.0.1:8080`
5. Optional extra hostnames for child apps on the same appliance, for example:
   - `jellyfin.example.com` → `http://127.0.0.1:8096`
   - `sonarr.example.com` → `http://127.0.0.1:8989`

Put Cloudflare Access in front of those hostnames if the stack must not be public.

## Store the token over SSH

```bash
ssh user@host
sudo mkdir -p /opt/aio-media-manager/config/cloudflare
sudo install -m 600 /dev/null /opt/aio-media-manager/config/cloudflare/tunnel.token
sudo tee /opt/aio-media-manager/config/cloudflare/tunnel.token >/dev/null <<'EOF'
eyJ...paste-token...
EOF
sudo chmod 600 /opt/aio-media-manager/config/cloudflare/tunnel.token
sudo chown "${PUID}:${PGID}" /opt/aio-media-manager/config/cloudflare/tunnel.token
```

On Synology use `/volume1/docker/aio-media-manager/config/cloudflare/`. On Unraid use `/mnt/user/appdata/aio-media-manager/cloudflare/`.

## Enable on the appliance

Set:

```bash
AMM_CLOUDFLARE_TUNNEL_ENABLED=true
AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE=/config/cloudflare/tunnel.token
```

or pass `AMM_CLOUDFLARE_TUNNEL_TOKEN` (the manager writes it to the token file and starts `cloudflared tunnel --no-autoupdate run --token-file …`).

Restart the container or native service. Dashboard shows a warning if the tunnel is enabled but not connected. Status: `GET /api/cloudflare/tunnel/status` (no token is returned).

## Docker Compose

Keep a **single** `aio-media-manager` service. Example environment:

```yaml
environment:
  AMM_CLOUDFLARE_TUNNEL_ENABLED: "true"
  AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE: /config/cloudflare/tunnel.token
```

Do not add a `cloudflared` service next to it.

## Native Linux

Install `cloudflared` on the host (Debian/Ubuntu):

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared
```

Do **not** run `cloudflared service install` if the AIO manager will supervise the process. Point `.env` at the token file and start `aio-media-manager.service`.

The GHCR image already includes the `cloudflared` binary.
