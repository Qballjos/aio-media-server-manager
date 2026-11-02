# Déployer

AIO est prévu pour tourner comme **une** installation — en général **un conteneur Docker**.  
N’ajoutez pas de service Compose séparé pour Sonarr, Radarr ou chaque client de téléchargement.

**Site de documentation :** [qballjos.github.io/aio-media-server-manager](https://qballjos.github.io/aio-media-server-manager/)  
**Image :** [`ghcr.io/qballjos/aio-media-server-manager`](https://github.com/Qballjos/aio-media-server-manager/pkgs/container/aio-media-server-manager)

| J’utilise… | Guide |
|-------------|--------|
| Docker / Compose (la plupart des gens) | [DOCKER.md](DOCKER.md) |
| Unraid | [UNRAID.md](UNRAID.md) · modèles dans [`unraid/`](unraid/) |
| Synology Container Manager | [SYNOLOGY.md](SYNOLOGY.md) · [`synology/`](synology/) |
| TrueNAS SCALE | [TRUENAS.md](TRUENAS.md) |
| Linux / LXC sans Docker | [LINUX.md](LINUX.md) |
| Accès distant (facultatif) | [CLOUDFLARE.md](CLOUDFLARE.md) |
| Porte de connexion sur les URL publiques | [CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md) |

Vue d’une nouvelle installation : [Installer](../docs/INSTALL.md) · une fois lancé : [Utiliser le tableau de bord](../docs/USAGE.md)

**Astuce :** Après avoir tiré une nouvelle image, **recréez** le conteneur pour que les ports et runtimes à jour s’appliquent. Un simple redémarrage ne suffit pas.
