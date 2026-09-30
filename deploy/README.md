# Deployment

AIO Media Server Manager is **one process tree** — typically **one container**. Never add a Compose service per application.

**Image:** [`ghcr.io/qballjos/aio-media-server-manager`](https://github.com/Qballjos/aio-media-server-manager/pkgs/container/aio-media-server-manager)

| Mode | Guide |
|------|--------|
| Docker (recommended) | [DOCKER.md](DOCKER.md) |
| Native Linux / LXC | [LINUX.md](LINUX.md) |
| Unraid | [UNRAID.md](UNRAID.md) |
| Synology Container Manager | [SYNOLOGY.md](SYNOLOGY.md), [`synology/`](synology/) |
| TrueNAS SCALE | [TRUENAS.md](TRUENAS.md) |
| Optional Cloudflare Tunnel | [CLOUDFLARE.md](CLOUDFLARE.md) |

Overview: [docs/INSTALL.md](../docs/INSTALL.md) · first-run: [docs/USAGE.md](../docs/USAGE.md)

Recreate the container after an image pull so WebUI port mappings, the Python 3.13 child runtime (Bazarr), and Debian `unrar` (SABnzbd) apply. Recyclarr is CLI-only and has no host port.
