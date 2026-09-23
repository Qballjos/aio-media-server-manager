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

sudo mkdir -p /opt/aio-media-manager/{config,config/vpn,downloads,media}
sudo chown -R "${PUID}:${PGID}" /opt/aio-media-manager
```

Use other paths if you already have libraries (for example `/srv/media` and `/srv/downloads`). Keep downloads and media on the same filesystem for hardlinks.

## Compose (recommended)

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
```

Point the volume paths in `docker-compose.yml` at the folders you created, and set `PUID`/`PGID` to the values from `id`.

```bash
docker compose pull
docker compose up -d
```

Open `http://<host>:8080`.

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
  -e PUID="${PUID}" -e PGID="${PGID}" \
  -v /opt/aio-media-manager/config:/config \
  -v /opt/aio-media-manager/downloads:/downloads \
  -v /opt/aio-media-manager/media:/media \
  ghcr.io/qballjos/aio-media-server-manager:latest
```

Add `-p` mappings for child WebUIs you want on the host, or use `--network host` (then the manager is still on port 8080).

## Private GHCR image

If the package is not public yet:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker pull ghcr.io/qballjos/aio-media-server-manager:latest
```

On GitHub: **Packages → aio-media-server-manager → Package settings → Change visibility → Public**.

## VPN (qBittorrent only)

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
