# Linux / LXC (ohne Docker)

Nutzen Sie dies auf Debian, Ubuntu oder einem Proxmox-LXC, wenn Sie **kein** Docker wollen.  
Sonarr und der Rest laufen weiter als Prozesse unter AIO — Sie legen keine systemd-Unit pro App an.

## Was Sie brauchen

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- Node.js 22 (Dashboard einmal bauen)
- `ffmpeg` (für Transkodierung / manche Media-Apps)
- Optionales VPN: `wireguard` oder `openvpn`, plus `iproute2`  
  Auf LXC: `nesting=1` und `/dev/net/tun` aktivieren

## Ordner über SSH anlegen

```bash
ssh user@host

LOGIN_USER="${SUDO_USER:-$(id -un)}"
HOME_DIR="$(getent passwd "${LOGIN_USER}" | cut -d: -f6)"
DATA="${HOME_DIR}/aio-media-manager"

sudo useradd --system --create-home --home-dir /opt/aio-media-manager --shell /usr/sbin/nologin amm || true
sudo mkdir -p \
  /opt/aio-media-manager \
  /var/lib/aio-media-manager/config \
  /var/lib/aio-media-manager/config/vpn \
  /var/lib/aio-media-manager/backups \
  "${DATA}/downloads" \
  "${DATA}/media"
sudo chown -R amm:amm /opt/aio-media-manager /var/lib/aio-media-manager "${DATA}"
id amm
```

Downloads und Medien bleiben im **Home des angemeldeten Benutzers** (`~/aio-media-manager`), damit der Dateimanager des Desktops sie sieht. Die Config bleibt unter `/var/lib`. Für vorhandene Bibliothekspfade lassen Sie Downloads und Medien als Geschwister auf demselben Dateisystem und zeigen in `.env` auf diese Verzeichnisse.

## Installieren

```bash
sudo -u amm git clone https://github.com/Qballjos/aio-media-server-manager.git /opt/aio-media-manager
cd /opt/aio-media-manager
sudo -u amm cp .env.example .env

LOGIN_USER="${SUDO_USER:-$(id -un)}"
HOME_DIR="$(getent passwd "${LOGIN_USER}" | cut -d: -f6)"
DATA="${HOME_DIR}/aio-media-manager"
sudo sed -i \
  -e "s|^AMM_CONFIG_DIR=.*|AMM_CONFIG_DIR=/var/lib/aio-media-manager/config|" \
  -e "s|^AMM_DOWNLOAD_DIR=.*|AMM_DOWNLOAD_DIR=${DATA}/downloads|" \
  -e "s|^AMM_MEDIA_DIR=.*|AMM_MEDIA_DIR=${DATA}/media|" \
  -e "s|^# AMM_BACKUP_DIR=.*|AMM_BACKUP_DIR=/var/lib/aio-media-manager/backups|" \
  /opt/aio-media-manager/.env
```

Zeigen Sie `AMM_CONFIG_DIR`, `AMM_DOWNLOAD_DIR`, `AMM_MEDIA_DIR` und `AMM_BACKUP_DIR` in `.env` auf die angelegten Verzeichnisse (`~/aio-media-manager/downloads` und `~/aio-media-manager/media` standardmäßig). Legen Sie `AMM_BACKUP_DIR` auf eine andere Platte oder einen anderen Mount, wenn möglich. Setzen Sie `PUID`/`PGID` auf `id amm` (oder Ihren Medienbenutzer). Setzen Sie `TZ` (oder `AMM_TIMEZONE`) auf Ihre IANA-Zeitzone. Optionales `GITHUB_TOKEN` und Zeitplan-Variablen stehen in `.env.example`; Sie können sie nach der Ersteinrichtung auch unter **Einstellungen** setzen.

```bash
sudo -u amm poetry install --only main --no-interaction
sudo -u amm bash -lc 'cd frontend && npm ci && npm run build'

sudo cp deploy/aio-media-manager.service /etc/systemd/system/
LOGIN_USER="${SUDO_USER:-$(id -un)}"
HOME_DIR="$(getent passwd "${LOGIN_USER}" | cut -d: -f6)"
sudo sed -i "s|/home/YOURUSER|${HOME_DIR}|g" /etc/systemd/system/aio-media-manager.service
sudo systemctl daemon-reload
sudo systemctl enable --now aio-media-manager
```

Öffnen Sie `http://<host>:8080`. Installierte Apps aktualisieren Sie später unter **Einstellungen → Updates** (Zeitpläne standardmäßig aus). Diesen Checkout aktualisieren und den Dienst neu starten aktualisiert AIO selbst. Bei einer nativen Installation sieht die Server-Karte auf Start die Netzwerkkarten des Hosts bereits.

Wenn das von systemd verwaltete Python 3.14 oder neuer ist, installieren Sie einen 3.13-Interpreter für Bazarr (`AMM_CHILD_PYTHON` auf `python3.13`), sonst scheitert Bazarr an fehlendem `PIL` oder nicht unterstütztem Python.

## Host-Pakete je Anwendung

Installieren Sie nur, was Sie ausführen. Auf ARM64 überspringen Sie Chromium — Flaresolverr ist nur x86_64 und im Katalog ausgeblendet.

| Pakete | Anwendungen |
|----------|----------------|
| `ffmpeg`, `libfontconfig1` | Jellyfin, Plex |
| `libicu*`, `libssl3`, `libsqlite3-0`, `sqlite3`, `libgssapi-krb5-2`, `zlib1g` | Sonarr, Radarr, Lidarr, Prowlarr, NeutArr |
| `git` | Recyclarr (klont TRaSH Guides) |
| `unrar` (RAR 5+), `p7zip-full`, [par2cmdline-turbo](https://sabnzbd.org/wiki/installation/par2cmdline-turbo) als `par2` | SABnzbd, NZBGet |
| Python 3.13, `libxml2`, `libxslt1.1`, `libjpeg62-turbo`, `python3-dev`, `build-essential` | Bazarr, SABnzbd, NeutArr |
| Manager-Python 3.14, `python3-dev`, `build-essential` | Shelfmark (Upstream verlangt Python >= 3.14) |
| Node.js 22 | Seerr |
| JRE 25, `mariadb-server` | Grimmory |
| `chromium`, `xvfb`, `fonts-liberation` | Flaresolverr (nur x86_64) |
| `iproute2`, `openvpn`, `wireguard-tools` | Optionales VPN (qBittorrent, Prowlarr, Flaresolverr) |

## Dienstdatei

[`aio-media-manager.service`](aio-media-manager.service) startet `/opt/aio-media-manager/.venv/bin/python main.py`. Wenn Poetry die venv woanders abgelegt hat, passen Sie `ExecStart` an (`poetry env info -p`). Die Download-/Medienpfade der Unit müssen zum Login-Home passen (`sed` in den Installationsschritten oben).

## LXC-Hinweise

- Unprivilegierte Container können keine VPN-Netzwerk-Namespaces anlegen; lassen Sie das VPN weg oder nutzen Sie einen privilegierten CT.
- Binden Sie Medien im CT unter dem Login-Home ein (`~/aio-media-manager`); lassen Sie Downloads und Medien auf demselben Dataset für Hardlinks.
