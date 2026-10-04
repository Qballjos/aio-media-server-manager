# Unraid installation

Deploy **one** container. Do not add Community Applications templates for Sonarr, Radarr, or download clients alongside this appliance.

**Templates in this repo**

| File | Purpose |
|------|---------|
| [`unraid/templates/aio-media-manager.xml`](unraid/templates/aio-media-manager.xml) | Canonical Docker template (ports, paths, env) |
| [`unraid/ca_profile.xml`](unraid/ca_profile.xml) | Community Applications maintainer profile |
| [`unraid.xml`](unraid.xml) | Same template at the older path (kept for compatibility) |

## Create folders over SSH

Enable SSH (Settings → Management Access), then:

```bash
ssh root@<unraid-ip>
```

Downloads and media live on the **user share** `aio-media-manager` (visible in Shares / the file browser). Config stays in appdata.

```bash
mkdir -p \
  /mnt/user/appdata/aio-media-manager/vpn \
  /mnt/user/backups/aio-media-manager \
  /mnt/user/aio-media-manager/downloads \
  /mnt/user/aio-media-manager/media

chown -R 99:100 \
  /mnt/user/appdata/aio-media-manager \
  /mnt/user/backups/aio-media-manager \
  /mnt/user/aio-media-manager
```

`/mnt/user/backups/aio-media-manager` receives the configuration backups. Use a share that lives on the array (not only the cache pool), so a cache failure does not take the backups with it.

TV, movies, anime, music, books, complete/incomplete downloads, torrent category folders, and transcode caches are created inside these mounts on first start.

`99:100` is Unraid `nobody`/`users` (PUID 99, PGID 100). If you use a custom share user, run `id thatuser` and `chown` to that UID:GID instead.

For hardlinks, keep downloads and media as subfolders of **one** cache or disk path (not two `/mnt/user` FUSE shares), for example a cache-only share named `aio-media-manager`:

```bash
mkdir -p /mnt/cache/aio-media-manager/downloads /mnt/cache/aio-media-manager/media
chown -R 99:100 /mnt/cache/aio-media-manager
```

Then bind `/data` to `/mnt/cache/aio-media-manager` (same share, disk path) instead of `/mnt/user/aio-media-manager`.

## Install from the template (your server)

### Option A — Local user template

1. Copy the XML onto the flash drive:

   ```bash
   mkdir -p /boot/config/plugins/dockerMan/templates-user
   curl -fsSL \
     -o /boot/config/plugins/dockerMan/templates-user/my-aio-media-manager.xml \
     https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/templates/aio-media-manager.xml
   ```

2. Docker → **Add Container** → select **aio-media-manager** (or `my-aio-media-manager`) from the Template list.
3. Confirm paths, `PUID`/`PGID`, and `TZ`, then Apply.
4. Open `http://<unraid-ip>:8080` and run the wizard.

### Option B — Manual Add Container

1. Docker → Add Container → advanced view.
2. Repository: `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Network: `bridge` (or `host` if you want every app WebUI on the Unraid IP).
4. Privileged: **On** (needed for qBittorrent VPN isolation).
5. Extra parameters: `--cap-add=NET_ADMIN --cap-add=SYS_MODULE`
6. Optional device: `/dev/dri` for Intel/AMD transcoding (skip if missing).
7. Ports (TCP): publish **8080** for the manager and the child WebUIs you installed (Sonarr **8989**, Radarr **7878**, qBittorrent **8081**, SABnzbd **8085**, Jellyfin **8096**, Prowlarr **9696**, Seerr **5055**, Plex **32400**, …). Full list: [INSTALL.md](../docs/INSTALL.md#ports). Or use Network `host`.
8. Paths:
   - `/config` → `/mnt/user/appdata/aio-media-manager`
   - `/data` → `/mnt/user/aio-media-manager`
   - `/backups` → `/mnt/user/backups/aio-media-manager`
9. Variables: `PUID=99`, `PGID=100`, `TZ=<IANA timezone>`, `AMM_DOWNLOAD_DIR=/data/downloads`, `AMM_MEDIA_DIR=/data/media`. Optional: `GITHUB_TOKEN`.

After updating the image, recreate the container so added WebUI port mappings take effect.

## Publish to Community Applications (public store)

Community Apps does **not** host your files. You keep a public GitHub repo with templates; Lime Technology’s CA scanner indexes it after you submit.

### 1. Prepare a templates repository

Recommended: a **dedicated public repo** (for example `Qballjos/unraid-templates`) whose root looks like:

```text
ca_profile.xml
templates/aio-media-manager.xml
```

Copy from this project:

```bash
# from a clone of aio-media-server-manager
mkdir -p ../unraid-templates/templates
cp deploy/unraid/ca_profile.xml ../unraid-templates/
cp deploy/unraid/templates/aio-media-manager.xml ../unraid-templates/templates/
```

Then:

1. Create the public GitHub repo and push `main`.
2. Edit `templates/aio-media-manager.xml` and set `<TemplateURL>` to the **raw** URL of that file in the new repo (must match the real path on `main`).
3. Keep `<Repository>` as `ghcr.io/qballjos/aio-media-server-manager:latest` (image stays on GHCR; only the template XML lives in the templates repo).
4. Optional: open an Unraid forum support thread and put its URL in `ca_profile.xml` `<Forum>` and the template `<Support>` tags (GitHub Issues is fine to start).

You *can* submit the main app repo instead if the XML is discoverable and every app has a `<Repository>` tag, but a small dedicated templates repo is what CA maintainers usually expect.

### 2. Submit

1. Sign in at **[https://ca.unraid.net/submit](https://ca.unraid.net/submit)** with your Unraid / forum account.
2. Register the **GitHub repository URL** (the templates repo).
3. Run **Validate**, then **Scan**. Fix any reported XML issues.
4. Wait for moderation. When approved, the app appears under the Apps tab for everyone.

Helpful docs:

- [Submission help](https://ca.unraid.net/submit/help)
- [Repository XML format](https://ca.unraid.net/submit/help/repository-xml)
- [XML field reference](https://ca.unraid.net/submit/help/xml-field-reference)
- [Browse catalog](https://ca.unraid.net/apps) (check for name clashes first)

Do **not** use the retired `selfhosters/unRAID-CA-templates` request flow.

### 3. After it is listed

- Ship updates by publishing a new container image (`:latest` or semver tags). Users update via Unraid’s Docker update — you usually do **not** bump the template for every release.
- Change the template XML only when ports, paths, or env vars change; CA re-reads `<TemplateURL>` on refresh.

### Private / self-only (not the public store)

To use your own GitHub templates without CA approval, append the repo URL to:

```text
/boot/config/plugins/dockerMan/template-repos
```

(one URL per line). Templates then appear under Docker → Add Container. That does **not** list the app in the public Community Applications catalog.

## FUSE / hardlinks

Prefer `/mnt/cache/aio-media-manager` or a single disk path for downloads and media when you care about hardlinks. Mixing `/mnt/user` (FUSE) with a disk share can break atomic moves.

## Updates

Change the repository tag or use Unraid's container update. Images are published from `main` as `:latest` and from git tags as semver.
