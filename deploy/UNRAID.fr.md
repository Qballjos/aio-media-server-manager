# Unraid

Installez **un** conteneur AIO. N’ajoutez pas de modèles Community Applications pour Sonarr, Radarr ou les clients de téléchargement — AIO les fait tourner lui-même.

**Modèles dans ce dépôt**

| Fichier | Rôle |
|------|---------|
| [`unraid/templates/aio-media-manager.xml`](unraid/templates/aio-media-manager.xml) | Modèle Docker (ports, chemins, env) |
| [`unraid/ca_profile.xml`](unraid/ca_profile.xml) | Profil du mainteneur Community Applications |
| [`unraid.xml`](unraid.xml) | Ancien chemin du même modèle (compatibilité) |

## Créer les dossiers en SSH

Activez SSH (**Settings → Management Access**), puis :

```bash
ssh root@<unraid-ip>
```

Les téléchargements et les médias vivent sur le **partage utilisateur** `aio-media-manager` (visible dans Shares / le navigateur de fichiers). La config reste dans appdata.

```bash
mkdir -p \
  /mnt/user/appdata/aio-media-manager/vpn \
  /mnt/user/backups/aio-media-manager \
  /mnt/user/aio-media-manager/downloads \
  /mnt/user/aio-media-manager/media

chown -R 99:100 \
  /mnt/user/appdata/aio-media-manager \
  /mnt/user/backups/aio-media-manager \
  /mnt/user/aio-media-manager
```

`/mnt/user/backups/aio-media-manager` reçoit les sauvegardes de configuration. Utilisez un partage qui vit sur l’array (pas seulement le pool de cache), pour qu’une panne de cache n’emporte pas les sauvegardes.

Séries, films, anime, musique, livres, bandes dessinées, téléchargements complets/incomplets, dossiers de catégories torrent et caches de transcodage sont créés dans ces montages au premier démarrage.

`99:100` est Unraid `nobody`/`users` (PUID 99, PGID 100). Si vous utilisez un utilisateur de partage personnalisé, lancez `id thatuser` et `chown` vers cet UID:GID.

Pour les liens physiques, gardez téléchargements et médias comme sous-dossiers d’**un** chemin de cache ou de disque (pas deux partages FUSE `/mnt/user`), par exemple un partage cache-only nommé `aio-media-manager` :

```bash
mkdir -p /mnt/cache/aio-media-manager/downloads /mnt/cache/aio-media-manager/media
chown -R 99:100 /mnt/cache/aio-media-manager
```

Liez ensuite `/data` à `/mnt/cache/aio-media-manager` (le même partage, chemin disque) au lieu de `/mnt/user/aio-media-manager`.

## Installer depuis le modèle (votre serveur)

### Option A — modèle utilisateur local

1. Copiez le XML sur la clé USB :

   ```bash
   mkdir -p /boot/config/plugins/dockerMan/templates-user
   curl -fsSL \
     -o /boot/config/plugins/dockerMan/templates-user/my-aio-media-manager.xml \
     https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/templates/aio-media-manager.xml
   ```

2. Docker → **Add Container** → choisissez **aio-media-manager** (ou `my-aio-media-manager`) dans la liste Template.
3. Confirmez les chemins, `PUID`/`PGID` et `TZ`, puis Apply.
4. Ouvrez `http://<unraid-ip>:8080` et suivez l’assistant.

### Option B — Add Container à la main

1. Docker → Add Container → vue avancée.
2. Repository : `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Network : `bridge` (ou `host` si vous voulez chaque WebUI d’app sur l’IP Unraid).
4. Privileged : **On** (nécessaire pour l’isolation VPN de qBittorrent / Prowlarr / Flaresolverr). Avec le VPN activé, ces apps attendent une poignée de main WireGuard live ; AIO met leur DNS en cache via le tunnel pour qu’un court trou ne coupe pas les indexeurs Prowlarr. Détails : [DOCKER.md](DOCKER.md#vpn-facultatif).
5. Extra parameters : `--cap-add=NET_ADMIN --cap-add=SYS_MODULE`
6. Périphérique facultatif : `/dev/dri` pour le transcodage Intel/AMD (à omettre s’il manque).
7. Ports (TCP) : publiez **8080** pour le gestionnaire et les WebUI enfants installées (Sonarr **8989**, Radarr **7878**, qBittorrent **8081**, SABnzbd **8085**, Jellyfin **8096**, Prowlarr **9696**, Seerr **5055**, Plex **32400**, …). Liste complète : [INSTALL.md](../docs/INSTALL.md#ports). Ou Network `host`.
8. Chemins :
   - `/config` → `/mnt/user/appdata/aio-media-manager`
   - `/data` → `/mnt/user/aio-media-manager`
   - `/backups` → `/mnt/user/backups/aio-media-manager`
   - `/host/sys` → `/sys` (lecture seule). La carte Serveur de l’accueil montre alors le trafic réseau du serveur. Le modèle appelle cela **Host sys** (avancé). Sans cette ligne, le graphique n’est que le trafic de ce conteneur.
9. Variables : `PUID=99`, `PGID=100`, `TZ=<IANA timezone>`, `AMM_DOWNLOAD_DIR=/data/downloads`, `AMM_MEDIA_DIR=/data/media`. Facultatif : `GITHUB_TOKEN`.

Après la mise à jour de l’image, recréez le conteneur pour que les nouveaux mappages de ports WebUI s’appliquent.

## Publier sur Community Applications (boutique publique)

Community Apps n’héberge **pas** vos fichiers. Vous gardez un dépôt GitHub public avec les modèles ; le scanner CA de Lime Technology l’indexe après votre soumission.

### 1. Préparer un dépôt de modèles

Recommandé : un **dépôt public dédié** (par exemple `Qballjos/unraid-templates`) dont la racine ressemble à :

```text
ca_profile.xml
templates/aio-media-manager.xml
```

Copiez depuis ce projet :

```bash
# from a clone of aio-media-server-manager
mkdir -p ../unraid-templates/templates
cp deploy/unraid/ca_profile.xml ../unraid-templates/
cp deploy/unraid/templates/aio-media-manager.xml ../unraid-templates/templates/
```

Puis :

1. Créez le dépôt GitHub public et poussez `main`.
2. Modifiez `templates/aio-media-manager.xml` et mettez `<TemplateURL>` sur l’URL **raw** de ce fichier dans le nouveau dépôt (elle doit correspondre au vrai chemin sur `main`).
3. Gardez `<Repository>` à `ghcr.io/qballjos/aio-media-server-manager:latest` (l’image reste sur GHCR ; seul le XML du modèle vit dans le dépôt de modèles).
4. Facultatif : ouvrez un fil d’assistance sur le forum Unraid et mettez son URL dans `ca_profile.xml` à `<Forum>` et dans les balises `<Support>` du modèle (GitHub Issues convient pour commencer).

Vous *pouvez* soumettre le dépôt principal de l’app à la place si le XML est découvrable et que chaque app a une balise `<Repository>`, mais un petit dépôt de modèles dédié est ce que les mainteneurs CA attendent en général.

### 2. Soumettre

1. Connectez-vous sur **[https://ca.unraid.net/submit](https://ca.unraid.net/submit)** avec votre compte Unraid / forum.
2. Enregistrez l’**URL du dépôt GitHub** (le dépôt de modèles).
3. Lancez **Validate**, puis **Scan**. Corrigez les problèmes XML signalés.
4. Attendez la modération. Une fois approuvée, l’app apparaît sous l’onglet Apps pour tout le monde.

Docs utiles :

- [Submission help](https://ca.unraid.net/submit/help)
- [Repository XML format](https://ca.unraid.net/submit/help/repository-xml)
- [XML field reference](https://ca.unraid.net/submit/help/xml-field-reference)
- [Browse catalog](https://ca.unraid.net/apps) (vérifiez d’abord les collisions de noms)

N’utilisez **pas** le flux de demande retiré `selfhosters/unRAID-CA-templates`.

### 3. Une fois listée

- Livrez les mises à jour en publiant une nouvelle image de conteneur (`:latest` ou des tags semver). Les utilisateurs mettent à jour via la mise à jour Docker d’Unraid — vous n’avez en général **pas** à faire avancer le modèle à chaque version.
- Ne changez le XML du modèle que lorsque les ports, les chemins ou les variables d’environnement changent ; CA relit `<TemplateURL>` au rafraîchissement.

### Privé / pour soi seulement (pas la boutique publique)

Pour utiliser vos propres modèles GitHub sans approbation CA, ajoutez l’URL du dépôt à :

```text
/boot/config/plugins/dockerMan/template-repos
```

(une URL par ligne). Les modèles apparaissent alors sous Docker → Add Container. Cela ne liste **pas** l’app dans le catalogue public Community Applications.

## FUSE / liens physiques

Préférez `/mnt/cache/aio-media-manager` ou un seul chemin de disque pour les téléchargements et les médias si les liens physiques comptent. Mélanger `/mnt/user` (FUSE) et un partage disque peut casser les déplacements atomiques.

## Mises à jour

Changez le tag du dépôt ou utilisez la mise à jour de conteneur d’Unraid, puis recréez pour que les nouveaux ports et le montage Host sys s’appliquent. Les images sont publiées depuis `main` en `:latest` et depuis les tags git en semver. Cela met AIO à jour. Les apps installées se mettent à jour depuis **Réglages → Mises à jour** (planifications désactivées par défaut).
