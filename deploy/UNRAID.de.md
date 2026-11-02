# Unraid: AIO Schritt für Schritt installieren

Du erstellst einen AIO-Container. Diese Route nutzt den SSD-Pool **cache** zum Herunterladen; die Bibliothek bleibt auf den normalen Datenträgern.

## Vor dem Start

- Zugriff auf die Unraid-Weboberfläche.
- Gestartetes Array und aktiviertes Docker.
- Ein aktiver SSD/NVMe-Pool namens cache mit freiem Platz. Ein Pool ist eine in Unraid benannte Gruppe von Datenträgern.

## 1. Server prüfen

Öffne **Main** und prüfe Array und Pool cache. Fehlt die SSD oder heißt der Pool anders, nutze [Fortgeschritten](UNRAID_ADVANCED.md). Keine Pfade raten und keine Laufwerke dafür formatieren.

**Prüfen:** cache ist aktiv und Docker erscheint als Tab. Sonst Settings → Docker → Enable Docker prüfen.

## 2. Unraid-Terminal öffnen

Klicke oben auf **>_**. Dieses Fenster läuft schon auf dem Server; SSH vom Laptop ist nicht nötig. Block einfügen und Enter drücken:

```bash
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/install.sh | sh
```

Das bereitet Ordner und Vorlage vor, keine separaten Mediencontainer.

**Prüfen:** Unraid template ready erscheint. Bei vorhandenen Downloads stoppen und vor Änderungen die fortgeschrittene Anleitung lesen.

## 3. Container hinzufügen

Öffne **Docker → Add Container** und wähle unter Template my-aio-media-manager oder aio-media-manager. Behalte die Pfade sowie PUID 99 und PGID 100 bei; das sind die Standardkennungen dieser Installation. Setze TZ auf deine Zeitzone, etwa Europe/Berlin. Wähle Apply und warte.

**Prüfen:** Ein Container aio-media-manager läuft.

## 4. Downloadspeicher prüfen

Unter **Shares → aio-download-cache** muss Primary storage auf cache und Secondary storage auf None stehen. Ältere Versionen nennen dies Use cache pool: Only. Wenn richtig, nichts ändern.

**Prüfen:** Mover verschiebt diese Arbeitsdateien nicht aufs Array. Bibliothek und fertige Torrents bleiben dort.

## 5. AIO öffnen

Beim Container-Icon **WebUI** wählen oder http://SERVER-IP:8080 mit deiner Unraid-Adresse öffnen.

**Prüfen:** Administratorkonto erstellen und Apps im AIO-Assistenten auswählen. Diese Apps nicht zusätzlich über Unraid Apps installieren.

Danach: [Dashboard kennenlernen](../docs/USAGE.md).

## 6. Ersten Film kopieren

Vorhandenes eigenes Unraid-Dateikonto verwenden oder unter **Users → Add User** einen normalen Benutzer mit Passwort erstellen. Nicht root für Dateifreigaben nutzen.

1. Unter **Shares → aio-media-manager → SMB Security Settings** Export Yes und Security Private wählen. Eigenem Dateibenutzer Lese-/Schreibzugriff geben, anderen nur wenn gewollt.
2. Im Windows-Explorer `\\SERVER-IP\aio-media-manager` öffnen, auf dem Mac Finder → Gehe zu → Mit Server verbinden mit `smb://SERVER-IP/aio-media-manager`. Eigene Server-IP verwenden.
3. Mit Dateikonto anmelden und unter media → movies einen eigenen Film kopieren.

**Prüfen:** die Datei liegt auf dem Server. Danach [erste Wiedergabe](../docs/USAGE.md#first-media).

## Wenn es nicht klappt

| Problem | Nächster Schritt |
|---|---|
| Vorlage fehlt | Prüfe Unraid template ready und aktualisiere den Docker-Tab. |
| Pool fehlt oder heißt anders | Fortgeschrittene Anleitung für anderen Pool oder HDD verwenden. |
| AIO öffnet nicht | Containerstatus und Server-IP prüfen; Portkonflikte stehen in der fortgeschrittenen Anleitung. |

## Fortgeschritten

Für eigene Speicherorte, SSD-Optionen, bestehende Installationen und technische Einstellungen: [UNRAID — Fortgeschritten](UNRAID_ADVANCED.md).

[Offizielle Produkthilfe: Unraid](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/).
