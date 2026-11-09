# Docker — Advanced

!!! info "Advanced"
    This is the technical reference. For a first installation, follow the beginner guide instead. [Beginner guide](DOCKER.md).

This is the usual way to run AIO: **one container** that starts the manager and every app you enable.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Works on:** `linux/amd64` and `linux/arm64`  
(On ARM, Flaresolverr is not available — it needs x86_64.)

---

## 1. Check your server

Run the following on the machine that will host AIO. If it is a different computer, connect over SSH first using your own username and server address. SSH opens a command prompt on that server; commands typed there run on the server.

```bash
docker info
docker compose version
git --version
```

**Expected:** Docker reports a running engine, Compose prints a version, and Git prints a version. If a command is missing, install that tool first. If Docker says permission denied, use your host's documented Docker access setup; do not continue until the commands work. NAS users should use their [platform guide](README.md) instead of installing a second Docker engine.

## 2. Download AIO's setup files

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
```

All following Compose commands run in **this folder**, the one containing `docker-compose.yml`.

## 3. Prepare the folders

```bash
id
export PUID="$(id -u)"
export PGID="$(id -g)"
export AMM_DATA_HOST="${HOME}/aio-media-manager"
mkdir -p config/vpn backups "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media"
sudo chown -R "${PUID}:${PGID}" config backups "${AMM_DATA_HOST}"
```

**Expected:** `config/` and `backups/` exist in the checkout, and `aio-media-manager/downloads` and `aio-media-manager/media` exist in your home folder. These match the actual default mounts in the repository's Compose file. Your settings live in `./config`, not `/opt/aio-media-manager/config`.

Open `docker-compose.yml` in a text editor before starting:

- Change the service's **PUID** and **PGID** values to the `uid` and `gid` printed by `id`. The Compose file defaults to `1000:1000`; exporting shell variables above does not override those literal values.
- Set **TZ** to your timezone, for example `Europe/Amsterdam`.
- Keep the volume mappings at first. To store media elsewhere, set `AMM_DATA_HOST` to your chosen parent before running Compose. It should contain `downloads/` and `media/`.
- `backups/` is a starting location. For protection against a failed config disk, change the host side of the `/backups` mapping to another disk or backup destination.

!!! tip "Using sudo?"
    Sudo can drop environment variables and change HOME to `/root`. If you need it, preserve the selected data path explicitly: `sudo env AMM_DATA_HOST="$AMM_DATA_HOST" docker compose up -d`. Use the same setting for later updates.

## 4. Start the container

```bash
docker compose pull
docker compose up -d
docker compose ps
```

**Expected:** one container named `aio-media-manager` is running. The first pull downloads the image and can take several minutes. Do not add separate Sonarr/Radarr/download-client containers.

Open `http://YOUR-SERVER-IP:8080` in your browser, using your server's real IP. You should see AIO's account-creation screen; create your administrator account, finish the wizard, then follow [Using the dashboard](../docs/USAGE.md).

If it does not start, inspect the error:

```bash
docker compose logs --tail=100
```

A port conflict means the host port is already taken. Change the host side of that mapping (the number before `:` in `ports:`), recreate with `docker compose up -d`, and use that new port in the browser. Do not change app listen ports to solve a host-port conflict.

## Updating later

From the same checkout, with the same data path and mappings, pull again and recreate:

```bash
docker compose pull
docker compose up -d --force-recreate
```

The container cannot replace its own image. Settings → Updates notifies a `:nightly` install only when `:nightly` moves, and a `:latest` install only when `:latest` moves. You still pull that tag on the host. Installed apps (Sonarr, Seerr, and the rest) update from **Settings → Updates**, one at a time or all at once. Those schedules default to off. Recreating the container does not bump them.

**Older compose that only published port 8080?** Copy the current `ports:` list from this repo and recreate, or child **Open UI** links will fail on the LAN.

**Adding `/backups` later:** create the host folder, add `- /path/to/backups:/backups` under `volumes:`, recreate. Old backups under `/config/backups` stay restorable until you remove them.

**Host network traffic on Home:** add `- /sys:/host/sys:ro` under `volumes:` and recreate. Without it, Home shows only the container's own traffic.

Optional `GITHUB_TOKEN` (compose or Settings → Updates) raises GitHub API limits. Do not commit the token.

### Build from this checkout

```bash
docker compose up -d --build
```

### Dev / test environment

```bash
./scripts/test-env.sh up
```

See [CONTRIBUTING.md](../CONTRIBUTING.md).

### Hardware transcoding (Intel/AMD)

The image includes **jellyfin-ffmpeg** (with Intel iHD / VA-API drivers). Map the host render node, recreate the container after pulling a build that has it, then in Jellyfin enable **Intel Quick Sync** (or VAAPI) under Playback → Transcoding.

```bash
docker compose -f docker-compose.yml -f compose.gpu.yml up -d
```

---

## 3. Plain `docker run` (alternative)

```bash
docker pull ghcr.io/qballjos/aio-media-server-manager:latest

docker run -d --name aio-media-manager --restart unless-stopped \
  --privileged \
  --cap-add NET_ADMIN --cap-add SYS_MODULE \
  --device /dev/dri:/dev/dri \
  -p 8080:8080 \
  -p 8081:8081 -p 8084:8084 -p 8085:8085 -p 8096:8096 \
  -p 8191:8191 -p 5055:5055 -p 6060:6060 \
  -p 6767:6767 -p 6789:6789 \
  -p 7878:7878 -p 8686:8686 -p 8989:8989 -p 9696:9696 -p 9705:9705 -p 11011:11011 \
  -p 32400:32400 \
  -e PUID="${PUID}" -e PGID="${PGID}" \
  -e TZ=UTC \
  -v /opt/aio-media-manager/config:/config \
  -v "${HOME}/aio-media-manager:/data" \
  -v /opt/aio-media-manager/backups:/backups \
  -v /sys:/host/sys:ro \
  -e AMM_DOWNLOAD_DIR=/data/downloads \
  -e AMM_MEDIA_DIR=/data/media \
  ghcr.io/qballjos/aio-media-server-manager:latest
```

Drop `--device /dev/dri` if the host has no Intel/AMD GPU (Docker Desktop on a Mac, many VPS hosts). Or use `--network host` instead of listing every `-p`.

Full port list: [Install → Ports](../docs/REFERENCE.md#ports).

---

## Private GHCR image

If pull fails because the package is private:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker pull ghcr.io/qballjos/aio-media-server-manager:latest
```

On GitHub you can also make the package public under **Packages → settings → Change visibility**.

---

## Optional VPN

For qBittorrent / Prowlarr / Flaresolverr traffic:

```bash
sudo mkdir -p /opt/aio-media-manager/config/vpn
sudo chown -R "${PUID}:${PGID}" /opt/aio-media-manager/config/vpn
# copy wg0.conf or an OpenVPN profile into that folder
```

1. Set `AMM_VPN_ENABLED=true` (and `AMM_VPN_ENFORCE=true` if torrents must not run without VPN).
2. Leave Usenet clients off the VPN — they use the normal network.
3. Save the profile under **Settings → VPN** (or mount it and enable via env), then **recreate** the container so WireGuard comes up on boot.

Privileged mode is required for `/dev/net/tun` and the VPN uid routing (WireGuard in the main network namespace; torrent apps run as a dedicated uid). Synology often needs **wireguard-go** from the image when the host has no WireGuard kernel module — see [SYNOLOGY.md](SYNOLOGY.md).

### What AIO does while VPN is on

- Those three apps start only after a live WireGuard handshake. If the tunnel is down at boot, they wait; AIO retries the VPN with backoff and starts them when it is up. A manual VPN **Stop** cancels that retry.
- DNS for those apps goes through a small caching forwarder inside AIO (`127.0.0.153`), bound to the tunnel interface so lookups cannot leak onto the house WAN. It asks several public resolvers in parallel and can serve a recent answer when upstream is briefly quiet — which keeps Prowlarr indexers from failing on a single timeout. Other apps (Sonarr, Radarr, SABnzbd, …) keep the container resolver.
- Usenet traffic never uses the tunnel.

---

## Reverse proxy or Cloudflare

- **No proxy needed** for home LAN use at `http://server-ip:8080`.
- Your own Traefik/Caddy/Nginx: set `AMM_TRUSTED_PROXIES` and optionally `AMM_ROOT_PATH`.
- **Cloudflare Tunnel** (no inbound ports): [CLOUDFLARE.md](CLOUDFLARE.md).  
  `cloudflared` runs **inside** this container — do not add a second Cloudflare service.
