# Docker

So läuft AIO üblicherweise: **ein Container**, der den Manager und jede App startet, die Sie einschalten.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Läuft auf:** `linux/amd64` und `linux/arm64`  
(Auf ARM ist Flaresolverr nicht verfügbar — es braucht x86_64.)

---

## 1. Ordner anlegen (über SSH)

```bash
ssh user@host
```

```bash
id
export PUID="$(id -u)"
export PGID="$(id -g)"
export AMM_DATA_HOST="${HOME}/aio-media-manager"

mkdir -p "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media"
sudo mkdir -p /opt/aio-media-manager/{config,config/vpn,backups}
sudo chown -R "${PUID}:${PGID}" "${AMM_DATA_HOST}" /opt/aio-media-manager
```

**Warum diese Pfade?**

- Downloads und Medien liegen unter **Ihrem Home**, damit der Dateimanager des Hosts sie sieht.
- Lassen Sie sie als zwei Ordner unter **einem** Elternordner, damit Hardlinks funktionieren. Getrennte Mounts auf verschiedenen Platten (oder verschiedenen btrfs-Subvolumes) erzwingen oft vollständige Kopien.
- Legen Sie **backups** auf eine andere Platte als **config**, wenn möglich. Ohne einen `/backups`-Mount fällt AIO auf `/config/backups` zurück und warnt in den Einstellungen.

Bibliotheken schon woanders? Setzen Sie `AMM_DATA_HOST` auf diesen Elternordner (darin müssen weiterhin `downloads` und `media` liegen).

---

## 2. Mit Compose starten (empfohlen)

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
```

Prüfen Sie `docker-compose.yml`:

- Die Volume-Pfade passen zu den angelegten Ordnern
- `PUID` / `PGID` passen zu `id`
- `TZ` ist Ihre Zeitzone (oder setzen Sie sie später in den Einstellungen)

Wenn Sie `sudo docker compose` nutzen, setzen Sie `AMM_DATA_HOST` ausdrücklich, damit Daten nicht in `/root` landen.

```bash
docker compose pull
docker compose up -d
```

Öffnen Sie `http://YOUR-HOST:8080`, legen Sie das Administratorkonto an und folgen Sie dann [Das Dashboard nutzen](../docs/USAGE.md).

**Später aktualisieren:** erneut holen und neu erstellen:

```bash
docker compose pull
docker compose up -d --force-recreate
```

Der Container kann sein eigenes Image nicht ersetzen. Einstellungen → Updates kann *melden*, wenn `:latest` sich verschoben hat; holen tun Sie weiter auf dem Host. Installierte Apps (Sonarr, Seerr und der Rest) aktualisieren Sie unter **Einstellungen → Updates**, einzeln oder alle auf einmal. Diese Zeitpläne sind standardmäßig aus. Den Container neu zu erstellen hebt sie nicht an.

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
  -p 7878:7878 -p 8686:8686 -p 8989:8989 -p 9696:9696 -p 9705:9705 \
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

Vollständige Portliste: [Installieren → Ports](../docs/INSTALL.md#ports).

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

Der privilegierte Modus ist nötig für Netzwerk-Namespaces und `/dev/net/tun`.

---

## Reverse-Proxy oder Cloudflare

- **Kein Proxy nötig** für das Heimnetz unter `http://server-ip:8080`.
- Eigenes Traefik/Caddy/Nginx: setzen Sie `AMM_TRUSTED_PROXIES` und optional `AMM_ROOT_PATH`.
- **Cloudflare Tunnel** (keine eingehenden Ports): [CLOUDFLARE.md](CLOUDFLARE.md).  
  `cloudflared` läuft **in** diesem Container — fügen Sie keinen zweiten Cloudflare-Dienst hinzu.
