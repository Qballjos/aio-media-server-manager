# Docker

C’est la façon habituelle de faire tourner AIO : **un conteneur** qui démarre le gestionnaire et chaque app que vous activez.

**Image :** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Fonctionne sur :** `linux/amd64` et `linux/arm64`  
(Sur ARM, Flaresolverr n’est pas disponible — il lui faut x86_64.)

---

## 1. Créer les dossiers (en SSH)

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

**Pourquoi ces chemins ?**

- Les téléchargements et les médias vivent sous **votre home**, pour que le gestionnaire de fichiers de l’hôte les voie.
- Gardez-les comme deux dossiers sous **un** parent pour que les liens physiques fonctionnent. Des montages séparés sur des disques différents (ou des sous-volumes btrfs différents) forcent souvent une copie complète.
- Mettez **backups** sur un autre disque que **config** si vous pouvez. Sans montage `/backups`, AIO retombe sur `/config/backups` et avertit dans Réglages.

Vous avez déjà des bibliothèques ailleurs ? Mettez `AMM_DATA_HOST` sur ce dossier parent (il doit toujours contenir `downloads` et `media`).

---

## 2. Démarrer avec Compose (recommandé)

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
```

Vérifiez `docker-compose.yml` :

- Les chemins de volumes correspondent aux dossiers créés
- `PUID` / `PGID` correspondent à `id`
- `TZ` est votre fuseau (ou réglez-le plus tard dans Réglages)

Si vous utilisez `sudo docker compose`, définissez `AMM_DATA_HOST` explicitement pour que les données n’atterrissent pas dans `/root`.

```bash
docker compose pull
docker compose up -d
```

Ouvrez `http://YOUR-HOST:8080`, créez le compte administrateur, puis suivez [Utiliser le tableau de bord](../docs/USAGE.md).

**Mettre à jour plus tard :** tirer à nouveau, puis recréer :

```bash
docker compose pull
docker compose up -d --force-recreate
```

Le conteneur ne peut pas remplacer sa propre image. Réglages → Mises à jour peut vous *signaler* quand `:latest` a bougé ; vous tirez toujours sur l’hôte. Les apps installées (Sonarr, Seerr et le reste) se mettent à jour depuis **Réglages → Mises à jour**, une par une ou toutes à la fois. Ces planifications sont désactivées par défaut. Recréer le conteneur ne les fait pas avancer.

**Ancien Compose qui ne publiait que le port 8080 ?** Copiez la liste `ports:` actuelle de ce dépôt et recréez, sinon les liens **Ouvrir l’interface** des apps enfants échouent sur le LAN.

**Ajouter `/backups` plus tard :** créez le dossier hôte, ajoutez `- /path/to/backups:/backups` sous `volumes:`, recréez. Les anciennes sauvegardes sous `/config/backups` restent restaurables jusqu’à ce que vous les retiriez.

**Trafic réseau de l’hôte sur Accueil :** ajoutez `- /sys:/host/sys:ro` sous `volumes:` et recréez. Sans cette ligne, Accueil ne montre que le trafic propre du conteneur.

Un `GITHUB_TOKEN` facultatif (Compose ou Réglages → Mises à jour) relève la limite de l’API GitHub. Ne commitez pas le jeton.

### Construire depuis cette copie

```bash
docker compose up -d --build
```

### Environnement de développement / test

```bash
./scripts/test-env.sh up
```

Voir [CONTRIBUTING.md](../CONTRIBUTING.md).

### Transcodage matériel (Intel/AMD)

```bash
docker compose -f docker-compose.yml -f compose.gpu.yml up -d
```

---

## 3. Simple `docker run` (autre possibilité)

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

Retirez `--device /dev/dri` si l’hôte n’a pas de GPU Intel/AMD (Docker Desktop sur un Mac, beaucoup d’hôtes VPS). Ou utilisez `--network host` au lieu de lister chaque `-p`.

Liste complète des ports : [Installer → Ports](../docs/INSTALL.md#ports).

---

## Image GHCR privée

Si le pull échoue parce que le paquet est privé :

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker pull ghcr.io/qballjos/aio-media-server-manager:latest
```

Sur GitHub vous pouvez aussi rendre le paquet public sous **Packages → settings → Change visibility**.

---

## VPN facultatif

Pour le trafic de qBittorrent / Prowlarr / Flaresolverr :

```bash
sudo mkdir -p /opt/aio-media-manager/config/vpn
sudo chown -R "${PUID}:${PGID}" /opt/aio-media-manager/config/vpn
# copy wg0.conf or an OpenVPN profile into that folder
```

1. Mettez `AMM_VPN_ENABLED=true` (et `AMM_VPN_ENFORCE=true` si les torrents ne doivent pas tourner sans VPN).
2. Laissez les clients Usenet hors du VPN — ils utilisent le réseau normal.

Le mode privilégié est nécessaire pour les espaces de noms réseau et `/dev/net/tun`.

---

## Reverse proxy ou Cloudflare

- **Pas de proxy nécessaire** pour le réseau local à `http://server-ip:8080`.
- Votre propre Traefik/Caddy/Nginx : définissez `AMM_TRUSTED_PROXIES` et éventuellement `AMM_ROOT_PATH`.
- **Cloudflare Tunnel** (pas de ports entrants) : [CLOUDFLARE.md](CLOUDFLARE.md).  
  `cloudflared` tourne **dans** ce conteneur — n’ajoutez pas un second service Cloudflare.
