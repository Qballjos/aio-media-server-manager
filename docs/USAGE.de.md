# Das Dashboard nutzen

Dieser Leitfaden gilt, nachdem AIO installiert ist und Sie die Weboberfläche öffnen können.

!!! success "Ziel"
    Schließen Sie den Assistenten für die Apps ab, die Sie brauchen, nutzen Sie Start im Alltag und **Oberfläche öffnen** im Katalog, wenn Sie den Bildschirm dieses Werkzeugs wollen.

Standardadresse im Heimnetz:

```text
http://YOUR-SERVER-IP:8080
```

Ersetzen Sie die IP (und den Port, wenn Sie ihn geändert haben).

---

## Erste Schritte

1. Legen Sie das **Administrator**konto an, wenn Sie dazu aufgefordert werden (Benutzername, **E-Mail**, Passwort).
2. Schließen Sie den Assistenten der Ersteinrichtung ab: die gewünschten Apps, einen Usenet-Server, falls Sie einen nutzen, optional VPN und einen optionalen Cloudflare Tunnel. Der Assistent installiert diese Auswahl. Tunnel und VPN starten, sobald der Assistent fertig ist, wenn Sie sie eingeschaltet haben.
3. Nach dem Neuanlegen des Containers antwortet das Dashboard, während Apps noch starten. Mit VPN an warten qBittorrent, Prowlarr und Flaresolverr auf den WireGuard-Handshake (AIO versucht das VPN erneut, wenn der erste Versuch scheitert). Cloudflare Tunnel startet zuletzt, nachdem die Apps antworten, damit cloudflared kein connection refused gegen Origins loggt, die noch nicht lauschen.
4. Warten Sie, bis **Katalog** diese Apps als **aktiv** zeigt. Nutzen Sie **Oberfläche öffnen** für alles, das noch ein eigenes Konto hat (Plex, Jellyfin, NZBGet).
5. Später fügen Sie mehr über **Katalog** hinzu. Sie brauchen nicht jede App.

Fangen Sie klein an (zum Beispiel Radarr + ein Download-Client + Jellyfin) und ergänzen Sie den Rest danach.

---

## Start

Start ist ein Raster. Telefon, Tablet und Desktop behalten jeweils ihr eigenes Layout (4, 8 und 12 Spalten). Die Layout-Schaltfläche auf dem Start-Reiter verschiebt, vergrößert, fügt hinzu und entfernt Widgets. **Einstellungen → Startseite** blendet die App-Leiste ein oder aus, setzt den Anmeldetext und speichert einen Jellyfin- oder Seerr-API-Schlüssel, wenn Start ihn nicht selbst lesen kann.

| Widget | Was es zeigt |
|--------|----------------|
| Begrüßung | Tageszeit |
| Suche | Suche in Seerr |
| Kalender | Kommende Folgen und Filme. Eine Staffel, die an einem Tag startet, ist eine Zeile |
| Downloads | Aktive Downloads, mit alles pausieren / alles fortsetzen. Hängende Einträge können Sie entfernen |
| Zuletzt hinzugefügt | Neue Serien und Filme. Scrollen lädt weitere Jellyfin-Seiten. Plex bleibt bei den letzten 20 |
| Anfragen | Seerr-Anfragen, die noch nicht fertig sind, plus was in den letzten 30 Tagen als verfügbar oder abgelehnt markiert wurde |
| Trending | Die Trending-Liste von Seerr. Scrollen lädt weiter |
| Wird abgespielt | Wer auf Jellyfin oder Plex schaut, inklusive Direktwiedergabe |
| Speicher | Plattennutzung von Config, Downloads und Medien |
| Server | CPU, Arbeitsspeicher und Netzwerk. Mit Host-`/sys` unter `/host/sys` sind das die Netzwerkkarten des Servers. Ohne diesen Mount nur der Verkehr dieses Containers |
| Braucht Aufmerksamkeit | Dieselben Prüfungen wie Einstellungen → Benachrichtigungen, mit einem Link, jeden Punkt zu beheben |
| Andere Downloads | Standardmäßig aus; über die Layout-Steuerung hinzufügen. Was SABnzbd, NZBGet und qBittorrent heruntergeladen haben, das kein Film und keine Serie ist (Musik, Bücher, Spiele, Software, Archive), jeweils mit einem Symbol für die Art |

Installieren, starten, stoppen und **Oberfläche öffnen** liegen im **Katalog**. Die Leiste unten auf Start öffnet Apps, die schon installiert sind.

**Oberfläche öffnen** im LAN sieht meist so aus: `http://YOUR-SERVER-IP:8989` (Beispiel Sonarr).  
Wenn Sie öffentliche Cloudflare-Hostnamen eingerichtet haben, kann **Oberfläche öffnen** stattdessen `https://sonarr.yourdomain.com` nutzen — siehe [Cloudflare Tunnel](deploy/CLOUDFLARE.md).

---

## Was der Assistent verknüpft

Sobald eine App gesund ist — oder wenn Sie **Auto-Verknüpfen** klicken — setzt AIO Download-Ordner und Kategorien, Stammordner und Download-Clients in Sonarr, Radarr und Lidarr, Prowlarr-Sync, Seerr, die Bazarr-Verknüpfung und die Startkonfigurationen von Recyclarr und NeutArr. **Einstellungen → Usenet** speichert den Newsserver und schickt ihn an SABnzbd und NZBGet. Prowlarr bekommt außerdem einen Startsatz öffentlicher Indexer. Entfernen Sie, was Sie nicht wollen; sie werden nicht wieder hinzugefügt.

Lassen Sie **Downloads** und **Medien** auf demselben Volume, damit fertige Dateien **Hardlinks** nutzen können.

Noch selbst zu erledigen:

- Ein Plex-Konto.
- Das Einrichtungs-Token des ersten NeutArr-Starts (unten), bis dieses Konto existiert.
- Anmeldung bei Jellyfin und NZBGet. Im LAN meldet **Oberfläche öffnen** Sie bereits bei Sonarr, Radarr, Lidarr, Prowlarr, qBittorrent, SABnzbd, Bazarr und Seerr als Administrator des Managers an. Öffentliche Hostnamen zeigen immer die eigene Anmeldung der App.
- Administrator und Assistent der Ersteinrichtung von Seerr werden für Sie aus dieser gemeinsamen Anmeldung abgeschlossen (über Jellyfin oder ein beanspruchtes Plex).

VPN, Cloudflare Tunnel, Recyclarr, NeutArr und Sicherungen sind optional.

### Einrichtungs-Token des ersten NeutArr-Starts

Beim ersten Start von NeutArr, bevor es ein Konto hat, verlangt es ein einmaliges Einrichtungs-Token.

1. Warten Sie, bis NeutArr **aktiv** ist.
2. Öffnen Sie **Katalog → NeutArr → Einstellungen**.
3. Kopieren Sie **Token für die Ersteinrichtung** und fügen Sie es in den Einrichtungsbildschirm von NeutArr ein.

Dieser Wert ist die Datei `/config/neutarr/.setup-token` im Gerät (der Host-Ordner, der als `/config` eingehängt ist). NeutArr löscht die Datei, nachdem das Konto angelegt wurde, und das Feld in Einstellungen wird leer. Solange NeutArr nicht gestartet ist, bleibt das Feld leer.

---

## Die Oberfläche jeder App öffnen

| Situation | Was Sie nutzen |
|-----------|-------------|
| Zu Hause im WLAN | **Oberfläche öffnen** → `http://IP:PORT` |
| Unterwegs mit Cloudflare | **Oberfläche öffnen** → `https://subdomain.yourdomain.com` |
| Sie haben den Lauschport einer App geändert | AIO aktualisiert veröffentlichte Routen; erstellen Sie den Container neu, wenn LAN-Links noch falsch aussehen. Der Port des Managers selbst ist Compose/Umgebung (`AMM_API_PORT`), sichtbar unter **Einstellungen → System** |

Wenn **Oberfläche öffnen** scheitert:

- Ist die App im Katalog **aktiv**?
- Sind Sie im selben Netz (für LAN-Links)?
- Für HTTPS-Links: ist der Tunnel verbunden und **Veröffentlichen** gelungen? ([Cloudflare-Anleitung](deploy/CLOUDFLARE.md))

---

## Einstellungen, die Sie wirklich nutzen

Namen in der Oberfläche können kurz sein; das ist, was sie in der Praxis bedeuten.

| Bereich | Warum er zählt |
|---------|----------------|
| **Konto** | Benutzername, E-Mail und Passwort des Administrators. Apps mit lokaler Anmeldung nutzen dasselbe Konto |
| **Darstellung** | Thema, Akzent, Hintergrund, Titel, Symbol in der Leiste, Anmelde-Logo und Favicon |
| **System** | Zeitzone, Protokollstufe, PUID/PGID und die AIO-Version. Speicherpfade stehen hier; Mounts ändern Sie in Compose, nicht in diesem Bildschirm. Der Lauschport des Managers ist nur Compose/Umgebung |
| **Updates** | Updates installierter Apps prüfen und anwenden, einzeln oder alle. Zeitpläne sind standardmäßig **aus**. Ein neueres AIO-Image ist nur ein Hinweis — auf dem Host holen und neu erstellen |
| **Sicherungen** | Config-Sicherung, prüfen, je App wiederherstellen und ein Zeitplan |
| **Netzwerk** | VPN für qBittorrent, Prowlarr und Flaresolverr (Usenet bleibt draußen), mit lokalem DNS-Cache für diese Apps, damit kurze Tunnel-Aussetzer Prowlarr-Indexer nicht offline schalten; Cloudflare Tunnel (startet nach den Apps beim Boot); öffentliche Subdomains; und vertrauenswürdige Proxys |
| **Benachrichtigungen** | Discord-Webhook und E-Mail, wenn eine App weiter abstürzt, VPN oder Tunnel ausfällt, ein Update da ist oder eine Platte über 90 % voll ist |
| **Usenet** | Newsserver (Host, Port, SSL, Anmeldung, Verbindungen), an SABnzbd und NZBGet geschickt. NZB-Indexer fügen Sie in Prowlarr hinzu |
| **Startseite** | Anmeldetext, App-Leiste und Jellyfin- / Seerr-API-Schlüssel, wenn Start sie nicht lesen kann |
| **Diagnose** | Warum ein Start-Widget leer ist. API-Schlüssel werden nie angezeigt. **Support-Link** ist vorübergehende Hilfe aus der Ferne — lassen Sie ihn **aus**, außer Sie debuggen mit jemandem, dem Sie vertrauen |

Geben Sie Apps nach einer wichtigen Netzwerk- oder Portänderung etwas Zeit zum Neuladen — oder starten Sie AIO neu, wenn Links veraltet bleiben.

## Bildschirme {#screens}

Hell steht links, dunkel rechts. Start ist hier leer, weil noch keine App mit Weboberfläche installiert ist. App-Einstellungen im Katalog sind das Fenster, das Sie von einer Katalogkarte öffnen (hier qBittorrent).

### Konto

| Hell | Dunkel |
| --- | --- |
| ![Konto in den Einstellungen, helles Thema](screenshots/light/settings.png) | ![Konto in den Einstellungen, dunkles Thema](screenshots/dark/settings.png) |

### Darstellung

| Hell | Dunkel |
| --- | --- |
| ![Darstellung, helles Thema](screenshots/light/settings-visuals.png) | ![Darstellung, dunkles Thema](screenshots/dark/settings-visuals.png) |

### System

| Hell | Dunkel |
| --- | --- |
| ![Systemeinstellungen, helles Thema](screenshots/light/settings-system.png) | ![Systemeinstellungen, dunkles Thema](screenshots/dark/settings-system.png) |

### Updates

| Hell | Dunkel |
| --- | --- |
| ![Updates, helles Thema](screenshots/light/settings-updates.png) | ![Updates, dunkles Thema](screenshots/dark/settings-updates.png) |

### Sicherungen

| Hell | Dunkel |
| --- | --- |
| ![Sicherungen, helles Thema](screenshots/light/settings-backups.png) | ![Sicherungen, dunkles Thema](screenshots/dark/settings-backups.png) |

### Netzwerk

| Hell | Dunkel |
| --- | --- |
| ![Netzwerkeinstellungen, helles Thema](screenshots/light/settings-network.png) | ![Netzwerkeinstellungen, dunkles Thema](screenshots/dark/settings-network.png) |

### Benachrichtigungen

| Hell | Dunkel |
| --- | --- |
| ![Benachrichtigungen, helles Thema](screenshots/light/settings-notifications.png) | ![Benachrichtigungen, dunkles Thema](screenshots/dark/settings-notifications.png) |

### Usenet

| Hell | Dunkel |
| --- | --- |
| ![Usenet-Einstellungen, helles Thema](screenshots/light/settings-usenet.png) | ![Usenet-Einstellungen, dunkles Thema](screenshots/dark/settings-usenet.png) |

### Startseite

| Hell | Dunkel |
| --- | --- |
| ![Startseiten-Einstellungen, helles Thema](screenshots/light/settings-homepage.png) | ![Startseiten-Einstellungen, dunkles Thema](screenshots/dark/settings-homepage.png) |

### Diagnose

| Hell | Dunkel |
| --- | --- |
| ![Diagnose, helles Thema](screenshots/light/settings-diagnostics.png) | ![Diagnose, dunkles Thema](screenshots/dark/settings-diagnostics.png) |

### App-Einstellungen im Katalog

| Hell | Dunkel |
| --- | --- |
| ![qBittorrent-Einstellungen im Katalog, helles Thema](screenshots/light/catalog-settings.png) | ![qBittorrent-Einstellungen im Katalog, dunkles Thema](screenshots/dark/catalog-settings.png) |

---

## Sicherungen

- Nutzen Sie die eingebaute Sicherung, wenn Sie eine Einrichtung behalten wollen.
- Sichern Sie auch den **Config**-Ordner auf dem Host (und den Backup-Mount, falls Sie einen nutzen).
- Mediendateien liegen getrennt — sichern Sie sie mit Ihrer normalen NAS- oder Plattenstrategie.

---

## Apps aktualisieren und AIO aktualisieren

| Was | Wie |
|------|-----|
| **AIO selbst** (Dashboard + Supervisor) | Holen Sie ein neues Docker-Image und **erstellen Sie den Container neu** ([Installieren](INSTALL.md)). Einstellungen → Updates sagt nur, wann `:latest` sich verschoben hat |
| **Installierte Apps** (Sonarr, Seerr und der Rest) | **Einstellungen → Updates**. Aktualisieren Sie eine App oder alle. Der Fortschritt steht dort, und Katalog und Start zeigen **Wird aktualisiert…**. Das Dashboard antwortet weiter. Zeitpläne sind standardmäßig **aus** |

Das Image aktualisiert diese Apps nicht von allein. Lesen Sie die Release-Hinweise auf GitHub, wenn sich etwas Großes geändert hat.

---

## Häufige Stolperstellen

| Problem | Versuchen Sie dies |
|---------|----------|
| Leerer Bildschirm oder Anmeldeschleife bei einer App | Löschen Sie die Website-Daten dieser URL; prüfen Sie, ob die App läuft |
| NeutArr verlangt ein Einrichtungs-Token | **Katalog → NeutArr → Einstellungen**, nachdem NeutArr läuft. Das Token verschwindet, sobald das NeutArr-Konto existiert |
| Rechtefehler beim Schreiben von Dateien | Der Besitzer des Host-Ordners muss zum Container-Benutzer passen (`PUID`/`PGID`) |
| Sonarr importiert, kopiert die Dateien aber | Downloads und Medien müssen ein Dateisystem teilen, damit Hardlinks funktionieren |
| Funktioniert zu Hause, nicht über Mobilfunk | Tunnel nötig (+ möglichst Access); LAN-IPs sind über Mobilfunk nicht erreichbar |
| Zwei Sonarrs im Konflikt | Entfernen Sie einen zusätzlichen Sonarr-Container; nur AIO soll ihn ausführen |
| Die Server-Grafik zählt nur diesen Container | Hängen Sie Host-`/sys` nur lesend unter `/host/sys` ein und erstellen Sie neu ([Docker](deploy/DOCKER.md)) |
| Zuletzt hinzugefügt von Jellyfin wirkt kurz | Scrollen Sie die Zeile — weitere Seiten werden geladen. Bleibt die Zeile leer, setzen Sie einen Jellyfin-API-Schlüssel unter **Einstellungen → Startseite** |
| Zuletzt hinzugefügt von Plex stoppt bei 20 | Diese Liste sind die letzten 20 von Plex |
| qBittorrent / Prowlarr / Flaresolverr bleiben nach dem Boot gestoppt | VPN ist an ohne Live-Handshake. Prüfen Sie **Einstellungen → Netzwerk**; AIO versucht den Tunnel erneut und startet diese Apps, sobald er wieder da ist. Ein manuelles VPN-**Stop** bricht den Retry ab |
| Prowlarr-Indexer nicht verfügbar / RSS-Fehler | Oft ein DNS-Timeout durch den VPN. Nach einem AIO-Update den Container neu anlegen, dann in Prowlarr **Test All** (und in Sonarr/Radarr erneut testen), damit der alte Fehler-Backoff weg ist. Ein Debug-Share zeigt Treffer des VPN-DNS-Caches und Fehler je Resolver |
| cloudflared loggt connection refused beim Boot | Erwartet bei älteren Images, als der Tunnel vor den Apps startete. Aktuelle Images starten Cloudflare zuletzt; neu anlegen von aktuellem `nightly` / `latest` |

---

## Nächste Schritte

- Checkliste für eine neue Installation: [Installieren](INSTALL.md)  
- Fernzugriff: [Cloudflare Tunnel](deploy/CLOUDFLARE.md)  
- Die Tür für öffentliche URLs schließen: [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md)
