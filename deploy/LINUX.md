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

sudo useradd --system --create-home --home-dir /opt/aio-media-manager --shell /usr/sbin/nologin amm || true
sudo mkdir -p \
  /opt/aio-media-manager \
  /var/lib/aio-media-manager/config \
  /var/lib/aio-media-manager/config/vpn \
  /var/lib/aio-media-manager/data/downloads \
  /var/lib/aio-media-manager/data/media
sudo chown -R amm:amm /opt/aio-media-manager /var/lib/aio-media-manager
id amm
```

To use existing library paths, keep downloads and media as siblings on the same filesystem:

```bash
sudo mkdir -p /srv/data/downloads /srv/data/media
sudo chown -R amm:amm /srv/data
```

## Install

```bash
sudo -u amm git clone https://github.com/Qballjos/aio-media-server-manager.git /opt/aio-media-manager
cd /opt/aio-media-manager
sudo -u amm cp .env.example .env
```

Point `AMM_CONFIG_DIR`, `AMM_DOWNLOAD_DIR`, and `AMM_MEDIA_DIR` in `.env` at the directories you created. Set `PUID`/`PGID` to `id amm` (or your media user). Set `TZ` (or `AMM_TIMEZONE`) to your IANA timezone. Optional `GITHUB_TOKEN` and update-schedule variables are documented in `.env.example`; you can also set them in **Settings** after first-run.

```bash
sudo -u amm poetry install --only main --no-interaction
sudo -u amm bash -lc 'cd frontend && npm ci && npm run build'

sudo cp deploy/aio-media-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aio-media-manager
```

Open `http://<host>:8080`.

If systemd-managed Python is 3.14+, install a 3.13 interpreter for Bazarr (`AMM_CHILD_PYTHON` pointing at `python3.13`) or Bazarr will fail on missing `PIL` / unsupported Python.

## Service file

[`aio-media-manager.service`](aio-media-manager.service) starts `/opt/aio-media-manager/.venv/bin/python main.py`. If Poetry placed the venv elsewhere, update `ExecStart` (`poetry env info -p`).

## LXC notes

- Unprivileged containers cannot create VPN network namespaces; skip VPN or use a privileged CT.
- Bind-mount media datasets into the CT; keep downloads and media on the same dataset for hardlinks.
