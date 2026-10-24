# Utiliser le tableau de bord

Ce guide s’adresse à vous une fois AIO installé et l’interface web ouverte.

!!! success "But"
    Terminez l’assistant pour les apps dont vous avez besoin, utilisez Accueil au quotidien, et **Ouvrir l’interface** dans le catalogue quand vous voulez l’écran de cet outil.

Adresse par défaut sur votre réseau local :

```text
http://YOUR-SERVER-IP:8080
```

Remplacez l’IP (et le port, si vous l’avez changé).

---

## Première fois

1. Créez le compte **administrateur** quand on vous le demande (nom, **e-mail**, mot de passe).
2. Terminez l’assistant de première exécution : les apps voulues, un serveur Usenet si vous en utilisez un, un VPN facultatif et un Cloudflare Tunnel facultatif. L’assistant installe ce choix. Le tunnel et le VPN démarrent dès que l’assistant est fini, si vous les avez activés.
3. Attendez que **Catalogue** affiche ces apps comme **actives**. Utilisez **Ouvrir l’interface** pour tout ce qui a encore un compte propre (Plex, Jellyfin, NZBGet).
4. Ajoutez-en plus tard depuis **Catalogue**. Vous n’avez pas besoin de chaque app.

Commencez petit (par exemple Radarr + un client de téléchargement + Jellyfin), puis ajoutez le reste.

---

## Accueil

Accueil est une grille. Téléphone, tablette et bureau gardent chacun leur disposition (4, 8 et 12 colonnes). Le bouton de disposition sur l’onglet Accueil déplace, agrandit, ajoute et retire des widgets. **Réglages → Page d’accueil** affiche ou masque la barre d’apps, règle le texte de connexion et enregistre une clé d’API Jellyfin ou Seerr si Accueil ne peut pas la lire seul.

| Widget | Ce qu’il montre |
|--------|----------------|
| Salutation | Moment de la journée |
| Recherche | Recherche dans Seerr |
| Calendrier | Épisodes et films à venir. Une saison qui commence le même jour tient sur une ligne |
| Téléchargements | Téléchargements actifs, avec tout mettre en pause / tout reprendre. Les éléments bloqués peuvent être retirés |
| Ajouts récents | Nouvelles séries et films. Faire défiler charge d’autres pages Jellyfin. Plex reste aux 20 derniers |
| Demandes | Demandes Seerr pas encore prêtes, plus ce qui a été marqué disponible ou refusé ces 30 derniers jours |
| Tendances | La liste des tendances de Seerr. Faire défiler continue de charger |
| En lecture | Qui regarde sur Jellyfin ou Plex, y compris la lecture directe |
| Stockage | Utilisation disque de la config, des téléchargements et des médias |
| Serveur | CPU, mémoire et réseau. Avec `/sys` de l’hôte monté sur `/host/sys`, ce sont les cartes réseau du serveur. Sans ce montage, seulement le trafic de ce conteneur |
| À surveiller | Les mêmes contrôles que Réglages → Notifications, avec un lien pour régler chaque point |

Installer, démarrer, arrêter et **Ouvrir l’interface** se trouvent dans **Catalogue**. La barre en bas d’Accueil ouvre les apps déjà installées.

**Ouvrir l’interface** sur le LAN ressemble en général à `http://YOUR-SERVER-IP:8989` (exemple Sonarr).  
Si vous avez configuré des noms d’hôte publics Cloudflare, **Ouvrir l’interface** peut utiliser `https://sonarr.yourdomain.com` à la place — voir [Cloudflare Tunnel](deploy/CLOUDFLARE.md).

---

## Ce que l’assistant relie

Dès qu’une app est saine — ou si vous cliquez sur **Liaison auto** — AIO règle les dossiers et catégories de téléchargement, les dossiers racines et les clients de téléchargement dans Sonarr, Radarr et Lidarr, la synchro Prowlarr, Seerr, le lien Bazarr, et les configurations de départ de Recyclarr et NeutArr. **Réglages → Usenet** enregistre le serveur de news et l’envoie à SABnzbd et NZBGet. Prowlarr reçoit aussi un jeu de départ d’indexeurs publics. Retirez ce que vous ne voulez pas ; ils ne sont pas rajoutés.

Gardez **downloads** et **media** sur le même volume pour que les fichiers terminés puissent être des **liens physiques**.

Encore à faire vous-même :

- Un compte Plex.
- Le jeton d’installation du premier démarrage de NeutArr (ci-dessous), jusqu’à ce que ce compte existe.
- La connexion à Jellyfin et NZBGet. Sur le LAN, **Ouvrir l’interface** vous connecte déjà à Sonarr, Radarr, Lidarr, Prowlarr, qBittorrent, SABnzbd, Bazarr et Seerr en tant qu’administrateur du gestionnaire. Les noms d’hôte publics montrent toujours la connexion propre de l’app.
- L’administrateur et l’assistant de première exécution de Seerr sont terminés pour vous à partir de cette connexion partagée (via Jellyfin, ou un Plex revendiqué).

VPN, Cloudflare Tunnel, Recyclarr, NeutArr et sauvegardes sont facultatifs.

### Jeton d’installation du premier démarrage de NeutArr

La première fois que NeutArr démarre, avant d’avoir un compte, il demande un jeton d’installation à usage unique.

1. Attendez que NeutArr soit **actif**.
2. Ouvrez **Catalogue → NeutArr → Réglages**.
3. Copiez **Jeton de première installation** et collez-le dans l’écran d’installation de NeutArr.

Cette valeur est le fichier `/config/neutarr/.setup-token` dans l’appliance (le dossier hôte monté comme `/config`). NeutArr supprime le fichier une fois le compte créé, et le champ dans Réglages se vide. Tant que NeutArr n’a pas démarré, le champ reste vide.

---

## Ouvrir l’interface de chaque app

| Situation | Ce que vous utilisez |
|-----------|-------------|
| À la maison en wifi | **Ouvrir l’interface** → `http://IP:PORT` |
| Hors de la maison avec Cloudflare | **Ouvrir l’interface** → `https://subdomain.yourdomain.com` |
| Vous avez changé le port d’écoute d’une app | AIO met à jour les routes publiées ; recréez le conteneur si les liens LAN ont encore l’air faux. Le port du gestionnaire lui-même est Compose/environnement (`AMM_API_PORT`), visible dans **Réglages → Système** |

Si **Ouvrir l’interface** échoue :

- L’app est-elle **active** dans le catalogue ?
- Êtes-vous sur le même réseau (pour les liens LAN) ?
- Pour les liens HTTPS : le tunnel est-il connecté et **Publier** a-t-il réussi ? ([Guide Cloudflare](deploy/CLOUDFLARE.md))

---

## Les réglages que vous utilisez vraiment

Les noms dans l’interface peuvent être courts ; voici ce qu’ils veulent dire en pratique.

| Section | Pourquoi ça compte |
|---------|----------------|
| **Compte** | Nom, e-mail et mot de passe de l’administrateur. Les apps avec une connexion locale utilisent le même compte |
| **Apparence** | Thème, accent, fond, titre, icône de la barre, logo de connexion et favicon |
| **Système** | Fuseau horaire, niveau de journal, PUID/PGID et version d’AIO. Les chemins de stockage sont ici ; les montages se changent dans Compose, pas dans cet écran. Le port d’écoute du gestionnaire est seulement Compose/environnement |
| **Mises à jour** | Vérifier et appliquer les mises à jour des apps installées, une par une ou toutes. Les planifications sont **désactivées** par défaut. Une image AIO plus récente n’est qu’un signal — tirez et recréez sur l’hôte |
| **Sauvegardes** | Sauvegarde de la config, vérification, restauration par app et une planification |
| **Réseau** | VPN pour qBittorrent, Prowlarr et Flaresolverr (Usenet reste dehors), Cloudflare Tunnel, sous-domaines publics et proxys de confiance |
| **Notifications** | Webhook Discord et e-mail si une app continue de planter, si le VPN ou le tunnel tombe, s’il y a une mise à jour, ou si un disque dépasse 90 % |
| **Usenet** | Serveur de news (hôte, port, SSL, identifiants, connexions), envoyé à SABnzbd et NZBGet. Les indexeurs NZB s’ajoutent dans Prowlarr |
| **Page d’accueil** | Texte de connexion, barre d’apps et clés d’API Jellyfin / Seerr si Accueil ne peut pas les lire |
| **Diagnostic** | Pourquoi un widget d’Accueil est vide. Les clés d’API ne sont jamais affichées. **Lien d’assistance** est une aide à distance temporaire — laissez-le **désactivé**, sauf si vous déboguez avec quelqu’un en qui vous avez confiance |

Laissez aux apps un moment pour se recharger après un changement important de réseau ou de port — ou redémarrez AIO si les liens restent périmés.

## Écrans {#screens}

Clair à gauche, sombre à droite. Accueil est vide ici parce qu’aucune app avec interface web n’est encore installée. Les réglages d’app dans le catalogue sont la fenêtre que vous ouvrez depuis une carte du catalogue (ici qBittorrent).

### Compte

| Clair | Sombre |
| --- | --- |
| ![Compte dans Réglages, thème clair](screenshots/light/settings.png) | ![Compte dans Réglages, thème sombre](screenshots/dark/settings.png) |

### Apparence

| Clair | Sombre |
| --- | --- |
| ![Apparence, thème clair](screenshots/light/settings-visuals.png) | ![Apparence, thème sombre](screenshots/dark/settings-visuals.png) |

### Système

| Clair | Sombre |
| --- | --- |
| ![Réglages système, thème clair](screenshots/light/settings-system.png) | ![Réglages système, thème sombre](screenshots/dark/settings-system.png) |

### Mises à jour

| Clair | Sombre |
| --- | --- |
| ![Mises à jour, thème clair](screenshots/light/settings-updates.png) | ![Mises à jour, thème sombre](screenshots/dark/settings-updates.png) |

### Sauvegardes

| Clair | Sombre |
| --- | --- |
| ![Sauvegardes, thème clair](screenshots/light/settings-backups.png) | ![Sauvegardes, thème sombre](screenshots/dark/settings-backups.png) |

### Réseau

| Clair | Sombre |
| --- | --- |
| ![Réglages réseau, thème clair](screenshots/light/settings-network.png) | ![Réglages réseau, thème sombre](screenshots/dark/settings-network.png) |

### Notifications

| Clair | Sombre |
| --- | --- |
| ![Notifications, thème clair](screenshots/light/settings-notifications.png) | ![Notifications, thème sombre](screenshots/dark/settings-notifications.png) |

### Usenet

| Clair | Sombre |
| --- | --- |
| ![Réglages Usenet, thème clair](screenshots/light/settings-usenet.png) | ![Réglages Usenet, thème sombre](screenshots/dark/settings-usenet.png) |

### Page d’accueil

| Clair | Sombre |
| --- | --- |
| ![Réglages de la page d’accueil, thème clair](screenshots/light/settings-homepage.png) | ![Réglages de la page d’accueil, thème sombre](screenshots/dark/settings-homepage.png) |

### Diagnostic

| Clair | Sombre |
| --- | --- |
| ![Diagnostic, thème clair](screenshots/light/settings-diagnostics.png) | ![Diagnostic, thème sombre](screenshots/dark/settings-diagnostics.png) |

### Réglages d’app dans le catalogue

| Clair | Sombre |
| --- | --- |
| ![Réglages qBittorrent dans le catalogue, thème clair](screenshots/light/catalog-settings.png) | ![Réglages qBittorrent dans le catalogue, thème sombre](screenshots/dark/catalog-settings.png) |

---

## Sauvegardes

- Utilisez la sauvegarde intégrée si vous avez une installation à conserver.
- Sauvegardez aussi le dossier **config** sur l’hôte (et le montage des sauvegardes si vous en utilisez un).
- Les fichiers média sont à part — sauvegardez-les avec votre stratégie NAS ou disque habituelle.

---

## Mettre à jour les apps et mettre à jour AIO

| Quoi | Comment |
|------|-----|
| **AIO lui-même** (tableau de bord + superviseur) | Tirez une nouvelle image Docker et **recréez le conteneur** ([Installer](INSTALL.md)). Réglages → Mises à jour indique seulement quand `:latest` a bougé |
| **Apps installées** (Sonarr, Seerr et le reste) | **Réglages → Mises à jour**. Mettez à jour une app ou toutes. La progression est là, et Catalogue et Accueil affichent **Mise à jour…**. Le tableau de bord continue de répondre. Les planifications sont **désactivées** par défaut |

L’image ne met pas ces apps à jour toute seule. Lisez les notes de version sur GitHub si quelque chose d’important a changé.

---

## Accrocs fréquents

| Problème | Essayez ceci |
|---------|----------|
| Écran vide ou boucle de connexion sur une app | Effacez les données du site pour cette URL ; vérifiez que l’app tourne |
| NeutArr demande un jeton d’installation | **Catalogue → NeutArr → Réglages** une fois NeutArr démarré. Le jeton disparaît dès que le compte NeutArr existe |
| Erreurs de droits à l’écriture | Le propriétaire du dossier hôte doit correspondre à l’utilisateur du conteneur (`PUID`/`PGID`) |
| Sonarr importe mais copie les fichiers | Téléchargements et médias doivent partager un système de fichiers pour les liens physiques |
| Ça marche à la maison, pas en données mobiles | Il faut un tunnel (+ Access de préférence) ; les IP du LAN ne sont pas joignables en données mobiles |
| Deux Sonarr en conflit | Retirez un conteneur Sonarr supplémentaire ; seul AIO doit le faire tourner |
| Le graphique serveur ne compte que ce conteneur | Montez `/sys` de l’hôte en lecture seule sur `/host/sys` et recréez ([Docker](deploy/DOCKER.md)) |
| Ajouts récents Jellyfin semblent courts | Faites défiler la rangée — d’autres pages se chargent. Si la rangée reste vide, mettez une clé d’API Jellyfin dans **Réglages → Page d’accueil** |
| Ajouts récents Plex s’arrêtent à 20 | Cette liste, ce sont les 20 derniers de Plex |

---

## Et ensuite

- Liste pour une nouvelle installation : [Installer](INSTALL.md)  
- Accès distant : [Cloudflare Tunnel](deploy/CLOUDFLARE.md)  
- Fermer la porte des URL publiques : [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md)
