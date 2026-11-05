# Docker — Avancé

!!! info "Avancé"
    Cette page est la référence technique. Pour une première installation, suivez le guide débutant. [Guide débutant](DOCKER.md).

C’est la façon habituelle de faire tourner AIO : **un conteneur** qui démarre le gestionnaire et chaque app que vous activez.

**Image :** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Fonctionne sur :** `linux/amd64` et `linux/arm64`  
(Sur ARM, Flaresolverr n’est pas disponible — il lui faut x86_64.)

---

## 1. Vérifiez le serveur

Exécutez ces commandes sur le serveur AIO, après connexion SSH avec votre propre utilisateur et adresse si nécessaire.

```bash
docker info
docker compose version
git --version
```

Résultat attendu : un moteur Docker actif et les versions Compose/Git. Réglez d’abord les outils absents et les erreurs de droits selon votre hôte. Sur NAS, utilisez le [guide de plateforme](README.md), sans installer un deuxième moteur Docker.

## 2. Récupérez les fichiers et créez les dossiers

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
id
export PUID="$(id -u)"
export PGID="$(id -g)"
export AMM_DATA_HOST="${HOME}/aio-media-manager"
mkdir -p config/vpn backups "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media"
sudo chown -R "${PUID}:${PGID}" config backups "${AMM_DATA_HOST}"
```

Restez ensuite dans le dossier contenant docker-compose.yml. Ces commandes créent config et backups dans le projet, puis downloads et media dans votre dossier personnel. Les montages par défaut utilisent **ces** dossiers, pas /opt/aio-media-manager/config.

## 3. Vérifiez docker-compose.yml

Ouvrez le fichier dans un éditeur. Réglez PUID/PGID sur les uid/gid affichés par id ; Compose contient initialement 1000:1000. Les variables exportées ne remplacent pas ces valeurs fixes. Réglez TZ, par exemple Europe/Paris. Gardez les montages au début ; placez les sauvegardes sur un autre disque si possible.

!!! tip "sudo"
    Avec sudo, les variables peuvent disparaître et HOME devenir /root. Passez le dossier explicitement : `sudo env AMM_DATA_HOST="$AMM_DATA_HOST" docker compose up -d`. Conservez ce chemin pour les mises à jour.

## 4. Démarrez AIO

```bash
docker compose pull
docker compose up -d
docker compose ps
```

Résultat attendu : un conteneur aio-media-manager actif. Le premier téléchargement de l’image peut prendre plusieurs minutes. Ouvrez http://IP-DE-VOTRE-SERVEUR:8080 avec la vraie adresse, créez le compte administrateur et terminez l’assistant. Consultez ensuite [le guide du tableau de bord](../docs/USAGE.md). En cas d’erreur : docker compose logs --tail=100. Pour un conflit de port, changez le côté **hôte**, recréez le conteneur et ouvrez le nouveau port.

## Mettre à jour ensuite

```bash
docker compose pull
docker compose up -d --force-recreate
```

Le conteneur ne peut pas remplacer sa propre image. Réglages → Mises à jour signale une installation `:nightly` seulement quand `:nightly` a bougé, et une installation `:latest` seulement quand `:latest` a bougé. Vous tirez toujours ce tag sur l’hôte. Les apps installées (Sonarr, Seerr et le reste) se mettent à jour depuis **Réglages → Mises à jour**, une par une ou toutes à la fois. Ces planifications sont désactivées par défaut. Recréer le conteneur ne les fait pas avancer.

Les images publiées lisent leur version et leur commit dans leurs propres métadonnées de build. D’anciennes valeurs `AMM_VERSION` ou `AMM_GIT_SHA` conservées dans Compose ne peuvent plus remplacer cette identité ni provoquer une fausse notification. Une installation depuis les sources sans métadonnées d’image utilise toujours ces variables.

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

L’image inclut **jellyfin-ffmpeg** (pilotes Intel iHD / VA-API). Montez le nœud de rendu hôte, recréez le conteneur après un pull qui l’embarque, puis activez **Intel Quick Sync** (ou VAAPI) dans Jellyfin sous Playback → Transcoding.

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

Liste complète des ports : [Installer → Ports](../docs/REFERENCE.md#ports).

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
3. Enregistrez le profil dans **Réglages → VPN** (ou montez-le et activez-le via l’environnement), puis **recréez** le conteneur pour que WireGuard démarre au boot.

Le mode privilégié est nécessaire pour `/dev/net/tun` et le routage par uid VPN (WireGuard dans l’espace de noms réseau principal ; les apps torrent tournent sous un uid dédié). Synology a souvent besoin de **wireguard-go** fourni par l’image si l’hôte n’a pas de module WireGuard — voir [SYNOLOGY.md](SYNOLOGY.md).

### Ce qu’AIO fait tant que le VPN est actif

- Ces trois apps ne démarrent qu’après une poignée de main WireGuard live. Si le tunnel est coupé au boot, elles attendent ; AIO réessaie le VPN avec un backoff et les démarre quand il est de retour. Un **Stop** manuel du VPN annule cette reprise.
- Le DNS de ces apps passe par un petit forwarder avec cache dans AIO (`127.0.0.153`), lié à l’interface du tunnel pour que les requêtes ne fuient pas sur le WAN de la maison. Il interroge plusieurs résolveurs publics en parallèle et peut renvoyer une réponse récente si l’amont est brièvement silencieux — ce qui évite que les indexeurs Prowlarr tombent sur un seul délai. Les autres apps (Sonarr, Radarr, SABnzbd, …) gardent le résolveur du conteneur.
- Le trafic Usenet n’utilise jamais le tunnel.

---

## Reverse proxy ou Cloudflare

- **Pas de proxy nécessaire** pour le réseau local à `http://server-ip:8080`.
- Votre propre Traefik/Caddy/Nginx : définissez `AMM_TRUSTED_PROXIES` et éventuellement `AMM_ROOT_PATH`.
- **Cloudflare Tunnel** (pas de ports entrants) : [CLOUDFLARE.md](CLOUDFLARE.md).  
  `cloudflared` tourne **dans** ce conteneur — n’ajoutez pas un second service Cloudflare.
