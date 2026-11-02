# Synology: AIO Schritt für Schritt installieren

Diese Anleitung gilt für eine **neue Installation**. Du erstellst ein Projekt in Container Manager, ohne selbst eine Konfigurationsdatei zu schreiben.

## Vor dem Start

- Eine Synology mit Container Manager im Paket-Zentrum.
- Dein eigenes DSM-Konto mit Administratorrechten und dessen Passwort; nicht einfach den Beispielnamen admin verwenden.
- Ein Computer im selben Heimnetz; DSM bleibt im Browser geöffnet.

## 1. Container Manager installieren

Öffne **Paket-Zentrum**, suche **Container Manager**, installiere und öffne ihn.

**Prüfen:** File Station zeigt die Freigabe **docker**. Nicht vor der Paketinstallation selbst erstellen. Diese Route verwendet volume1; für andere Volumes siehe [Fortgeschritten](SYNOLOGY_ADVANCED.md).

## 2. Persönlichen Ordner und SSH aktivieren

Aktiviere **Systemsteuerung → Benutzer und Gruppe → Erweitert → Benutzer-Home-Dienst / User Home Service**. Damit erhält dein Konto einen persönlichen Medienordner.

Aktiviere dann **Systemsteuerung → Terminal und SNMP → Terminal → SSH-Dienst aktivieren**, lasse Port 22 und wähle Übernehmen.

**Prüfen:** File Station zeigt home und SSH ist angehakt.

## 3. Mit der NAS verbinden

Öffne **Terminal** auf macOS oder **Windows Terminal / PowerShell** auf Windows. Befehle gehören hier hinein, nicht in die Browseradresse. Ersetze Benutzer und NAS-IP in `ssh BENUTZER@NAS-IP`. Beispiel:

```bash
ssh alex@192.168.1.50
```

Verwende deine eigenen Daten. Die NAS-IP steht in der DSM-Adresse oder unter Systemsteuerung → Netzwerk → Netzwerkschnittstelle. Bestätige die erste Verbindung nur bei richtiger Adresse. Beim Eingeben des DSM-Passworts sind keine Zeichen sichtbar; das ist normal.

**Prüfen:** Die Eingabezeile nennt jetzt deine NAS. Der nächste Befehl läuft dort.

## 4. Projektdateien vorbereiten

Füge den ganzen Block in das verbundene Terminal ein und drücke Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
```

Das Skript erstellt Ordner und Projektdatei; AIO startet noch nicht. Sudo fragt gegebenenfalls nach deinem DSM-Passwort.

**Prüfen:** Am Ende steht Container Manager project files are ready. Notiere den ausgegebenen Compose-Pfad. Bei einer Fehlermeldung hier stoppen.

## 5. Projekt in DSM erstellen

Öffne **Container Manager → Projekt → Erstellen**.

1. Name: aio-media-manager.
2. Pfad: der ausgegebene Ordner, normalerweise docker → aio-media-manager.
3. Die dort vorhandene docker-compose.yml verwenden. Falls DSM einen Upload verlangt, diese erzeugte Datei auswählen und keine zweite Konfiguration anlegen.
4. Einstellungen beibehalten, Assistent abschließen und Projekt starten.

**Prüfen:** Ein Container aio-media-manager wird aktiv. Der erste Download kann einige Minuten dauern.

## 6. Dashboard öffnen

Öffne **http://NAS-IP:8080** mit deiner wirklichen NAS-Adresse.

**Prüfen:** AIO zeigt die Kontoerstellung. Erstelle das Administratorkonto und wähle im Assistenten nur benötigte Apps. Dateien liegen normalerweise in File Station → home → aio-media-manager. Mit `exit` beendest du SSH; SSH später abzuschalten stoppt AIO nicht.

Danach: [Dashboard kennenlernen](../docs/USAGE.md).

## Wenn es nicht klappt

| Problem | Nächster Schritt |
|---|---|
| Container Manager fehlt | Prüfe die Unterstützung deines NAS-Modells. Ein selbst erstellter docker-Ordner ersetzt das Paket nicht. |
| Skriptfehler oder Permission denied | DSM-Konto, laufenden Container Manager und docker-Ordner prüfen. Fehlermeldung aufbewahren. |
| AIO öffnet nicht | Projektstatus prüfen; NAS-IP statt Laptop-IP mit :8080 verwenden. |

## Fortgeschritten

Für eigene Speicherorte, SSD-Optionen, bestehende Installationen und technische Einstellungen: [SYNOLOGY — Fortgeschritten](SYNOLOGY_ADVANCED.md).

[Offizielle Produkthilfe: Synology](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project?version=7).
