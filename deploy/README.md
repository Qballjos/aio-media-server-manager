# Deploy

AIO is meant to run as **one** install — usually **one Docker container**.  
Do not add a separate Compose service for Sonarr, Radarr, or each download client.

**Friendly docs site:** [qballjos.github.io/aio-media-server-manager](https://qballjos.github.io/aio-media-server-manager/)  
**Image:** [`ghcr.io/qballjos/aio-media-server-manager`](https://github.com/Qballjos/aio-media-server-manager/pkgs/container/aio-media-server-manager)

| I am using… | Guide |
|-------------|--------|
| Docker / Compose (most people) | [DOCKER.md](DOCKER.md) |
| Unraid | [UNRAID.md](UNRAID.md) · templates in [`unraid/`](unraid/) |
| Synology Container Manager | [SYNOLOGY.md](SYNOLOGY.md) · [`synology/`](synology/) |
| TrueNAS SCALE | [TRUENAS.md](TRUENAS.md) |
| Linux / LXC without Docker | [LINUX.md](LINUX.md) |
| Remote access (optional) | [CLOUDFLARE.md](CLOUDFLARE.md) |
| Login gate on public URLs | [CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md) |

New install overview: [Install](../docs/INSTALL.md) · after it runs: [Using the dashboard](../docs/USAGE.md)

**Tip:** After you pull a new image, **recreate** the container so updated ports and runtimes apply. A restart alone is not enough.
