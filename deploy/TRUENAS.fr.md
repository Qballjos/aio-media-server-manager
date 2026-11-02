# TrueNAS : AIO pas à pas

Cette route utilise le **formulaire Custom App** à partir de TrueNAS SCALE 24.10. Commencez avec AIO et Jellyfin ; les autres apps et ports viendront ensuite.

## Avant de commencer

- Droits pour gérer apps et stockage dans TrueNAS.
- Un pool existant : ne créez ni ne formatez un pool simplement pour installer AIO.
- Stockage Apps déjà configuré ; terminez d’abord la sélection initiale du pool si demandée.

## 1. Créer trois dossiers AIO

Dans **Datasets**, choisissez votre pool existant. Utilisez **Add Dataset** pour aio-config, aio-data et aio-backups. Un dataset est ici un dossier de stockage géré par TrueNAS.

Notez les chemins complets affichés. Avec un pool media, ce serait par exemple /mnt/media/aio-config ; utilisez votre propre nom de pool.

**Vérification :** trois nouveaux datasets, sans reprendre des dossiers contenant d’autres données.

## 2. Noter le compte de l’app

Dans **Credentials → Local Users / Users**, trouvez apps et notez ses numéros utilisateur/groupe, souvent 568, mais utilisez vos valeurs. Ce sont des identifiants pour les dossiers, pas des mots de passe.

**Vérification :** deux numéros notés. Les accès se règlent dans le formulaire plus bas, pas sur tout le pool.

## 3. Ouvrir le formulaire

Choisissez **Apps → Discover Apps → Custom App**, avec le formulaire normal, pas Install via YAML.

| Champ | Valeur |
|---|---|
| Application name | aio-media-manager |
| Image repository | ghcr.io/qballjos/aio-media-server-manager |
| Image tag | latest |

**Vérification :** ne rajoutez pas :latest au dépôt quand le tag a son propre champ.

## 4. Relier les dossiers

Sous **Storage → Host Path**, ajoutez trois correspondances modifiables :

| Vrai chemin NAS | Mount path dans AIO |
|---|---|
| Votre chemin aio-config | /config |
| Votre chemin aio-data | /data |
| Votre chemin aio-backups | /backups |

Gardez les correspondances modifiables. Pour chacun des trois **Host Path**, cochez **Enable ACL**, puis **Add** dans ACL Entries, **ID Type = User**, le numéro utilisateur apps dans **ID**, et **Access = Full Control**. Appliquez seulement aux trois nouveaux datasets. ACL est la liste des comptes autorisés. Si ces champs manquent, suivez d’abord l’aide TrueNAS de votre version.

**Vérification :** trois chemins NAS distincts avec exactement /config, /data et /backups.

## 5. Entrer les réglages de base

Ajoutez dans Environment variables :

| Nom | Valeur |
|---|---|
| PUID | Numéro utilisateur apps noté |
| PGID | Numéro groupe apps noté |
| AMM_DOWNLOAD_DIR | /data/downloads |
| AMM_MEDIA_DIR | /data/media |

Dans Port forwarding, ajoutez TCP **8080 vers 8080** pour AIO et **8096 vers 8096** pour Jellyfin. Laissez VPN/GPU et extras de côté.

**Vérification :** deux ports configurés. Si un port est occupé, lisez Avancé plutôt que choisir au hasard.

## 6. Installer et ouvrir AIO

Cliquez Install, attendez Running, puis ouvrez **http://IP-TRUENAS:8080** avec votre adresse. Le bouton WebUI n’existe pas dans toutes les variantes.

**Vérification :** créez le compte administrateur, sélectionnez d’abord seulement Jellyfin et ouvrez-le dans AIO. Ajoutez les autres apps plus tard avec leurs ports dans la référence avancée.

Ensuite : [découvrir le tableau de bord](../docs/USAGE.md).

## 7. Accéder aux médias depuis l’ordinateur

La copie d’un premier film demande un accès fichiers. Utilisez un compte de partage TrueNAS normal, pas root/apps. Créez-le si nécessaire dans **Credentials → Users → Add**, avec mot de passe et authentification SMB.

1. Dans **Datasets → aio-data → Permissions → Edit ACL**, ajoutez votre utilisateur fichiers avec **Modify** et héritage vers fichiers/sous-dossiers. Gardez l’accès apps existant ; ne remplacez pas toute la liste. En enregistrant, cochez **Apply permissions recursively** pour appliquer cet accès aussi aux sous-dossiers existants. Modifiez seulement aio-data.
2. Dans **Shares → Windows (SMB) Shares → Add**, choisissez le vrai chemin aio-data, nommez le partage **aio-media** et enregistrez. Démarrez SMB si demandé.
3. Dans l’Explorateur Windows, ouvrez `\\IP-TRUENAS\aio-media`, pas dans le navigateur. Sur Mac, **Finder → Aller → Se connecter au serveur** et `smb://IP-TRUENAS/aio-media`. Utilisez votre IP et compte fichiers.
4. Copiez un film que vous possédez dans media → movies. AIO crée ces sous-dossiers au démarrage. Ne partagez pas config et backups.

**Vérification :** le film est visible sur le NAS. Continuez avec [la première lecture](../docs/USAGE.md#first-media).


## En cas de problème

| Problème | Étape suivante |
|---|---|
| Formulaire différent | Vérifiez la version : cette route concerne les apps Docker depuis 24.10. Consultez l’aide officielle ou Avancé. |
| Permission denied | Vérifiez les trois datasets AIO et apps, pas le pool entier. |
| AIO ne s’ouvre pas | Vérifiez l’IP TrueNAS, :8080 et la correspondance du port. |
| Autre app inaccessible | Cette route publie seulement AIO/Jellyfin ; ajoutez les ports nécessaires via Avancé. |

## Avancé

Pour d’autres emplacements, les options SSD, les installations existantes et les réglages techniques : [TRUENAS — Avancé](TRUENAS_ADVANCED.md).

[Aide officielle du produit: TrueNAS](https://www.truenas.com/docs/scale/25.04/scaleuireference/apps/installcustomappscreens/).

[TrueNAS: app storage and folder access](https://apps.truenas.com/getting-started/app-storage/).
