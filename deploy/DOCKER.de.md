# Docker auf Linux: AIO Schritt für Schritt

Diese Route gilt für einen **Linux-Server mit funktionierendem Docker**. Bei Unraid, Synology oder TrueNAS die [eigene Plattform](README.md) wählen und nicht beide Installationen ausführen.

## Vor dem Start

- Linux mit Docker, Docker Compose und Git; fehlendes Docker zuerst nach [offizieller Anleitung](https://docs.docker.com/engine/install/) installieren.
- Ein Konto, das bereits Docker-Befehle ausführen darf.
- Ein Computer im selben Netz.

## 1. Befehlsfenster öffnen

Auf dem Server selbst Terminal öffnen. Von einem anderen Computer mit Terminal oder Windows Terminal und `ssh BENUTZER@SERVER-IP` verbinden; beide Werte ersetzen. Danach laufen die Blöcke auf dem Server.

```bash
docker info
docker compose version
git --version
```

**Prüfen:** Docker zeigt Serverdaten, Compose/Git eine Version. Bei command not found oder permission denied zuerst Installation/Zugriff beheben.

## 2. AIO-Dateien vorbereiten

Im selben Terminal einfügen:

Besteht hier schon ein Ordner aio-media-server-manager? Diesen Block nicht ausführen, Ordner behalten und [Fortgeschritten](DOCKER_ADVANCED.md) nutzen. Jede Zeile läuft nur, wenn die vorige erfolgreich war.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git &&
cd aio-media-server-manager &&
export AMM_DATA_HOST="${HOME}/aio-media-manager" &&
mkdir -p config/vpn backups "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media" &&
sed -i -e "s/PUID: \"1000\"/PUID: \"$(id -u)\"/" -e "s/PGID: \"1000\"/PGID: \"$(id -g)\"/" docker-compose.yml
```

Das lädt die Projektdateien, erstellt die Ordner und trägt dein Linux-Konto automatisch als AIO-Benutzer ein. Du musst keine Nummern suchen oder Dateien bearbeiten.

**Prüfen:** keine Fehler; du stehst im Ordner aio-media-server-manager mit docker-compose.yml. Diesen Ordner behalten: config enthält Einstellungen und backups deren Sicherungen. Medien liegen separat unter aio-media-manager im Home-Ordner. Besteht der Projektordner schon, nicht löschen, sondern Fortgeschritten lesen.

## 3. AIO starten

Im selben Projektordner ausführen:

```bash
docker compose pull
docker compose up -d
docker compose ps
```

Die erste Zeile lädt die Software, die zweite startet sie im Hintergrund und die dritte zeigt den Status.

**Prüfen:** ein Container aio-media-manager steht auf Up oder Running. Das Terminal danach zu schließen stoppt AIO nicht.

## 4. Dashboard öffnen

Im Browser **http://SERVER-IP:8080** mit deiner echten Linux-Serveradresse öffnen.

**Prüfen:** Administratorkonto erstellen und gewünschte Apps im Assistenten auswählen. Diese Apps nicht zusätzlich als eigene Container installieren.

Danach: [Dashboard kennenlernen](../docs/USAGE.md).

## Wenn es nicht klappt

| Problem | Nächster Schritt |
|---|---|
| Docker-Zugriffsfehler | Docker-Zugriff auf dem Host klären; nicht wahllos alles als root ausführen. |
| Projektordner besteht schon | Behalten und die Anleitung für bestehende Installationen unter Fortgeschritten nutzen. |
| Startfehler | Im Projektordner docker compose logs --tail=100 ausführen und die Meldung behalten. |
| Browser verbindet nicht | docker compose ps, Server-IP und :8080 im selben Heimnetz prüfen. |

## Fortgeschritten

Für eigene Speicherorte, SSD-Optionen, bestehende Installationen und technische Einstellungen: [DOCKER — Fortgeschritten](DOCKER_ADVANCED.md).
