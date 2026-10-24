---
hide:
  - navigation
  - toc
title: AIO Media Server Manager
---

<div class="aio-hero" markdown>

<div class="aio-hero__brand" markdown>
<img src="assets/logo-aio-media-manager.png" alt="" width="40" height="40" />
AIO Media Server Manager
</div>

# Toute votre pile média. Une installation.

<p class="aio-hero__lead">
Téléchargements, apps *Arr et lecture — depuis un seul tableau de bord.
Pas de fichier Compose rempli de conteneurs Sonarr, Radarr et qBittorrent.
</p>

<div class="aio-hero__actions" markdown>

[Installer maintenant](INSTALL.md){ .md-button .md-button--primary }
[Utiliser le tableau de bord](USAGE.md){ .md-button }
[GitHub](https://github.com/Qballjos/aio-media-server-manager){ .md-button }

</div>
</div>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Connexion administrateur, thème clair](screenshots/light/login.png)

</div>

<div class="aio-shot" markdown>

![Connexion administrateur, thème sombre](screenshots/dark/login.png)

</div>

</div>

<p class="aio-shot-caption">Connexion — clair et sombre.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Accueil avant l’installation d’applications, thème clair](screenshots/light/dashboard.png)

</div>

<div class="aio-shot" markdown>

![Accueil avant l’installation d’applications, thème sombre](screenshots/dark/dashboard.png)

</div>

</div>

<p class="aio-shot-caption">Accueil avant l’installation d’apps avec une interface web.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Catalogue avec cartes d’apps et commandes d’installation, thème clair](screenshots/light/catalog.png)

</div>

<div class="aio-shot" markdown>

![Catalogue avec cartes d’apps et commandes d’installation, thème sombre](screenshots/dark/catalog.png)

</div>

</div>

<p class="aio-shot-caption">Catalogue — recherche, filtres et installation.</p>

<div class="aio-pair" markdown>

<div class="aio-shot" markdown>

![Page Compte des réglages, thème clair](screenshots/light/settings.png)

</div>

<div class="aio-shot" markdown>

![Page Compte des réglages, thème sombre](screenshots/dark/settings.png)

</div>

</div>

<p class="aio-shot-caption">Réglages. L’apparence, les réglages des apps et les autres sections sont dans <a href="USAGE.md#screens">Utiliser le tableau de bord</a>.</p>

## Commencez là où vous en êtes

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __Nouveau ici__

    ---

    Créez les dossiers, démarrez le conteneur, ouvrez l’interface.

    [:octicons-arrow-right-24: Guide d’installation](INSTALL.md)

-   :material-view-dashboard-outline:{ .lg .middle } __Déjà en marche__

    ---

    Accueil, Catalogue et Ouvrir l’interface de chaque app.

    [:octicons-arrow-right-24: Utiliser le tableau de bord](USAGE.md)

-   :material-docker:{ .lg .middle } __Hôte Docker__

    ---

    Le chemin habituel pour les NAS et les serveurs Linux.

    [:octicons-arrow-right-24: Guide Docker](deploy/DOCKER.md)

-   :material-cloud-lock-outline:{ .lg .middle } __Loin de la maison__

    ---

    HTTPS via Cloudflare Tunnel, puis une porte de connexion avec Access.

    [:octicons-arrow-right-24: Accès distant](deploy/CLOUDFLARE.md)

</div>

## Choisissez votre plateforme

<div class="grid cards" markdown>

-   :material-nas:{ .lg .middle } __Unraid__

    ---

    Un conteneur dans l’esprit de Community Applications.

    [Guide Unraid](deploy/UNRAID.md)

-   :material-server:{ .lg .middle } __Synology__

    ---

    Un projet Container Manager.

    [Guide Synology](deploy/SYNOLOGY.md)

-   :material-harddisk:{ .lg .middle } __TrueNAS__

    ---

    Une app personnalisée sur SCALE.

    [Guide TrueNAS](deploy/TRUENAS.md)

-   :material-linux:{ .lg .middle } __Linux / LXC__

    ---

    Installation native sans Docker.

    [Guide Linux](deploy/LINUX.md)

</div>

## Ce que vous obtenez

<div class="grid cards" markdown>

-   :material-monitor-dashboard:{ .lg .middle } __Un tableau de bord__

    ---

    L’accueil pour ce qui est nouveau, en lecture ou à surveiller. Le catalogue pour installer, démarrer/arrêter et **Ouvrir l’interface**.

-   :material-television-play:{ .lg .middle } __Automatisation + bibliothèques__

    ---

    Sonarr, Radarr, Lidarr et Bazarr — quand vous les voulez.

-   :material-download:{ .lg .middle } __Téléchargements__

    ---

    Clients torrent et Usenet, VPN facultatif sur le chemin de téléchargement.

-   :material-cast:{ .lg .middle } __Regarder et demander__

    ---

    Jellyfin, Plex et Seerr — le même appareil.

</div>

<div class="aio-callout" markdown>

**La seule règle :** une installation AIO = un conteneur (ou un service natif).  
N’ajoutez pas de conteneurs Sonarr, Radarr ou qBittorrent à côté.

</div>

## Usage prévu

AIO est un outil de gestion auto-hébergé pour une bibliothèque média personnelle et un homelab :

- Des fichiers qui vous appartiennent (vidéos maison, photos de famille, domaine public, ou vos propres sauvegardes de médias physiques).
- La configuration du réseau local et l’administration du serveur.

Ce dépôt n’héberge ni ne distribue de contenu protégé. Ce n’est ni une licence ni un bouclier juridique. L’utiliser pour obtenir, télécharger, diffuser ou partager du matériel protégé sans autorisation enfreint le droit d’auteur dans la plupart des endroits. Vous êtes responsable des lois là où vous vivez.

## Vibe coded

**Oui — cette app a été vibe coded.**  
Elle a été construite avec de la programmation en binôme avec une IA dans Cursor, guidée par un humain qui voulait une pile média complète sans surveiller douze conteneurs. C’est voulu, pas un secret.

Si quelque chose est encore rugueux, ouvrez une issue ou une PR. Les vibes s’améliorent avec les retours.

## Image

```text
ghcr.io/qballjos/aio-media-server-manager:latest
```

Fonctionne sur `linux/amd64` et `linux/arm64`. Après un pull, recréez le conteneur pour que les nouveaux ports et runtimes s’appliquent.
