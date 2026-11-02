# Votre première installation AIO

Inutile de connaître chaque app. Choisissez votre serveur actuel et suivez un seul guide.

!!! info "Qu’allez-vous installer ?"
    AIO gère les outils média dans **un seul conteneur**, une application empaquetée sur votre serveur. Installez AIO une fois, puis ajoutez les apps dans **AIO → Catalogue**, sans conteneurs supplémentaires pour chacune.

## 1. Choisissez votre serveur

| Serveur | Guide | Vérifiez d’abord |
|---|---|---|
| Unraid | [Unraid](deploy/UNRAID.md) | Array démarré ; pool SSD/NVMe monté |
| NAS Synology | [Synology](deploy/SYNOLOGY.md) | Container Manager installé et actif ; DSM crée le dossier docker |
| TrueNAS SCALE | [TrueNAS](deploy/TRUENAS.md) | Accès pour créer une app personnalisée et ses dossiers |
| Autre serveur Docker | [Docker](deploy/DOCKER.md) | Docker et Docker Compose actifs |
| Linux / Proxmox LXC sans Docker | [Linux](deploy/LINUX.md) | Expérience de l’administration Linux |

Exécutez les commandes sur le serveur, pas sur l’ordinateur où vous lisez cette page. Vous ouvrirez ensuite le tableau de bord sur votre ordinateur ou téléphone.

## 2. Où vont vos fichiers ?

Le guide de votre plateforme crée les bons dossiers. Ne copiez pas les chemins fictifs d’une autre plateforme.

| Dossier | Contenu | Conseil |
|---|---|---|
| Config | Réglages, comptes et bases de données | À sauvegarder |
| Téléchargements temporaires | Fichiers en cours et décompression | SSD/NVMe ; place pour téléchargement et extraction |
| Torrents terminés | Fichiers éventuellement encore partagés | HDD possible |
| Bibliothèque | Films et séries organisés | Grands HDD possibles |
| Sauvegardes | Copies des réglages | De préférence sur un autre disque |

Le **chemin hôte** est sur le NAS ; le **chemin conteneur**, comme `/data/media`, est la façon dont AIO voit ce même dossier. Il ne s’agit pas de deux bibliothèques. Téléchargements sur SSD et bibliothèque sur HDD fonctionnent ensemble ; les imports copient les fichiers. Les liens physiques exigent le même système de fichiers et ne sont pas obligatoires.

!!! tip "Gardez les valeurs par défaut au départ"
    Changez les chemins et ports seulement en cas de conflit. VPN, domaine et Cloudflare sont facultatifs et peuvent attendre.

## 3. Ouvrez AIO

Une fois le conteneur démarré, ouvrez dans votre navigateur :

```text
http://IP-DE-VOTRE-SERVEUR:8080
```

Remplacez l’IP par l’adresse de votre NAS. `http://192.168.1.50:8080` est seulement un exemple. Si vous avez changé le port hôte, utilisez votre nouveau port.

**Résultat attendu :** l’écran de création de compte AIO. Choisissez nom d’utilisateur, e-mail et mot de passe. Un écran de connexion signifie qu’un compte existe déjà : utilisez-le.

## 4. Terminez l’assistant

1. Choisissez les apps nécessaires, par exemple Jellyfin pour lire les médias et vos outils d’automatisation/téléchargement.
2. Un compte Usenet sert uniquement à un client Usenet. AIO ne fournit pas d’abonnement.
3. Vous pouvez laisser VPN et accès distant désactivés.
4. Attendez l’installation et vérifiez **Running** dans le catalogue.
5. Ouvrez l’app avec **Open UI**. Jellyfin/Plex peuvent demander leurs propres comptes et bibliothèques ; le compte AIO ne les remplace pas.

**Résultat attendu :** Home, Catalogue et Réglages, avec vos apps dans le catalogue. La première installation peut prendre du temps. En cas d’échec, consultez les logs avant de réinstaller.

## 5. Personnalisez l’accueil

[Essayez la démo visuelle des widgets](index.md#app-preview), puis le [guide du tableau de bord](USAGE.md#customize-home). Il montre le bouton de disposition, l’ajout, le déplacement et le redimensionnement. Les widgets vides attendent souvent le contenu d’une app liée.

## Si vous êtes bloqué

| Problème | Étape suivante |
|---|---|
| Le navigateur ne se connecte pas | Vérifiez AIO, l’IP et le port hôte. Testez d’abord sur le même réseau domestique. |
| Port occupé | Modifiez le côté hôte de la correspondance de port et ouvrez ce nouveau port. |
| Permission denied | Suivez les droits du guide de votre plateforme. PUID/PGID sont les identifiants numériques utilisateur/groupe utilisés par AIO. |
| Dossier docker absent sur Synology | Installez et démarrez DSM Container Manager ; ne créez pas ce dossier manuellement avant. |
| Widget vide | Vérifiez l’app liée dans le catalogue et le [guide des widgets](USAGE.md#customize-home). |
| Téléchargements lents | Vérifiez la répartition HDD/SSD du téléchargement et de l’extraction dans le guide NAS. |
| Open UI ne fonctionne pas | Vérifiez l’état de l’app et son port publié. |

## Mises à jour et accès distant

Pour AIO, récupérez la nouvelle image et recréez le conteneur avec les mêmes correspondances de dossiers ; un simple redémarrage ne suffit pas. Les apps internes se mettent à jour dans **Réglages → Updates** ; les planifications sont désactivées par défaut. Configurez [Cloudflare Tunnel](deploy/CLOUDFLARE.md) et [Access](deploy/CLOUDFLARE_ACCESS.md) après avoir vérifié le fonctionnement local.

Les tableaux suivants sont une référence, pas des éléments à apprendre par cœur.

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
