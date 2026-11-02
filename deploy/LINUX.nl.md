# Linux / LXC (geen Docker)

Gebruik dit op Debian, Ubuntu of een Proxmox-LXC als je **geen** Docker wilt.  
Sonarr en de rest draaien nog steeds als processen onder AIO — je maakt geen systemd-unit per app.

## Wat je nodig hebt

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- Node.js 22 (bouw het dashboard één keer)
- `ffmpeg` (voor transcoden / sommige media-apps); voor Jellyfin-HW bij voorkeur `jellyfin-ffmpeg7` van [repo.jellyfin.org](https://repo.jellyfin.org)
- Optionele VPN: `wireguard` of `openvpn`, plus `iproute2`  
  Op LXC: zet `nesting=1` en `/dev/net/tun` aan

## Mappen maken via SSH

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

Downloads en media blijven in de **home van de ingelogde gebruiker** (`~/aio-media-manager`), zodat de bestandsbeheerder van de desktop ze ziet. Config blijft onder `/var/lib`. Voor bestaande bibliotheekpaden houd je downloads en media als buren op hetzelfde bestandssysteem en wijs je `.env` naar die mappen.

## Installeren

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

Wijs `AMM_CONFIG_DIR`, `AMM_DOWNLOAD_DIR`, `AMM_MEDIA_DIR` en `AMM_BACKUP_DIR` in `.env` naar de mappen die je hebt gemaakt (`~/aio-media-manager/downloads` en `~/aio-media-manager/media` standaard). Zet `AMM_BACKUP_DIR` op een andere schijf of mount als dat kan. Zet `PUID`/`PGID` op `id amm` (of je mediagebruiker). Zet `TZ` (of `AMM_TIMEZONE`) op je IANA-tijdzone. Optionele `GITHUB_TOKEN` en schema-variabelen staan in `.env.example`; je kunt ze ook in **Instellingen** zetten na de eerste start.

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

Open `http://<host>:8080`. Geïnstalleerde apps werk je later bij via **Instellingen → Updates** (schema’s staan standaard uit). Deze checkout bijwerken en de service herstarten werkt AIO zelf bij. Bij een native installatie ziet de serverkaart op Start de netwerkkaarten van de host al.

Als de Python van systemd 3.14 of nieuwer is, installeer dan een 3.13-interpreter voor Bazarr (`AMM_CHILD_PYTHON` naar `python3.13`), anders faalt Bazarr op ontbrekende `PIL` of een niet-ondersteunde Python.

## Hostpakketten per applicatie

Installeer alleen wat je gaat draaien. Op ARM64 sla je Chromium over — Flaresolverr is alleen x86_64 en verborgen in de catalogus.

| Pakketten | Applicaties |
|----------|----------------|
| `jellyfin-ffmpeg7` (voorkeur) of `ffmpeg`, `libfontconfig1` | Jellyfin, Plex |
| `libicu*`, `libssl3`, `libsqlite3-0`, `sqlite3`, `libgssapi-krb5-2`, `zlib1g` | Sonarr, Radarr, Lidarr, Prowlarr, NeutArr |
| `git` | Recyclarr (kloont TRaSH Guides) |
| `unrar` (RAR 5+), `p7zip-full`, [par2cmdline-turbo](https://sabnzbd.org/wiki/installation/par2cmdline-turbo) als `par2` | SABnzbd, NZBGet |
| Python 3.13, `libxml2`, `libxslt1.1`, `libjpeg62-turbo`, `python3-dev`, `build-essential` | Bazarr, SABnzbd, NeutArr |
| Manager-Python 3.14, `python3-dev`, `build-essential` | Shelfmark (upstream vraagt Python >= 3.14) |
| Node.js 22 | Seerr |
| JRE 25, `mariadb-server` | Grimmory |
| `chromium`, `xvfb`, `fonts-liberation` | Flaresolverr (alleen x86_64) |
| `iproute2`, `openvpn`, `wireguard-tools` | Optionele VPN (qBittorrent, Prowlarr, Flaresolverr) |

## Servicebestand

[`aio-media-manager.service`](aio-media-manager.service) start `/opt/aio-media-manager/.venv/bin/python main.py`. Als Poetry de venv ergens anders heeft gezet, pas dan `ExecStart` aan (`poetry env info -p`). De download-/mediapaden van de unit moeten overeenkomen met de login-home (`sed` in de installatiestappen hierboven).

## LXC-opmerkingen

- Unprivileged containers kunnen geen VPN-netwerknamespaces maken; sla de VPN over of gebruik een privileged CT.
- Bind-mount media in de CT onder de login-home (`~/aio-media-manager`); houd downloads en media op dezelfde dataset voor hardlinks.
