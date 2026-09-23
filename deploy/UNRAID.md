# Unraid installation

Deploy **one** container. Do not add Community Applications templates for Sonarr, Radarr, or download clients alongside this appliance.

## Create folders over SSH

Enable SSH (Settings → Management Access), then:

```bash
ssh root@<unraid-ip>
```

```bash
mkdir -p \
  /mnt/user/appdata/aio-media-manager/vpn \
  /mnt/cache/data/downloads \
  /mnt/cache/data/media

chown -R 99:100 \
  /mnt/user/appdata/aio-media-manager \
  /mnt/cache/data
```

TV, movies, anime, music, books, complete/incomplete downloads, torrent category folders, and transcode caches are created inside these mounts on first start.

`99:100` is Unraid `nobody`/`users` (PUID 99, PGID 100). If you use a custom share user, run `id thatuser` and `chown` to that UID:GID instead.

For hardlinks, keep downloads and media as subfolders of **one** cache or disk path (not two `/mnt/user` FUSE shares), for example:

```bash
mkdir -p /mnt/cache/appdata/aio-media-manager/vpn
mkdir -p /mnt/cache/data/downloads /mnt/cache/data/media
chown -R 99:100 /mnt/cache/appdata/aio-media-manager /mnt/cache/data
```

## Docker template

1. Docker → Add Container.
2. Switch to **advanced view**.
3. Repository: `ghcr.io/qballjos/aio-media-server-manager:latest`
4. Network: `bridge` (or `host` if you want every app WebUI on the Unraid IP).
5. Privileged: **On** (needed for qBittorrent VPN isolation).
6. Extra parameters: `--device /dev/dri:/dev/dri --cap-add=NET_ADMIN --cap-add=SYS_MODULE`
7. Port: `8080` → `8080` (plus any child ports you want published).
8. Paths (must match the SSH folders):
   - `/config` → `/mnt/user/appdata/aio-media-manager`
   - `/data` → `/mnt/cache/data`
9. Variables: `PUID=99`, `PGID=100`, `AMM_DOWNLOAD_DIR=/data/downloads`, `AMM_MEDIA_DIR=/data/media`.

A starting XML template is in [`unraid.xml`](unraid.xml) (copy into `/boot/config/plugins/dockerMan/templates-user/` if you maintain local templates).

Open `http://<unraid-ip>:8080` and run the wizard.

## FUSE / hardlinks

Prefer `/mnt/cache/...` or a single disk path for downloads and media when you care about hardlinks. Mixing `/mnt/user` (FUSE) with a disk share can break atomic moves.

## Updates

Change the repository tag or use Unraid's container update. Images are published from `main` as `:latest` and from git tags as semver.
