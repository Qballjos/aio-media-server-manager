# Synology Container Manager

Deploy **one** AIO container. Do not add separate containers for Sonarr, Radarr, or download clients.

## Suggested setup

1. Build or load the `aio-media-manager` image on the NAS.
2. In Container Manager, create a container with:
   - Port: `8080/tcp`
   - Volumes:
     - `/volume1/docker/aio-media-manager/config` → `/config`
     - `/volume1/media` → `/media`
     - `/volume1/downloads` → `/downloads`
   - Environment: `PUID` / `PGID` matching the share permissions (`id` of the media user).
3. Optional hardware transcoding: add device `/dev/dri`.
4. Optional torrent VPN: enable privileged mode and `NET_ADMIN`, then place a WireGuard/OpenVPN profile in `/config/vpn/`.

Open `http://<nas-ip>:8080` and complete the first-run wizard.
