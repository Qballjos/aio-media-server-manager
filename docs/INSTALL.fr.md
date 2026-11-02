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
| Linux / Proxmox LXC sans Docker | [Linux](ADVANCED.md) | Expérience de l’administration Linux |

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

Téléchargements SSD et bibliothèque HDD fonctionnent ensemble. Suivez les dossiers du guide ; le stockage personnalisé est expliqué dans Avancé.

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

La référence technique se trouve séparément dans Avancé.

## Avancé

Ces pages concernent les réglages personnalisés et le dépannage technique. Ce ne sont pas des étapes obligatoires après l’installation. [Avancé](ADVANCED.md).

### Ports et variables de configuration {#ports}

[Ports et variables de configuration](REFERENCE.md#ports).
