# Linux / LXC (sans Docker)

Utilisez ceci sur Debian, Ubuntu ou un LXC Proxmox si vous préférez **ne pas** utiliser Docker.  
Sonarr et le reste tournent toujours comme des processus sous AIO — vous ne créez pas d’unité systemd par app.

## Ce qu’il vous faut

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- Node.js 22 (construire le tableau de bord une fois)
- `ffmpeg` (pour le transcodage / certaines apps média)
- VPN facultatif : `wireguard` ou `openvpn`, plus `iproute2`  
  Sur LXC : activez `nesting=1` et `/dev/net/tun`

## Créer les dossiers en SSH

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

Les téléchargements et les médias restent dans le **home de l’utilisateur connecté** (`~/aio-media-manager`) pour que le gestionnaire de fichiers du bureau les voie. La config reste sous `/var/lib`. Pour des chemins de bibliothèque existants, gardez téléchargements et médias comme voisins sur le même système de fichiers et pointez `.env` vers ces dossiers.

## Installer

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

Pointez `AMM_CONFIG_DIR`, `AMM_DOWNLOAD_DIR`, `AMM_MEDIA_DIR` et `AMM_BACKUP_DIR` dans `.env` vers les dossiers créés (`~/aio-media-manager/downloads` et `~/aio-media-manager/media` par défaut). Mettez `AMM_BACKUP_DIR` sur un autre disque ou montage si vous pouvez. Mettez `PUID`/`PGID` sur `id amm` (ou votre utilisateur média). Mettez `TZ` (ou `AMM_TIMEZONE`) sur votre fuseau IANA. `GITHUB_TOKEN` et les variables de planification, facultatifs, sont documentés dans `.env.example` ; vous pouvez aussi les régler dans **Réglages** après la première exécution.

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

Ouvrez `http://<host>:8080`. Les apps installées se mettent à jour plus tard depuis **Réglages → Mises à jour** (planifications désactivées par défaut). Mettre à jour cette copie et redémarrer le service met AIO lui-même à jour. Sur une installation native, la carte Serveur de l’accueil voit déjà les cartes réseau de l’hôte.

Si le Python géré par systemd est 3.14 ou plus récent, installez un interpréteur 3.13 pour Bazarr (`AMM_CHILD_PYTHON` vers `python3.13`), sinon Bazarr échoue sur un `PIL` manquant ou un Python non pris en charge.

## Paquets de l’hôte par application

N’installez que ce que vous allez faire tourner. Sur ARM64, sautez Chromium — Flaresolverr est réservé à x86_64 et masqué dans le catalogue.

| Paquets | Applications |
|----------|----------------|
| `ffmpeg`, `libfontconfig1` | Jellyfin, Plex |
| `libicu*`, `libssl3`, `libsqlite3-0`, `sqlite3`, `libgssapi-krb5-2`, `zlib1g` | Sonarr, Radarr, Lidarr, Prowlarr, NeutArr |
| `git` | Recyclarr (clone TRaSH Guides) |
| `unrar` (RAR 5+), `p7zip-full`, [par2cmdline-turbo](https://sabnzbd.org/wiki/installation/par2cmdline-turbo) comme `par2` | SABnzbd, NZBGet |
| Python 3.13, `libxml2`, `libxslt1.1`, `libjpeg62-turbo`, `python3-dev`, `build-essential` | Bazarr, SABnzbd, NeutArr |
| Python du gestionnaire 3.14, `python3-dev`, `build-essential` | Shelfmark (l’amont exige Python >= 3.14) |
| Node.js 22 | Seerr |
| JRE 25, `mariadb-server` | Grimmory |
| `chromium`, `xvfb`, `fonts-liberation` | Flaresolverr (x86_64 seulement) |
| `iproute2`, `openvpn`, `wireguard-tools` | VPN facultatif (qBittorrent, Prowlarr, Flaresolverr) |

## Fichier de service

[`aio-media-manager.service`](aio-media-manager.service) démarre `/opt/aio-media-manager/.venv/bin/python main.py`. Si Poetry a placé le venv ailleurs, mettez `ExecStart` à jour (`poetry env info -p`). Les chemins de téléchargement et de médias de l’unité doivent correspondre au home de connexion (`sed` dans les étapes d’installation ci-dessus).

## Notes LXC

- Les conteneurs non privilégiés ne peuvent pas créer d’espaces de noms réseau VPN ; sautez le VPN ou utilisez un CT privilégié.
- Montez les médias dans le CT sous le home de connexion (`~/aio-media-manager`) ; gardez téléchargements et médias sur le même dataset pour les liens physiques.
