# Het dashboard gebruiken

Deze gids is voor nadat AIO is geïnstalleerd en je de webinterface kunt openen.

!!! success "Doel"
    Rond de wizard af voor de apps die je nodig hebt, gebruik Start dagelijks en gebruik **Interface openen** in de catalogus wanneer je het scherm van die tool wilt.

Standaardadres op je thuisnetwerk:

```text
http://YOUR-SERVER-IP:8080
```

Vervang het IP (en de poort, als je die hebt gewijzigd).

---

## Eerste keer

1. Maak het **beheerders**account wanneer daarom wordt gevraagd (gebruikersnaam, **e-mail**, wachtwoord).
2. Rond de wizard van de eerste start af: de apps die je wilt, een Usenet-server als je die gebruikt, optioneel VPN en een optionele Cloudflare Tunnel. De wizard installeert die keuze. De tunnel en de VPN starten meteen als de wizard klaar is, als je ze hebt aangezet.
3. Na het opnieuw aanmaken van de container antwoordt het dashboard terwijl apps nog starten. Met VPN aan wachten qBittorrent, Prowlarr en Flaresolverr tot de WireGuard-handshake klaar is (AIO probeert de VPN opnieuw als de eerste poging mislukt). Cloudflare Tunnel start als laatste, nadat de apps antwoorden, zodat cloudflared geen connection refused logt tegen origins die nog niet luisteren.
4. Wacht tot **Catalogus** die apps als **actief** toont. Gebruik **Interface openen** voor alles wat nog een eigen account heeft (Plex, Jellyfin, NZBGet).
5. Voeg later meer toe vanuit **Catalogus**. Je hebt niet elke app nodig.

Begin klein (bijvoorbeeld Radarr + één downloadclient + Jellyfin) en voeg de rest daarna toe.

---

## Start

Start is een raster. Telefoon, tablet en desktop houden elk hun eigen indeling (4, 8 en 12 kolommen). De indelingsknop op het tabblad Start verplaatst, vergroot, voegt toe en verwijdert widgets. **Instellingen → Startpagina** toont of verbergt de app-balk, zet de aanmeldtekst en bewaart een Jellyfin- of Seerr-API-sleutel als Start die zelf niet kan lezen.

| Widget | Wat hij toont |
|--------|----------------|
| Begroeting | Moment van de dag |
| Zoeken | Zoeken in Seerr |
| Kalender | Aankomende afleveringen en films. Een seizoen dat op één dag valt, is één regel |
| Downloaden | Actieve downloads, met alles pauzeren / alles hervatten. Vastgelopen items kun je verwijderen |
| Recent toegevoegd | Nieuwe series en films. Scrollen laadt verdere Jellyfin-pagina’s. Plex blijft bij de laatste 20 |
| Aanvragen | Seerr-aanvragen die nog niet klaar zijn, plus wat de laatste 30 dagen als beschikbaar of afgewezen is gemarkeerd |
| Trending | De trendinglijst van Seerr. Scrollen blijft laden |
| Wordt afgespeeld | Wie kijkt op Jellyfin of Plex, inclusief direct afspelen |
| Opslag | Schijfgebruik van config, downloads en media |
| Server | CPU, geheugen en netwerk. Met host-`/sys` gemount op `/host/sys` zijn dit de netwerkkaarten van de server. Zonder die mount is het alleen het verkeer van deze container |
| Aandacht nodig | Dezelfde controles als Instellingen → Meldingen, met een link om elk punt op te lossen |

Installeren, starten, stoppen en **Interface openen** staan in **Catalogus**. De balk onderaan Start opent apps die al geïnstalleerd zijn.

**Interface openen** op het LAN ziet er meestal uit als `http://YOUR-SERVER-IP:8989` (voorbeeld voor Sonarr).  
Als je publieke Cloudflare-hostnamen hebt ingesteld, kan **Interface openen** in plaats daarvan `https://sonarr.yourdomain.com` gebruiken — zie [Cloudflare Tunnel](deploy/CLOUDFLARE.md).

---

## Wat de wizard koppelt

Als een app gezond is — of als je op **Auto-koppelen** klikt — zet AIO downloadmappen en categorieën, hoofdmapen en downloadclients in Sonarr, Radarr en Lidarr, Prowlarr-sync, Seerr, Bazarr-koppeling en startconfiguraties voor Recyclarr en NeutArr. **Instellingen → Usenet** bewaart de nieuwsserver en stuurt die naar SABnzbd en NZBGet. Prowlarr krijgt ook een startset publieke indexers. Verwijder wat je niet wilt; ze worden niet opnieuw toegevoegd.

Houd **downloads** en **media** op hetzelfde volume, zodat voltooide bestanden kunnen **hardlinken**.

Nog zelf af te maken:

- Een Plex-account.
- Het setup-token van de eerste start van NeutArr (hieronder), tot dat account bestaat.
- Aanmelden bij Jellyfin en NZBGet. Op het LAN meldt **Interface openen** je al aan bij Sonarr, Radarr, Lidarr, Prowlarr, qBittorrent, SABnzbd, Bazarr en Seerr als de beheerder van de manager. Publieke hostnamen tonen altijd de eigen aanmelding van de app.
- De beheerder en de wizard van de eerste start van Seerr worden voor je afgerond vanuit die gedeelde login (via Jellyfin, of een geclaimde Plex).

VPN, Cloudflare Tunnel, Recyclarr, NeutArr en back-ups zijn optioneel.

### Setup-token van de eerste start van NeutArr

De eerste keer dat NeutArr start, voordat het een account heeft, vraagt het om een eenmalig setup-token.

1. Wacht tot NeutArr **actief** is.
2. Open **Catalogus → NeutArr → Instellingen**.
3. Kopieer **Token voor de eerste start** en plak het in het setupscherm van NeutArr.

Die waarde is het bestand `/config/neutarr/.setup-token` in het apparaat (de hostmap die als `/config` is gemount). NeutArr verwijdert het bestand nadat het account is aangemaakt, en het veld in Instellingen wordt leeg. Tot NeutArr is gestart, blijft het veld leeg.

---

## De interface van elke app openen

| Situatie | Wat je gebruikt |
|-----------|-------------|
| Thuis op wifi | **Interface openen** → `http://IP:PORT` |
| Buiten huis met Cloudflare | **Interface openen** → `https://subdomain.yourdomain.com` |
| Je hebt de luisterpoort van een app gewijzigd | AIO werkt gepubliceerde routes bij; maak de container opnieuw aan als LAN-links er nog verkeerd uitzien. De poort van de manager zelf is compose/env (`AMM_API_PORT`), te zien bij **Instellingen → Systeem** |

Als **Interface openen** faalt:

- Is de app **actief** in de catalogus?
- Zit je op hetzelfde netwerk (voor LAN-links)?
- Voor HTTPS-links: is de tunnel verbonden en is **Publiceren** gelukt? ([Cloudflare-gids](deploy/CLOUDFLARE.md))

---

## Instellingen die je echt gebruikt

Namen in de interface kunnen kort zijn; dit is wat ze in de praktijk betekenen.

| Onderdeel | Waarom het ertoe doet |
|---------|----------------|
| **Account** | Gebruikersnaam, e-mail en wachtwoord van de beheerder. Apps met een lokale login gebruiken hetzelfde account |
| **Weergave** | Thema, accent, achtergrond, titel, icoon in de balk, aanmeldlogo en favicon |
| **Systeem** | Tijdzone, logniveau, PUID/PGID en de AIO-versie. Opslagpaden staan hier; mounts wijzig je in compose, niet in dit scherm. De luisterpoort van de manager is alleen compose/env |
| **Updates** | Updates van geïnstalleerde apps controleren en toepassen, één voor één of allemaal. Schema’s staan standaard **uit**. Een nieuwere AIO-image is alleen een melding — ophalen en opnieuw aanmaken op de host |
| **Back-ups** | Config-back-up, controleren, herstellen per app en een schema |
| **Netwerk** | VPN voor qBittorrent, Prowlarr en Flaresolverr (Usenet blijft erbuiten), met een lokale DNS-cache voor die apps zodat korte tunnelhaperingen Prowlarr-indexers niet offline gooien; Cloudflare Tunnel (start na de apps bij boot); publieke subdomeinen; en vertrouwde proxy’s |
| **Meldingen** | Discord-webhook en e-mail als een app blijft crashen, de VPN of tunnel wegvalt, er een update is, of een schijf over 90% vol is |
| **Usenet** | Nieuwsserver (host, poort, SSL, login, verbindingen), gestuurd naar SABnzbd en NZBGet. NZB-indexers voeg je toe in Prowlarr |
| **Startpagina** | Aanmeldtekst, app-balk en Jellyfin- / Seerr-API-sleutels als Start ze niet kan lezen |
| **Diagnose** | Waarom een Start-widget leeg is. API-sleutels worden nooit getoond. **Ondersteuningslink** is tijdelijke hulp op afstand — laat die **uit**, tenzij je samen met iemand die je vertrouwt aan het debuggen bent |

Geef apps na een belangrijke netwerk- of poortwijziging even de tijd om te herladen — of herstart AIO als links verouderd blijven.

## Schermen {#screens}

Licht staat links, donker rechts. Start is hier leeg omdat er nog geen app met een webinterface is geïnstalleerd. App-instellingen in de catalogus zijn het venster dat je vanaf een cataloguskaart opent (dit is qBittorrent).

### Account

| Licht | Donker |
| --- | --- |
| ![Account in Instellingen, licht thema](screenshots/light/settings.png) | ![Account in Instellingen, donker thema](screenshots/dark/settings.png) |

### Weergave

| Licht | Donker |
| --- | --- |
| ![Weergave, licht thema](screenshots/light/settings-visuals.png) | ![Weergave, donker thema](screenshots/dark/settings-visuals.png) |

### Systeem

| Licht | Donker |
| --- | --- |
| ![Systeeminstellingen, licht thema](screenshots/light/settings-system.png) | ![Systeeminstellingen, donker thema](screenshots/dark/settings-system.png) |

### Updates

| Licht | Donker |
| --- | --- |
| ![Updates, licht thema](screenshots/light/settings-updates.png) | ![Updates, donker thema](screenshots/dark/settings-updates.png) |

### Back-ups

| Licht | Donker |
| --- | --- |
| ![Back-ups, licht thema](screenshots/light/settings-backups.png) | ![Back-ups, donker thema](screenshots/dark/settings-backups.png) |

### Netwerk

| Licht | Donker |
| --- | --- |
| ![Netwerkinstellingen, licht thema](screenshots/light/settings-network.png) | ![Netwerkinstellingen, donker thema](screenshots/dark/settings-network.png) |

### Meldingen

| Licht | Donker |
| --- | --- |
| ![Meldingen, licht thema](screenshots/light/settings-notifications.png) | ![Meldingen, donker thema](screenshots/dark/settings-notifications.png) |

### Usenet

| Licht | Donker |
| --- | --- |
| ![Usenet-instellingen, licht thema](screenshots/light/settings-usenet.png) | ![Usenet-instellingen, donker thema](screenshots/dark/settings-usenet.png) |

### Startpagina

| Licht | Donker |
| --- | --- |
| ![Startpagina-instellingen, licht thema](screenshots/light/settings-homepage.png) | ![Startpagina-instellingen, donker thema](screenshots/dark/settings-homepage.png) |

### Diagnose

| Licht | Donker |
| --- | --- |
| ![Diagnose, licht thema](screenshots/light/settings-diagnostics.png) | ![Diagnose, donker thema](screenshots/dark/settings-diagnostics.png) |

### App-instellingen in de catalogus

| Licht | Donker |
| --- | --- |
| ![qBittorrent-instellingen in de catalogus, licht thema](screenshots/light/catalog-settings.png) | ![qBittorrent-instellingen in de catalogus, donker thema](screenshots/dark/catalog-settings.png) |

---

## Back-ups

- Gebruik de ingebouwde back-up als je een opstelling hebt die je wilt houden.
- Maak ook een back-up van de map **config** op de host (en van de backups-mount als je die gebruikt).
- Mediabestanden staan apart — back die up met je gewone NAS- of schijfstrategie.

---

## Apps bijwerken tegenover AIO bijwerken

| Wat | Hoe |
|------|-----|
| **AIO zelf** (dashboard + supervisor) | Haal een nieuwe Docker-image op en **maak de container opnieuw aan** ([Installeren](INSTALL.md)). Instellingen → Updates zegt alleen wanneer `:latest` is verschoven |
| **Geïnstalleerde apps** (Sonarr, Seerr en de rest) | **Instellingen → Updates**. Werk één app of allemaal bij. De voortgang staat daar, en Catalogus en Start tonen **Bezig met bijwerken…**. Het dashboard blijft antwoorden. Schema’s staan standaard **uit** |

De image werkt die apps niet vanzelf bij. Lees de release-opmerkingen op GitHub als er iets groots is veranderd.

---

## Veelvoorkomende haperingen

| Probleem | Probeer dit |
|---------|----------|
| Leeg scherm of aanmeldlus bij een app | Wis de sitegegevens van die URL; controleer of de app draait |
| NeutArr vraagt om een setup-token | **Catalogus → NeutArr → Instellingen** nadat NeutArr draait. Het token verdwijnt zodra het NeutArr-account bestaat |
| Rechtenfouten bij het schrijven van bestanden | De eigenaar van de hostmap moet overeenkomen met de containergebruiker (`PUID`/`PGID`) |
| Sonarr importeert maar kopieert bestanden | Downloads en media moeten één bestandssysteem delen voor hardlinks |
| Werkt thuis, niet op mobiele data | Tunnel nodig (+ bij voorkeur Access); LAN-IP’s zijn niet bereikbaar via mobiele data |
| Twee Sonarrs die botsen | Verwijder een extra Sonarr-container; alleen AIO mag hem draaien |
| De servergrafiek telt alleen deze container | Mount host-`/sys` alleen-lezen op `/host/sys` en maak opnieuw aan ([Docker](deploy/DOCKER.md)) |
| Recent toegevoegd van Jellyfin lijkt kort | Scroll de rij — er worden meer pagina’s geladen. Blijft de rij leeg, zet dan een Jellyfin-API-sleutel bij **Instellingen → Startpagina** |
| Recent toegevoegd van Plex stopt bij 20 | Die lijst is de laatste 20 van Plex |
| qBittorrent / Prowlarr / Flaresolverr blijven gestopt na boot | VPN staat aan zonder live handshake. Kijk bij **Instellingen → Netwerk**; AIO probeert de tunnel opnieuw en start die apps als hij omhoog is. Een handmatige VPN-**Stop** annuleert die poging |
| Prowlarr-indexers niet beschikbaar / RSS-fouten | Vaak een DNS-timeout via de VPN. Maak na een AIO-update de container opnieuw aan, klik daarna **Test All** in Prowlarr (en test opnieuw in Sonarr/Radarr) zodat de oude fout-backoff weg is. Een debug-share toont hits van de VPN-DNS-cache en fouten per resolver |
| cloudflared logt connection refused bij boot | Verwacht op oudere images toen de tunnel vóór de apps startte. Huidige images starten Cloudflare als laatste; maak opnieuw aan vanaf een actuele `nightly` / `latest` |

---

## Volgende stappen

- Checklist voor een nieuwe installatie: [Installeren](INSTALL.md)  
- Toegang van buitenaf: [Cloudflare Tunnel](deploy/CLOUDFLARE.md)  
- De deur op slot voor publieke URL’s: [Cloudflare Access](deploy/CLOUDFLARE_ACCESS.md)
