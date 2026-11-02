---
hide:
  - navigation
  - toc
title: AIO Media Server Manager
---

<div class="aio-landing">
<section class="landing-hero" aria-labelledby="landing-title">
<div class="landing-intro">
<p class="eyebrow">VOTRE SERVEUR. VOS MÉDIAS. VOS RÈGLES.</p>
<h1 id="landing-title">Votre serveur média complet.<br>
<span>Moins de réglages. Plus de cinéma.</span>
</h1>
<p class="landing-lead">Installez une fois, choisissez vos applications et laissez AIO relier les outils compatibles. Commencez avec l’assistant, puis configurez sauvegardes, mises à jour et options avancées selon vos besoins.</p>
<div class="landing-actions">
<a class="landing-button primary" href="#install">Installer AIO <span aria-hidden="true">↗</span>
</a>
<a class="landing-button" href="#app-preview">Découvrir le tableau de bord <span aria-hidden="true">↓</span>
</a>
</div>
<div class="hero-proof">
<span>Docker · Unraid · Synology · TrueNAS</span>
<span>Open source · Self-hosted</span>
</div>
</div>
<div class="showcase-wrap" id="app-preview" role="region" aria-label="Aperçu de l’interface AIO">
<div class="preview-controls js-only">
<div class="preview-tabs" role="tablist" aria-label="Aperçu de l’interface AIO">
<button type="button" role="tab" id="preview-tab-current" aria-controls="preview-panel-current" aria-selected="true" tabindex="0" data-screen="current">App actuelle</button>
<button type="button" role="tab" id="preview-tab-home" aria-controls="preview-panel-home" aria-selected="false" tabindex="-1" data-screen="home">Essayer les widgets</button>
<button type="button" role="tab" id="preview-tab-catalog" aria-controls="preview-panel-catalog" aria-selected="false" tabindex="-1" data-screen="catalog">Catalogue</button>
<button type="button" role="tab" id="preview-tab-settings" aria-controls="preview-panel-settings" aria-selected="false" tabindex="-1" data-screen="settings">Réglages</button>
</div>
<button type="button" class="preview-theme" data-preview-theme aria-pressed="false" data-light="Clair" data-dark="Sombre">◐ <span>Sombre</span>
</button>
</div>
<div class="browser-frame" data-preview data-theme="light">
<div class="browser-chrome">
<span class="browser-dots" aria-hidden="true">
<i>
</i>
<i>
</i>
<i>
</i>
</span>
<span>aio.home <span aria-hidden="true">/</span> <span data-screen-name>App actuelle</span>
</span>
<span class="browser-lock" aria-hidden="true">⌘</span>
</div>
<div class="preview-panel" id="preview-panel-current" role="tabpanel" aria-labelledby="preview-tab-current" data-panel="current">
<img src="__AIO_ASSET__/screenshots/light/home.png" data-preview-image="home" alt="Interface réelle avec exemples fictifs : affiches, téléchargements et dates de sortie des épisodes et films." width="1280" loading="eager">
<p class="preview-screenshot-caption">Interface réelle avec exemples fictifs : affiches, téléchargements et dates de sortie des épisodes et films.</p>
</div>
<div class="preview-panel" id="preview-panel-home" role="tabpanel" aria-labelledby="preview-tab-home" data-panel="home" hidden>
<div class="demo-dashboard" data-widget-lab>
<div class="demo-nav">
<span class="demo-brand">
<img src="__AIO_ASSET__/assets/logo-aio-media-manager.png" alt="" width="26" height="26"> AIO <span>Media Manager</span>
</span>
<span class="demo-online">
<i>
</i>Tout est prêt</span>
</div>
<div class="demo-greeting">
<div>
<span class="demo-kicker">HOME</span>
<h3>Moins de gestion.<br>
<span>Plus de soirées cinéma.</span>
</h3>
</div>
<button class="demo-edit js-only" type="button" data-edit aria-pressed="false" data-edit-label="Organiser les widgets" data-done-label="Terminé">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
<rect x="3" y="3" width="7" height="10" rx="1.5"/>
<rect x="14" y="3" width="7" height="6" rx="1.5"/>
<rect x="3" y="17" width="7" height="4" rx="1.5"/>
<rect x="14" y="13" width="7" height="8" rx="1.5"/>
</svg>
<span>Organiser les widgets</span>
</button>
</div>
<div class="demo-toolbar js-only" data-demo-toolbar hidden>
<button type="button" data-add>＋ Ajouter un widget</button>
<button type="button" data-reset>↺ Réinitialiser la démo</button>
</div>
<div class="demo-grid" data-demo-grid>
<article class="demo-widget demo-search is-wide" data-widget="search" data-default-wide="true" tabindex="0" aria-label="Recherche">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="À gauche">←</button>
<button type="button" data-move="1" aria-label="À droite">→</button>
<button type="button" data-remove aria-label="Retirer le widget: Recherche">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<h4 class="demo-sr-only">Recherche</h4>
<form class="demo-search-form" data-demo-search-form>
<label class="demo-sr-only" for="sample-library-search">Chercher un film ou une série…</label>
<span aria-hidden="true">⌕</span>
<input id="sample-library-search" type="search" data-demo-search disabled placeholder="Chercher un film ou une série…" autocomplete="off">
<button type="submit" disabled aria-label="Chercher dans la bibliothèque fictive">→</button>
</form>
<button class="demo-resize" type="button" data-resize aria-label="Changer la taille: Recherche">↘</button>
</article>
<article class="demo-widget demo-recent is-wide" data-widget="recent" data-default-wide="true" tabindex="0" aria-label="Ajouts récents">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="À gauche">←</button>
<button type="button" data-move="1" aria-label="À droite">→</button>
<button type="button" data-remove aria-label="Retirer le widget: Ajouts récents">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<div class="demo-widget-heading">
<h4>Ajouts récents</h4>
<span class="demo-count" data-demo-count data-results-label="Résultats dans la bibliothèque fictive">3</span>
</div>
<div class="demo-poster-grid">
<figure class="demo-poster" data-sample-title="Orbit">
<img src="__AIO_ASSET__/assets/demo-posters/orbit.svg" width="300" height="450" alt="Affiche illustrative fictive: Orbit">
<figcaption>
<strong>Orbit</strong>
<span>Série · S02 · E03</span>
</figcaption>
</figure>
<figure class="demo-poster" data-sample-title="The Last Light">
<img src="__AIO_ASSET__/assets/demo-posters/last-light.svg" width="300" height="450" alt="Affiche illustrative fictive: The Last Light">
<figcaption>
<strong>The Last Light</strong>
<span>Film · 2026</span>
</figcaption>
</figure>
<figure class="demo-poster" data-sample-title="Northbound">
<img src="__AIO_ASSET__/assets/demo-posters/northbound.svg" width="300" height="450" alt="Affiche illustrative fictive: Northbound">
<figcaption>
<strong>Northbound</strong>
<span>Série · S01 · E05</span>
</figcaption>
</figure>
</div>
<p class="demo-no-results" data-demo-no-results hidden role="status">Aucun résultat. Essayez Orbit, Northbound ou The Last Light.</p>
<button class="demo-resize" type="button" data-resize aria-label="Changer la taille: Ajouts récents">↘</button>
</article>
<article class="demo-widget demo-calendar" data-widget="calendar" data-default-wide="false" tabindex="0" aria-label="Calendrier des sorties">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="À gauche">←</button>
<button type="button" data-move="1" aria-label="À droite">→</button>
<button type="button" data-remove aria-label="Retirer le widget: Calendrier des sorties">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<h4>▦ Calendrier des sorties</h4>
<p class="demo-agenda-label">Prochains épisodes et sorties de films</p>
<div class="demo-release-list">
<div class="demo-release" data-release-title="Orbit">
<span class="demo-release-date">
<strong>03</strong>
<span>NOV</span>
</span>
<img src="__AIO_ASSET__/assets/demo-posters/orbit.svg" alt="" width="24" height="36">
<span class="demo-release-title">
<strong>Orbit</strong>
<small>Épisode · S02E04</small>
</span>
</div>
<div class="demo-release" data-release-title="The Last Light">
<span class="demo-release-date">
<strong>07</strong>
<span>NOV</span>
</span>
<img src="__AIO_ASSET__/assets/demo-posters/last-light.svg" alt="" width="24" height="36">
<span class="demo-release-title">
<strong>The Last Light</strong>
<small>Sortie du film</small>
</span>
</div>
<div class="demo-release" data-release-title="Northbound">
<span class="demo-release-date">
<strong>08</strong>
<span>NOV</span>
</span>
<img src="__AIO_ASSET__/assets/demo-posters/northbound.svg" alt="" width="24" height="36">
<span class="demo-release-title">
<strong>Northbound</strong>
<small>Épisode · S01E06</small>
</span>
</div>
</div>
<button class="demo-resize" type="button" data-resize aria-label="Changer la taille: Calendrier des sorties">↘</button>
</article>
<article class="demo-widget demo-download" data-widget="downloads" tabindex="0" aria-label="Téléchargements">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="À gauche">←</button>
<button type="button" data-move="1" aria-label="À droite">→</button>
<button type="button" data-remove aria-label="Retirer le widget: Téléchargements">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<h4>↓ Téléchargements</h4>
<div class="demo-download-line">
<span>Collection de films libres<small>Téléchargement fictif</small>
</span>
<strong>108 <small>MB/s</small>
</strong>
</div>
<div class="demo-progress">
<span>
</span>
</div>
<span class="demo-widget-note">68% · 2.4 GB / 3.5 GB</span>
<button class="demo-resize" type="button" data-resize aria-label="Changer la taille: Téléchargements">↘</button>
</article>
<article class="demo-widget demo-server" data-widget="server" data-default-hidden="true" hidden tabindex="0" aria-label="Serveur">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="À gauche">←</button>
<button type="button" data-move="1" aria-label="À droite">→</button>
<button type="button" data-remove aria-label="Retirer le widget: Serveur">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<h4>⌁ Serveur</h4>
<div class="demo-server-numbers">
<span>
<strong>12<small>%</small>
</strong>CPU</span>
<span>
<strong>4.2<small> GB</small>
</strong>Mémoire</span>
</div>
<svg class="demo-chart" viewBox="0 0 320 55" aria-hidden="true">
<path d="M0 44 L20 40 L40 43 L60 18 L80 31 L100 26 L120 35 L140 13 L160 24 L180 20 L200 30 L220 9 L240 23 L260 17 L280 25 L300 12 L320 18"/>
</svg>
<button class="demo-resize" type="button" data-resize aria-label="Changer la taille: Serveur">↘</button>
</article>
</div>
<div class="demo-dock" aria-label="Apps actives">
<span title="Sonarr">
<img src="__AIO_ASSET__/assets/app-icons/sonarr.svg" alt="Sonarr" width="30" height="30">
</span>
<span title="Radarr">
<img src="__AIO_ASSET__/assets/app-icons/radarr.svg" alt="Radarr" width="30" height="30">
</span>
<span title="Prowlarr">
<img src="__AIO_ASSET__/assets/app-icons/prowlarr.svg" alt="Prowlarr" width="30" height="30">
</span>
<span title="SABnzbd">
<img src="__AIO_ASSET__/assets/app-icons/sabnzbd.svg" alt="SABnzbd" width="30" height="30">
</span>
<span title="Jellyfin">
<img src="__AIO_ASSET__/assets/app-icons/jellyfin.svg" alt="Jellyfin" width="30" height="30">
</span>
<span title="Seerr">
<img src="__AIO_ASSET__/assets/app-icons/seerr.svg" alt="Seerr" width="30" height="30">
</span>
<span class="demo-dock-more">+8</span>
</div>
</div>
</div>
<div class="preview-panel" id="preview-panel-catalog" role="tabpanel" aria-labelledby="preview-tab-catalog" data-panel="catalog" hidden>
<img src="__AIO_ASSET__/screenshots/light/catalog.png?v=app-store-20261102" data-preview-image="catalog" alt="Catalogue — Capture de l’application AIO" width="1280" height="720" loading="lazy">
</div>
<div class="preview-panel" id="preview-panel-settings" role="tabpanel" aria-labelledby="preview-tab-settings" data-panel="settings" hidden>
<img src="__AIO_ASSET__/screenshots/light/settings.png?v=app-store-20261102" data-preview-image="settings" alt="Réglages — Capture de l’application AIO" width="1280" height="720" loading="lazy">
</div>
</div>
<p class="preview-caption">Aperçu interactif · données fictives<span aria-hidden="true"> · </span>
<span data-preview-status role="status">Aperçu uniquement · aucun changement sur votre serveur</span>
</p>
</div>
</section>
<div class="landing-note js-only">
<span class="note-icon" aria-hidden="true">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
<rect x="3" y="3" width="7" height="10" rx="1.5"/>
<rect x="14" y="3" width="7" height="6" rx="1.5"/>
<rect x="3" y="17" width="7" height="4" rx="1.5"/>
<rect x="14" y="13" width="7" height="8" rx="1.5"/>
</svg>
</span>
<p>Essayez : ouvrez Organiser les widgets, puis déplacez, agrandissez ou ajoutez une carte. Cette démo simplifiée n’est pas votre serveur.</p>
</div>
<noscript>
<p class="landing-note">Sans JavaScript, l’aperçu reste statique. Les guides et captures restent accessibles.</p>
</noscript>
<section class="landing-section" id="how-it-works">
<div class="section-heading">
<p class="eyebrow">DE L’INSTALLATION AU QUOTIDIEN</p>
<h2>Simple pour débuter. De quoi évoluer.</h2>
</div>
<ol class="widget-steps">
<li><span class="step-number">1</span><div><h3>Installer sur votre serveur</h3><p>Choisissez Docker, Unraid, Synology ou TrueNAS ci-dessous. Le guide explique le stockage, les permissions et le démarrage d’AIO.</p></div></li>
<li><span class="step-number">2</span><div><h3>Choisir vos applications</h3><p>Créez votre compte administrateur et suivez l’assistant. Choisissez votre serveur média et les outils utiles ; ajoutez-en d’autres plus tard.</p></div></li>
<li><span class="step-number">3</span><div><h3>Laisser AIO les relier</h3><p>AIO configure les connexions compatibles, les clients de téléchargement et les dossiers des bibliothèques. Vous fournissez vos identifiants et sources média.</p></div></li>
<li><span class="step-number">4</span><div><h3>Personnaliser votre installation</h3><p>Ouvrez vos applications depuis un tableau de bord. Organisez les widgets et configurez sauvegardes, mises à jour et options avancées à votre rythme.</p></div></li>
</ol>
<a class="landing-button primary" href="#install">Choisir votre serveur ↓</a>
<p><a class="landing-text-link" href="ADVANCED.md">Vous avez déjà un serveur média ? Consultez les guides avancés avant de modifier votre installation.</a></p>
</section>
<section class="landing-section widget-section" id="widgets">
<div class="section-heading">
<p class="eyebrow">UN ACCUEIL À VOTRE IMAGE</p>
<h2>La place pour ce qui compte.</h2>
<p>Organisez votre accueil. Essayez les commandes ci-dessus, puis faites de même dans AIO.</p>
<a href="#app-preview" class="landing-text-link" data-try-widgets>Essayer la démo des widgets ↑</a>
</div>
<ol class="widget-steps">
<li>
<span class="step-number">1</span>
<div>
<h3>Ouvrir la disposition</h3>
<p>Sur Home, choisissez l’icône à quatre blocs à côté des onglets. Les poignées et la barre de modification apparaissent.</p>
</div>
</li>
<li>
<span class="step-number">2</span>
<div>
<h3>Déplacer les widgets</h3>
<p>Faites glisser une carte à sa nouvelle place. Sur téléphone, utilisez sa poignée pour pouvoir toujours faire défiler la page.</p>
</div>
</li>
<li>
<span class="step-number">3</span>
<div>
<h3>Choisir la taille</h3>
<p>Faites glisser le coin inférieur droit ou ouvrez les réglages du widget pour choisir une taille. Vous pouvez aussi le retirer ici.</p>
</div>
</li>
<li>
<span class="step-number">4</span>
<div>
<h3>Ajouter ce qui manque</h3>
<p>Choisissez Ajouter un widget, puis Cette taille ou Toutes les tailles et le widget. Les changements sont enregistrés automatiquement ; terminez avec Terminé.</p>
</div>
</li>
</ol>
<p class="section-footnote">Téléphone, tablette et ordinateur peuvent avoir leur propre disposition. Les widgets vides peuvent disparaître hors du mode édition, jusqu’à ce que l’app liée fournisse du contenu.</p>
</section>
<section class="landing-section feature-row">
<div>
<p class="eyebrow">LE CATALOGUE</p>
<h2>Vos outils préférés.<br>
<span class="gradient-text">Un seul endroit pour les gérer.</span>
</h2>
<p>Choisissez Découvrir, Mes apps ou une catégorie dans le menu. Ouvrir lance l’app ; son nom ou son icône affiche ses réglages.</p>
<a class="landing-text-link" href="USAGE.md">Découvrir le tableau de bord →</a>
</div>
<figure class="feature-shot">
<img src="__AIO_ASSET__/screenshots/light/catalog.png?v=app-store-20261102" data-theme-image="catalog" alt="Catalogue" width="1280" height="720" loading="lazy">
</figure>
</section>
<section class="landing-section feature-row reverse">
<div>
<p class="eyebrow">MOINS D’EFFORT. PLUS DE CONTRÔLE.</p>
<h2>Bien régler, une fois.</h2>
<p>Les réglages sont groupés avec un champ de recherche. Profil et apparence sont dans Personnel, les connexions dans Connexions, les mises à jour et sauvegardes dans Maintenance.</p>
<a class="landing-text-link" href="USAGE.md#screens">Découvrir le tableau de bord →</a>
</div>
<figure class="feature-shot">
<img src="__AIO_ASSET__/screenshots/light/settings.png?v=app-store-20261102" data-theme-image="settings" alt="Réglages" width="1280" height="720" loading="lazy">
</figure>
</section>
<section class="landing-section" id="install">
<div class="section-heading">
<p class="eyebrow">ON VOUS ACCOMPAGNE</p>
<h2>Commencez avec votre serveur.</h2>
<p>Choisissez votre plateforme. Nous vous guidons étape par étape.</p>
</div>
<div class="platform-grid">
<a class="platform-card" href="deploy/UNRAID.md">
<span class="platform-symbol" aria-hidden="true">▤</span>
<h3>Unraid</h3>
<p>Unraid ? Commencez par le modèle et le stockage SSD des téléchargements.</p>
<span class="platform-arrow" aria-hidden="true">↗</span>
</a>
<a class="platform-card" href="deploy/SYNOLOGY.md">
<span class="platform-symbol" aria-hidden="true">▥</span>
<h3>Synology</h3>
<p>Un NAS Synology ? Installez Container Manager, puis créez un projet.</p>
<span class="platform-arrow" aria-hidden="true">↗</span>
</a>
<a class="platform-card" href="deploy/DOCKER.md">
<span class="platform-symbol" aria-hidden="true">▰</span>
<h3>Docker</h3>
<p>Docker sur un autre serveur ? Utilisez la configuration à un conteneur.</p>
<span class="platform-arrow" aria-hidden="true">↗</span>
</a>
<a class="platform-card" href="deploy/TRUENAS.md">
<span class="platform-symbol" aria-hidden="true">▧</span>
<h3>TrueNAS</h3>
<p>TrueNAS SCALE ? Suivez la configuration d’une app personnalisée.</p>
<span class="platform-arrow" aria-hidden="true">↗</span>
</a>
</div>
</section>
<section class="landing-section beginner-callout">
<span class="beginner-symbol" aria-hidden="true">✳</span>
<div>
<h2>Vous débutez ? Par ici.</h2>
<p>Inutile de connaître toutes les apps. Le guide explique les prérequis, où cliquer et le résultat attendu.</p>
<a class="landing-button primary" href="INSTALL.md">Lire le guide d’installation ↗</a>
</div>
<p class="advanced-route-link"><a href="ADVANCED.md" class="landing-text-link">Configuration avancée →</a></p>
</section>
<section class="landing-section landing-faq">
<div class="section-heading">
<p class="eyebrow">FAQ</p>
<h2>Bon à savoir.</h2>
</div>
<details>
<summary>Ai-je besoin de toutes les apps ?</summary>
<p>Non. Commencez par un serveur média et les outils nécessaires. Ajoutez les autres plus tard via le catalogue.</p>
</details>
<details>
<summary>Où vont mes films et séries ?</summary>
<p>Sur votre serveur. Le SSD peut accélérer téléchargement et décompression ; la bibliothèque peut rester sur HDD.</p>
</details>
<details>
<summary>Faut-il un VPN ou un domaine ?</summary>
<p>Pas pour commencer à la maison. Vous pourrez les configurer plus tard.</p>
</details>
<details>
<summary>Est-ce un vrai serveur dans mon navigateur ?</summary>
<p>Non. Le tableau de bord est une démo avec des données fictives. Catalogue et Réglages montrent de vrais screenshots AIO. Rien ne se connecte à votre serveur.</p>
</details>
</section>
<section class="landing-section landing-end">
<h2>Vos médias. Une gestion plus sereine.</h2>
<p>Auto-hébergé. Open source. Vos outils média, réunis.</p>
<a class="landing-button primary" href="INSTALL.md">Commencer ↗</a>
<a class="landing-button" href="https://github.com/Qballjos/aio-media-server-manager">Voir sur GitHub</a>
</section>
</div>
