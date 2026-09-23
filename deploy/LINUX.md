# Native Linux / LXC installation

Use this when you want the appliance on Debian, Ubuntu, or a Proxmox LXC **without** Docker. Child apps are still processes under the manager, not extra systemd units.

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- Node.js 22 (to build the dashboard once)
- `ffmpeg` (transcoding / some media apps)
- Optional VPN: `wireguard` or `openvpn`, plus `iproute2`; LXC needs `nesting=1` and `/dev/net/tun`

## Install

```bash
sudo useradd --system --create-home --home-dir /opt/aio-media-manager --shell /usr/sbin/nologin amm
sudo mkdir -p /var/lib/aio-media-manager/{config,downloads,media}
sudo chown -R amm:amm /opt/aio-media-manager /var/lib/aio-media-manager

sudo -u amm git clone https://github.com/Qballjos/aio-media-server-manager.git /opt/aio-media-manager
cd /opt/aio-media-manager
sudo -u amm cp .env.example .env
```

Point `AMM_CONFIG_DIR`, `AMM_DOWNLOAD_DIR`, and `AMM_MEDIA_DIR` in `.env` at `/var/lib/aio-media-manager/...` (or your real library paths). Set `PUID`/`PGID` to the media user that owns those directories.

```bash
sudo -u amm poetry install --only main --no-interaction
sudo -u amm bash -lc 'cd frontend && npm ci && npm run build'

sudo cp deploy/aio-media-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aio-media-manager
```

Open `http://<host>:8080`.

If the host has no systemd, run `poetry run python main.py` under the built-in supervisor (tmux/screen, or your process manager). Do not add one systemd unit per *Arr application.

## Service file

[`aio-media-manager.service`](aio-media-manager.service) starts `/opt/aio-media-manager/.venv/bin/python main.py`. If Poetry placed the venv elsewhere, update `ExecStart` (`poetry env info -p`).

## LXC notes

- Unprivileged containers cannot create VPN network namespaces; skip VPN or use a privileged CT.
- Bind-mount media datasets into the CT; keep downloads and media on the same dataset for hardlinks.
