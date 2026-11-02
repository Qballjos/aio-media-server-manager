# TrueNAS: AIO Schritt für Schritt

Diese Route nutzt das **Custom-App-Formular** ab TrueNAS SCALE 24.10. Zuerst laufen AIO und Jellyfin; weitere Apps und Ports kommen später.

## Vor dem Start

- Rechte für Apps und Speicherverwaltung in TrueNAS.
- Ein vorhandener Pool; keinen neuen Pool erstellen oder formatieren, nur um AIO zu installieren.
- Eingerichteter Apps-Speicher; eine anfängliche Poolauswahl zuerst abschließen.

## 1. Drei AIO-Ordner erstellen

Unter **Datasets** den vorhandenen Pool wählen und mit **Add Dataset** aio-config, aio-data und aio-backups erstellen. Ein Dataset ist hier ein von TrueNAS verwalteter Speicherordner.

Die angezeigten vollständigen Pfade notieren. Ein Pool media ergäbe etwa /mnt/media/aio-config; deinen eigenen Poolnamen verwenden.

**Prüfen:** drei neue Datasets. Keine vorhandenen fremden Datenordner für diese Schritte auswählen.

## 2. App-Konto notieren

Unter **Credentials → Local Users / Users** apps suchen und die numerische Benutzer- und Gruppen-ID notieren, oft 568, aber die eigenen Werte verwenden. Das sind Kennungen für Ordnerzugriff, keine Passwörter.

**Prüfen:** zwei Nummern sind notiert. Zugriff wird unten im App-Formular vergeben; nicht die Rechte des ganzen Pools ändern.

## 3. App-Formular öffnen

Unter **Apps → Discover Apps → Custom App** das normale Formular wählen, nicht Install via YAML.

| Feld | Wert |
|---|---|
| Application name | aio-media-manager |
| Image repository | ghcr.io/qballjos/aio-media-server-manager |
| Image tag | latest |

**Prüfen:** bei separatem Tag-Feld kein zusätzliches :latest an die Repository-Adresse hängen.

## 4. Ordner verbinden

Unter **Storage → Host Path** drei schreibbare Zuordnungen erstellen:

| Echter NAS-Pfad | Mount path in AIO |
|---|---|
| Dein aio-config-Pfad | /config |
| Dein aio-data-Pfad | /data |
| Dein aio-backups-Pfad | /backups |

Jede Zuordnung schreibbar lassen. Bei allen drei **Host Path**-Zuordnungen **Enable ACL** wählen, unter ACL Entries **Add**, **ID Type = User**, in **ID** die notierte apps-Benutzer-ID und **Access = Full Control**. Nur auf die drei neuen Datasets anwenden. ACL ist die Liste der erlaubten Konten. Fehlen diese Felder, zuerst die TrueNAS-Anleitung deiner Version verwenden.

**Prüfen:** drei verschiedene NAS-Pfade mit genau /config, /data und /backups.

## 5. Grundeinstellungen eintragen

Unter Environment variables eintragen:

| Name | Wert |
|---|---|
| PUID | Notierte apps-Benutzernummer |
| PGID | Notierte apps-Gruppennummer |
| AMM_DOWNLOAD_DIR | /data/downloads |
| AMM_MEDIA_DIR | /data/media |

Unter Port forwarding TCP **8080 nach 8080** für AIO und **8096 nach 8096** für Jellyfin anlegen. VPN/GPU zunächst auslassen.

**Prüfen:** zwei Portzuordnungen. Bei belegtem Port Fortgeschritten lesen, keine Nummer raten.

## 6. Installieren und öffnen

Install wählen, auf Running warten und **http://TRUENAS-IP:8080** mit deiner tatsächlichen Adresse öffnen. Nicht jede Variante zeigt einen WebUI-Knopf.

**Prüfen:** Administratorkonto erstellen, zunächst nur Jellyfin im Assistenten auswählen und über AIO öffnen. Weitere Apps später mit ihren Ports aus der fortgeschrittenen Referenz hinzufügen.

Danach: [Dashboard kennenlernen](../docs/USAGE.md).

## 7. Medienordner vom Computer erreichen

Für die erste Filmkopie brauchst du Dateizugriff. Nutze ein normales TrueNAS-Dateifreigabekonto, nicht root/apps. Falls nötig unter **Credentials → Users → Add** mit Passwort und SMB-Anmeldung erstellen.

1. Unter **Datasets → aio-data → Permissions → Edit ACL** deinen Dateibenutzer mit **Modify** und Vererbung für Dateien/Unterordner hinzufügen. Bestehenden apps-Zugang behalten; nicht die ganze Liste ersetzen. Beim Speichern **Apply permissions recursively** aktivieren, damit auch vorhandene Unterordner diesen Zugriff erhalten. Nur aio-data ändern.
2. Unter **Shares → Windows (SMB) Shares → Add** den echten aio-data-Pfad wählen, Freigabe **aio-media** nennen und speichern. SMB-Dienst starten, falls gefragt.
3. Im Windows-Explorer `\\TRUENAS-IP\aio-media` öffnen, nicht im Browser. Auf dem Mac **Finder → Gehe zu → Mit Server verbinden** und `smb://TRUENAS-IP/aio-media`. Eigene IP und Dateikonto verwenden.
4. Unter media → movies einen eigenen Film hineinkopieren. AIO erstellt diese Unterordner beim Start. Config und Backups nicht mitfreigeben.

**Prüfen:** der Film ist auf dem NAS sichtbar. Danach [erste Wiedergabe](../docs/USAGE.md#first-media).


## Wenn es nicht klappt

| Problem | Nächster Schritt |
|---|---|
| Anderes Formular | Version prüfen; die Route gilt für Docker-basierte Apps ab 24.10. TrueNAS-Hilfe/Fortgeschritten nutzen. |
| Permission denied | Drei AIO-Datasets und apps-Konto prüfen, nicht den ganzen Pool ändern. |
| AIO öffnet nicht | TrueNAS-IP, :8080 und Portzuordnung prüfen. |
| Weitere App öffnet nicht | Für zusätzliche Apps müssen weitere Ports freigegeben werden; siehe Fortgeschritten. |

## Fortgeschritten

Für eigene Speicherorte, SSD-Optionen, bestehende Installationen und technische Einstellungen: [TRUENAS — Fortgeschritten](TRUENAS_ADVANCED.md).

[Offizielle Produkthilfe: TrueNAS](https://www.truenas.com/docs/scale/25.04/scaleuireference/apps/installcustomappscreens/).

[TrueNAS: app storage and folder access](https://apps.truenas.com/getting-started/app-storage/).
