# Synology Container Manager (Project)

Deploy **one** AIO Container Manager **project**. Do not add extra project services or separate containers for Sonarr, Radarr, or download clients.

Image: `ghcr.io/qballjos/aio-media-server-manager:latest`  
Use a DSM build that can run `linux/amd64` or `linux/arm64` images.

## Create the project over SSH

Enable SSH (Control Panel → Terminal & SNMP → Enable SSH service), then:

```bash
ssh admin@<nas-ip>
```

The install script creates `/volume1/docker/aio-media-manager`, the config/downloads/media folders, and writes `docker-compose.yml` with your `PUID`/`PGID`:

```bash
id
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
```

If SSH is `admin` but the media share belongs to another user:

```bash
id media
sudo PUID=1026 PGID=100 sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Other volume or paths:

```bash
sudo VOLUME=/volume2 \
     DOWNLOADS=/volume2/downloads \
     MEDIA=/volume2/media \
     PUID=1026 PGID=100 \
     sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

The generated file is `/volume1/docker/aio-media-manager/docker-compose.yml` (no `build:` key — Container Manager pulls GHCR). A static copy lives in [`synology/docker-compose.yml`](synology/docker-compose.yml).

If GHCR is private: `sudo docker login ghcr.io` before starting the project.

## Import in Container Manager

1. Open **Container Manager → Project → Create**.
2. **Project name:** `aio-media-manager`
3. **Path:** `/volume1/docker/aio-media-manager` (same folder the script used).
4. **Source:** use the **existing** `docker-compose.yml` (do not paste a second compose file or add more services).
5. Start the project.

The UI should show a single service `aio-media-manager`. Open `http://<nas-ip>:8080` and complete the wizard.

To start from SSH instead of the UI:

```bash
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml pull
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml up -d
```

After that, Container Manager still lists it if the project path matches.

## Hardware transcoding

If `/dev/dri` exists, add this block under `aio-media-manager` in the project compose file, then rebuild/start the project:

```yaml
    devices:
      - /dev/dri:/dev/dri
```

```bash
ls -l /dev/dri
```

## VPN (qBittorrent only)

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/vpn
# scp wg0.conf into that directory
```

Set `AMM_VPN_ENABLED=true` in the project compose (and `AMM_VPN_ENFORCE=true` if torrents must not run without a tunnel), then start the project again.

## Permissions

`PUID`/`PGID` in the compose file must match the `chown` the script applied. If apps cannot write, fix ownership over SSH rather than running as root.
