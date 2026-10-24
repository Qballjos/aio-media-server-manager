# Installer

Mettez AIO en route en trois étapes : créer les dossiers, démarrer l’app, ouvrir le tableau de bord.

!!! tip "Vous préférez un chemin court ?"
    La plupart des gens commencent par **[Docker](deploy/DOCKER.md)** ou le guide de leur NAS (**[Unraid](deploy/UNRAID.md)** · **[Synology](deploy/SYNOLOGY.md)** · **[TrueNAS](deploy/TRUENAS.md)**), puis reviennent ici pour les ports et les mises à jour.

## Avant de commencer

1. **Choisissez où ça tourne** — Unraid, Synology, TrueNAS, Docker simple ou Linux natif.
2. **Prévoyez deux sortes de stockage :**
   - **Config** — réglages et bases de données (petit, à sauvegarder)
   - **Téléchargements + médias** — les gros fichiers (gardez-les sur le **même** disque ou partage pour que les liens physiques fonctionnent)
3. **Connaissez votre identifiant utilisateur** — sous Linux/NAS, les apps tournent souvent sous un utilisateur précis (`PUID` / `PGID`). Faites-le correspondre au propriétaire des dossiers, sinon vous aurez des erreurs de droits.

Il ne vous faut **qu’un** conteneur AIO. N’installez pas Sonarr, Radarr ou les clients de téléchargement comme apps séparées à côté.

**Image :** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Architectures :** `linux/amd64`, `linux/arm64` (Flaresolverr est réservé à x86_64 et masqué sur ARM)

## Choisissez votre plateforme

| Où ça tourne | Guide |
|------------------|--------|
| Docker (n’importe quel hôte) | [Docker](deploy/DOCKER.md) |
| Unraid | [Unraid](deploy/UNRAID.md) |
| Synology | [Synology](deploy/SYNOLOGY.md) |
| TrueNAS SCALE | [TrueNAS](deploy/TRUENAS.md) |
| Debian / Ubuntu / Proxmox LXC (sans Docker) | [Linux](deploy/LINUX.md) |
| Toutes les options | [Aperçu](deploy/README.md) |

Chaque guide de plateforme commence par : ouvrir SSH → créer les dossiers → démarrer AIO.

## Dossiers sur l’hôte

Connectez-vous en SSH, puis créez quelque chose comme ceci (les chemins varient selon la plateforme — suivez votre guide) :

```bash
ssh user@host

mkdir -p "$HOME/aio-media-manager/downloads" "$HOME/aio-media-manager/media"
sudo mkdir -p /path/to/config /path/to/config/vpn /path/to/backups
id   # note uid= (PUID) and gid= (PGID)
sudo chown -R "$PUID:$PGID" "$HOME/aio-media-manager" /path/to/config /path/to/backups
```

Gardez **downloads** et **media** comme voisins sous un même dossier pour que *Arr puisse faire des liens physiques. Montez un dossier **backups** séparé sur `/backups` si vous pouvez (idéalement un autre disque que la config).

Dans ces montages, AIO dispose des bibliothèques comme `media/tv`, `media/movies` et `downloads/complete`.

## Après le démarrage

1. Ouvrez le tableau de bord : `http://YOUR-SERVER-IP:8080`  
   (Utilisez un autre port si vous en avez mappé un.)
2. Créez le compte administrateur (nom, **e-mail**, mot de passe).
3. Terminez l’assistant de première exécution, puis suivez [Utiliser le tableau de bord](USAGE.md).

Après `docker compose pull`, **recréez** le conteneur (pas seulement un redémarrage) pour que les nouveaux ports et runtimes s’appliquent. Cela met AIO à jour. Les apps installées se mettent à jour depuis **Réglages → Mises à jour** dans le tableau de bord. Ces planifications sont désactivées par défaut.

Le fichier Compose du dépôt monte `/sys` de l’hôte en lecture seule sur `/host/sys`, pour que la carte Serveur de l’accueil compte les cartes réseau du serveur. Un ancien Compose sans cette ligne ne montre que le trafic du conteneur, jusqu’à ce que vous l’ajoutiez et recréiez. Voir [Docker](deploy/DOCKER.md).

## Facultatif : atteindre les apps hors de la maison

1. [Cloudflare Tunnel](deploy/CLOUDFLARE.md) — HTTPS sans ouvrir de ports sur le routeur  
2. [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md) — une porte de connexion pour que des inconnus n’ouvrent pas les apps d’administration

## Ports {#ports}

L’interface du gestionnaire utilise **8080**. Les apps enfants écoutent dans le même conteneur. Compose et les modèles NAS publient ces ports sur l’hôte pour que **Ouvrir l’interface** fonctionne (`http://YOUR-IP:8989` pour Sonarr, et ainsi de suite). Le réseau hôte est une alternative si vous ne voulez pas mapper chaque port.

| Application | Port par défaut |
|-------------|--------------|
| <img src="../assets/logo-aio-media-manager.png" alt="" class="aio-app-icon" /> Interface du gestionnaire | 8080 |
| <img src="../assets/app-icons/qbittorrent.svg" alt="" class="aio-app-icon" /> qBittorrent | 8081 |
| <img src="../assets/app-icons/shelfmark.png" alt="" class="aio-app-icon" /> Shelfmark | 8084 |
| <img src="../assets/app-icons/sabnzbd.svg" alt="" class="aio-app-icon" /> SABnzbd | 8085 |
| <img src="../assets/app-icons/jellyfin.svg" alt="" class="aio-app-icon" /> Jellyfin | 8096 |
| <img src="../assets/app-icons/flaresolverr.png" alt="" class="aio-app-icon" /> Flaresolverr | 8191 (x86_64 seulement) |
| <img src="../assets/app-icons/bazarr.svg" alt="" class="aio-app-icon" /> Bazarr | 6767 |
| <img src="../assets/app-icons/nzbget.svg" alt="" class="aio-app-icon" /> NZBGet | 6789 |
| <img src="../assets/app-icons/lidarr.svg" alt="" class="aio-app-icon" /> Lidarr | 8686 |
| <img src="../assets/app-icons/sonarr.svg" alt="" class="aio-app-icon" /> Sonarr | 8989 |
| <img src="../assets/app-icons/radarr.svg" alt="" class="aio-app-icon" /> Radarr | 7878 |
| <img src="../assets/app-icons/prowlarr.svg" alt="" class="aio-app-icon" /> Prowlarr | 9696 |
| <img src="../assets/app-icons/seerr.svg" alt="" class="aio-app-icon" /> Seerr | 5055 |
| <img src="../assets/app-icons/grimmory.svg" alt="" class="aio-app-icon" /> Grimmory | 6060 |
| <img src="../assets/app-icons/neutarr.svg" alt="" class="aio-app-icon" /> NeutArr | 9705 |
| <img src="../assets/app-icons/recyclarr.svg" alt="" class="aio-app-icon" /> Recyclarr | aucun (CLI seulement) |
| <img src="../assets/app-icons/plex.svg" alt="" class="aio-app-icon" /> Plex | 32400 |

## Variables d’environnement courantes

Copiez [`.env.example`](../.env.example) pour une installation native. Beaucoup peuvent aussi se régler plus tard dans **Réglages**.

| Variable | Rôle |
|----------|---------|
| `PUID` / `PGID` | Utilisateur sous lequel tournent les apps (identique au propriétaire des dossiers) |
| `TZ` / `AMM_TIMEZONE` | Fuseau pour les journaux et les planifications |
| `AMM_DOWNLOAD_DIR` / `AMM_MEDIA_DIR` | Chemins dans le conteneur (les montages hôte se changent dans Compose) |
| `GITHUB_TOKEN` | Facultatif ; limite d’API GitHub plus haute pour les mises à jour |
| `AMM_CLOUDFLARE_TUNNEL_*` | Tunnel distant facultatif |
| `AMM_VPN_*` | VPN facultatif pour les apps liées au torrent |

## Si quelque chose ne va pas

- **L’interface ne s’ouvre pas** — le conteneur tourne-t-il ? Le port hôte est-il le bon ?
- **Permission refusée** — le propriétaire du dossier doit correspondre à `PUID`/`PGID`.
- **Ouvrir l’interface d’une app enfant échoue sur le LAN** — publiez le port de cette app (tableau ci-dessus) ou utilisez le réseau hôte ; les anciens fichiers Compose qui ne mappaient que `8080` doivent être mis à jour.
- **Apps en double** — retirez les conteneurs Sonarr/Radarr séparés ; seul AIO doit les faire tourner.

## Développement

Pour travailler sur le code, lancez la copie **dans Docker** (binaires Linux). Voir [Contributing](../CONTRIBUTING.md) et `./scripts/test-env.sh up`.
