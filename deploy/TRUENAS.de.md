# TrueNAS SCALE

Stellen Sie AIO als **eine** Custom App / Docker-Installation bereit. Installieren Sie Sonarr, Radarr oder Download-Clients nicht zusätzlich als eigene SCALE-Apps, wenn Sie dieses Alles-in-einem-Modell wollen.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`

## Datasets und Ordner anlegen (SSH)

Aktivieren Sie SSH (**System → Services → SSH**), dann:

```bash
ssh admin@<truenas-ip>
```

Ersetzen Sie `tank` durch den Namen Ihres Pools. Die Config bleibt auf einem Apps-Dataset. **Downloads und Medien kommen ins Home des angemeldeten Benutzers**, damit die Files-Oberfläche sie anzeigen kann (`~/aio-media-manager`). Lassen Sie die beiden als Verzeichnisse auf **demselben** Dataset, damit *Arr Hardlinks nutzen kann.

```bash
sudo zfs create -p tank/apps/aio-media-manager
sudo zfs create -p tank/backups/aio-media-manager

LOGIN_USER="${SUDO_USER:-$(id -un)}"
HOME_DIR="$(getent passwd "${LOGIN_USER}" | cut -d: -f6)"
DATA="${HOME_DIR}/aio-media-manager"

sudo mkdir -p \
  /mnt/tank/apps/aio-media-manager/vpn \
  "${DATA}/downloads" \
  "${DATA}/media"
```

`tank/backups/aio-media-manager` hält die Konfigurationssicherungen. Ein eigenes Dataset können Sie nach eigenem Zeitplan snapshotten oder replizieren. Legen Sie es auf einen anderen Pool, wenn Sie einen haben.

Serien, Filme, Anime, Musik, Bücher, Comics, vollständige/unvollständige Downloads, Torrent-Kategorien und Transcode-Caches werden beim ersten Start in diesen Mounts angelegt.

Setzen Sie den Besitzer auf Ihren Medienbenutzer (TrueNAS `apps` ist oft UID/GID `568`; prüfen Sie mit `id apps` oder `id`):

```bash
id apps
sudo chown -R 568:568 \
  /mnt/tank/apps/aio-media-manager \
  "${DATA}" \
  /mnt/tank/backups/aio-media-manager
```

Wenn User Home nicht aktiv ist, legen Sie es unter Credentials → Users an, oder setzen Sie `DATA` auf einen Ordner, den Sie in **Files** sehen (weiterhin ein Elternordner für `downloads` und `media`).

## Custom App

1. **Apps → Discover → Custom App** (oder Launch Docker Image).
2. Image: `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Portweiterleitung: `8080` → `8080` plus die WebUI-Ports der Kind-Apps aus [INSTALL.md](../docs/INSTALL.md#ports) (oder Host-Netzwerk).
4. Speicher (Pfade aus den SSH-Befehlen oben):
   - `/mnt/tank/apps/aio-media-manager` → `/config`
   - `$HOME/aio-media-manager` → `/data`
   - `/mnt/tank/backups/aio-media-manager` → `/backups`
   - `/sys` → `/host/sys` (nur lesend), damit die Server-Karte auf Start den Netzwerkverkehr des Servers zeigt. Ohne diesen Mount ist die Grafik nur der Verkehr dieses Containers.
5. Umgebung: `PUID` / `PGID` = die UID/GID aus Ihrem `chown`, plus `TZ`, `AMM_DOWNLOAD_DIR=/data/downloads` und `AMM_MEDIA_DIR=/data/media`. Optional `GITHUB_TOKEN` für das GitHub-Limit (oder Einstellungen → Updates nach der Ersteinrichtung).
6. Privileged / `NET_ADMIN`, wenn Sie VPN für qBittorrent, Prowlarr und Flaresolverr einschalten. Diese Apps warten auf einen Live-Tunnel; ihr DNS wird über den Tunnel gecacht (Usenet bleibt draußen). Details: [DOCKER.md](DOCKER.md#optionales-vpn).
7. GPU: reichen Sie `/dev/dri` durch (Intel/AMD) oder die NVIDIA-Laufzeit beim Transkodieren.

Die Oberfläche des Managers ist `http://<truenas-ip>:8080`. Erstellen Sie die Custom App nach einem Image-Update neu, damit neu veröffentlichte Ports gelten.

## Updates

TrueNAS holt ein neueres `:latest`, wenn Sie die App aktualisieren. Pinnen Sie ein Semver-Tag (`:0.2.0`), wenn Sie langsamer aktualisieren wollen, sobald Git-Tags existieren. Das aktualisiert AIO. Installierte Apps aktualisieren Sie unter **Einstellungen → Updates** (Zeitpläne sind standardmäßig aus).
