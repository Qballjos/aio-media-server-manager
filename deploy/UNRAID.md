# Unraid

Install **one** AIO container. Do not also add Community Applications templates for Sonarr, Radarr, or download clients — AIO runs those inside itself.

**Templates in this repo**

| File | Purpose |
|------|---------|
| [`unraid/templates/aio-media-manager.xml`](unraid/templates/aio-media-manager.xml) | Docker template (ports, paths, env) |
| [`unraid/ca_profile.xml`](unraid/ca_profile.xml) | Community Applications maintainer profile |
| [`unraid.xml`](unraid.xml) | Older path for the same template (compatibility) |

## Prepare SSD download storage over SSH

Start the array with a mounted SSD/NVMe pool, then enable SSH (**Settings → Management Access**) and connect as root:

```bash
ssh root@<unraid-ip>
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/install.sh | sh
```

The installer validates `/mnt/cache` before writing folders and installs the local Docker template. To select a differently named pool:

```bash
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/install.sh -o /tmp/amm-install.sh
CACHE_ROOT=/mnt/fast sh /tmp/amm-install.sh
```

| Data | Host path (default) | Container path |
|---|---|---|
| Active downloads: SABnzbd, NZBGet, qBittorrent | `/mnt/cache/aio-download-cache/incomplete` | `/data/downloads/incomplete` |
| Completed Usenet downloads / unpacking | `/mnt/cache/aio-download-cache/complete` | `/data/downloads/complete` |
| Finished torrents for seeding | `/mnt/user/aio-media-manager/downloads/torrents` | `/data/downloads/torrents` |
| Imported media library | `/mnt/user/aio-media-manager/media` | `/data/media` |
| App configuration | `/mnt/user/appdata/aio-media-manager` | `/config` |
| Configuration backups | `/mnt/user/backups/aio-media-manager` | `/backups` |

The installer creates an `aio-download-cache` pool-only share configuration. In **Shares**, verify its primary storage is your SSD pool and secondary storage is **None** (older Unraid: **Use cache pool: Only**). Mover must not move active staging files onto the array. An existing share with different storage settings causes setup to stop rather than overwrite them. Keep the `aio-media-manager` media share and backups on the array, and appdata on your preferred pool.

Leave enough SSD space for all concurrent downloads plus unpacking; a large archive can temporarily require both its compressed and extracted sizes. These direct pool mounts do not overflow to the array. Configure the downloader's minimum-free-space pause threshold accordingly; Unraid's share free-space threshold does not protect direct pool writes.

SSD staging and HDD media are different filesystems, so *Arr imports **copy** files. Completed torrents move back to the Data mount for seeding; hardlinks from those files to the library require the same physical filesystem. Keep the two nested download mounts after `/data` in the template.

**Existing installations:** the installer refuses nonempty or symlinked staging directories so applying the template cannot hide queued files. Stop AIO, copy and verify both staging directories to the chosen pool, retain a rollback copy, then clear the old staging directories and apply the new mounts. Do not copy between `/mnt/user` and `/mnt/disk*` representations of the same files. This is preparation for a new setup, not an automatic migration of a running container.

Without a pool, setup stops with instructions. For a deliberate HDD-only install, prepare the normal data/config/backup folders and remove both SSD staging mounts in Unraid's template editor; download performance will depend on the array.

## Install from the template (your server)

### Option A — Local user template

1. Run the preparation script above; it installs `/boot/config/plugins/dockerMan/templates-user/my-aio-media-manager.xml` with the selected pool paths.

2. Docker → **Add Container** → select **aio-media-manager** (or `my-aio-media-manager`) from the Template list.
3. Confirm paths, `PUID`/`PGID`, and `TZ`, then Apply.
4. Open `http://<unraid-ip>:8080` and run the wizard.

### Option B — Manual Add Container

1. Docker → Add Container → advanced view.
2. Repository: `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Network: `bridge` (or `host` if you want every app WebUI on the Unraid IP).
4. Privileged: **On** (needed for qBittorrent / Prowlarr / Flaresolverr VPN isolation). With VPN on, those apps wait for a live WireGuard handshake; AIO caches their DNS through the tunnel so short hiccups do not knock Prowlarr indexers offline. Details: [DOCKER.md](DOCKER.md#optional-vpn).
5. Extra parameters: `--cap-add=NET_ADMIN --cap-add=SYS_MODULE`
6. Optional device: `/dev/dri` for Intel/AMD transcoding (skip if missing).
7. Ports (TCP): publish **8080** for the manager and the child WebUIs you installed (Sonarr **8989**, Radarr **7878**, qBittorrent **8081**, SABnzbd **8085**, Jellyfin **8096**, Prowlarr **9696**, Seerr **5055**, Plex **32400**, …). Full list: [INSTALL.md](../docs/INSTALL.md#ports). Or use Network `host`.
8. Paths:
   - `/config` → `/mnt/user/appdata/aio-media-manager`
   - `/data` → `/mnt/user/aio-media-manager`
   - `/data/downloads/incomplete` → `/mnt/cache/aio-download-cache/incomplete` (your SSD pool)
   - `/data/downloads/complete` → `/mnt/cache/aio-download-cache/complete` (your SSD pool)
   - `/backups` → `/mnt/user/backups/aio-media-manager`
   - `/host/sys` → `/sys` (read-only). Home's Server card then shows the server's network traffic. The template lists this as **Host sys** (advanced). Without it, the graph is only this container's traffic.
9. Variables: `PUID=99`, `PGID=100`, `TZ=<IANA timezone>`, `AMM_DOWNLOAD_DIR=/data/downloads`, `AMM_MEDIA_DIR=/data/media`. Optional: `GITHUB_TOKEN`.

After updating the image, recreate the container so added WebUI port mappings take effect.

??? note "For maintainers: publishing a template (not needed for installation)"

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

The default layout prioritizes SSD download speed and array library capacity. SSD-to-array imports copy files. Finished torrents and the library remain under `/data`; hardlinks between them require the same physical filesystem. Do not mix `/mnt/user` and `/mnt/disk*` views of the same files during migration.

## Updates

Change the repository tag or use Unraid's container update, then recreate so new ports and the Host sys mount apply. Images are published from `main` as `:latest` and from git tags as semver. That updates AIO. Installed apps update from **Settings → Updates** (schedules default to off).
