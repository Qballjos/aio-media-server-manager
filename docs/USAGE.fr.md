# Utiliser AIO pas à pas

Commencez ici quand AIO s’ouvre dans votre navigateur. Faites fonctionner une app avant d’en ajouter d’autres.

## 1. Terminer la première configuration

Créez le compte administrateur et terminez l’assistant. Commencez par exemple avec Jellyfin pour vos fichiers existants. Laissez VPN et accès distant désactivés au début. Attendez Running dans le catalogue.

## 2. Les trois pages

| AIO | |
|---|---|
| Home | Téléchargements, sorties et informations serveur ; les widgets sont personnalisables. |
| Catalogue | Installer les apps, vérifier leur état et les ouvrir avec Ouvrir. |
| Réglages | Apparence, compte et mises à jour AIO ; ce n’est pas ici que vous ajoutez des films à votre bibliothèque. |

## Utiliser le nouveau catalogue {#catalog-menu}

Ouvrez **Catalogue** en haut. Choisissez la vue à gauche ; les apps apparaissent à droite.

| Choix à gauche | Contenu affiché |
|---|---|
| **Découvrir** | Apps mises en avant et catalogue complet. |
| **Mes apps** | Apps déjà installées, même arrêtées. |
| **Actif** | Uniquement les apps en cours d’exécution. |
| **Disponible** | Apps à installer. |
| **Recherche / Catégorie** | Chercher une app par nom ou par type. |

Au-dessus de la liste, triez par popularité ou de A à Z. Une app manque ? Effacez la recherche et choisissez Découvrir pour retirer la sélection de statut ou catégorie.

Pour Jellyfin : recherchez Jellyfin. Choisissez **Installer** si nécessaire, attendez **Running**, puis **Ouvrir**. Si l’app est installée mais arrêtée, choisissez d’abord **Démarrer**. Ouvrir lance l’app dans un nouvel onglet.

Cliquez sur le nom, l’icône ou la ligne d’une app pour ouvrir sa **fenêtre de réglages**, sans ouvrir l’app elle-même. **⋯** propose selon son état Réglages, Arrêter, Redémarrer, Journaux, Mettre à jour et Désinstaller. Fermez avec × ou Échap. Enregistrez uniquement les changements souhaités.

Les **réglages d’app dans Catalogue** concernent une app. La page **Réglages** en haut concerne AIO : profil, apparence, connexions, sauvegardes et mises à jour.

![Catalog: sidebar, app rows and Open buttons](screenshots/light/catalog.png?v=app-store-20261102)

## Se repérer dans les réglages {#settings-menu}

Réglages utilise la même disposition que le catalogue : groupe et page à gauche, contenu à droite. La recherche filtre le menu, pas les valeurs enregistrées. Faites défiler le menu pour voir les groupes du bas. Sur téléphone, ouvrez **Sections des réglages**, puis choisissez une page.

| Que voulez-vous modifier ? | Page à choisir |
|---|---|
| Nom, photo ou mot de passe | Personnel → **Profil** |
| Langue, thème ou fond | Personnel → **Langue et apparence** |
| Barre d’apps ou texte de connexion | Tableau de bord → **Page d’accueil** |
| Mettre à jour une app | Maintenance → **Mises à jour** |
| Sauvegarder les réglages | Maintenance → **Sauvegardes** |
| Comprendre un widget vide | Système → **Aide et diagnostic** |
| Clés d’API, TV ou Homey | Connexions → **Connexions des apps** |

Le menu ouvre une page. Modifiez l’option à droite et utilisez le bouton **Enregistrer** du bloc lorsqu’il est affiché. Déplacez les widgets directement sur **Accueil** avec l’icône à quatre blocs ; Page d’accueil règle la barre d’apps et le texte de connexion.

![Settings: grouped sidebar and search](screenshots/light/settings.png?v=app-store-20261102)

## 3. Ouvrir votre première app

Dans le catalogue, trouvez Jellyfin et choisissez Ouvrir. Terminez son propre assistant si demandé. Les dossiers par défaut sont /data/media/movies pour les films et /data/media/tv pour les séries. Ils correspondent aux dossiers NAS déjà reliés ; ne créez pas une deuxième copie à cause du nom différent.

**Vérification : Jellyfin s’ouvre dans un onglet séparé. Sans fichiers média, la bibliothèque est vide ; c’est normal.**

## 4. Lire votre premier film {#first-media}

Copiez un fichier film que vous possédez dans le **dossier movies du serveur**, pas Downloads ni la démo du site.

| Serveur | Dossier cible |
|---|---|
| Synology | DSM File Station → home → aio-media-manager → media → movies. Choisissez Téléverser puis le fichier sur votre ordinateur. |
| Unraid | Partage réseau aio-media-manager → media → movies. La dernière étape Unraid explique le partage privé. |
| TrueNAS | Partage réseau aio-media → media → movies. L’étape 7 TrueNAS configure l’accès. |
| Docker sur Linux | Sur le serveur, dossier personnel → aio-media-manager → media → movies. Depuis un autre ordinateur, copie SSH avec scp ci-dessous. |

Pour un serveur Linux distant, lancez ce bloc **sur votre ordinateur**, en remplaçant chemin du fichier, utilisateur et IP. La destination correspond à l’installation standard dans le dossier personnel.

Un chemin Windows ressemble à `C:\Users\Alex\Videos\MonFilm.mp4`, sur Mac à `/Users/alex/Movies/MonFilm.mp4`. Gardez les guillemets autour de votre vrai chemin et les mêmes utilisateur/IP que pour SSH.

```bash
scp "/PATH/TO/YOUR/FILM.mp4" YOUR-USER@SERVER-IP:aio-media-manager/media/movies/
```

Pour une série utilisez media/tv. Après la copie, ouvrez Jellyfin → Dashboard → Bibliothèques et lancez Scan All Libraries ou l’analyse de cette bibliothèque. Revenez à l’accueil Jellyfin, ouvrez le film et choisissez Lire.

**Vérification : le film apparaît et se lit. Sinon comparez le dossier du serveur au chemin choisi dans Jellyfin et relancez l’analyse.**

## 5. Organiser les widgets Home {#customize-home}

<div class="widget-visual-guide" role="group" aria-label="Organiser les widgets de l’accueil">
<div class="widget-visual-step"><span class="visual-number">1</span><strong>Le bouton de disposition</strong><div class="visual-nav"><span>Home</span><span>Catalog</span><span>Settings</span><span class="visual-highlight"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="7" height="10" rx="1.5"/><rect x="14" y="3" width="7" height="6" rx="1.5"/><rect x="3" y="17" width="7" height="4" rx="1.5"/><rect x="14" y="13" width="7" height="8" rx="1.5"/></svg></span></div><p>Sur Home, choisissez l’icône à quatre blocs à côté des onglets. Les poignées et la barre de modification apparaissent.</p></div>
<div class="widget-visual-step"><span class="visual-number">2</span><strong>Déplacer : glisser la poignée</strong><div class="visual-widget"><span class="visual-grip">⠿</span><span class="visual-remove">×</span><strong>Téléchargements</strong><span class="visual-widget-line"></span><span class="visual-widget-line short"></span><span class="visual-corner">↘</span></div><p>Taille : glisser ce coin</p></div>
<div class="widget-visual-step"><span class="visual-number">3</span><strong>Choisir un widget</strong><div class="visual-toolbar"><span>＋ Ajouter un widget</span><span>Terminé</span></div><p>Choisissez Ajouter un widget, puis Cette taille ou Toutes les tailles et le widget. Les changements sont enregistrés automatiquement ; terminez avec Terminé.</p></div>
</div>

[Organiser les widgets Home](index.md#app-preview){ .md-button .md-button--primary }

Ces images expliquent les vraies commandes. La démo du site utilise des données fictives sans modifier votre tableau de bord.

### Pourquoi un widget est-il vide ?

Vérifiez l’app correspondante dans le catalogue. Les ajouts récents demandent des médias dans Jellyfin/Plex ; le calendrier des titres prévus dans les apps liées. Les widgets vides peuvent disparaître hors édition. Ajouter un widget n’installe pas son app source.

## 6. À quoi servent les autres apps ?

| App | |
|---|---|
| Jellyfin / Plex | Lire les fichiers média existants. |
| Sonarr / Radarr | Organiser séries / films et automatiser les téléchargements choisis. |
| SABnzbd / NZBGet | Télécharger via Usenet avec votre compte fournisseur. |
| qBittorrent | Télécharger et partager des torrents. |
| Prowlarr | Gérer les sources de recherche des apps d’automatisation. |

Vous n’avez pas besoin de tout. Ajoutez une app dans le catalogue selon vos besoins. Les connexions détaillées sont dans Avancé.

## 7. Mettre les apps à jour

Réglages → Updates met à jour les apps internes. AIO lui-même se met à jour séparément dans NAS/Docker ; voir le guide avancé de la plateforme. Avant un changement, créez une sauvegarde des réglages dans Backups.

## Captures et référence technique {#screens}

[Captures et référence technique](USAGE_ADVANCED.md#screens).

## Avancé

Connexions personnalisées, VPN, clés et diagnostics sont dans le guide avancé du tableau de bord. [Avancé](USAGE_ADVANCED.md).
