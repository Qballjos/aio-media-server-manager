# Native Linux / LXC installation

Use this when you want the appliance on Debian, Ubuntu, or a Proxmox LXC **without** Docker. Child apps are still processes under the manager, not extra systemd units.

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- Node.js 22 (to build the dashboard once)
- `ffmpeg` (transcoding / some media apps)
- Optional VPN: `wireguard` or `openvpn`, plus `iproute2`; LXC needs `nesting=1` and `/dev/net/tun`

## Create folders over SSH

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

Downloads and media stay in the **login user's home** (`~/aio-media-manager`) so the desktop file manager can see them. Config stays under `/var/lib`. To use existing library paths, keep downloads and media as siblings on the same filesystem and point `.env` at those directories.

## Install

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

Point `AMM_CONFIG_DIR`, `AMM_DOWNLOAD_DIR`, `AMM_MEDIA_DIR`, and `AMM_BACKUP_DIR` in `.env` at the directories you created (`~/aio-media-manager/downloads` and `~/aio-media-manager/media` by default). Put `AMM_BACKUP_DIR` on another disk or mount if you can. Set `PUID`/`PGID` to `id amm` (or your media user). Set `TZ` (or `AMM_TIMEZONE`) to your IANA timezone. Optional `GITHUB_TOKEN` and update-schedule variables are documented in `.env.example`; you can also set them in **Settings** after first-run.

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

Open `http://<host>:8080`.

If systemd-managed Python is 3.14+, install a 3.13 interpreter for Bazarr (`AMM_CHILD_PYTHON` pointing at `python3.13`) or Bazarr will fail on missing `PIL` / unsupported Python.

## Host packages by application

Install only what you will run. On ARM64, skip Chromium — Flaresolverr is x86_64-only and is hidden from the catalog.

| Packages | Applications |
|----------|----------------|
| `ffmpeg`, `libfontconfig1` | Jellyfin, Plex |
| `libicu*`, `libssl3`, `libsqlite3-0`, `sqlite3`, `libgssapi-krb5-2`, `zlib1g` | Sonarr, Radarr, Lidarr, Prowlarr, Profilarr, NeutArr |
| `git` | Recyclarr (clones TRaSH Guides) |
| `unrar` (RAR 5+), `par2`, `p7zip-full` | SABnzbd, NZBGet |
| Python 3.13, `libxml2`, `libxslt1.1`, `libjpeg62-turbo`, `python3-dev`, `build-essential` | Bazarr, SABnzbd, Shelfmark, NeutArr |
| Node.js 22 | Seerr |
| JRE 25, `mariadb-server` | Grimmory |
| `chromium`, `xvfb`, `fonts-liberation` | Flaresolverr (x86_64 only) |
| `iproute2`, `openvpn`, `wireguard-tools` | Optional VPN (qBittorrent, Prowlarr, Flaresolverr) |

## Service file

[`aio-media-manager.service`](aio-media-manager.service) starts `/opt/aio-media-manager/.venv/bin/python main.py`. If Poetry placed the venv elsewhere, update `ExecStart` (`poetry env info -p`). The unit’s download/media paths must match the login home (`sed` in the install steps above).

## LXC notes

- Unprivileged containers cannot create VPN network namespaces; skip VPN or use a privileged CT.
- Bind-mount media into the CT under the login home (`~/aio-media-manager`); keep downloads and media on the same dataset for hardlinks.
