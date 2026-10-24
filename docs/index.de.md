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

# Ihr ganzer Medien-Stapel. Eine Installation.

<p class="aio-hero__lead">
Downloads, *Arr-Apps und Wiedergabe — von einem Dashboard aus.
Keine Compose-Datei voller Sonarr-, Radarr- und qBittorrent-Container.
</p>

<div class="aio-hero__actions" markdown>

[Jetzt installieren](INSTALL.md){ .md-button .md-button--primary }
[Das Dashboard nutzen](USAGE.md){ .md-button }
[GitHub](https://github.com/Qballjos/aio-media-server-manager){ .md-button }

</div>
</div>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Anmeldung als Administrator, helles Thema](screenshots/light/login.png)

</div>

<div class="aio-shot" markdown>

![Anmeldung als Administrator, dunkles Thema](screenshots/dark/login.png)

</div>

</div>

<p class="aio-shot-caption">Anmeldung — hell und dunkel.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Start, bevor Anwendungen installiert sind, helles Thema](screenshots/light/dashboard.png)

</div>

<div class="aio-shot" markdown>

![Start, bevor Anwendungen installiert sind, dunkles Thema](screenshots/dark/dashboard.png)

</div>

</div>

<p class="aio-shot-caption">Start, bevor Apps mit einer Weboberfläche installiert sind.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Katalog mit App-Karten und Installationsschaltflächen, helles Thema](screenshots/light/catalog.png)

</div>

<div class="aio-shot" markdown>

![Katalog mit App-Karten und Installationsschaltflächen, dunkles Thema](screenshots/dark/catalog.png)

</div>

</div>

<p class="aio-shot-caption">Katalog — Suche, Filter und Installation.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Konto-Seite in den Einstellungen, helles Thema](screenshots/light/settings.png)

</div>

<div class="aio-shot" markdown>

![Konto-Seite in den Einstellungen, dunkles Thema](screenshots/dark/settings.png)

</div>

</div>

<p class="aio-shot-caption">Einstellungen. Darstellung, App-Einstellungen und die übrigen Bereiche stehen in <a href="USAGE.md#screens">Das Dashboard nutzen</a>.</p>

## Fangen Sie dort an, wo Sie sind

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __Neu hier__

    ---

    Ordner anlegen, den Container starten, die Oberfläche öffnen.

    [:octicons-arrow-right-24: Installationsanleitung](INSTALL.md)

-   :material-view-dashboard-outline:{ .lg .middle } __Läuft schon__

    ---

    Start, Katalog und Oberfläche öffnen je App.

    [:octicons-arrow-right-24: Das Dashboard nutzen](USAGE.md)

-   :material-docker:{ .lg .middle } __Docker-Host__

    ---

    Der übliche Weg für NAS-Geräte und Linux-Server.

    [:octicons-arrow-right-24: Docker-Anleitung](deploy/DOCKER.md)

-   :material-cloud-lock-outline:{ .lg .middle } __Unterwegs__

    ---

    HTTPS über Cloudflare Tunnel, danach eine Anmeldung mit Access.

    [:octicons-arrow-right-24: Fernzugriff](deploy/CLOUDFLARE.md)

</div>

## Plattform wählen

<div class="grid cards" markdown>

-   :material-nas:{ .lg .middle } __Unraid__

    ---

    Ein Container im Stil von Community Applications.

    [Unraid-Anleitung](deploy/UNRAID.md)

-   :material-server:{ .lg .middle } __Synology__

    ---

    Ein Projekt im Container Manager.

    [Synology-Anleitung](deploy/SYNOLOGY.md)

-   :material-harddisk:{ .lg .middle } __TrueNAS__

    ---

    Eine Custom App auf SCALE.

    [TrueNAS-Anleitung](deploy/TRUENAS.md)

-   :material-linux:{ .lg .middle } __Linux / LXC__

    ---

    Native Installation ohne Docker.

    [Linux-Anleitung](deploy/LINUX.md)

</div>

## Was Sie bekommen

<div class="grid cards" markdown>

-   :material-monitor-dashboard:{ .lg .middle } __Ein Dashboard__

    ---

    Start für das, was neu ist, läuft oder Aufmerksamkeit braucht. Katalog für Installieren, Starten/Stoppen und **Oberfläche öffnen**.

-   :material-television-play:{ .lg .middle } __Automatisierung + Bibliotheken__

    ---

    Sonarr, Radarr, Lidarr und Bazarr — wenn Sie sie wollen.

-   :material-download:{ .lg .middle } __Downloads__

    ---

    Torrent- und Usenet-Clients, optional ein VPN auf dem Download-Pfad.

-   :material-cast:{ .lg .middle } __Schauen und anfragen__

    ---

    Jellyfin, Plex und Seerr — dasselbe Gerät.

</div>

<div class="aio-callout" markdown>

**Die eine Regel:** eine AIO-Installation = ein Container (oder ein nativer Dienst).  
Keine eigenen Sonarr-, Radarr- oder qBittorrent-Container daneben stellen.

</div>

## Vorgesehene Nutzung

AIO ist ein Self-Hosting-Werkzeug für eine persönliche Mediensammlung und ein Homelab:

- Dateien, die Ihnen gehören (Heimvideos, Familienfotos, gemeinfreie Medien oder eigene Sicherungen physischer Medien).
- Einrichtung des lokalen Netzes und Verwaltung des Servers.

Dieses Repository hostet oder verteilt kein urheberrechtlich geschütztes Material. Es ist keine Lizenz und kein rechtlicher Schutz. Es zu nutzen, um unbefugt geschütztes Material zu beschaffen, herunterzuladen, zu streamen oder zu teilen, verstößt an den meisten Orten gegen das Urheberrecht. Sie sind für die Gesetze an Ihrem Wohnort verantwortlich.

## Vibe coded

**Ja — diese App wurde vibe coded.**  
Sie entstand mit KI-Paarprogrammierung in Cursor, gesteuert von einem Menschen, der einen kompletten Medien-Stapel wollte, ohne zwölf Container zu beaufsichtigen. Das ist Absicht, kein Geheimnis.

Wenn etwas roh wirkt, öffnen Sie ein Issue oder einen PR. Die Vibes werden durch Feedback besser.

## Image

```text
ghcr.io/qballjos/aio-media-server-manager:latest
```

Läuft auf `linux/amd64` und `linux/arm64`. Nach einem Pull den Container neu erstellen, damit neue Ports und Laufzeiten gelten.
