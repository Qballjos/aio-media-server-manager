# Docker installation

Primary deployment. One container runs the manager and every supervised application.

Image: `ghcr.io/qballjos/aio-media-server-manager:latest`  
Architectures: `linux/amd64`, `linux/arm64`

## Compose (recommended)

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
mkdir -p config downloads media
```

Edit `docker-compose.yml` so `PUID`/`PGID` match `id` on the host, and so the volume paths point at your libraries.

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
  -e PUID=1000 -e PGID=1000 \
  -v /path/to/config:/config \
  -v /path/to/downloads:/downloads \
  -v /path/to/media:/media \
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

1. Place a WireGuard (`wg0.conf`) or OpenVPN profile in `/config/vpn/` on the host volume.
2. Set `AMM_VPN_ENABLED=true` (and `AMM_VPN_ENFORCE=true` if torrents must not run without a tunnel).
3. Keep Usenet clients off the VPN; they stay on the container's normal network.

Privileged mode is required for network namespaces and `/dev/net/tun`.

## Reverse proxy

The manager works at `http://server-ip:8080` with no proxy. If you put Traefik, Caddy, or Nginx in front, set `AMM_TRUSTED_PROXIES` to the proxy address and `AMM_ROOT_PATH` if the UI is not at `/`.
