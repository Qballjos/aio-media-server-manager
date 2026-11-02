# Docker sur Linux : AIO pas à pas

Cette route utilise un **serveur Linux avec Docker fonctionnel**. Sur Unraid, Synology ou TrueNAS, choisissez [votre plateforme](README.md) sans cumuler les deux installations.

## Avant de commencer

- Linux avec Docker, Docker Compose et Git ; [installer Docker](https://docs.docker.com/engine/install/) d’abord si nécessaire.
- Un compte autorisé à utiliser Docker.
- Un ordinateur sur le même réseau.

## 1. Ouvrir le terminal du serveur

Sur le serveur, ouvrez Terminal. À distance, utilisez Terminal ou Windows Terminal avec `ssh UTILISATEUR@IP-DU-SERVEUR`, en remplaçant les deux valeurs. Les blocs suivants s’exécutent ensuite sur le serveur.

```bash
docker info
docker compose version
git --version
```

**Vérification :** Docker affiche des informations serveur et Compose/Git leurs versions. En cas de command not found ou permission denied, réglez d’abord installation et accès.

## 2. Préparer les fichiers AIO

Dans le même terminal :

Un dossier aio-media-server-manager existe déjà ici ? Ne lancez pas ce bloc ; conservez-le et utilisez [Avancé](DOCKER_ADVANCED.md). Chaque ligne ne s’exécute que si la précédente réussit.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git &&
cd aio-media-server-manager &&
export AMM_DATA_HOST="${HOME}/aio-media-manager" &&
mkdir -p config/vpn backups "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media" &&
sed -i -e "s/PUID: \"1000\"/PUID: \"$(id -u)\"/" -e "s/PGID: \"1000\"/PGID: \"$(id -g)\"/" docker-compose.yml
```

Ce bloc télécharge le projet, crée les dossiers et choisit automatiquement votre compte Linux pour AIO. Aucun identifiant numérique à chercher ni fichier à modifier.

**Vérification :** aucune erreur ; vous êtes dans aio-media-server-manager avec docker-compose.yml. Gardez ce dossier : config contient les réglages, backups leurs sauvegardes. Les médias sont séparés dans aio-media-manager de votre dossier personnel. Si le projet existe déjà, ne le supprimez pas ; consultez Avancé.

## 3. Démarrer AIO

Dans le même dossier de projet :

```bash
docker compose pull
docker compose up -d
docker compose ps
```

La première ligne télécharge le logiciel, la deuxième le démarre en arrière-plan, la troisième affiche son état.

**Vérification :** un conteneur aio-media-manager affiche Up ou Running. Fermer le terminal ensuite ne l’arrête pas.

## 4. Ouvrir le tableau de bord

Ouvrez **http://IP-DU-SERVEUR:8080** avec la vraie adresse de votre serveur Linux.

**Vérification :** créez le compte administrateur et choisissez les apps dans l’assistant. Ne les installez pas aussi dans des conteneurs séparés.

Ensuite : [découvrir le tableau de bord](../docs/USAGE.md).

## En cas de problème

| Problème | Étape suivante |
|---|---|
| Erreur de droits Docker | Réglez l’accès Docker de votre hôte ; ne passez pas toutes les commandes en root au hasard. |
| Projet déjà présent | Conservez-le et suivez les installations existantes dans Avancé. |
| Erreur au démarrage | Dans le dossier du projet, lancez docker compose logs --tail=100 et gardez le message. |
| Navigateur bloqué | Vérifiez docker compose ps, l’IP du serveur et :8080 sur le réseau local. |

## Avancé

Pour d’autres emplacements, les options SSD, les installations existantes et les réglages techniques : [DOCKER — Avancé](DOCKER_ADVANCED.md).
