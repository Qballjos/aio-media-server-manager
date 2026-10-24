# Platforms

AIO hoort als **één** installatie te draaien — meestal **één Docker-container**.  
Voeg geen aparte Compose-service toe voor Sonarr, Radarr of elke downloadclient.

**Documentatiesite:** [qballjos.github.io/aio-media-server-manager](https://qballjos.github.io/aio-media-server-manager/)  
**Image:** [`ghcr.io/qballjos/aio-media-server-manager`](https://github.com/Qballjos/aio-media-server-manager/pkgs/container/aio-media-server-manager)

| Ik gebruik… | Gids |
|-------------|--------|
| Docker / Compose (de meeste mensen) | [DOCKER.md](DOCKER.md) |
| Unraid | [UNRAID.md](UNRAID.md) · sjablonen in [`unraid/`](unraid/) |
| Synology Container Manager | [SYNOLOGY.md](SYNOLOGY.md) · [`synology/`](synology/) |
| TrueNAS SCALE | [TRUENAS.md](TRUENAS.md) |
| Linux / LXC zonder Docker | [LINUX.md](LINUX.md) |
| Toegang van buitenaf (optioneel) | [CLOUDFLARE.md](CLOUDFLARE.md) |
| Aanmeldpoort op publieke URL’s | [CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md) |

Overzicht van een nieuwe installatie: [Installeren](../docs/INSTALL.md) · als het draait: [Het dashboard gebruiken](../docs/USAGE.md)

**Tip:** Nadat je een nieuwe image hebt opgehaald, **maak je de container opnieuw aan**, zodat bijgewerkte poorten en runtimes gelden. Alleen herstarten is niet genoeg.
