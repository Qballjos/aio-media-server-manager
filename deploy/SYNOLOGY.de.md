# Synology

Führen Sie AIO als **ein** Container-Manager-**Projekt** aus. Fügen Sie keine zusätzlichen Dienste oder eigene Sonarr-/Radarr-/Download-Container daneben hinzu.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
Ihr DSM muss `linux/amd64`- oder `linux/arm64`-Images ausführen können.

## Ordner und das Projekt anlegen (SSH)

Aktivieren Sie SSH (**Systemsteuerung → Terminal und SNMP → SSH-Dienst aktivieren**), dann:

```bash
ssh admin@<nas-ip>
```

Das Installationsskript legt `/volume1/docker/aio-media-manager` an (mit `config/` und `backups/`) und einen Datenbaum im **DSM-Benutzer-Home** (`File Station → Home → aio-media-manager` mit `downloads/` und `media/`). Dieser Pfad ist ein echtes Benutzer-Home, deshalb kann DSM ihn anzeigen. Ein bloßer Ordner `/volume1/data` ist kein freigegebener Ordner und erscheint nicht in File Station; das Skript erneut ausführen verschiebt diesen Baum ins Home, falls er noch existiert. Downloads und Medien bleiben ein Bind (`/data`), damit *Arr Hardlinks nutzen kann. Config-Sicherungen gehen auf den Mount `/backups`; nehmen Sie diesen Ordner in eine Hyper-Backup-Aufgabe auf, oder zeigen Sie `BACKUPS=` auf ein anderes Volume.

Der Benutzer-Home-Dienst muss an sein (Systemsteuerung → Benutzer und Gruppe → Erweitert). SSH als der DSM-Benutzer, dessen Home die Bibliotheken halten soll, oder setzen Sie `HOME_USER=`.

```bash
id
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
```

Wenn SSH `admin` ist, Home aber einem anderen DSM-Benutzer gehören soll:

```bash
id media
sudo HOME_USER=media PUID=1026 PGID=100 sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Anderes Volume oder andere Pfade:

```bash
sudo VOLUME=/volume2 \
     HOME_USER=media \
     BACKUPS=/volume1/backups/aio-media-manager \
     PUID=1026 PGID=100 \
     sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Um Bibliotheken auf einem freigegebenen DSM-Ordner statt im Home zu lassen, setzen Sie `DATA=` auf diesen Ordner (weiterhin ein Elternordner für `downloads` und `media`):

```bash
sudo DATA=/volume1/media/aio-media-manager \
     PUID=1026 PGID=100 \
     sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Die erzeugte Datei ist `/volume1/docker/aio-media-manager/docker-compose.yml` (kein `build:`-Schlüssel — Container Manager holt GHCR). Eine statische Kopie liegt in [`synology/docker-compose.yml`](synology/docker-compose.yml).

Wenn GHCR privat ist: `sudo docker login ghcr.io`, bevor Sie das Projekt starten.

## In Container Manager importieren

1. Öffnen Sie **Container Manager → Projekt → Erstellen**.
2. **Projektname:** `aio-media-manager`
3. **Pfad:** `/volume1/docker/aio-media-manager` (derselbe Ordner, den das Skript genutzt hat).
4. **Quelle:** nutzen Sie die **vorhandene** `docker-compose.yml` (fügen Sie keine zweite Compose-Datei ein und keine weiteren Dienste hinzu).
5. Starten Sie das Projekt.

Die Oberfläche sollte einen einzelnen Dienst `aio-media-manager` zeigen. Öffnen Sie `http://<nas-ip>:8080` für den Manager. **Oberfläche öffnen** auf Katalogkarten nutzt die App-Ports (Sonarr `8989`, Radarr `7878`, …), die das Projekt-Compose jetzt veröffentlicht. Wenn Sie Compose vor dieser Änderung erzeugt haben, kopieren Sie die `ports:`-Liste aus [`synology/docker-compose.yml`](synology/docker-compose.yml) in die Projektdatei und erstellen Sie den Container neu.

Das Installationsskript hängt Host-`/sys` auch nur lesend unter `/host/sys` ein, damit die Server-Karte auf Start den Netzwerkverkehr des NAS zeigt. Wenn das Projekt-Compose davor erzeugt wurde, fügen Sie `- /sys:/host/sys:ro` unter `volumes:` ein und erstellen Sie neu. Ohne diese Zeile ist die Grafik nur der Verkehr dieses Containers. Installierte Apps aktualisieren Sie später unter **Einstellungen → Updates** (Zeitpläne standardmäßig aus). Das Projekt neu zu erstellen aktualisiert AIO.

Zum Starten über SSH statt über die Oberfläche:

```bash
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml pull
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml up -d
```

Danach listet Container Manager es weiter, wenn der Projektpfad übereinstimmt.

## Hardware-Transkodierung

Wenn `/dev/dri` existiert, fügen Sie diesen Block unter `aio-media-manager` in die Projekt-Compose-Datei ein, erstellen Sie neu und starten Sie das Projekt:

```yaml
    devices:
      - /dev/dri:/dev/dri
```

```bash
ls -l /dev/dri
```

## VPN (qBittorrent, Prowlarr, Flaresolverr)

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/vpn
# scp wg0.conf into that directory
```

Setzen Sie `AMM_VPN_ENABLED=true` im Projekt-Compose und starten Sie das Projekt erneut. Solange das VPN an ist, können Prowlarr und qBittorrent das Haus-WAN nicht nutzen: sie verlassen das Netz nur durch den Tunnel und bleiben gestoppt, wenn der Tunnel aus ist. Der Synology-Kernel hat oft kein WireGuard-Modul; das Appliance-Image enthält **wireguard-go** als Rückfall und legt `/dev/net/tun` an, wenn es fehlt. Das funktioniert nur, wenn das Projekt `privileged: true` bleibt (das Installationsskript setzt das). Erstellen Sie den Container nach dem Holen eines aktuellen Images neu und speichern Sie das VPN danach unter **Einstellungen → Netzwerk**. OpenVPN nutzt denselben Geräteknoten und braucht ebenfalls den privilegierten Modus.

## Cloudflare Tunnel

Fügen Sie keinen zweiten Projektdienst hinzu. Schreiben Sie das Token auf das NAS und aktivieren Sie den Tunnel danach unter **Einstellungen → Netzwerk** (über Neustarts hinweg gespeichert). Optional setzen Sie `AMM_CLOUDFLARE_TUNNEL_ENABLED=true` im Projekt-Compose. Siehe [CLOUDFLARE.md](CLOUDFLARE.md).

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/cloudflare
sudo tee /volume1/docker/aio-media-manager/config/cloudflare/tunnel.token >/dev/null <<'EOF'
eyJ...paste-token...
EOF
sudo chmod 600 /volume1/docker/aio-media-manager/config/cloudflare/tunnel.token
```

## Rechte

`PUID`/`PGID` in der Compose-Datei müssen zum `chown` passen, den das Skript angewendet hat. Wenn Apps nicht schreiben können, korrigieren Sie den Besitzer über SSH, statt als root zu laufen.
