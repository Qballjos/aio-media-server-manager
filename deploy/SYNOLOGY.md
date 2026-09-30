# Synology Container Manager (Project)

Deploy **one** AIO Container Manager **project**. Do not add extra project services or separate containers for Sonarr, Radarr, or download clients.

Image: `ghcr.io/qballjos/aio-media-server-manager:latest`  
Use a DSM build that can run `linux/amd64` or `linux/arm64` images.

## Create the project over SSH

Enable SSH (Control Panel → Terminal & SNMP → Enable SSH service), then:

```bash
ssh admin@<nas-ip>
```

The install script creates `/volume1/docker/aio-media-manager` (with `config/` and `backups/`) and a data tree in the **DSM user home** (`File Station → Home → aio-media-manager` with `downloads/` and `media/`). That path is a real user home, so DSM can browse it. A raw `/volume1/data` folder is not a shared folder and does not show up in File Station; re-running the script moves that tree into home if it still exists. Downloads and media stay one bind (`/data`) so *Arr can hardlink. Config backups go to the `/backups` mount; include that folder in a Hyper Backup task, or point `BACKUPS=` at another volume.

User Home Service must be on (Control Panel → User & Group → Advanced). SSH as the DSM user whose Home should hold the libraries, or set `HOME_USER=`.

```bash
id
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
```

If SSH is `admin` but Home should belong to another DSM user:

```bash
id media
sudo HOME_USER=media PUID=1026 PGID=100 sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Other volume or paths:

```bash
sudo VOLUME=/volume2 \
     HOME_USER=media \
     BACKUPS=/volume1/backups/aio-media-manager \
     PUID=1026 PGID=100 \
     sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

To keep libraries on a DSM shared folder instead of Home, set `DATA=` to that folder (still one parent for `downloads` and `media`):

```bash
sudo DATA=/volume1/media/aio-media-manager \
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

The UI should show a single service `aio-media-manager`. Open `http://<nas-ip>:8080` for the manager. **Open UI** on catalog cards uses the app ports (Sonarr `8989`, Radarr `7878`, …), which the project compose now publishes. If you generated compose before that change, copy the `ports:` list from [`synology/docker-compose.yml`](synology/docker-compose.yml) into the project file and recreate the container.

To start from SSH instead of the UI:

```bash
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml pull
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml up -d
```

After that, Container Manager still lists it if the project path matches.

## Hardware transcoding

If `/dev/dri` exists, add this block under `aio-media-manager` in the project compose file, then recreate and start the project:

```yaml
    devices:
      - /dev/dri:/dev/dri
```

```bash
ls -l /dev/dri
```

## VPN (qBittorrent, Prowlarr, Flaresolverr)

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/vpn
# scp wg0.conf into that directory
```

Set `AMM_VPN_ENABLED=true` in the project compose (and `AMM_VPN_ENFORCE=true` if torrents must not run without a tunnel), then start the project again. Synology’s kernel often has no WireGuard module; the appliance image includes **wireguard-go** as a fallback. Recreate the container after pulling a current image, then save VPN in **Settings → Network**. OpenVPN works without that module if `/dev/net/tun` is present (privileged mode).

## Cloudflare Tunnel

Do not add a second project service. Write the token on the NAS, then set `AMM_CLOUDFLARE_TUNNEL_ENABLED=true` in the project compose. See [CLOUDFLARE.md](CLOUDFLARE.md).

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/cloudflare
sudo tee /volume1/docker/aio-media-manager/config/cloudflare/tunnel.token >/dev/null <<'EOF'
eyJ...paste-token...
EOF
sudo chmod 600 /volume1/docker/aio-media-manager/config/cloudflare/tunnel.token
```

## Permissions

`PUID`/`PGID` in the compose file must match the `chown` the script applied. If apps cannot write, fix ownership over SSH rather than running as root.
