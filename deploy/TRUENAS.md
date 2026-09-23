# TrueNAS SCALE

Use a **single** custom app / Docker deployment. Do not deploy the *Arr stack as separate SCALE apps if you want this appliance model.

Image: `ghcr.io/qballjos/aio-media-server-manager:latest`

## Create datasets and folders over SSH

Enable SSH (System → Services → SSH), then:

```bash
ssh admin@<truenas-ip>
```

Replace `tank` with your pool name. Create datasets, then the directories the container will mount:

```bash
sudo zfs create -p tank/apps/aio-media-manager
sudo zfs create -p tank/data

sudo mkdir -p \
  /mnt/tank/apps/aio-media-manager/vpn \
  /mnt/tank/data/downloads \
  /mnt/tank/data/media
```

TV, movies, anime, music, books, complete/incomplete downloads, torrent category folders, and transcode caches are created inside these mounts on first start.

Set the owner to your media user (TrueNAS `apps` is often UID/GID `568`; confirm with `id apps` or `id`):

```bash
id apps
sudo chown -R 568:568 \
  /mnt/tank/apps/aio-media-manager \
  /mnt/tank/data
```

Keep downloads and media as **directories on one dataset**. Two ZFS datasets cannot hardlink to each other.

## Custom App

1. **Apps → Discover → Custom App** (or Launch Docker Image).
2. Image: `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Port forwarding: `8080` → `8080` (and child WebUI ports, or host network).
4. Storage (paths from the SSH commands above):
   - `/mnt/tank/apps/aio-media-manager` → `/config`
   - `/mnt/tank/data` → `/data`
5. Environment: `PUID` / `PGID` = the UID/GID you used with `chown`, plus `AMM_DOWNLOAD_DIR=/data/downloads` and `AMM_MEDIA_DIR=/data/media`.
6. Privileged / `NET_ADMIN` if you enable qBittorrent VPN.
7. GPU: pass `/dev/dri` (Intel/AMD) or NVIDIA runtime when transcoding.

The manager UI is `http://<truenas-ip>:8080`.

## Updates

TrueNAS will pull a newer `:latest` when you update the app. Pin a semver tag (`:0.1.0`) if you want slower upgrades once git tags exist.
