---
hide:
  - navigation
  - toc
title: AIO Media Server Manager
---

<div class="aio-landing">
<section class="landing-hero" aria-labelledby="landing-title">
<div class="landing-intro">
<p class="eyebrow">YOUR SERVER. YOUR MEDIA. YOUR RULES.</p>
<h1 id="landing-title">Your complete media server.<br>
<span>Less setup. More watching.</span>
</h1>
<p class="landing-lead">Install once, choose your apps, and let AIO connect supported tools for you. Start with a guided setup; grow into backups, updates and advanced settings.</p>
<div class="landing-actions">
<a class="landing-button primary" href="#install">Install AIO <span aria-hidden="true">↗</span>
</a>
<a class="landing-button" href="#app-preview">Explore the dashboard <span aria-hidden="true">↓</span>
</a>
</div>
<div class="hero-proof">
<span>Docker · Unraid · Synology · TrueNAS</span>
<span>Open source · Self-hosted</span>
</div>
</div>
<div class="showcase-wrap" id="app-preview" role="region" aria-label="AIO interface preview">
<div class="preview-controls js-only">
<div class="preview-tabs" role="tablist" aria-label="AIO interface preview">
<button type="button" role="tab" id="preview-tab-current" aria-controls="preview-panel-current" aria-selected="true" tabindex="0" data-screen="current">Current app</button>
<button type="button" role="tab" id="preview-tab-home" aria-controls="preview-panel-home" aria-selected="false" tabindex="-1" data-screen="home">Try widgets</button>
<button type="button" role="tab" id="preview-tab-catalog" aria-controls="preview-panel-catalog" aria-selected="false" tabindex="-1" data-screen="catalog">Catalog</button>
<button type="button" role="tab" id="preview-tab-settings" aria-controls="preview-panel-settings" aria-selected="false" tabindex="-1" data-screen="settings">Settings</button>
</div>
<button type="button" class="preview-theme" data-preview-theme aria-pressed="false" data-light="Light" data-dark="Dark">◐ <span>Dark</span>
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
<span>aio.home <span aria-hidden="true">/</span> <span data-screen-name>Current app</span>
</span>
<span class="browser-lock" aria-hidden="true">⌘</span>
</div>
<div class="preview-panel" id="preview-panel-current" role="tabpanel" aria-labelledby="preview-tab-current" data-panel="current">
<img src="__AIO_ASSET__/screenshots/light/home.png" data-preview-image="home" alt="Real interface, fictional examples: posters, downloads and episode/movie release dates." width="1280" loading="eager">
<p class="preview-screenshot-caption">Real interface, fictional examples: posters, downloads and episode/movie release dates.</p>
</div>
<div class="preview-panel" id="preview-panel-home" role="tabpanel" aria-labelledby="preview-tab-home" data-panel="home" hidden>
<div class="demo-dashboard" data-widget-lab>
<div class="demo-nav">
<span class="demo-brand">
<img src="__AIO_ASSET__/assets/logo-aio-media-manager.png" alt="" width="26" height="26"> AIO <span>Media Manager</span>
</span>
<span class="demo-online">
<i>
</i>All systems ready</span>
</div>
<div class="demo-greeting">
<div>
<span class="demo-kicker">HOME</span>
<h3>A little less admin.<br>
<span>A little more movie night.</span>
</h3>
</div>
<button class="demo-edit js-only" type="button" data-edit aria-pressed="false" data-edit-label="Arrange widgets" data-done-label="Done">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
<rect x="3" y="3" width="7" height="10" rx="1.5"/>
<rect x="14" y="3" width="7" height="6" rx="1.5"/>
<rect x="3" y="17" width="7" height="4" rx="1.5"/>
<rect x="14" y="13" width="7" height="8" rx="1.5"/>
</svg>
<span>Arrange widgets</span>
</button>
</div>
<div class="demo-toolbar js-only" data-demo-toolbar hidden>
<button type="button" data-add>＋ Add widget</button>
<button type="button" data-reset>↺ Reset demo</button>
</div>
<div class="demo-grid" data-demo-grid>
<article class="demo-widget demo-search is-wide" data-widget="search" data-default-wide="true" tabindex="0" aria-label="Search">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="Move left">←</button>
<button type="button" data-move="1" aria-label="Move right">→</button>
<button type="button" data-remove aria-label="Remove widget: Search">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<h4 class="demo-sr-only">Search</h4>
<form class="demo-search-form" data-demo-search-form>
<label class="demo-sr-only" for="sample-library-search">Find a film or series…</label>
<span aria-hidden="true">⌕</span>
<input id="sample-library-search" type="search" data-demo-search disabled placeholder="Find a film or series…" autocomplete="off">
<button type="submit" disabled aria-label="Search sample library">→</button>
</form>
<button class="demo-resize" type="button" data-resize aria-label="Change size: Search">↘</button>
</article>
<article class="demo-widget demo-recent is-wide" data-widget="recent" data-default-wide="true" tabindex="0" aria-label="Recently added">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="Move left">←</button>
<button type="button" data-move="1" aria-label="Move right">→</button>
<button type="button" data-remove aria-label="Remove widget: Recently added">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<div class="demo-widget-heading">
<h4>Recently added</h4>
<span class="demo-count" data-demo-count data-results-label="Results in the sample library">3</span>
</div>
<div class="demo-poster-grid">
<figure class="demo-poster" data-sample-title="Orbit">
<img src="__AIO_ASSET__/assets/demo-posters/orbit.svg" width="300" height="450" alt="Illustrated sample poster: Orbit">
<figcaption>
<strong>Orbit</strong>
<span>Series · S02 · E03</span>
</figcaption>
</figure>
<figure class="demo-poster" data-sample-title="The Last Light">
<img src="__AIO_ASSET__/assets/demo-posters/last-light.svg" width="300" height="450" alt="Illustrated sample poster: The Last Light">
<figcaption>
<strong>The Last Light</strong>
<span>Film · 2026</span>
</figcaption>
</figure>
<figure class="demo-poster" data-sample-title="Northbound">
<img src="__AIO_ASSET__/assets/demo-posters/northbound.svg" width="300" height="450" alt="Illustrated sample poster: Northbound">
<figcaption>
<strong>Northbound</strong>
<span>Series · S01 · E05</span>
</figcaption>
</figure>
</div>
<p class="demo-no-results" data-demo-no-results hidden role="status">No matches. Try Orbit, Northbound or The Last Light.</p>
<button class="demo-resize" type="button" data-resize aria-label="Change size: Recently added">↘</button>
</article>
<article class="demo-widget demo-calendar" data-widget="calendar" data-default-wide="false" tabindex="0" aria-label="Release calendar">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="Move left">←</button>
<button type="button" data-move="1" aria-label="Move right">→</button>
<button type="button" data-remove aria-label="Remove widget: Release calendar">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<h4>▦ Release calendar</h4>
<p class="demo-agenda-label">Upcoming episodes &amp; film releases</p>
<div class="demo-release-list">
<div class="demo-release" data-release-title="Orbit">
<span class="demo-release-date">
<strong>03</strong>
<span>NOV</span>
</span>
<img src="__AIO_ASSET__/assets/demo-posters/orbit.svg" alt="" width="24" height="36">
<span class="demo-release-title">
<strong>Orbit</strong>
<small>Episode · S02E04</small>
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
<small>Film release</small>
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
<small>Episode · S01E06</small>
</span>
</div>
</div>
<button class="demo-resize" type="button" data-resize aria-label="Change size: Release calendar">↘</button>
</article>
<article class="demo-widget demo-download" data-widget="downloads" tabindex="0" aria-label="Downloading">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="Move left">←</button>
<button type="button" data-move="1" aria-label="Move right">→</button>
<button type="button" data-remove aria-label="Remove widget: Downloading">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<h4>↓ Downloading</h4>
<div class="demo-download-line">
<span>Open movie collection<small>Sample download</small>
</span>
<strong>108 <small>MB/s</small>
</strong>
</div>
<div class="demo-progress">
<span>
</span>
</div>
<span class="demo-widget-note">68% · 2.4 GB / 3.5 GB</span>
<button class="demo-resize" type="button" data-resize aria-label="Change size: Downloading">↘</button>
</article>
<article class="demo-widget demo-server" data-widget="server" data-default-hidden="true" hidden tabindex="0" aria-label="Server">
<div class="demo-widget-tools">
<button type="button" data-move="-1" aria-label="Move left">←</button>
<button type="button" data-move="1" aria-label="Move right">→</button>
<button type="button" data-remove aria-label="Remove widget: Server">×</button>
</div>
<span class="demo-grip" aria-hidden="true">⠿</span>
<h4>⌁ Server</h4>
<div class="demo-server-numbers">
<span>
<strong>12<small>%</small>
</strong>CPU</span>
<span>
<strong>4.2<small> GB</small>
</strong>Memory</span>
</div>
<svg class="demo-chart" viewBox="0 0 320 55" aria-hidden="true">
<path d="M0 44 L20 40 L40 43 L60 18 L80 31 L100 26 L120 35 L140 13 L160 24 L180 20 L200 30 L220 9 L240 23 L260 17 L280 25 L300 12 L320 18"/>
</svg>
<button class="demo-resize" type="button" data-resize aria-label="Change size: Server">↘</button>
</article>
</div>
<div class="demo-dock" aria-label="Apps running">
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
<img src="__AIO_ASSET__/screenshots/light/catalog.png?v=app-store-20261102" data-preview-image="catalog" alt="Catalog — AIO application screenshot" width="1280" height="720" loading="lazy">
</div>
<div class="preview-panel" id="preview-panel-settings" role="tabpanel" aria-labelledby="preview-tab-settings" data-panel="settings" hidden>
<img src="__AIO_ASSET__/screenshots/light/settings.png?v=app-store-20261102" data-preview-image="settings" alt="Settings — AIO application screenshot" width="1280" height="720" loading="lazy">
</div>
</div>
<p class="preview-caption">Interactive preview · sample data<span aria-hidden="true"> · </span>
<span data-preview-status role="status">Preview only · nothing changes on your server</span>
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
<p>Try it: open Arrange widgets, then move, resize or add a card. This is a simplified demo, not your server.</p>
</div>
<noscript>
<p class="landing-note">With JavaScript disabled, the preview remains a static example. The guides and screenshots still work.</p>
</noscript>
<section class="landing-section" id="how-it-works">
<div class="section-heading">
<p class="eyebrow">FROM INSTALL TO EVERYDAY USE</p>
<h2>Easy to start. Room to grow.</h2>
</div>
<ol class="widget-steps">
<li><span class="step-number">1</span><div><h3>Install on your server</h3><p>Choose Docker, Unraid, Synology or TrueNAS below. Follow the guide for storage, permissions and starting AIO.</p></div></li>
<li><span class="step-number">2</span><div><h3>Choose your apps</h3><p>Create your administrator account and follow the setup wizard. Pick the media server and tools you need; add more later.</p></div></li>
<li><span class="step-number">3</span><div><h3>Let AIO connect them</h3><p>AIO configures supported connections, download clients and library folders. Your provider details and media sources remain yours to supply.</p></div></li>
<li><span class="step-number">4</span><div><h3>Make it your own</h3><p>Open your apps from one dashboard. Arrange widgets and configure backups, updates and advanced options when you need them.</p></div></li>
</ol>
<a class="landing-button primary" href="#install">Choose your server ↓</a>
<p><a class="landing-text-link" href="ADVANCED.md">Already running a media stack? Review the advanced guides before changing your setup.</a></p>
</section>
<section class="landing-section widget-section" id="widgets">
<div class="section-heading">
<p class="eyebrow">HOME, YOUR WAY</p>
<h2>Make room for what matters.</h2>
<p>Your Home screen is yours to arrange. Try the controls in the preview above, then do the same in AIO.</p>
<a href="#app-preview" class="landing-text-link" data-try-widgets>Try the widget demo ↑</a>
</div>
<ol class="widget-steps">
<li>
<span class="step-number">1</span>
<div>
<h3>Open the layout editor</h3>
<p>On Home, choose the four-block layout icon next to the page tabs. Widget handles and an editing toolbar appear.</p>
</div>
</li>
<li>
<span class="step-number">2</span>
<div>
<h3>Move things around</h3>
<p>Drag a widget to its new place. On a phone, drag its grip so you can still scroll the page.</p>
</div>
</li>
<li>
<span class="step-number">3</span>
<div>
<h3>Find the right size</h3>
<p>Drag the lower-right corner, or open a widget’s settings and choose a size. Remove a widget there too.</p>
</div>
</li>
<li>
<span class="step-number">4</span>
<div>
<h3>Add it. Make it yours.</h3>
<p>Choose Add widget, pick This size or Every size, then choose a widget. Changes save automatically; choose Done when finished.</p>
</div>
</li>
</ol>
<p class="section-footnote">Phone, tablet and desktop can each have their own layout. Empty widgets may disappear outside edit mode until their connected app has something to show.</p>
</section>
<section class="landing-section feature-row">
<div>
<p class="eyebrow">THE CATALOG</p>
<h2>The tools you love.<br>
<span class="gradient-text">One place to run them.</span>
</h2>
<p>Browse Discover, My apps and categories in the sidebar. Choose Open to launch an app; choose its name or icon to see its settings.</p>
<a class="landing-text-link" href="USAGE.md">Learn the dashboard →</a>
</div>
<figure class="feature-shot">
<img src="__AIO_ASSET__/screenshots/light/catalog.png?v=app-store-20261102" data-theme-image="catalog" alt="Catalog" width="1280" height="720" loading="lazy">
</figure>
</section>
<section class="landing-section feature-row reverse">
<div>
<p class="eyebrow">LESS FUSS. MORE CONTROL.</p>
<h2>Set it up once.</h2>
<p>Grouped settings with search. Find your profile and appearance under Personal, connections under Connections, and updates and backups under Maintenance.</p>
<a class="landing-text-link" href="USAGE.md#screens">Learn the dashboard →</a>
</div>
<figure class="feature-shot">
<img src="__AIO_ASSET__/screenshots/light/settings.png?v=app-store-20261102" data-theme-image="settings" alt="Settings" width="1280" height="720" loading="lazy">
</figure>
</section>
<section class="landing-section" id="install">
<div class="section-heading">
<p class="eyebrow">LET’S GET YOU SET UP</p>
<h2>Start with your server.</h2>
<p>Pick the name you recognise. We’ll take it from there, one step at a time.</p>
</div>
<div class="platform-grid">
<a class="platform-card" href="deploy/UNRAID.md">
<span class="platform-symbol" aria-hidden="true">▤</span>
<h3>Unraid</h3>
<p>Have an Unraid server? Start with the template and SSD download setup.</p>
<span class="platform-arrow" aria-hidden="true">↗</span>
</a>
<a class="platform-card" href="deploy/SYNOLOGY.md">
<span class="platform-symbol" aria-hidden="true">▥</span>
<h3>Synology</h3>
<p>Using a Synology NAS? Install Container Manager first, then create one project.</p>
<span class="platform-arrow" aria-hidden="true">↗</span>
</a>
<a class="platform-card" href="deploy/DOCKER.md">
<span class="platform-symbol" aria-hidden="true">▰</span>
<h3>Docker</h3>
<p>Running Docker elsewhere? Use the single-container setup.</p>
<span class="platform-arrow" aria-hidden="true">↗</span>
</a>
<a class="platform-card" href="deploy/TRUENAS.md">
<span class="platform-symbol" aria-hidden="true">▧</span>
<h3>TrueNAS</h3>
<p>Using TrueNAS SCALE? Follow the custom app setup.</p>
<span class="platform-arrow" aria-hidden="true">↗</span>
</a>
</div>
</section>
<section class="landing-section beginner-callout">
<span class="beginner-symbol" aria-hidden="true">✳</span>
<div>
<h2>New to this? Start here</h2>
<p>No need to know every app or every setting. The install guide explains what you need, what to click, and what you should see next.</p>
<a class="landing-button primary" href="INSTALL.md">Read the install guide ↗</a>
</div>
<p class="advanced-route-link"><a href="ADVANCED.md" class="landing-text-link">Advanced setup →</a></p>
</section>
<section class="landing-section landing-faq">
<div class="section-heading">
<p class="eyebrow">FAQ</p>
<h2>A few things worth knowing.</h2>
</div>
<details>
<summary>Do I need every app?</summary>
<p>No. Start with a media server and the tools you actually need. Add more later from Catalog.</p>
</details>
<details>
<summary>Where do my movies and shows go?</summary>
<p>They stay on your server. SSD download staging can speed up downloading and unpacking; the main library can stay on your HDDs.</p>
</details>
<details>
<summary>Do I need a VPN or public domain?</summary>
<p>Neither is required to start on your home network. Both can be configured later.</p>
</details>
<details>
<summary>Is this a working server in my browser?</summary>
<p>No. The dashboard is a visual demo with sample data. Catalog and Settings show real AIO screenshots. Nothing here connects to your server.</p>
</details>
</section>
<section class="landing-section landing-end">
<h2>Your media. A calmer home for it.</h2>
<p>Self-hosted. Open source. Built to bring your home media tools together.</p>
<a class="landing-button primary" href="INSTALL.md">Get started ↗</a>
<a class="landing-button" href="https://github.com/Qballjos/aio-media-server-manager">View on GitHub</a>
</section>
</div>
