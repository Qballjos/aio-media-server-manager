# TrueNAS SCALE

Use a **single** custom app / Docker deployment. Do not deploy the *Arr stack as separate SCALE apps if you want this appliance model.

Image: `ghcr.io/qballjos/aio-media-server-manager:latest`

## Datasets

Create datasets (examples):

- `tank/apps/aio-media-manager` (config)
- `tank/downloads`
- `tank/media`

Keep downloads and media on the same pool/dataset layout so hardlinks work. Set the dataset owner to your media user (for example UID 568 `apps`, or a dedicated user).

## Custom App

1. **Apps → Discover → Custom App** (or Launch Docker Image).
2. Image: `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Port forwarding: `8080` → `8080` (and child WebUI ports, or host network).
4. Storage:
   - config dataset → `/config`
   - downloads dataset → `/downloads`
   - media dataset → `/media`
5. Environment: `PUID` / `PGID` = dataset owner.
6. Privileged / `NET_ADMIN` if you enable qBittorrent VPN.
7. GPU: pass `/dev/dri` (Intel/AMD) or NVIDIA runtime when transcoding.

The manager UI is `http://<truenas-ip>:8080`.

## Updates

TrueNAS will pull a newer `:latest` when you update the app. Pin a semver tag (`:0.1.0`) if you want slower upgrades once git tags exist.
