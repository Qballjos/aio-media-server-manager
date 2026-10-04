# Docker

This is the usual way to run AIO: **one container** that starts the manager and every app you enable.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Works on:** `linux/amd64` and `linux/arm64`  
(On ARM, Flaresolverr is not available — it needs x86_64.)

---

## 1. Create folders (over SSH)

```bash
ssh user@host
```

```bash
id
export PUID="$(id -u)"
export PGID="$(id -g)"
export AMM_DATA_HOST="${HOME}/aio-media-manager"

mkdir -p "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media"
sudo mkdir -p /opt/aio-media-manager/{config,config/vpn,backups}
sudo chown -R "${PUID}:${PGID}" "${AMM_DATA_HOST}" /opt/aio-media-manager
```

**Why these paths?**

- Downloads and media live under **your home** so the host file manager can see them.
- Keep them as two folders under **one** parent so hardlinks work. Separate mounts on different disks (or different btrfs subvolumes) often force full copies.
- Put **backups** on another disk than **config** when you can. Without a `/backups` mount, AIO falls back to `/config/backups` and warns in Settings.

Already have libraries elsewhere? Set `AMM_DATA_HOST` to that parent folder (it still needs `downloads` and `media` inside it).

---

## 2. Start with Compose (recommended)

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
```

Check `docker-compose.yml`:

- Volume paths match the folders you created
- `PUID` / `PGID` match `id`
- `TZ` is your timezone (or set it later in Settings)

If you use `sudo docker compose`, set `AMM_DATA_HOST` explicitly so data does not land in `/root`.

```bash
docker compose pull
docker compose up -d
```

Open `http://YOUR-HOST:8080`, create the admin account, then follow [Using the dashboard](../docs/USAGE.md).

**Updating later:** pull again, then recreate:

```bash
docker compose pull
docker compose up -d --force-recreate
```

The container cannot replace its own image. Settings → Updates can *notify* you when `:latest` moved; you still pull on the host.

**Older compose that only published port 8080?** Copy the current `ports:` list from this repo and recreate, or child **Open UI** links will fail on the LAN.

**Adding `/backups` later:** create the host folder, add `- /path/to/backups:/backups` under `volumes:`, recreate. Old backups under `/config/backups` stay restorable until you remove them.

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
  -p 6767:6767 -p 6789:6789 -p 6868:6868 \
  -p 7878:7878 -p 8686:8686 -p 8989:8989 -p 9696:9696 -p 9705:9705 \
  -p 32400:32400 \
  -e PUID="${PUID}" -e PGID="${PGID}" \
  -e TZ=UTC \
  -v /opt/aio-media-manager/config:/config \
  -v "${HOME}/aio-media-manager:/data" \
  -v /opt/aio-media-manager/backups:/backups \
  -e AMM_DOWNLOAD_DIR=/data/downloads \
  -e AMM_MEDIA_DIR=/data/media \
  ghcr.io/qballjos/aio-media-server-manager:latest
```

Drop `--device /dev/dri` if the host has no Intel/AMD GPU (Docker Desktop on a Mac, many VPS hosts). Or use `--network host` instead of listing every `-p`.

Full port list: [Install → Ports](../docs/INSTALL.md#ports).

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

Privileged mode is required for network namespaces and `/dev/net/tun`.

---

## Reverse proxy or Cloudflare

- **No proxy needed** for home LAN use at `http://server-ip:8080`.
- Your own Traefik/Caddy/Nginx: set `AMM_TRUSTED_PROXIES` and optionally `AMM_ROOT_PATH`.
- **Cloudflare Tunnel** (no inbound ports): [CLOUDFLARE.md](CLOUDFLARE.md).  
  `cloudflared` runs **inside** this container — do not add a second Cloudflare service.
