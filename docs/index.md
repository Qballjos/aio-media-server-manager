---
hide:
  - navigation
  - toc
title: AIO Media Server Manager
---

<div class="aio-hero" markdown>

<div class="aio-hero__brand" markdown>
<img src="assets/logo-aio-media-manager.png" alt="" width="40" height="40" />
AIO Media Server Manager
</div>

# Your whole media stack. One install.

<p class="aio-hero__lead">
Downloads, *Arr apps, and streaming — supervised from a single dashboard.
No Compose file full of Sonarr, Radarr, and qBittorrent containers.
</p>

<div class="aio-hero__actions" markdown>

[Install now](INSTALL.md){ .md-button .md-button--primary }
[Using the dashboard](USAGE.md){ .md-button }
[GitHub](https://github.com/Qballjos/aio-media-server-manager){ .md-button }

</div>
</div>

<div class="aio-shot" markdown>
![AIO Media Manager sign-in](screenshots/login.png)
</div>

<div class="aio-shot" markdown>
![AIO Media Manager home dashboard](screenshots/dashboard.png)
</div>

<div class="aio-shot" markdown>
![AIO Media Manager application catalog](screenshots/catalog.png)
</div>

## Start where you are

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __New here__

    ---

    Create folders, start the container, open the UI.

    [:octicons-arrow-right-24: Install guide](INSTALL.md)

-   :material-view-dashboard-outline:{ .lg .middle } __Already running__

    ---

    Enable apps, open each web UI, wire libraries.

    [:octicons-arrow-right-24: Using the dashboard](USAGE.md)

-   :material-docker:{ .lg .middle } __Docker host__

    ---

    The usual path for NAS boxes and Linux servers.

    [:octicons-arrow-right-24: Docker guide](deploy/DOCKER.md)

-   :material-cloud-lock-outline:{ .lg .middle } __Away from home__

    ---

    HTTPS via Cloudflare Tunnel, then a login gate with Access.

    [:octicons-arrow-right-24: Remote access](deploy/CLOUDFLARE.md)

</div>

## Pick your platform

<div class="grid cards" markdown>

-   :material-nas:{ .lg .middle } __Unraid__

    ---

    One Community Applications–style container.

    [Unraid guide](deploy/UNRAID.md)

-   :material-server:{ .lg .middle } __Synology__

    ---

    One Container Manager project.

    [Synology guide](deploy/SYNOLOGY.md)

-   :material-harddisk:{ .lg .middle } __TrueNAS__

    ---

    One custom app on SCALE.

    [TrueNAS guide](deploy/TRUENAS.md)

-   :material-linux:{ .lg .middle } __Linux / LXC__

    ---

    Native install without Docker.

    [Linux guide](deploy/LINUX.md)

</div>

## What you get

<div class="grid cards" markdown>

-   :material-monitor-dashboard:{ .lg .middle } __One dashboard__

    ---

    Status, start/stop, and **Open UI** for every app you enable.

-   :material-television-play:{ .lg .middle } __Automation + libraries__

    ---

    Sonarr, Radarr, Lidarr, Bazarr, and friends — when you want them.

-   :material-download:{ .lg .middle } __Downloads__

    ---

    Torrents and Usenet clients, optional VPN on the download path.

-   :material-cast:{ .lg .middle } __Watch & request__

    ---

    Jellyfin, Plex, Seerr, and more — same appliance.

</div>

<div class="aio-callout" markdown>

**The one rule:** one AIO install = one container (or one native service).  
Do not add separate Sonarr/Radarr/qBittorrent containers next to it.

</div>

## Image

```text
ghcr.io/qballjos/aio-media-server-manager:latest
```

Works on `linux/amd64` and `linux/arm64`. After a pull, recreate the container so new ports and runtimes apply.
