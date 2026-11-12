# Avancé: ports et paramètres

[Guide débutant](INSTALL.md) · [Avancé](ADVANCED.md)

## Ports {#ports}

L’interface du gestionnaire utilise **8080**. Les apps enfants écoutent dans le même conteneur. Compose et les modèles NAS publient ces ports sur l’hôte pour que **Ouvrir l’interface** fonctionne (`http://YOUR-IP:8989` pour Sonarr, et ainsi de suite). Le réseau hôte est une alternative si vous ne voulez pas mapper chaque port.

| Application | Port par défaut |
|-------------|--------------|
| <img src="__AIO_ASSET__/assets/logo-aio-media-manager.png" alt="" class="aio-app-icon" /> Interface du gestionnaire | 8080 |
| <img src="__AIO_ASSET__/assets/app-icons/qbittorrent.svg" alt="" class="aio-app-icon" /> qBittorrent | 8081 |
| <img src="__AIO_ASSET__/assets/app-icons/shelfmark.png" alt="" class="aio-app-icon" /> Shelfmark | 8084 |
| <img src="__AIO_ASSET__/assets/app-icons/sabnzbd.svg" alt="" class="aio-app-icon" /> SABnzbd | 8085 |
| <img src="__AIO_ASSET__/assets/app-icons/jellyfin.svg" alt="" class="aio-app-icon" /> Jellyfin | 8096 |
| <img src="__AIO_ASSET__/assets/app-icons/flaresolverr.png" alt="" class="aio-app-icon" /> Flaresolverr | 8191 (x86_64 seulement) |
| <img src="__AIO_ASSET__/assets/app-icons/bazarr.svg" alt="" class="aio-app-icon" /> Bazarr | 6767 |
| <img src="__AIO_ASSET__/assets/app-icons/nzbget.svg" alt="" class="aio-app-icon" /> NZBGet | 6789 |
| <img src="__AIO_ASSET__/assets/app-icons/lidarr.svg" alt="" class="aio-app-icon" /> Lidarr | 8686 |
| <img src="__AIO_ASSET__/assets/app-icons/sonarr.svg" alt="" class="aio-app-icon" /> Sonarr | 8989 |
| <img src="__AIO_ASSET__/assets/app-icons/radarr.svg" alt="" class="aio-app-icon" /> Radarr | 7878 |
| <img src="__AIO_ASSET__/assets/app-icons/prowlarr.svg" alt="" class="aio-app-icon" /> Prowlarr | 9696 |
| <img src="__AIO_ASSET__/assets/app-icons/seerr.svg" alt="" class="aio-app-icon" /> Seerr | 5055 |
| <img src="__AIO_ASSET__/assets/app-icons/grimmory.svg" alt="" class="aio-app-icon" /> Grimmory | 6060 |
| <img src="__AIO_ASSET__/assets/app-icons/neutarr.svg" alt="" class="aio-app-icon" /> NeutArr | 9705 |
| <img src="__AIO_ASSET__/assets/app-icons/cleanuparr.svg" alt="" class="aio-app-icon" /> Cleanuparr | 11011 |
| <img src="__AIO_ASSET__/assets/app-icons/recyclarr.svg" alt="" class="aio-app-icon" /> Recyclarr | aucun (CLI seulement) |
| <img src="__AIO_ASSET__/assets/app-icons/plex.svg" alt="" class="aio-app-icon" /> Plex | 32400 |

## Variables d’environnement courantes

Copiez [`.env.example`](../.env.example) pour une installation native. Beaucoup peuvent aussi se régler plus tard dans **Réglages**.

| Variable | Rôle |
|----------|---------|
| `PUID` / `PGID` | Utilisateur sous lequel tournent les apps (identique au propriétaire des dossiers) |
| `TZ` / `AMM_TIMEZONE` | Fuseau pour les journaux et les planifications |
| `AMM_DOWNLOAD_DIR` / `AMM_MEDIA_DIR` | Chemins dans le conteneur (les montages hôte se changent dans Compose) |
| `GITHUB_TOKEN` | Facultatif ; limite d’API GitHub plus haute pour les mises à jour |
| `AMM_CLOUDFLARE_TUNNEL_*` | Tunnel distant facultatif (`cloudflared` démarre après les apps au boot) |
| `AMM_VPN_*` | VPN facultatif pour qBittorrent, Prowlarr et Flaresolverr (ils attendent le tunnel ; cache DNS local pour ces apps) |
| `AMM_SECURE_COOKIES` | Activer avec `true` pour HTTPS ; valeur par défaut `false` pour HTTP sur le réseau local. |
| `AMM_PREFLIGHT_MIN_FREE_MB` | Espace libre minimal en MiB par emplacement avant installation/mise à jour ; valeur par défaut `512`. |
| `AMM_BACKUP_RECOVERY_TOKEN` | Secret de récupération facultatif de l’opérateur, au moins 32 caractères, uniquement sans compte administrateur fonctionnel. À supprimer après récupération ; voir le guide de sécurité. |

- [Vérifications, sauvegardes externes et restauration](operations.md)
- [Sessions, HTTPS et récupération d’urgence](security-operations.md)
