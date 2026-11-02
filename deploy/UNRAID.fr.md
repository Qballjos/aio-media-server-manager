# Unraid : installer AIO pas à pas

Vous créez un conteneur AIO. Cette route utilise le pool SSD **cache** pour les téléchargements ; la bibliothèque reste sur les disques habituels.

## Avant de commencer

- Accès à l’interface web Unraid.
- Array démarré et Docker activé.
- Pool SSD/NVMe actif nommé cache, avec de la place. Un pool est un groupe de disques nommé dans Unraid.

## 1. Vérifier le serveur

Ouvrez **Main**, vérifiez l’array et le pool cache. Sans SSD ou avec un autre nom, utilisez [Avancé](UNRAID_ADVANCED.md). Ne devinez pas les chemins et ne formatez pas de disque pour suivre le guide.

**Vérification :** cache est actif et l’onglet Docker existe ; sinon vérifiez Settings → Docker → Enable Docker.

## 2. Ouvrir le terminal Unraid

Cliquez sur **>_** dans la barre du haut. Ce terminal est déjà sur le serveur ; pas besoin de SSH depuis votre ordinateur. Collez le bloc et appuyez sur Entrée :

```bash
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/install.sh | sh
```

Il prépare les dossiers et le modèle, pas des conteneurs média séparés.

**Vérification :** Unraid template ready apparaît. Si des téléchargements existent déjà, arrêtez-vous et lisez le guide avancé avant de changer les dossiers.

## 3. Ajouter le conteneur

Ouvrez **Docker → Add Container**. Choisissez my-aio-media-manager ou aio-media-manager dans Template. Gardez les chemins, PUID 99 et PGID 100, les identifiants prévus pour cette installation. Choisissez votre TZ, par exemple Europe/Paris, puis Apply.

**Vérification :** un conteneur aio-media-manager est actif.

## 4. Vérifier le stockage

Dans **Shares → aio-download-cache**, Primary storage doit être cache et Secondary storage None. Les anciennes versions affichent Use cache pool: Only. Si c’est correct, ne changez rien.

**Vérification :** Mover ne déplace pas les fichiers de travail vers l’array. Bibliothèque et torrents terminés restent sur l’array.

## 5. Ouvrir AIO

Sur l’icône du conteneur, choisissez WebUI, ou ouvrez http://IP-DU-SERVEUR:8080 avec votre adresse.

**Vérification :** créez le compte administrateur et choisissez vos apps dans AIO, sans les installer aussi via Unraid Apps.

Ensuite : [découvrir le tableau de bord](../docs/USAGE.md).

## 6. Copier votre premier film

Utilisez votre compte fichiers Unraid existant ou créez un utilisateur normal avec mot de passe dans **Users → Add User**. N’utilisez pas root pour le partage.

1. Dans **Shares → aio-media-manager → SMB Security Settings**, choisissez Export Yes, Security Private et donnez lecture/écriture à votre utilisateur fichiers. Ne donnez pas accès aux autres sans le vouloir.
2. Dans l’Explorateur Windows ouvrez `\\IP-DU-SERVEUR\aio-media-manager`. Sur Mac : Finder → Aller → Se connecter au serveur avec `smb://IP-DU-SERVEUR/aio-media-manager`. Utilisez la vraie IP.
3. Connectez-vous avec le compte fichiers et copiez un film que vous possédez dans media → movies.

**Vérification :** le fichier est sur le serveur. Ensuite [première lecture](../docs/USAGE.md#first-media).

## En cas de problème

| Problème | Étape suivante |
|---|---|
| Modèle absent | Vérifiez Unraid template ready puis actualisez Docker. |
| Pool absent ou différent | Utilisez Avancé pour un autre pool ou une installation HDD. |
| AIO ne s’ouvre pas | Vérifiez état et IP ; les conflits de port sont expliqués dans Avancé. |

## Avancé

Pour d’autres emplacements, les options SSD, les installations existantes et les réglages techniques : [UNRAID — Avancé](UNRAID_ADVANCED.md).

[Aide officielle du produit: Unraid](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/).
