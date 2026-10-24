# Installeren

Zet AIO in drie stappen aan: mappen maken, de app starten, het dashboard openen.

!!! tip "Liever een korte route?"
    De meeste mensen beginnen met **[Docker](deploy/DOCKER.md)** of hun NAS-gids (**[Unraid](deploy/UNRAID.md)** · **[Synology](deploy/SYNOLOGY.md)** · **[TrueNAS](deploy/TRUENAS.md)**) en komen daarna hier terug voor poorten en updates.

## Voordat je begint

1. **Kies waar het draait** — Unraid, Synology, TrueNAS, gewone Docker of native Linux.
2. **Plan twee soorten opslag:**
   - **Config** — instellingen en databases (klein, maak hier een back-up van)
   - **Downloads + media** — de grote bestanden (houd die op **dezelfde** schijf/share, zodat hardlinks werken)
3. **Ken je gebruikers-ID** — op Linux/NAS draaien apps vaak als een bepaalde gebruiker (`PUID` / `PGID`). Laat dat overeenkomen met de eigenaar van je mappen, anders krijg je rechtenfouten.

Je hebt maar **één** AIO-container nodig. Installeer Sonarr, Radarr of downloadclients niet als losse apps ernaast.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Architecturen:** `linux/amd64`, `linux/arm64` (Flaresolverr is alleen x86_64 en verborgen op ARM)

## Kies je platform

| Waar het draait | Gids |
|------------------|--------|
| Docker (elke host) | [Docker](deploy/DOCKER.md) |
| Unraid | [Unraid](deploy/UNRAID.md) |
| Synology | [Synology](deploy/SYNOLOGY.md) |
| TrueNAS SCALE | [TrueNAS](deploy/TRUENAS.md) |
| Debian / Ubuntu / Proxmox LXC (geen Docker) | [Linux](deploy/LINUX.md) |
| Alle opties op een rij | [Overzicht](deploy/README.md) |

Elke platformgids begint met: SSH openen → mappen maken → AIO starten.

## Mappen op de host

Log in via SSH en maak iets als dit (paden verschillen per platform — volg je gids):

```bash
ssh user@host

mkdir -p "$HOME/aio-media-manager/downloads" "$HOME/aio-media-manager/media"
sudo mkdir -p /path/to/config /path/to/config/vpn /path/to/backups
id   # note uid= (PUID) and gid= (PGID)
sudo chown -R "$PUID:$PGID" "$HOME/aio-media-manager" /path/to/config /path/to/backups
```

Houd **downloads** en **media** als buren onder één map, zodat *Arr kan hardlinken. Mount een aparte map **backups** op `/backups` als dat kan (bij voorkeur een andere schijf dan config).

In die mounts legt AIO bibliotheken aan zoals `media/tv`, `media/movies` en `downloads/complete`.

## Nadat het start

1. Open het dashboard: `http://YOUR-SERVER-IP:8080`  
   (Gebruik een andere poort als je die hebt gemapt.)
2. Maak het beheerdersaccount (gebruikersnaam, **e-mail**, wachtwoord).
3. Rond de wizard van de eerste start af en volg daarna [Het dashboard gebruiken](USAGE.md).

Na `docker compose pull` moet je de container **opnieuw aanmaken** (niet alleen herstarten), zodat nieuwe poorten en runtimes gelden. Dat werkt AIO bij. Geïnstalleerde apps werk je bij via **Instellingen → Updates** in het dashboard. Die schema’s staan standaard uit.

Het compose-bestand van de repo mount host-`/sys` alleen-lezen op `/host/sys`, zodat de serverkaart op Start de netwerkkaarten van de server telt. Een ouder compose-bestand zonder die regel toont alleen het verkeer van de container, tot je de regel toevoegt en opnieuw aanmaakt. Zie [Docker](deploy/DOCKER.md).

## Optioneel: apps bereiken buiten huis

1. [Cloudflare Tunnel](deploy/CLOUDFLARE.md) — HTTPS zonder routerpoorten open te zetten  
2. [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md) — een aanmeldpoort, zodat vreemden de beheerapps niet kunnen openen

## Poorten {#ports}

De interface van de manager gebruikt **8080**. Kind-apps luisteren in dezelfde container. Compose en NAS-sjablonen publiceren die poorten op de host, zodat **Interface openen** werkt (`http://YOUR-IP:8989` voor Sonarr, enzovoort). Host-netwerk is een alternatief als je niet elke poort wilt mappen.

| Applicatie | Standaardpoort |
|-------------|--------------|
| <img src="../assets/logo-aio-media-manager.png" alt="" class="aio-app-icon" /> Manager-UI | 8080 |
| <img src="../assets/app-icons/qbittorrent.svg" alt="" class="aio-app-icon" /> qBittorrent | 8081 |
| <img src="../assets/app-icons/shelfmark.png" alt="" class="aio-app-icon" /> Shelfmark | 8084 |
| <img src="../assets/app-icons/sabnzbd.svg" alt="" class="aio-app-icon" /> SABnzbd | 8085 |
| <img src="../assets/app-icons/jellyfin.svg" alt="" class="aio-app-icon" /> Jellyfin | 8096 |
| <img src="../assets/app-icons/flaresolverr.png" alt="" class="aio-app-icon" /> Flaresolverr | 8191 (alleen x86_64) |
| <img src="../assets/app-icons/bazarr.svg" alt="" class="aio-app-icon" /> Bazarr | 6767 |
| <img src="../assets/app-icons/nzbget.svg" alt="" class="aio-app-icon" /> NZBGet | 6789 |
| <img src="../assets/app-icons/lidarr.svg" alt="" class="aio-app-icon" /> Lidarr | 8686 |
| <img src="../assets/app-icons/sonarr.svg" alt="" class="aio-app-icon" /> Sonarr | 8989 |
| <img src="../assets/app-icons/radarr.svg" alt="" class="aio-app-icon" /> Radarr | 7878 |
| <img src="../assets/app-icons/prowlarr.svg" alt="" class="aio-app-icon" /> Prowlarr | 9696 |
| <img src="../assets/app-icons/seerr.svg" alt="" class="aio-app-icon" /> Seerr | 5055 |
| <img src="../assets/app-icons/grimmory.svg" alt="" class="aio-app-icon" /> Grimmory | 6060 |
| <img src="../assets/app-icons/neutarr.svg" alt="" class="aio-app-icon" /> NeutArr | 9705 |
| <img src="../assets/app-icons/recyclarr.svg" alt="" class="aio-app-icon" /> Recyclarr | geen (alleen CLI) |
| <img src="../assets/app-icons/plex.svg" alt="" class="aio-app-icon" /> Plex | 32400 |

## Veelgebruikte omgevingsvariabelen

Kopieer [`.env.example`](../.env.example) voor native installs. Veel hiervan kun je later ook in **Instellingen** zetten.

| Variabele | Doel |
|----------|---------|
| `PUID` / `PGID` | Gebruiker waaronder de apps draaien (gelijk aan de mapeigenaar) |
| `TZ` / `AMM_TIMEZONE` | Tijdzone voor logs en schema’s |
| `AMM_DOWNLOAD_DIR` / `AMM_MEDIA_DIR` | Paden in de container (host-mounts wijzig je in compose) |
| `GITHUB_TOKEN` | Optioneel; hogere GitHub-API-limiet voor updates |
| `AMM_CLOUDFLARE_TUNNEL_*` | Optionele tunnel voor toegang van buitenaf |
| `AMM_VPN_*` | Optionele VPN voor torrent-gerelateerde apps |

## Als er iets misgaat

- **Interface opent niet** — draait de container? Klopt de hostpoort?
- **Toegang geweigerd** — de eigenaar van de map moet overeenkomen met `PUID`/`PGID`.
- **Interface openen van een kind-app faalt op het LAN** — publiceer de poort van die app (tabel hierboven) of gebruik host-netwerk; oude compose-bestanden die alleen `8080` mappen, moeten worden bijgewerkt.
- **Apps dubbel** — verwijder losse Sonarr-/Radarr-containers; alleen AIO mag ze draaien.

## Ontwikkelaars

Om aan de code te werken, draai je de checkout **in Docker** (Linux-binaries). Zie [Contributing](../CONTRIBUTING.md) en `./scripts/test-env.sh up`.
