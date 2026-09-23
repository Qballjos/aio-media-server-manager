# Synology Container Manager

Deploy **one** AIO container. Do not add separate containers for Sonarr, Radarr, or download clients.

Image: `ghcr.io/qballjos/aio-media-server-manager:latest`  
Use a DSM build that can run `linux/amd64` or `linux/arm64` images (most Plus and 2025 ARM NAS units).

## Suggested setup

1. Pull the image (SSH or Container Manager → Image):

   ```bash
   sudo docker pull ghcr.io/qballjos/aio-media-server-manager:latest
   ```

   If GHCR is private, run `sudo docker login ghcr.io` first.

2. Create folders (File Station or SSH), for example:
   - `/volume1/docker/aio-media-manager/config`
   - `/volume1/downloads`
   - `/volume1/media`

3. **Container Manager → Container → Create** from that image:
   - Port: `8080/tcp` (add child app ports or use host network).
   - Volumes:
     - `/volume1/docker/aio-media-manager/config` → `/config`
     - `/volume1/media` → `/media`
     - `/volume1/downloads` → `/downloads`
   - Environment: `PUID` / `PGID` matching the share permissions (`id` of the media user, often `1026` / `100` on DSM).
   - Privileged: on if you will use torrent VPN.
   - Devices: `/dev/dri` when the NAS has an iGPU and you want transcoding.

4. Optional torrent VPN: place a WireGuard/OpenVPN profile in `/volume1/docker/aio-media-manager/config/vpn/` and set `AMM_VPN_ENABLED=true`.

Open `http://<nas-ip>:8080` and complete the first-run wizard.

## Permissions

Map the container to the same user DSM uses for the media shared folder. If apps cannot write, fix the share ACL rather than running as root.
