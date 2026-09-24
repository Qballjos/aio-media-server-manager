# Docker installation

Primary deployment. One container runs the manager and every supervised application.

Image: `ghcr.io/qballjos/aio-media-server-manager:latest`  
Architectures: `linux/amd64`, `linux/arm64`

## Create folders over SSH

SSH into the machine that will run Docker:

```bash
ssh user@host
```

Create the bind-mount directories, then set ownership to the media user (`id` prints `PUID`/`PGID`):

```bash
id
export PUID="$(id -u)"
export PGID="$(id -g)"

sudo mkdir -p /opt/aio-media-manager/{config,config/vpn,data/downloads,data/media}
sudo chown -R "${PUID}:${PGID}" /opt/aio-media-manager
```

Use other paths if you already have libraries (for example `/srv/data/media` and `/srv/data/downloads`). Keep downloads and media as subfolders of **one** host directory so hardlinks work. Two separate bind mounts, even on btrfs, often fail if they are different subvolumes.

## Compose (recommended)

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
```

Point the volume paths in `docker-compose.yml` at the folders you created, and set `PUID`/`PGID` to the values from `id`. Set `TZ` to your IANA timezone (or change it later in Settings → General).

```bash
docker compose pull
docker compose up -d
```

Open `http://<host>:8080`. Create the administrator (username, **email**, password), then complete or skip the stack wizard ([Usage](../docs/USAGE.md)). If you already ran an older compose that only published `8080`, merge the current `ports:` list and `docker compose up -d --force-recreate`.

Optional `GITHUB_TOKEN` (or Settings → GitHub) raises GitHub API limits for catalog installs and scheduled update checks. Do not commit the token; the example compose leaves it commented.

To rebuild from this checkout instead of GHCR:

```bash
docker compose up -d --build
```

## Plain Docker

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
  -v /opt/aio-media-manager/data:/data \
  -e AMM_DOWNLOAD_DIR=/data/downloads \
  -e AMM_MEDIA_DIR=/data/media \
  ghcr.io/qballjos/aio-media-server-manager:latest
```

Add `-p` mappings for child WebUIs (the example above publishes the catalog defaults), or use `--network host` (then the manager is still on port 8080).

## Private GHCR image

If the package is not public yet:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker pull ghcr.io/qballjos/aio-media-server-manager:latest
```

On GitHub: **Packages → aio-media-server-manager → Package settings → Change visibility → Public**.

## VPN (qBittorrent, Prowlarr, Flaresolverr)

```bash
sudo mkdir -p /opt/aio-media-manager/config/vpn
sudo chown -R "${PUID}:${PGID}" /opt/aio-media-manager/config/vpn
# copy wg0.conf or an OpenVPN profile into that directory over SSH/SCP
```

1. Set `AMM_VPN_ENABLED=true` (and `AMM_VPN_ENFORCE=true` if torrents must not run without a tunnel).
2. Keep Usenet clients off the VPN; they stay on the container's normal network.

Privileged mode is required for network namespaces and `/dev/net/tun`.

## Reverse proxy

The manager works at `http://server-ip:8080` with no proxy. If you put Traefik, Caddy, or Nginx in front, set `AMM_TRUSTED_PROXIES` to the proxy address and `AMM_ROOT_PATH` if the UI is not at `/`.

To expose the appliance with **Cloudflare Tunnel** (no inbound ports), see [CLOUDFLARE.md](CLOUDFLARE.md). `cloudflared` runs inside this container — do not add a second Compose service.
