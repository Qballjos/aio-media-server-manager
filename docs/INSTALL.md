# Your first AIO installation

You do not need to install every app or understand Docker to choose the right guide. Start with the server you already have.

!!! info "What you are installing"
    AIO is one application that manages several media tools inside **one container** (a packaged app running on your server). Install AIO once. Add Sonarr, Radarr, Jellyfin and download clients from **AIO → Catalog**, rather than installing separate containers for them.

## 1. Pick your server

Follow **one** guide below. Do not run commands from all the guides.

| Your server | Start here | Check this first |
|---|---|---|
| Unraid | [Unraid setup](deploy/UNRAID.md) | Array started; SSD/NVMe pool mounted for fast downloads |
| Synology NAS | [Synology setup](deploy/SYNOLOGY.md) | Container Manager installed and running; let DSM create the docker folder |
| TrueNAS SCALE | [TrueNAS setup](deploy/TRUENAS.md) | Permission to create a custom app and storage folders |
| Another computer with Docker | [Docker setup](deploy/DOCKER.md) | Docker and Docker Compose installed and running |
| Debian, Ubuntu or Proxmox LXC without Docker | [Native Linux setup](ADVANCED.md) | Comfortable administering a Linux server |

A **NAS** is a network storage server. If you are reading this on a laptop, the server is usually a separate device. Run installation commands on that device; open the dashboard from your laptop or phone afterward.

## 2. Know where your files will go

The platform guide creates the right folders for you. Do not copy placeholder paths from a different platform.

| Folder | What it holds | Keep in mind |
|---|---|---|
| Config | App settings, accounts and databases | Keep backups of this folder |
| Download staging | Files being downloaded or unpacked | SSD/NVMe helps here; leave room for downloading **and** extraction |
| Finished torrents | Completed torrents that may still be seeding | Can stay on HDD storage |
| Media library | Your organised films, shows and other media | Can stay on large HDDs |
| Backups | Saved configuration backups | Prefer a separate disk or backup destination |

A **host path** is a folder on your NAS. A **container path**, such as `/data/media`, is how AIO sees that folder inside the container. They refer to the same files through a folder mapping; do not create a second library because the path looks different.

SSD downloads and an HDD library can work together. Follow the folders in your platform guide; custom storage is covered under Advanced.

!!! tip "Leave the defaults alone at first"
    Keep the paths and ports from your platform guide unless they conflict with something already running. A VPN, domain name and Cloudflare account are **optional**. You can add them later.

## 3. Open AIO

Once your platform guide says the container is running, open this address in a browser:

```text
http://YOUR-SERVER-IP:8080
```

Replace `YOUR-SERVER-IP` with your NAS/server's address, for example `http://192.168.1.50:8080`. That address is only an example; use the address shown by your router or NAS. If you changed the host port, use that port instead of `8080`.

**You should see:** the AIO account-creation screen. Create your administrator account with a username, email and password. If you see a login screen instead, an account already exists; sign in with that account.

## 4. Finish the setup wizard

1. Choose only the apps you need. A small starting point is **Jellyfin** for playback, plus the automation/download tools you actually use.
2. Enter a Usenet provider account **only if you chose a Usenet downloader**. AIO does not supply a Usenet subscription.
3. Leave VPN and remote access off unless you are ready to configure them.
4. Finish the wizard and wait for installation. Open **Catalog** and look for **Running** on your chosen apps.
5. Choose **Open UI** on an app to finish its own setup. Jellyfin/Plex can need their own account and library settings; the AIO account does not replace them.

**You should see:** Home, Catalog and Settings in AIO, with your chosen apps listed in Catalog. A first download of an app can take time. If an app stays stopped or fails, open its logs rather than repeatedly reinstalling it.

## 5. Make Home your own

[Try the visual widget example](index.md#app-preview), then follow [the dashboard guide](USAGE.md#customize-home). It shows the layout button, adding widgets, moving them and changing their size. An empty Home does not necessarily mean something is broken: many widgets need a connected app with content first.

## If you get stuck

| What you see | What to do next |
|---|---|
| Browser cannot connect | Confirm AIO is running. Check the server IP and mapped host port. Use the same home network first. |
| Port already in use | Another app is using that host port. Change the **host** side of the mapping in your platform settings, then open the new port. |
| Permission denied | Follow the ownership step in your platform guide. PUID/PGID are the numeric user/group IDs AIO uses; they must be allowed to write to the folders. |
| Synology docker folder missing | Install and start DSM Container Manager first. Do not make the docker shared folder manually before installation. |
| Home widget empty | Check Catalog for the app it depends on, then the widget help in [Using the dashboard](USAGE.md#customize-home). |
| Download speed low | Check whether active downloads/unpacking land on HDDs or SSD. Use the storage options in your NAS guide. |
| Open UI cannot connect | Check that app is running and its port is published (advanced port reference). |

## Updates and optional remote access

Updating AIO and updating the apps inside it are different actions:

- **AIO:** follow your platform's container update flow. Pull the new image and **recreate** the container while keeping the same folder mappings. A restart alone does not apply a new image.
- **Managed apps:** use **Settings → Updates** in AIO. Automatic schedules default to off.
- **Remote access:** configure [Cloudflare Tunnel](deploy/CLOUDFLARE.md), then [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md). Start locally before adding this.

Technical reference material is kept separately under Advanced.

## Advanced

These pages cover custom setups and troubleshooting. They are not extra steps you must complete after installing AIO. [Advanced](ADVANCED.md).

### Ports and configuration variables {#ports}

[Ports and configuration variables](REFERENCE.md#ports).
