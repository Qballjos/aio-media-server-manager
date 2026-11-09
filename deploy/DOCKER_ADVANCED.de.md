# Docker — Fortgeschritten

!!! info "Fortgeschritten"
    Dies ist die technische Referenz. Für die erste Installation nutze die Einsteigeranleitung. [Einsteigeranleitung](DOCKER.md).

So läuft AIO üblicherweise: **ein Container**, der den Manager und jede App startet, die Sie einschalten.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Läuft auf:** `linux/amd64` und `linux/arm64`  
(Auf ARM ist Flaresolverr nicht verfügbar — es braucht x86_64.)

---

## 1. Server prüfen

Führe diese Befehle auf dem AIO-Server aus, gegebenenfalls nach SSH-Anmeldung mit eigenem Benutzer und Serveradresse.

```bash
docker info
docker compose version
git --version
```

Erwartet: eine laufende Docker-Engine sowie Compose- und Git-Versionen. Fehlende Werkzeuge oder Zugriffsfehler zuerst nach Host-Anleitung beheben. Auf NAS-Systemen die [Plattformanleitung](README.md) verwenden, keine zweite Docker-Engine installieren.

## 2. Dateien holen und Ordner anlegen

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
id
export PUID="$(id -u)"
export PGID="$(id -g)"
export AMM_DATA_HOST="${HOME}/aio-media-manager"
mkdir -p config/vpn backups "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media"
sudo chown -R "${PUID}:${PGID}" config backups "${AMM_DATA_HOST}"
```

Bleibe danach im Ordner mit docker-compose.yml. Die Befehle erstellen config und backups im Checkout sowie Downloads und Medien im Home-Verzeichnis. Die Standard-Mounts verwenden **diese** Ordner, nicht /opt/aio-media-manager/config.

## 3. docker-compose.yml prüfen

Öffne die Datei im Texteditor. Setze PUID/PGID auf uid/gid aus id; im Compose stehen zunächst 1000:1000. Exportierte Shellvariablen überschreiben diese festen Werte nicht. Setze TZ etwa auf Europe/Berlin. Ordnerzuordnungen zunächst beibehalten; Backups möglichst später auf einen anderen Datenträger legen.

!!! tip "sudo"
    Bei sudo können Variablen verloren gehen und HOME kann /root werden. Gib den Datenpfad ausdrücklich mit: `sudo env AMM_DATA_HOST="$AMM_DATA_HOST" docker compose up -d`. Bei Updates denselben Pfad verwenden.

## 4. AIO starten

```bash
docker compose pull
docker compose up -d
docker compose ps
```

Erwartet: ein laufender Container aio-media-manager. Der erste Image-Download kann einige Minuten dauern. Öffne http://DEINE-SERVER-IP:8080 mit deiner tatsächlichen Adresse, erstelle das Administratorkonto und schließe den Assistenten ab. Danach [Dashboard-Anleitung](../docs/USAGE.md). Bei Fehlern: docker compose logs --tail=100. Bei Portkonflikten die **Hostseite** ändern, Container neu erstellen und den neuen Port öffnen.

## Später aktualisieren

```bash
docker compose pull
docker compose up -d --force-recreate
```

Der Container kann sein eigenes Image nicht ersetzen. Einstellungen → Updates meldet eine `:nightly`-Installation nur, wenn `:nightly` sich verschoben hat, und eine `:latest`-Installation nur, wenn `:latest` sich verschoben hat. Holen tun Sie weiter diesen Tag auf dem Host. Installierte Apps (Sonarr, Seerr und der Rest) aktualisieren Sie unter **Einstellungen → Updates**, einzeln oder alle auf einmal. Diese Zeitpläne sind standardmäßig aus. Den Container neu zu erstellen hebt sie nicht an.

Veröffentlichte Images lesen Version und Commit aus ihren eigenen Build-Metadaten. Alte `AMM_VERSION`- oder `AMM_GIT_SHA`-Werte in Compose können diese Identität nicht überschreiben oder eine falsche Update-Meldung auslösen. Bei einer Quellcode-Installation ohne Image-Metadaten werden diese Variablen weiterhin verwendet.

**Ältere Compose-Datei, die nur Port 8080 veröffentlicht hat?** Kopieren Sie die aktuelle `ports:`-Liste aus diesem Repo und erstellen Sie neu, sonst scheitern die **Oberfläche öffnen**-Links der Kind-Apps im LAN.

**`/backups` später ergänzen:** Host-Ordner anlegen, `- /path/to/backups:/backups` unter `volumes:` eintragen und neu erstellen. Alte Sicherungen unter `/config/backups` bleiben wiederherstellbar, bis Sie sie entfernen.

**Host-Netzwerkverkehr auf Start:** fügen Sie `- /sys:/host/sys:ro` unter `volumes:` ein und erstellen Sie neu. Ohne diese Zeile zeigt Start nur den eigenen Verkehr des Containers.

Ein optionales `GITHUB_TOKEN` (Compose oder Einstellungen → Updates) hebt das GitHub-API-Limit. Committen Sie das Token nicht.

### Aus diesem Checkout bauen

```bash
docker compose up -d --build
```

### Entwicklungs- / Testumgebung

```bash
./scripts/test-env.sh up
```

Siehe [CONTRIBUTING.md](../CONTRIBUTING.md).

### Hardware-Transkodierung (Intel/AMD)

Das Image enthält **jellyfin-ffmpeg** (mit Intel-iHD-/VA-API-Treibern). Host-Render-Node mappen, Container nach dem Pull neu erstellen, in Jellyfin unter Playback → Transcoding **Intel Quick Sync** (oder VAAPI) aktivieren.

```bash
docker compose -f docker-compose.yml -f compose.gpu.yml up -d
```

---

## 3. Einfaches `docker run` (Alternative)

```bash
docker pull ghcr.io/qballjos/aio-media-server-manager:latest

docker run -d --name aio-media-manager --restart unless-stopped \
  --privileged \
  --cap-add NET_ADMIN --cap-add SYS_MODULE \
  --device /dev/dri:/dev/dri \
  -p 8080:8080 \
  -p 8081:8081 -p 8084:8084 -p 8085:8085 -p 8096:8096 \
  -p 8191:8191 -p 5055:5055 -p 6060:6060 \
  -p 6767:6767 -p 6789:6789 \
  -p 7878:7878 -p 8686:8686 -p 8989:8989 -p 9696:9696 -p 9705:9705 -p 11011:11011 \
  -p 32400:32400 \
  -e PUID="${PUID}" -e PGID="${PGID}" \
  -e TZ=UTC \
  -v /opt/aio-media-manager/config:/config \
  -v "${HOME}/aio-media-manager:/data" \
  -v /opt/aio-media-manager/backups:/backups \
  -v /sys:/host/sys:ro \
  -e AMM_DOWNLOAD_DIR=/data/downloads \
  -e AMM_MEDIA_DIR=/data/media \
  ghcr.io/qballjos/aio-media-server-manager:latest
```

Lassen Sie `--device /dev/dri` weg, wenn der Host keine Intel/AMD-GPU hat (Docker Desktop auf einem Mac, viele VPS-Hosts). Oder nutzen Sie `--network host` statt jeder einzelnen `-p`.

Vollständige Portliste: [Installieren → Ports](../docs/REFERENCE.md#ports).

---

## Privates GHCR-Image

Wenn pull scheitert, weil das Paket privat ist:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker pull ghcr.io/qballjos/aio-media-server-manager:latest
```

Auf GitHub können Sie das Paket auch öffentlich machen unter **Packages → settings → Change visibility**.

---

## Optionales VPN

Für den Verkehr von qBittorrent / Prowlarr / Flaresolverr:

```bash
sudo mkdir -p /opt/aio-media-manager/config/vpn
sudo chown -R "${PUID}:${PGID}" /opt/aio-media-manager/config/vpn
# copy wg0.conf or an OpenVPN profile into that folder
```

1. Setzen Sie `AMM_VPN_ENABLED=true` (und `AMM_VPN_ENFORCE=true`, wenn Torrents nicht ohne VPN laufen dürfen).
2. Lassen Sie Usenet-Clients außerhalb des VPN — sie nutzen das normale Netz.
3. Speichern Sie das Profil unter **Einstellungen → VPN** (oder mounten und per Umgebung aktivieren), dann den Container **neu anlegen**, damit WireGuard beim Boot hochkommt.

Der privilegierte Modus ist nötig für `/dev/net/tun` und das VPN-UID-Routing (WireGuard im Haupt-Netzwerk-Namespace; Torrent-Apps laufen unter einer eigenen UID). Synology braucht oft **wireguard-go** aus dem Image, wenn der Host kein WireGuard-Kernelmodul hat — siehe [SYNOLOGY.md](SYNOLOGY.md).

### Was AIO macht, solange das VPN an ist

- Diese drei Apps starten erst nach einem Live-WireGuard-Handshake. Ist der Tunnel beim Boot down, warten sie; AIO versucht das VPN mit Backoff erneut und startet sie, wenn er wieder da ist. Ein manuelles VPN-**Stop** bricht den Retry ab.
- DNS für diese Apps läuft über einen kleinen Caching-Forwarder in AIO (`127.0.0.153`), an die Tunnel-Schnittstelle gebunden, damit Lookups nicht aufs Haus-WAN leaken. Er fragt mehrere öffentliche Resolver parallel und kann eine frische Antwort liefern, wenn Upstream kurz still ist — damit Prowlarr-Indexer nicht an einem Timeout scheitern. Andere Apps (Sonarr, Radarr, SABnzbd, …) behalten den Container-Resolver.
- Usenet-Verkehr nutzt den Tunnel nie.

---

## Reverse-Proxy oder Cloudflare

- **Kein Proxy nötig** für das Heimnetz unter `http://server-ip:8080`.
- Eigenes Traefik/Caddy/Nginx: setzen Sie `AMM_TRUSTED_PROXIES` und optional `AMM_ROOT_PATH`.
- **Cloudflare Tunnel** (keine eingehenden Ports): [CLOUDFLARE.md](CLOUDFLARE.md).  
  `cloudflared` läuft **in** diesem Container — fügen Sie keinen zweiten Cloudflare-Dienst hinzu.
