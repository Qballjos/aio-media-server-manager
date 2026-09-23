# Synology Container Manager

Deploy **one** AIO container. Do not add separate containers for Sonarr, Radarr, or download clients.

Image: `ghcr.io/qballjos/aio-media-server-manager:latest`  
Use a DSM build that can run `linux/amd64` or `linux/arm64` images (most Plus and 2025 ARM NAS units).

## Create folders over SSH

Enable SSH (Control Panel → Terminal & SNMP → Enable SSH service), then:

```bash
ssh admin@<nas-ip>
```

Adjust `/volume1` if your storage pool uses another volume. Create the bind-mount directories as the media user (DSM often uses UID `1026` / GID `100` — confirm with `id`):

```bash
id
export PUID="$(id -u)"
export PGID="$(id -g)"

sudo mkdir -p \
  /volume1/docker/aio-media-manager/config/vpn \
  /volume1/downloads \
  /volume1/media/{movies,tv}

sudo chown -R "${PUID}:${PGID}" \
  /volume1/docker/aio-media-manager \
  /volume1/downloads \
  /volume1/media
```

If you run SSH as `admin` but the share is owned by another user:

```bash
id media
sudo chown -R 1026:100 \
  /volume1/docker/aio-media-manager \
  /volume1/downloads \
  /volume1/media
```

## Pull the image

```bash
sudo docker pull ghcr.io/qballjos/aio-media-server-manager:latest
```

If GHCR is private, run `sudo docker login ghcr.io` first.

## Create the container

**Container Manager → Container → Create** from that image:

- Port: `8080/tcp` (add child app ports or use host network).
- Volumes:
  - `/volume1/docker/aio-media-manager/config` → `/config`
  - `/volume1/media` → `/media`
  - `/volume1/downloads` → `/downloads`
- Environment: `PUID` / `PGID` matching the `chown` above.
- Privileged: on if you will use torrent VPN.
- Devices: `/dev/dri` when the NAS has an iGPU and you want transcoding.

Optional torrent VPN over SSH:

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/vpn
# scp wg0.conf into that directory, then set AMM_VPN_ENABLED=true on the container
```

Open `http://<nas-ip>:8080` and complete the first-run wizard.

## Permissions

Map the container to the same user DSM uses for the media shared folder. If apps cannot write, fix ownership with `chown` over SSH rather than running as root.
