# Deine erste AIO-Installation

Du musst nicht jede App kennen. Wähle deinen vorhandenen Server und folge genau einer Anleitung.

!!! info "Was wird installiert?"
    AIO betreibt die Medientools in **einem Container**, einer verpackten Anwendung auf deinem Server. Installiere AIO einmal und füge Apps über **AIO → Katalog** hinzu, statt separate Container daneben anzulegen.

## 1. Wähle deinen Server

| Server | Anleitung | Zuerst prüfen |
|---|---|---|
| Unraid | [Unraid](deploy/UNRAID.md) | Array gestartet; SSD/NVMe-Pool eingebunden |
| Synology NAS | [Synology](deploy/SYNOLOGY.md) | Container Manager installiert und gestartet; DSM legt den docker-Ordner an |
| TrueNAS SCALE | [TrueNAS](deploy/TRUENAS.md) | Zugriff zum Anlegen eigener Apps und Speicherordner |
| Anderer Docker-Server | [Docker](deploy/DOCKER.md) | Docker und Docker Compose laufen |
| Linux / Proxmox LXC ohne Docker | [Linux](deploy/LINUX.md) | Erfahrung mit Linux-Serververwaltung |

Befehle gehören auf den Server, nicht auf den Laptop, auf dem du diese Seite liest. Danach kannst du das Dashboard auf Laptop oder Handy öffnen.

## 2. Wo liegen die Dateien?

Die Plattformanleitung erstellt die richtigen Ordner. Übernimm keine Platzhalterpfade einer anderen Plattform.

| Ordner | Inhalt | Empfehlung |
|---|---|---|
| Config | Einstellungen, Konten, Datenbanken | Sichern |
| Download-Staging | Laufende Downloads und Entpacken | SSD/NVMe; Platz für Download und entpackte Dateien |
| Fertige Torrents | Dateien für weiteres Seeding | HDD möglich |
| Medienbibliothek | Geordnete Filme und Serien | Große HDDs möglich |
| Backups | Kopien der Einstellungen | Möglichst auf einem anderen Datenträger |

Ein **Hostpfad** liegt auf dem NAS; ein **Containerpfad** wie `/data/media` ist die Sicht von AIO auf denselben Ordner. Das sind nicht zwei Bibliotheken. SSD-Staging und HDD-Bibliothek funktionieren zusammen; Importe kopieren Dateien. Hardlinks funktionieren nur im selben Dateisystem und sind keine Voraussetzung für AIO.

!!! tip "Zuerst bei den Vorgaben bleiben"
    Ändere Pfade und Ports nur bei Konflikten. VPN, Domain und Cloudflare sind optional und können später eingerichtet werden.

## 3. AIO öffnen

Sobald der Container läuft, öffne im Browser:

```text
http://DEINE-SERVER-IP:8080
```

Ersetze die IP durch die Adresse deines NAS. `http://192.168.1.50:8080` ist nur ein Beispiel. Verwende bei geänderter Hostport-Zuordnung deinen eigenen Port.

**Erwartetes Ergebnis:** die Kontoerstellung für AIO. Lege Benutzername, E-Mail und Passwort fest. Bei einem Anmeldebildschirm besteht bereits ein Konto; melde dich damit an.

## 4. Den Assistenten abschließen

1. Wähle nur benötigte Apps, etwa Jellyfin zur Wiedergabe und deine Automatisierungs-/Downloadtools.
2. Ein Usenet-Konto brauchst du nur für einen Usenet-Downloader. AIO liefert kein Abonnement.
3. VPN und Fernzugriff kannst du vorerst ausgeschaltet lassen.
4. Warte auf die Installation und prüfe im Katalog den Status **Running**.
5. Öffne die App über **Open UI**. Jellyfin/Plex können eigene Konten und Bibliothekseinstellungen benötigen; das AIO-Konto ersetzt diese nicht.

**Erwartetes Ergebnis:** Home, Katalog und Einstellungen sowie deine Apps im Katalog. Die erste Installation kann dauern. Bei Fehlern zuerst die Logs prüfen, statt immer wieder neu zu installieren.

## 5. Home gestalten

[Probiere die visuelle Widget-Demo](index.md#app-preview) und folge der [Dashboard-Anleitung](USAGE.md#customize-home). Sie zeigt Layout-Symbol, Hinzufügen, Verschieben und Größenänderung. Leere Widgets warten häufig auf Inhalte einer verbundenen App.

## Hilfe bei Problemen

| Problem | Nächster Schritt |
|---|---|
| Browser verbindet nicht | Läuft AIO? Stimmen IP und Hostport? Zuerst im selben Heimnetz testen. |
| Port belegt | Hostseite der Portzuordnung ändern und den neuen Port im Browser öffnen. |
| Permission denied | Ordnerbesitz laut Plattformanleitung prüfen. PUID/PGID sind die numerischen Benutzer-/Gruppen-IDs von AIO. |
| Synology docker-Ordner fehlt | Zuerst DSM Container Manager installieren und starten; Ordner nicht vorher selbst anlegen. |
| Widget leer | Zugehörige App im Katalog und die [Widget-Anleitung](USAGE.md#customize-home) prüfen. |
| Downloads langsam | HDD-/SSD-Zuordnung für Download und Entpacken laut NAS-Anleitung prüfen. |
| Open UI funktioniert nicht | App-Status und veröffentlichten Port prüfen. |

## Updates und Fernzugriff

AIO selbst wird durch Abrufen des neuen Images und Neuerstellen des Containers mit denselben Ordnerzuordnungen aktualisiert; ein Neustart allein reicht nicht. Die Apps darin aktualisierst du über **Einstellungen → Updates**; Zeitpläne sind standardmäßig aus. Richte [Cloudflare Tunnel](deploy/CLOUDFLARE.md) und [Access](deploy/CLOUDFLARE_ACCESS.md) erst ein, wenn der lokale Zugriff funktioniert.

Die folgenden Tabellen sind Nachschlagewerk, keine Lernvoraussetzung.

## Ports {#ports}

Die Oberfläche des Managers nutzt **8080**. Kind-Apps lauschen im selben Container. Compose und NAS-Vorlagen veröffentlichen diese Ports auf dem Host, damit **Oberfläche öffnen** funktioniert (`http://YOUR-IP:8989` für Sonarr und so weiter). Host-Netzwerk ist eine Alternative, wenn Sie nicht jeden Port mappen wollen.

| Anwendung | Standardport |
|-------------|--------------|
| <img src="__AIO_ASSET__/assets/logo-aio-media-manager.png" alt="" class="aio-app-icon" /> Manager-Oberfläche | 8080 |
| <img src="__AIO_ASSET__/assets/app-icons/qbittorrent.svg" alt="" class="aio-app-icon" /> qBittorrent | 8081 |
| <img src="__AIO_ASSET__/assets/app-icons/shelfmark.png" alt="" class="aio-app-icon" /> Shelfmark | 8084 |
| <img src="__AIO_ASSET__/assets/app-icons/sabnzbd.svg" alt="" class="aio-app-icon" /> SABnzbd | 8085 |
| <img src="__AIO_ASSET__/assets/app-icons/jellyfin.svg" alt="" class="aio-app-icon" /> Jellyfin | 8096 |
| <img src="__AIO_ASSET__/assets/app-icons/flaresolverr.png" alt="" class="aio-app-icon" /> Flaresolverr | 8191 (nur x86_64) |
| <img src="__AIO_ASSET__/assets/app-icons/bazarr.svg" alt="" class="aio-app-icon" /> Bazarr | 6767 |
| <img src="__AIO_ASSET__/assets/app-icons/nzbget.svg" alt="" class="aio-app-icon" /> NZBGet | 6789 |
| <img src="__AIO_ASSET__/assets/app-icons/lidarr.svg" alt="" class="aio-app-icon" /> Lidarr | 8686 |
| <img src="__AIO_ASSET__/assets/app-icons/sonarr.svg" alt="" class="aio-app-icon" /> Sonarr | 8989 |
| <img src="__AIO_ASSET__/assets/app-icons/radarr.svg" alt="" class="aio-app-icon" /> Radarr | 7878 |
| <img src="__AIO_ASSET__/assets/app-icons/prowlarr.svg" alt="" class="aio-app-icon" /> Prowlarr | 9696 |
| <img src="__AIO_ASSET__/assets/app-icons/seerr.svg" alt="" class="aio-app-icon" /> Seerr | 5055 |
| <img src="__AIO_ASSET__/assets/app-icons/grimmory.svg" alt="" class="aio-app-icon" /> Grimmory | 6060 |
| <img src="__AIO_ASSET__/assets/app-icons/neutarr.svg" alt="" class="aio-app-icon" /> NeutArr | 9705 |
| <img src="__AIO_ASSET__/assets/app-icons/recyclarr.svg" alt="" class="aio-app-icon" /> Recyclarr | keine (nur CLI) |
| <img src="__AIO_ASSET__/assets/app-icons/plex.svg" alt="" class="aio-app-icon" /> Plex | 32400 |

## Häufige Umgebungsvariablen

Kopieren Sie [`.env.example`](../.env.example) für native Installationen. Vieles davon lässt sich später auch unter **Einstellungen** setzen.

| Variable | Zweck |
|----------|---------|
| `PUID` / `PGID` | Benutzer, als der die Apps laufen (muss zum Ordnerbesitzer passen) |
| `TZ` / `AMM_TIMEZONE` | Zeitzone für Protokolle und Zeitpläne |
| `AMM_DOWNLOAD_DIR` / `AMM_MEDIA_DIR` | Pfade im Container (Host-Mounts ändern Sie in Compose) |
| `GITHUB_TOKEN` | Optional; höheres GitHub-API-Limit für Updates |
| `AMM_CLOUDFLARE_TUNNEL_*` | Optionaler Tunnel für Fernzugriff (`cloudflared` startet nach den Apps beim Boot) |
| `AMM_VPN_*` | Optionales VPN für qBittorrent, Prowlarr und Flaresolverr (sie warten auf den Tunnel; lokaler DNS-Cache für diese Apps) |
