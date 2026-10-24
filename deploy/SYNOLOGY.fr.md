# Synology

Faites tourner AIO comme **un** **projet** Container Manager. N’ajoutez pas de services supplémentaires ni de conteneurs Sonarr/Radarr/téléchargement à côté.

**Image :** `ghcr.io/qballjos/aio-media-server-manager:latest`  
Votre DSM doit pouvoir exécuter des images `linux/amd64` ou `linux/arm64`.

## Créer les dossiers et le projet (SSH)

Activez SSH (**Panneau de configuration → Terminal et SNMP → Activer le service SSH**), puis :

```bash
ssh admin@<nas-ip>
```

Le script d’installation crée `/volume1/docker/aio-media-manager` (avec `config/` et `backups/`) et un arbre de données dans le **home utilisateur DSM** (`File Station → Home → aio-media-manager` avec `downloads/` et `media/`). Ce chemin est un vrai home utilisateur, donc DSM peut le parcourir. Un dossier brut `/volume1/data` n’est pas un dossier partagé et n’apparaît pas dans File Station ; relancer le script déplace cet arbre dans le home s’il existe encore. Téléchargements et médias restent un seul bind (`/data`) pour que *Arr puisse faire des liens physiques. Les sauvegardes de config vont sur le montage `/backups` ; incluez ce dossier dans une tâche Hyper Backup, ou pointez `BACKUPS=` vers un autre volume.

Le service Home utilisateur doit être activé (Panneau de configuration → Utilisateur et groupe → Avancé). SSH en tant que l’utilisateur DSM dont le Home doit contenir les bibliothèques, ou définissez `HOME_USER=`.

```bash
id
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
```

Si SSH est `admin` mais que le Home doit appartenir à un autre utilisateur DSM :

```bash
id media
sudo HOME_USER=media PUID=1026 PGID=100 sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Autre volume ou autres chemins :

```bash
sudo VOLUME=/volume2 \
     HOME_USER=media \
     BACKUPS=/volume1/backups/aio-media-manager \
     PUID=1026 PGID=100 \
     sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Pour garder les bibliothèques sur un dossier partagé DSM au lieu du Home, mettez `DATA=` sur ce dossier (toujours un parent unique pour `downloads` et `media`) :

```bash
sudo DATA=/volume1/media/aio-media-manager \
     PUID=1026 PGID=100 \
     sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Le fichier généré est `/volume1/docker/aio-media-manager/docker-compose.yml` (pas de clé `build:` — Container Manager tire GHCR). Une copie statique se trouve dans [`synology/docker-compose.yml`](synology/docker-compose.yml).

Si GHCR est privé : `sudo docker login ghcr.io` avant de démarrer le projet.

## Importer dans Container Manager

1. Ouvrez **Container Manager → Projet → Créer**.
2. **Nom du projet :** `aio-media-manager`
3. **Chemin :** `/volume1/docker/aio-media-manager` (le même dossier que le script a utilisé).
4. **Source :** utilisez le `docker-compose.yml` **existant** (ne collez pas un second fichier Compose et n’ajoutez pas d’autres services).
5. Démarrez le projet.

L’interface doit montrer un seul service `aio-media-manager`. Ouvrez `http://<nas-ip>:8080` pour le gestionnaire. **Ouvrir l’interface** sur les cartes du catalogue utilise les ports des apps (Sonarr `8989`, Radarr `7878`, …), que le Compose du projet publie maintenant. Si vous avez généré le Compose avant ce changement, copiez la liste `ports:` de [`synology/docker-compose.yml`](synology/docker-compose.yml) dans le fichier du projet et recréez le conteneur.

Le script d’installation monte aussi `/sys` de l’hôte en lecture seule sur `/host/sys`, pour que la carte Serveur de l’accueil montre le trafic réseau du NAS. Si le Compose du projet a été généré avant cela, ajoutez `- /sys:/host/sys:ro` sous `volumes:` et recréez. Sans cette ligne, le graphique n’est que le trafic de ce conteneur. Les apps installées se mettent à jour plus tard depuis **Réglages → Mises à jour** (planifications désactivées par défaut). Recréer le projet met AIO à jour.

Pour démarrer en SSH au lieu de l’interface :

```bash
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml pull
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml up -d
```

Ensuite, Container Manager le liste encore si le chemin du projet correspond.

## Transcodage matériel

Si `/dev/dri` existe, ajoutez ce bloc sous `aio-media-manager` dans le fichier Compose du projet, puis recréez et démarrez le projet :

```yaml
    devices:
      - /dev/dri:/dev/dri
```

```bash
ls -l /dev/dri
```

## VPN (qBittorrent, Prowlarr, Flaresolverr)

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/vpn
# scp wg0.conf into that directory
```

Mettez `AMM_VPN_ENABLED=true` dans le Compose du projet, puis redémarrez le projet. Tant que le VPN est actif, Prowlarr et qBittorrent ne peuvent pas utiliser le WAN de la maison : ils ne sortent que par le tunnel, et ils restent arrêtés si le tunnel est coupé. Le noyau Synology n’a souvent pas de module WireGuard ; l’image de l’appliance inclut **wireguard-go** en repli et crée `/dev/net/tun` s’il manque. Cela ne marche que si le projet reste `privileged: true` (le script d’installation le définit). Recréez le conteneur après avoir tiré une image à jour, puis enregistrez le VPN dans **Réglages → Réseau**. OpenVPN utilise le même nœud de périphérique et a aussi besoin du mode privilégié.

## Cloudflare Tunnel

N’ajoutez pas un second service au projet. Écrivez le jeton sur le NAS, puis activez le tunnel dans **Réglages → Réseau** (conservé entre les redémarrages). Vous pouvez aussi mettre `AMM_CLOUDFLARE_TUNNEL_ENABLED=true` dans le Compose du projet. Voir [CLOUDFLARE.md](CLOUDFLARE.md).

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/cloudflare
sudo tee /volume1/docker/aio-media-manager/config/cloudflare/tunnel.token >/dev/null <<'EOF'
eyJ...paste-token...
EOF
sudo chmod 600 /volume1/docker/aio-media-manager/config/cloudflare/tunnel.token
```

## Droits

`PUID`/`PGID` dans le fichier Compose doivent correspondre au `chown` appliqué par le script. Si les apps ne peuvent pas écrire, corrigez le propriétaire en SSH plutôt que de tourner en root.
