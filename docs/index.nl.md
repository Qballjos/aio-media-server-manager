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

# Je hele media-stack. Eén installatie.

<p class="aio-hero__lead">
Downloads, *Arr-apps en afspelen — vanuit één dashboard.
Geen Compose-bestand vol Sonarr-, Radarr- en qBittorrent-containers.
</p>

<div class="aio-hero__actions" markdown>

[Nu installeren](INSTALL.md){ .md-button .md-button--primary }
[Het dashboard gebruiken](USAGE.md){ .md-button }
[GitHub](https://github.com/Qballjos/aio-media-server-manager){ .md-button }

</div>
</div>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Aanmelden als beheerder, licht thema](screenshots/light/login.png)

</div>

<div class="aio-shot" markdown>

![Aanmelden als beheerder, donker thema](screenshots/dark/login.png)

</div>

</div>

<p class="aio-shot-caption">Aanmelden — licht en donker.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Start voordat er apps zijn geïnstalleerd, licht thema](screenshots/light/dashboard.png)

</div>

<div class="aio-shot" markdown>

![Start voordat er apps zijn geïnstalleerd, donker thema](screenshots/dark/dashboard.png)

</div>

</div>

<p class="aio-shot-caption">Start voordat er apps met een webinterface zijn geïnstalleerd.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Catalogus met app-kaarten en installatieknoppen, licht thema](screenshots/light/catalog.png)

</div>

<div class="aio-shot" markdown>

![Catalogus met app-kaarten en installatieknoppen, donker thema](screenshots/dark/catalog.png)

</div>

</div>

<p class="aio-shot-caption">Catalogus — zoeken, filters en installeren.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Accountpagina in Instellingen, licht thema](screenshots/light/settings.png)

</div>

<div class="aio-shot" markdown>

![Accountpagina in Instellingen, donker thema](screenshots/dark/settings.png)

</div>

</div>

<p class="aio-shot-caption">Instellingen. Weergave, app-instellingen en de andere onderdelen staan in <a href="USAGE.md#screens">Het dashboard gebruiken</a>.</p>

## Begin waar je bent

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __Nieuw hier__

    ---

    Mappen maken, de container starten, de interface openen.

    [:octicons-arrow-right-24: Installatiegids](INSTALL.md)

-   :material-view-dashboard-outline:{ .lg .middle } __Draait al__

    ---

    Start, Catalogus en Interface openen per app.

    [:octicons-arrow-right-24: Het dashboard gebruiken](USAGE.md)

-   :material-docker:{ .lg .middle } __Docker-host__

    ---

    De gewone route voor NAS-apparaten en Linux-servers.

    [:octicons-arrow-right-24: Dockergids](deploy/DOCKER.md)

-   :material-cloud-lock-outline:{ .lg .middle } __Buiten huis__

    ---

    HTTPS via Cloudflare Tunnel, daarna een aanmeldpoort met Access.

    [:octicons-arrow-right-24: Toegang van buitenaf](deploy/CLOUDFLARE.md)

</div>

## Kies je platform

<div class="grid cards" markdown>

-   :material-nas:{ .lg .middle } __Unraid__

    ---

    Eén container in de stijl van Community Applications.

    [Unraid-gids](deploy/UNRAID.md)

-   :material-server:{ .lg .middle } __Synology__

    ---

    Eén project in Container Manager.

    [Synology-gids](deploy/SYNOLOGY.md)

-   :material-harddisk:{ .lg .middle } __TrueNAS__

    ---

    Eén custom app op SCALE.

    [TrueNAS-gids](deploy/TRUENAS.md)

-   :material-linux:{ .lg .middle } __Linux / LXC__

    ---

    Native installatie zonder Docker.

    [Linux-gids](deploy/LINUX.md)

</div>

## Wat je krijgt

<div class="grid cards" markdown>

-   :material-monitor-dashboard:{ .lg .middle } __Eén dashboard__

    ---

    Start voor wat nieuw is, speelt of aandacht nodig heeft. Catalogus voor installeren, starten/stoppen en **Interface openen**.

-   :material-television-play:{ .lg .middle } __Automatisering + bibliotheken__

    ---

    Sonarr, Radarr, Lidarr en Bazarr — als je ze wilt.

-   :material-download:{ .lg .middle } __Downloads__

    ---

    Torrent- en Usenet-clients, optioneel een VPN op het downloadpad.

-   :material-cast:{ .lg .middle } __Kijken en aanvragen__

    ---

    Jellyfin, Plex en Seerr — hetzelfde apparaat.

</div>

<div class="aio-callout" markdown>

**De ene regel:** één AIO-installatie = één container (of één native service).  
Zet er geen losse Sonarr-, Radarr- of qBittorrent-containers naast.

</div>

## Bedoeld gebruik

AIO is een self-hostingbeheertool voor een persoonlijke mediabibliotheek en een homelab:

- Bestanden die van jou zijn (thuisvideo’s, familiefoto’s, publiek domein, of je eigen back-ups van fysieke media).
- Inrichting van het lokale netwerk en beheer van de server.

Deze repository host of verspreidt geen auteursrechtelijk beschermd materiaal. Het is geen licentie en geen juridisch schild. Het gebruiken om ongeautoriseerd beschermd materiaal te verkrijgen, te downloaden, te streamen of te delen is in de meeste landen in strijd met het auteursrecht. Jij bent verantwoordelijk voor de wetten waar je woont.

## Vibe coded

**Ja — deze app is vibe coded.**  
Hij is gebouwd met AI-pairprogrammeren in Cursor, gestuurd door een mens die een volledige media-stack wilde zonder twaalf containers in de gaten te houden. Dat is bewust, geen geheim.

Als iets ruw aanvoelt, open een issue of een PR. De vibes worden beter van feedback.

## Image

```text
ghcr.io/qballjos/aio-media-server-manager:latest
```

Werkt op `linux/amd64` en `linux/arm64`. Haal een nieuwe image op en maak de container opnieuw aan, zodat nieuwe poorten en runtimes gelden.
