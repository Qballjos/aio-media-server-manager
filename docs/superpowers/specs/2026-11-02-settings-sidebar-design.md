# Instellingen met zijmenu

## Doel
Pas impressie 1 toe: een rustig instellingenvenster met gegroepeerde navigatie links en één onderwerp rechts. Verbeter vindbaarheid door bestaande opties te hernoemen en te verplaatsen.

## Benaderingen
1. Zijmenu met detailpagina: gekozen door de gebruiker; goed voor uitgebreide serverinstellingen.
2. Tegeloverzicht: geeft overzicht maar voegt een navigatiestap toe.
3. Compacte voorkeurenlijst: geschikt voor eenvoudige opties, minder geschikt voor complexe configuraties.

## Voorgestelde indeling
- **Persoonlijk**
  - Profiel: naam, gebruikersnaam, e-mail, avatar en wachtwoord.
  - Taal en uiterlijk: taal, thema, kleurmodus, achtergrond, transparantie en branding.
- **Dashboard**
  - Startpagina: app-dock en welkomsttekst op het aanmeldscherm.
- **Verbindingen**
  - VPN: provider, protocol, configuratie en bestaande verbindingsacties.
  - Externe toegang: Cloudflare Tunnel, publieke hostnamen en toegangsregels.
  - App-koppelingen: Jellyfin- en Seerr-sleutels en bestaande tv-koppelingen.
  - Usenet: provider, server en downloadclients.
- **Onderhoud**
  - Updates: controle, installatieplanning en GitHub-toegang.
  - Back-ups: planning, bewaartermijn, downloaden en herstellen.
  - Meldingen: e-mail, Discord en gebeurteniskeuze.
- **Systeem**
  - Server en opslag: tijdzone, logniveau, bestandsrechten, systeeminfo en opslagpaden.
  - Hulp en diagnose: widgetproblemen, tijdelijke ondersteuningslink en recente fouten.
  - Over deze app: installatie op dit apparaat en bestaande donatielinks.

## Presentatie en gedrag
Desktop: vastblijvend zijmenu met pictogrammen en duidelijke actieve markering, daarnaast paginatitel, korte uitleg en rustige compacte secties. Mobiel: inklapbare categorienavigatie boven de inhoud. Bestaande lichte en donkere thema's en accentkleuren blijven ondersteund.

Een zoekveld filtert de navigatie op paginanamen en relevante trefwoorden. Heldere labels vervangen technische of onduidelijke namen, met vertalingen voor de bestaande talen.

Bestaande opslagacties blijven per logisch formulier werken; directe schakelaars blijven direct opslaan. Geen algemene opslagbalk die ten onrechte suggereert dat losse serveracties één transactie vormen. Gevoelige en geavanceerde velden behouden hun validatie en uitleg. Bestaande instellingenlinks krijgen een passende doorverwijzing.

## Grenzen
Geen nieuwe backendfuncties, verzonnen verbindingsopties of wijziging van opgeslagen waarden. Werk in deze checkout; reeds aanwezige wijzigingen buiten deze taak blijven intact.

## Verificatie
Controleer navigatie en oude links, zoekfunctie, behoud van formulieren en acties, vertalingen, frontendtests en productiebuild. Controleer waar mogelijk de weergave op desktop en mobiel, in licht en donker.
