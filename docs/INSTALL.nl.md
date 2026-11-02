# Je eerste AIO-installatie

Je hoeft niet alle apps te kennen. Begin bij de server die je al hebt en volg één handleiding.

!!! info "Wat installeer je?"
    AIO beheert meerdere mediatools in **één container**: één verpakte app op je server. Installeer AIO één keer. Voeg Sonarr, Radarr, Jellyfin en downloadclients toe via **AIO → Catalogus**, niet als losse containers ernaast.

## 1. Kies jouw server

| Jouw server | Handleiding | Controleer eerst |
|---|---|---|
| Unraid | [Unraid](deploy/UNRAID.md) | Array gestart; SSD/NVMe-pool gekoppeld voor snelle downloads |
| Synology NAS | [Synology](deploy/SYNOLOGY.md) | Container Manager geïnstalleerd en actief; laat DSM de docker-map maken |
| TrueNAS SCALE | [TrueNAS](deploy/TRUENAS.md) | Toegang om een eigen app en opslagmappen te maken |
| Andere server met Docker | [Docker](deploy/DOCKER.md) | Docker en Docker Compose geïnstalleerd en actief |
| Debian, Ubuntu of Proxmox LXC zonder Docker | [Linux](deploy/LINUX.md) | Ervaring met Linux-serverbeheer |

Volg **één** gids, niet de opdrachten van alle platforms. Een NAS is een opslagserver in je netwerk. Voer opdrachten uit op die server; daarna open je het dashboard op je laptop of telefoon.

## 2. Begrijp waar je bestanden staan

De platformgids maakt de juiste mappen. Neem geen voorbeeldpaden van een ander platform over.

| Map | Inhoud | Goed om te weten |
|---|---|---|
| Config | Instellingen, accounts en databases | Maak hier back-ups van |
| Tijdelijke downloads | Bestanden die worden gedownload of uitgepakt | SSD/NVMe helpt; houd ruimte voor downloaden **én** uitpakken |
| Afgeronde torrents | Bestanden die nog kunnen worden gedeeld (seeden) | Mogen op HDD-opslag blijven |
| Mediabibliotheek | Geordende films, series en andere media | Mag op grote HDD’s blijven |
| Back-ups | Kopieën van de instellingen | Liefst op een andere schijf of back-uplocatie |

Een **hostpad** is een map op je NAS. Een **containerpad**, zoals `/data/media`, is hoe AIO diezelfde map binnen de container ziet. Het zijn geen twee aparte bibliotheken.

SSD-downloadopslag en een HDD-bibliotheek werken samen. Imports kopiëren dan bestanden. Hardlinks (twee namen voor één opgeslagen bestand) werken alleen binnen hetzelfde bestandssysteem; ze zijn een optimalisatie, geen vereiste voor AIO.

!!! tip "Begin met de standaardinstellingen"
    Laat paden en poorten uit de gids staan, tenzij iets anders ze al gebruikt. Een VPN, domeinnaam en Cloudflare-account zijn **optioneel** en kunnen later.

## 3. Open AIO

Als de container actief is, open je dit in een browser:

```text
http://JOUW-SERVER-IP:8080
```

Vervang `JOUW-SERVER-IP` door het adres van je NAS. Bijvoorbeeld `http://192.168.1.50:8080`: dit is alleen een voorbeeld, gebruik je eigen adres uit de router of NAS. Heb je de hostpoort gewijzigd? Gebruik dan die poort in plaats van 8080.

**Dit hoort te verschijnen:** het scherm om een beheerdersaccount te maken. Vul een gebruikersnaam, e-mailadres en wachtwoord in. Zie je al een inlogscherm? Dan bestaat er een account; log daarmee in.

## 4. Rond de wizard af

1. Kies alleen de apps die je nodig hebt. Begin bijvoorbeeld met **Jellyfin** om af te spelen en de automatiserings-/downloadtools die je gebruikt.
2. Vul alleen een Usenet-account in als je een Usenet-downloader kiest. AIO levert geen Usenet-abonnement.
3. Laat VPN en toegang van buitenaf uit als je die nog niet wilt instellen.
4. Rond de wizard af en wacht op installatie. Zoek in **Catalogus** naar **Actief / Running** bij je apps.
5. Gebruik **Open UI** om de eigen installatie van een app af te ronden. Jellyfin en Plex kunnen eigen accounts en bibliotheekinstellingen nodig hebben; je AIO-account vervangt die niet.

**Dit hoort te verschijnen:** Home, Catalogus en Instellingen met je apps in de catalogus. Een eerste installatie kan even duren. Blijft een app gestopt of mislukt deze? Bekijk eerst de logs in plaats van steeds opnieuw te installeren.

## 5. Maak de hoofdpagina van jou

[Probeer het visuele widgetvoorbeeld](index.md#app-preview) en lees [de dashboardgids](USAGE.md#customize-home). Je ziet de indelingsknop, het toevoegen, verplaatsen en groter of kleiner maken. Een lege widget betekent niet automatisch dat iets kapot is: vaak moet een gekoppelde app eerst inhoud hebben.

## Als je vastloopt

| Wat zie je? | Wat doe je? |
|---|---|
| Browser kan niet verbinden | Controleer of AIO actief is, het serveradres klopt en je de juiste hostpoort gebruikt. Probeer eerst op hetzelfde thuisnetwerk. |
| Poort al in gebruik | Een andere app gebruikt die hostpoort. Wijzig de **hostkant** van de poortkoppeling en open daarna die nieuwe poort. |
| Permission denied | Volg de eigenaars-/rechtenstap in je platformgids. PUID/PGID zijn de nummers van de gebruiker/groep waarmee AIO schrijft. |
| Docker-map ontbreekt op Synology | Installeer en start eerst DSM Container Manager. Maak de gedeelde docker-map niet vooraf zelf. |
| Widget leeg | Controleer de gekoppelde app in Catalogus en [de widgetuitleg](USAGE.md#customize-home). |
| Downloads langzaam | Controleer of downloaden en uitpakken op HDD of SSD gebeurt. Volg de opslagopties in je NAS-gids. |
| Open UI werkt niet | Controleer of de app actief is en de poort beschikbaar is; zie de tabel hieronder. |

## Updates en toegang van buitenaf

- **AIO bijwerken:** volg de container-update van je platform. Haal de nieuwe image op en maak de container opnieuw aan met dezelfde mapkoppelingen. Alleen herstarten past geen nieuwe image toe.
- **Apps bijwerken:** via **Instellingen → Updates** in AIO. Automatische schema’s staan standaard uit.
- **Van buitenaf:** stel [Cloudflare Tunnel](deploy/CLOUDFLARE.md) en daarna [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md) in. Zorg eerst dat alles thuis werkt.

De tabellen hieronder zijn naslagwerk; je hoeft ze niet uit je hoofd te leren.

## Poorten {#ports}

De interface van de manager gebruikt **8080**. Kind-apps luisteren in dezelfde container. Compose en NAS-sjablonen publiceren die poorten op de host, zodat **Interface openen** werkt (`http://YOUR-IP:8989` voor Sonarr, enzovoort). Host-netwerk is een alternatief als je niet elke poort wilt mappen.

| Applicatie | Standaardpoort |
|-------------|--------------|
| <img src="__AIO_ASSET__/assets/logo-aio-media-manager.png" alt="" class="aio-app-icon" /> Manager-UI | 8080 |
| <img src="__AIO_ASSET__/assets/app-icons/qbittorrent.svg" alt="" class="aio-app-icon" /> qBittorrent | 8081 |
| <img src="__AIO_ASSET__/assets/app-icons/shelfmark.png" alt="" class="aio-app-icon" /> Shelfmark | 8084 |
| <img src="__AIO_ASSET__/assets/app-icons/sabnzbd.svg" alt="" class="aio-app-icon" /> SABnzbd | 8085 |
| <img src="__AIO_ASSET__/assets/app-icons/jellyfin.svg" alt="" class="aio-app-icon" /> Jellyfin | 8096 |
| <img src="__AIO_ASSET__/assets/app-icons/flaresolverr.png" alt="" class="aio-app-icon" /> Flaresolverr | 8191 (alleen x86_64) |
| <img src="__AIO_ASSET__/assets/app-icons/bazarr.svg" alt="" class="aio-app-icon" /> Bazarr | 6767 |
| <img src="__AIO_ASSET__/assets/app-icons/nzbget.svg" alt="" class="aio-app-icon" /> NZBGet | 6789 |
| <img src="__AIO_ASSET__/assets/app-icons/lidarr.svg" alt="" class="aio-app-icon" /> Lidarr | 8686 |
| <img src="__AIO_ASSET__/assets/app-icons/sonarr.svg" alt="" class="aio-app-icon" /> Sonarr | 8989 |
| <img src="__AIO_ASSET__/assets/app-icons/radarr.svg" alt="" class="aio-app-icon" /> Radarr | 7878 |
| <img src="__AIO_ASSET__/assets/app-icons/prowlarr.svg" alt="" class="aio-app-icon" /> Prowlarr | 9696 |
| <img src="__AIO_ASSET__/assets/app-icons/seerr.svg" alt="" class="aio-app-icon" /> Seerr | 5055 |
| <img src="__AIO_ASSET__/assets/app-icons/grimmory.svg" alt="" class="aio-app-icon" /> Grimmory | 6060 |
| <img src="__AIO_ASSET__/assets/app-icons/neutarr.svg" alt="" class="aio-app-icon" /> NeutArr | 9705 |
| <img src="__AIO_ASSET__/assets/app-icons/recyclarr.svg" alt="" class="aio-app-icon" /> Recyclarr | geen (alleen CLI) |
| <img src="__AIO_ASSET__/assets/app-icons/plex.svg" alt="" class="aio-app-icon" /> Plex | 32400 |

## Veelgebruikte omgevingsvariabelen

Kopieer [`.env.example`](../.env.example) voor native installs. Veel hiervan kun je later ook in **Instellingen** zetten.

| Variabele | Doel |
|----------|---------|
| `PUID` / `PGID` | Gebruiker waaronder de apps draaien (gelijk aan de mapeigenaar) |
| `TZ` / `AMM_TIMEZONE` | Tijdzone voor logs en schema’s |
| `AMM_DOWNLOAD_DIR` / `AMM_MEDIA_DIR` | Paden in de container (host-mounts wijzig je in compose) |
| `GITHUB_TOKEN` | Optioneel; hogere GitHub-API-limiet voor updates |
| `AMM_CLOUDFLARE_TUNNEL_*` | Optionele tunnel voor toegang van buitenaf (`cloudflared` start na de apps bij boot) |
| `AMM_VPN_*` | Optionele VPN voor qBittorrent, Prowlarr en Flaresolverr (ze wachten op de tunnel; lokale DNS-cache voor die apps) |
