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

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Administrator sign-in, light theme](screenshots/light/login.png)

</div>

<div class="aio-shot" markdown>

![Administrator sign-in, dark theme](screenshots/dark/login.png)

</div>

</div>

<p class="aio-shot-caption">Sign-in — light and dark.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Home before any applications are installed, light theme](screenshots/light/dashboard.png)

</div>

<div class="aio-shot" markdown>

![Home before any applications are installed, dark theme](screenshots/dark/dashboard.png)

</div>

</div>

<p class="aio-shot-caption">Home before any apps with a WebUI are installed.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Catalog with application cards and install controls, light theme](screenshots/light/catalog.png)

</div>

<div class="aio-shot" markdown>

![Catalog with application cards and install controls, dark theme](screenshots/dark/catalog.png)

</div>

</div>

<p class="aio-shot-caption">Catalog — search, filters, and install.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Settings account page, light theme](screenshots/light/settings.png)

</div>

<div class="aio-shot" markdown>

![Settings account page, dark theme](screenshots/dark/settings.png)

</div>

</div>

<p class="aio-shot-caption">Settings. Visuals, catalog app settings, and the other sections are in <a href="USAGE.md#screens">Using the dashboard</a>.</p>

## Start where you are

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __New here__

    ---

    Create folders, start the container, open the UI.

    [:octicons-arrow-right-24: Install guide](INSTALL.md)

-   :material-view-dashboard-outline:{ .lg .middle } __Already running__

    ---

    Home, Catalog, and each app's Open UI.

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

    Home for what is new, playing, or needs a look. Catalog for install, start/stop, and **Open UI**.

-   :material-television-play:{ .lg .middle } __Automation + libraries__

    ---

    Sonarr, Radarr, Lidarr, and Bazarr — when you want them.

-   :material-download:{ .lg .middle } __Downloads__

    ---

    Torrents and Usenet clients, optional VPN on the download path.

-   :material-cast:{ .lg .middle } __Watch & request__

    ---

    Jellyfin, Plex, and Seerr — same appliance.

</div>

<div class="aio-callout" markdown>

**The one rule:** one AIO install = one container (or one native service).  
Do not add separate Sonarr/Radarr/qBittorrent containers next to it.

</div>

## Intended use

AIO is a self-hosting management tool for a personal media library and a home lab:

- Files you own (home videos, family photos, public-domain media, or your own backups of physical media).
- Local network setup and server administration.

This repository does not host or distribute copyrighted content. It is not a licence or a legal shield. Using it to acquire, download, stream, or share unauthorized copyrighted material breaks copyright law in most places. You are responsible for following the laws where you live.

## Vibe coded

**Yes — this app was vibe coded.**  
It was built with AI pair-programming in Cursor, steered by a human who wanted a full media stack without babysitting twelve containers. That is intentional, not a secret.

If something is rough around the edges, open an issue or a PR. The vibes improve with feedback.

## Image

```text
ghcr.io/qballjos/aio-media-server-manager:latest
```

Works on `linux/amd64` and `linux/arm64`. After a pull, recreate the container so new ports and runtimes apply.
