# TrueNAS SCALE

Déployez AIO comme **une** custom app / installation Docker. N’installez pas aussi Sonarr, Radarr ou les clients de téléchargement comme apps SCALE séparées si vous voulez ce modèle tout-en-un.

**Image :** `ghcr.io/qballjos/aio-media-server-manager:latest`

## Créer les datasets et les dossiers (SSH)

Activez SSH (**System → Services → SSH**), puis :

```bash
ssh admin@<truenas-ip>
```

Remplacez `tank` par le nom de votre pool. La config reste sur un dataset d’apps. **Les téléchargements et les médias vont dans le home de l’utilisateur connecté**, pour que l’interface Files puisse les parcourir (`~/aio-media-manager`). Gardez les deux comme dossiers sur le **même** dataset pour que *Arr puisse faire des liens physiques.

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

`tank/backups/aio-media-manager` contient les sauvegardes de configuration. Un dataset séparé se snapshotte ou se réplique selon son propre calendrier. Mettez-le sur un autre pool si vous en avez un.

Séries, films, anime, musique, livres, bandes dessinées, téléchargements complets/incomplets, dossiers de catégories torrent et caches de transcodage sont créés dans ces montages au premier démarrage.

Mettez le propriétaire sur votre utilisateur média (TrueNAS `apps` est souvent UID/GID `568` ; vérifiez avec `id apps` ou `id`) :

```bash
id apps
sudo chown -R 568:568 \
  /mnt/tank/apps/aio-media-manager \
  "${DATA}" \
  /mnt/tank/backups/aio-media-manager
```

Si le home utilisateur n’est pas activé, créez-le sous Credentials → Users, ou mettez `DATA` sur un dossier visible dans **Files** (toujours un parent unique pour `downloads` et `media`).

## Custom App

1. **Apps → Discover → Custom App** (ou Launch Docker Image).
2. Image : `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Redirection de ports : `8080` → `8080` plus les ports WebUI des apps enfants de [INSTALL.md](../docs/INSTALL.md#ports) (ou réseau hôte).
4. Stockage (chemins des commandes SSH ci-dessus) :
   - `/mnt/tank/apps/aio-media-manager` → `/config`
   - `$HOME/aio-media-manager` → `/data`
   - `/mnt/tank/backups/aio-media-manager` → `/backups`
   - `/sys` → `/host/sys` (lecture seule), pour que la carte Serveur de l’accueil montre le trafic réseau du serveur. Sans ce montage, le graphique n’est que le trafic de ce conteneur.
5. Environnement : `PUID` / `PGID` = l’UID/GID utilisé avec `chown`, plus `TZ`, `AMM_DOWNLOAD_DIR=/data/downloads` et `AMM_MEDIA_DIR=/data/media`. `GITHUB_TOKEN` facultatif pour la limite GitHub (ou Réglages → Mises à jour après la première exécution).
6. Privileged / `NET_ADMIN` si vous activez le VPN qBittorrent.
7. GPU : passez `/dev/dri` (Intel/AMD) ou le runtime NVIDIA pour le transcodage.

L’interface du gestionnaire est `http://<truenas-ip>:8080`. Recréez la custom app après une mise à jour d’image pour que les ports nouvellement publiés s’appliquent.

## Mises à jour

TrueNAS tire un `:latest` plus récent quand vous mettez l’app à jour. Épinglez un tag semver (`:0.1.0`) si vous voulez des mises à jour plus lentes une fois que des tags git existent. Cela met AIO à jour. Les apps installées se mettent à jour depuis **Réglages → Mises à jour** (planifications désactivées par défaut).
