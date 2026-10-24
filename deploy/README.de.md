# Bereitstellen

AIO soll als **eine** Installation laufen — meist **ein Docker-Container**.  
Fügen Sie keinen eigenen Compose-Dienst für Sonarr, Radarr oder jeden Download-Client hinzu.

**Dokumentationsseite:** [qballjos.github.io/aio-media-server-manager](https://qballjos.github.io/aio-media-server-manager/)  
**Image:** [`ghcr.io/qballjos/aio-media-server-manager`](https://github.com/Qballjos/aio-media-server-manager/pkgs/container/aio-media-server-manager)

| Ich nutze… | Anleitung |
|-------------|--------|
| Docker / Compose (die meisten) | [DOCKER.md](DOCKER.md) |
| Unraid | [UNRAID.md](UNRAID.md) · Vorlagen in [`unraid/`](unraid/) |
| Synology Container Manager | [SYNOLOGY.md](SYNOLOGY.md) · [`synology/`](synology/) |
| TrueNAS SCALE | [TRUENAS.md](TRUENAS.md) |
| Linux / LXC ohne Docker | [LINUX.md](LINUX.md) |
| Fernzugriff (optional) | [CLOUDFLARE.md](CLOUDFLARE.md) |
| Anmeldung vor öffentlichen URLs | [CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md) |

Überblick über eine neue Installation: [Installieren](../docs/INSTALL.md) · wenn es läuft: [Das Dashboard nutzen](../docs/USAGE.md)

**Tipp:** Nach dem Holen eines neuen Images den Container **neu erstellen**, damit aktualisierte Ports und Laufzeiten gelten. Ein Neustart allein reicht nicht.
