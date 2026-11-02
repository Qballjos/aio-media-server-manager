# AIO gebruiken, stap voor stap

Begin hier zodra je AIO in je browser kunt openen. Laat eerst één app werken en voeg later toe wat je mist.

## 1. Rond je eerste installatie af

Maak het beheerdersaccount en doorloop de wizard. Begin bijvoorbeeld met Jellyfin om je eigen mediabestanden af te spelen. Laat VPN en toegang van buitenaf uit totdat alles thuis werkt. Wacht tot de gekozen app in Catalogus Actief / Running toont.

## 2. Leer de drie pagina’s kennen

| AIO | |
|---|---|
| Home / Start | Bekijk downloads, aankomende releases en serverinformatie. De widgets kun je zelf indelen. |
| Catalogus | Installeer apps, bekijk of ze actief zijn en open een app met Open. |
| Instellingen | Pas het uiterlijk van AIO, je account en updates aan. Hier voeg je geen films toe aan je mediaserver. |

**Header:** Start, Catalogus en Instellingen blijven gecentreerd over de volledige header. Op smalle schermen krijgen ze een eigen gecentreerde rij. De header scrollt mee met de pagina. Op Start staat de knop met vier blokjes rechts, naast je account. Alle app-pagina’s, bedieningselementen en labels gebruiken Figtree; als dat weblettertype niet kan laden, gebruikt de app overal dezelfde systeemlettertypen als terugval.

## De nieuwe catalogus gebruiken {#catalog-menu}

Open bovenaan **Catalogus**. Links kies je wat je wilt zien; rechts verschijnen de apps.

| Keuze links | Wat zie je? |
|---|---|
| **Ontdekken** | Uitgelichte apps en de volledige catalogus. |
| **Mijn apps** | Apps die je al hebt geïnstalleerd, ook als ze gestopt zijn. |
| **Actief** | Alleen apps die nu draaien. |
| **Beschikbaar** | Apps die je nog kunt installeren. |
| **Zoeken / Categorie** | Zoek op appnaam of kies een soort app. |

Boven de applijst kun je sorteren op Populariteit of A tot Z. Mis je een app? Wis de zoekopdracht en kies Ontdekken om de selectie op status of categorie weg te halen.

Beginnen met Jellyfin: zoek op Jellyfin. Kies **Installeren** als de app nog ontbreekt, wacht op **Actief / Running** en klik op **Open**. Is de app geïnstalleerd maar gestopt? Kies eerst **Start**. Open opent Jellyfin in een eigen browsertabblad.

Klik op de naam, het pictogram of de rij van een app om het **venster met app-instellingen** te openen. Dit opent niet de app zelf. Onder **⋯** staan onder andere Instellingen, Stoppen, Herstarten, Logs, Bijwerken en Verwijderen, afhankelijk van de appstatus. Sluit het venster met × of Escape. Sla alleen op als je die app wilt wijzigen.

**App-instellingen in Catalogus** gelden voor één app. De pagina **Instellingen** bovenaan is voor AIO zelf: je profiel, uiterlijk, koppelingen, back-ups en updates.

![Catalog: sidebar, app rows and Open buttons](screenshots/light/catalog.png?v=app-store-20261102)

## Je weg vinden in Instellingen {#settings-menu}

Instellingen gebruikt dezelfde indeling als de catalogus: een zijmenu links en de gekozen pagina rechts. Kies links een groep en onderdeel. Het zoekveld doorzoekt het menu, niet de opgeslagen instellingen. Scroll in het zijmenu voor de onderste groepen. Op een telefoon open je **Onderdelen van instellingen** en kies je daarna een pagina.

| Wat wil je aanpassen? | Kies deze pagina |
|---|---|
| Naam, profielfoto of wachtwoord | Persoonlijk → **Profiel** |
| Taal, thema of achtergrond | Persoonlijk → **Taal en uiterlijk** |
| App-balk of aanmeldtekst | Dashboard → **Startpagina** |
| Een app bijwerken | Onderhoud → **Updates** |
| Een instellingenback-up maken | Onderhoud → **Back-ups** |
| Ontdekken waarom een widget leeg is | Systeem → **Hulp en diagnose** |
| API-sleutels, tv of Homey koppelen | Verbindingen → **App-koppelingen** |

Het zijmenu opent alleen een pagina. Verander rechts de gewenste instelling en gebruik de knop **Opslaan** van dat onderdeel als die verschijnt. Widgets verplaats je op **Start** met de knop met vier blokjes; Startpagina-instellingen regelen de app-balk en aanmeldtekst.

![Settings: grouped sidebar and search](screenshots/light/settings.png?v=app-store-20261102)

## 3. Open je eerste app

Ga naar Catalogus, zoek Jellyfin en kies Open. Rond de eigen installatie van Jellyfin af als die daarom vraagt. Vraagt Jellyfin om bibliotheekmappen? Gebruik bij de standaardinstallatie /data/media/movies voor films en /data/media/tv voor series. Dit zijn de mediamappen die de platformgids al heeft gekoppeld. Maak geen tweede kopie omdat je NAS een ander pad toont.

**Controle: Jellyfin opent in een eigen browsertabblad. Zonder mediabestanden is een bibliotheek leeg; dat is normaal.**

## 4. Speel je eerste film af {#first-media}

Neem een filmbestand dat je zelf hebt, bijvoorbeeld MijnFilm.mp4. Kopieer het naar de **map movies op je server**, niet naar Downloads en niet naar het websitevoorbeeld.

| Server | Waar zet je het bestand? |
|---|---|
| Synology | Open DSM File Station → home → aio-media-manager → media → movies. Kies Uploaden en selecteer het bestand op je computer. |
| Unraid | Open de netwerkshare aio-media-manager en daarna media → movies. De laatste stap van de Unraid-gids legt uit hoe je die privéshare aanzet. |
| TrueNAS | Open de netwerkshare aio-media en daarna media → movies. Stap 7 van de TrueNAS-gids regelt de toegang. |
| Docker op Linux | Open op de server je persoonlijke map → aio-media-manager → media → movies. Vanaf een andere computer kun je via SSH kopiëren met scp, zoals hieronder. |

Voor een Linux-server op afstand voer je dit **op je computer** uit. Vervang het bestandspad, de gebruikersnaam en het server-IP. Het voorbeeld kopieert naar de standaardinstallatie in je persoonlijke map.

Een Windows-bestandspad ziet er bijvoorbeeld uit als `C:\Users\Alex\Videos\MijnFilm.mp4`; op een Mac kan dat `/Users/alex/Movies/MijnFilm.mp4` zijn. Laat de aanhalingstekens om je echte pad staan. Gebruik dezelfde servergebruiker en hetzelfde IP als bij je SSH-verbinding.

```bash
scp "/PATH/TO/YOUR/FILM.mp4" YOUR-USER@SERVER-IP:aio-media-manager/media/movies/
```

Een serie zet je in media/tv. Open na het kopiëren Jellyfin → Dashboard → Bibliotheken en kies Alle bibliotheken scannen / Scan All Libraries (of de scanoptie van je bibliotheek). Ga terug naar het beginscherm van Jellyfin, open de film en kies Afspelen.

**Controle: de film verschijnt en begint af te spelen. Verschijnt hij niet? Controleer of het bestand op de server in dezelfde map staat die je in Jellyfin hebt gekozen en scan opnieuw.**

## 5. De widgets op Home aanpassen {#customize-home}

<div class="widget-visual-guide" role="group" aria-label="De widgets op je hoofdpagina aanpassen">
<div class="widget-visual-step"><span class="visual-number">1</span><strong>De bewerkknop</strong><div class="visual-nav"><span class="visual-nav-pages"><span>Home</span><span>Catalog</span><span>Settings</span></span><span class="visual-nav-tools"><span class="visual-highlight"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="7" height="10" rx="1.5"/><rect x="14" y="3" width="7" height="6" rx="1.5"/><rect x="3" y="17" width="7" height="4" rx="1.5"/><rect x="14" y="13" width="7" height="8" rx="1.5"/></svg></span><span aria-label="Account">●</span></span></div><p>Ga naar Home en klik op het pictogram met vier blokjes rechts in de header, naast je account. Er verschijnen handgrepen en een bewerkbalk.</p></div>
<div class="widget-visual-step"><span class="visual-number">2</span><strong>Verplaatsen: sleep de handgreep</strong><div class="visual-widget"><span class="visual-grip">⠿</span><span class="visual-remove">×</span><strong>Downloads</strong><span class="visual-widget-line"></span><span class="visual-widget-line short"></span><span class="visual-corner">↘</span></div><p>Formaat: sleep deze hoek</p></div>
<div class="widget-visual-step"><span class="visual-number">3</span><strong>Kies wat je toevoegt</strong><div class="visual-toolbar"><span>＋ Widget toevoegen</span><span>Klaar</span></div><p>Kies Widget toevoegen, daarna Dit formaat of Elk formaat en vervolgens de widget. Wijzigingen worden automatisch opgeslagen; kies Klaar als je klaar bent.</p></div>
</div>

[De widgets op Home aanpassen](index.md#app-preview){ .md-button .md-button--primary }

Deze plaatjes leggen de echte bediening uit. Het websitevoorbeeld gebruikt fictieve gegevens en verandert niets aan jouw dashboard.

### Waarom is een widget leeg?

Controleer eerst in Catalogus of de bijbehorende app actief is. Recent toegevoegd heeft media in Jellyfin/Plex nodig; de agenda heeft geplande titels uit gekoppelde apps nodig. Een lege widget kan buiten de bewerkstand verdwijnen. Een widget toevoegen installeert niet automatisch de app die hij nodig heeft.

## 6. Waar zijn de andere apps voor?

| App | |
|---|---|
| Jellyfin / Plex | Je eigen mediabestanden afspelen. |
| Sonarr / Radarr | Series / films ordenen en gekozen downloads automatiseren. |
| SABnzbd / NZBGet | Downloaden via Usenet; hiervoor heb je zelf een provideraccount nodig. |
| qBittorrent | Torrents downloaden en delen. |
| Prowlarr | De zoekbronnen van de automatiseringsapps beheren. |

Je hebt niet alles nodig. Voeg een app via Catalogus toe als je weet waarvoor je die wilt gebruiken. De technische koppelingen staan onder Geavanceerd.

## 7. Apps bijwerken

Gebruik Instellingen → Updates voor de apps binnen AIO. AIO zelf bijwerken doe je apart in je NAS-/Docker-interface; daarvoor is de geavanceerde platformgids. Maak eerst een instellingenback-up via Instellingen → Back-ups voordat je een werkende opstelling verandert.

## Screenshots en technische naslag {#screens}

[Screenshots en technische naslag](USAGE_ADVANCED.md#screens).

### Controles, voortgang en herstel

Voor een installatie of handmatige update toont AIO controles voor opslag, onderhoud en downloadtoegang. Los een blokkade op voordat je doorgaat. **Catalogus → Installatievoortgang** toont de stappen en opent de live logs; je kunt het venster sluiten en opnieuw openen. Mislukt het instellen na een geslaagde installatie, dan probeert **Opnieuw proberen** alleen het starten en koppelen opnieuw.

Via **Instellingen → App-koppelingen → Mijn installatie controleren** lees je de daadwerkelijk opgeslagen koppelingen terug. **Auto-koppelen** past de automatische configuratie toe; de controle zelf wijzigt geen app-instellingen. Publieke startindexers vereisen een expliciete keuze.

**Instellingen → Back-ups** ondersteunt versleutelde HTTPS/WebDAV-kopieën en veilige hersteltests in een tijdelijke map. Bewaar het versleutelingswachtwoord buiten de server. **Instellingen → Meldingen** bevat opslaggrenzen en recente incidenten. De app-instellingen van Recyclarr hebben een **Handmatige configuratie** om eigen YAML exact te behouden.

Lees [installatiecontrole en herstel](operations.md) en [sessies, HTTPS en noodherstel](security-operations.md).

## Geavanceerd

Voor eigen koppelingen, VPN, sleutels en uitgebreide diagnose ga je naar de geavanceerde dashboardgids. [Geavanceerd](USAGE_ADVANCED.md).
