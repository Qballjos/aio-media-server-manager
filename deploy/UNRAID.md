# Unraid installation

Deploy **one** container. Do not add Community Applications templates for Sonarr, Radarr, or download clients alongside this appliance.

## Docker template

1. Docker → Add Container.
2. Switch to **advanced view**.
3. Repository: `ghcr.io/qballjos/aio-media-server-manager:latest`
4. Network: `bridge` (or `host` if you want every app WebUI on the Unraid IP).
5. Privileged: **On** (needed for qBittorrent VPN isolation).
6. Extra parameters: `--device /dev/dri:/dev/dri --cap-add=NET_ADMIN --cap-add=SYS_MODULE`
7. Port: `8080` → `8080` (plus any child ports you want published).
8. Paths:
   - `/config` → `/mnt/user/appdata/aio-media-manager`
   - `/downloads` → `/mnt/user/downloads`
   - `/media` → `/mnt/user/media`
9. Variables: `PUID=99`, `PGID=100` (Unraid `nobody` / `users` unless you use a custom share user).

A starting XML template is in [`unraid.xml`](unraid.xml) (copy into `/boot/config/plugins/dockerMan/templates-user/` if you maintain local templates).

Open `http://<unraid-ip>:8080` and run the wizard.

## FUSE / hardlinks

Prefer `/mnt/cache/...` or a single disk path for downloads and media when you care about hardlinks. Mixing `/mnt/user` (FUSE) with a disk share can break atomic moves.

## Updates

Change the repository tag or use Unraid's container update. Images are published from `main` as `:latest` and from git tags as semver.
