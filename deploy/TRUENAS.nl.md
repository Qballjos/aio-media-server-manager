# TrueNAS SCALE

Zet AIO neer als **één** custom app / Docker-installatie. Installeer Sonarr, Radarr of downloadclients niet ook als losse SCALE-apps als je dit alles-in-één-model wilt.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`

## Datasets en mappen maken (SSH)

Zet SSH aan (**System → Services → SSH**) en daarna:

```bash
ssh admin@<truenas-ip>
```

Vervang `tank` door de naam van je pool. Config blijft op een apps-dataset. **Downloads en media komen in de home van de ingelogde gebruiker**, zodat de Files-interface ze kan tonen (`~/aio-media-manager`). Houd die twee als mappen op **dezelfde** dataset, zodat *Arr kan hardlinken.

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

`tank/backups/aio-media-manager` bewaart de configuratieback-ups. Een aparte dataset kun je op een eigen schema snapshotten of repliceren. Zet hem op een andere pool als je die hebt.

Series, films, anime, muziek, boeken, strips, complete/incomplete downloads, torrentcategorieën en transcode-caches worden bij de eerste start in deze mounts aangemaakt.

Zet de eigenaar op je mediagebruiker (TrueNAS `apps` is vaak UID/GID `568`; controleer met `id apps` of `id`):

```bash
id apps
sudo chown -R 568:568 \
  /mnt/tank/apps/aio-media-manager \
  "${DATA}" \
  /mnt/tank/backups/aio-media-manager
```

Als user home niet aan staat, maak die aan onder Credentials → Users, of zet `DATA` op een map die je in **Files** ziet (nog steeds één ouder voor `downloads` en `media`).

## Custom App

1. **Apps → Discover → Custom App** (of Launch Docker Image).
2. Image: `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Port forwarding: `8080` → `8080` plus de WebUI-poorten van de kind-apps uit [INSTALL.md](../docs/INSTALL.md#ports) (of host-netwerk).
4. Storage (paden uit de SSH-commando’s hierboven):
   - `/mnt/tank/apps/aio-media-manager` → `/config`
   - `$HOME/aio-media-manager` → `/data`
   - `/mnt/tank/backups/aio-media-manager` → `/backups`
   - `/sys` → `/host/sys` (alleen-lezen), zodat de serverkaart op Start het netwerkverkeer van de server toont. Zonder deze mount is de grafiek alleen het verkeer van deze container.
5. Omgeving: `PUID` / `PGID` = de UID/GID die je bij `chown` hebt gebruikt, plus `TZ`, `AMM_DOWNLOAD_DIR=/data/downloads` en `AMM_MEDIA_DIR=/data/media`. Optioneel `GITHUB_TOKEN` voor de GitHub-limiet (of Instellingen → Updates na de eerste start).
6. Privileged / `NET_ADMIN` als je de qBittorrent-VPN aanzet.
7. GPU: geef `/dev/dri` door (Intel/AMD) of de NVIDIA-runtime bij transcoden.

De interface van de manager is `http://<truenas-ip>:8080`. Maak de custom app opnieuw aan na een image-update, zodat nieuw gepubliceerde poorten gelden.

## Updates

TrueNAS haalt een nieuwere `:latest` op als je de app bijwerkt. Pin een semver-tag (`:0.2.0`) als je langzamer wilt upgraden zodra er git-tags zijn. Dat werkt AIO bij. Geïnstalleerde apps werk je bij via **Instellingen → Updates** (schema’s staan standaard uit).
