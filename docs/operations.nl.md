# Installatiecontrole, externe back-ups en herstel

## Controleer de koppelingen

Open **Instellingen → App-koppelingen → Mijn installatie controleren**. AIO leest
de opgeslagen bibliotheekmappen, downloadclients, indexersynchronisatie en
standaard aanvraagdoelen in Seerr terug. De controle wijzigt geen instellingen
en downloadt geen media. Een eigen configuratie kan bewust afwijken.

Een gestopte app of ontbrekende API-sleutel levert een fout met uitleg op. Start
de betrokken apps en kies **Auto-koppelen** om de bestaande automatische
configuratie opnieuw toe te passen. Controleer opnieuw zodra dit klaar is.

De startset publieke torrentindexers staat standaard uit. Kies deze expliciet
in de wizard of bij App-koppelingen en start daarna Auto-koppelen. Uitschakelen
verwijdert geen bestaande indexers. Je kunt eigen bronnen blijven beheren in
Prowlarr. Verwijderde startindexers worden niet opnieuw toegevoegd.

## Vóór installeren en bijwerken

Bij installeren vanuit Catalogus en handmatige updates toont AIO eerst de
opslag-, onderhouds- en downloadcontroles. De server controleert dit opnieuw
voordat een app wordt gewijzigd. De opslag voor instellingen, apps, tijdelijke
bestanden, back-ups, downloads en media moet beschrijfbaar zijn en standaard
minimaal 512 MiB vrij hebben. Dit is een ondergrens, geen schatting van de
uiteindelijke grootte van een app. Pas de ondergrens desgewenst aan met
`AMM_PREFLIGHT_MIN_FREE_MB` op de server.

GitHub-toegang en de beschikbare API-aanvragen worden met begrensde wachttijden
gecontroleerd. Kan de controle niet worden afgerond, dan verschijnt een
waarschuwing: een download uit de cache of vanaf een andere bron kan nog werken.
Te weinig ruimte, een uitgeput GitHub-quotum, conflicterend onderhoud of een
vereiste herstart blokkeren de handeling.

**Catalogus → Installatievoortgang** toont stappen en tijdstippen. Via **Logs
bekijken** open je de bestaande live-logviewer. Sluit het venster gerust en open
het later opnieuw. **Opnieuw proberen** herhaalt een mislukte installatie; als
de app al geïnstalleerd is, worden alleen starten en koppelen herhaald. Los een
onvolledige rollback eerst op. Per app blijven de laatste 100 stappen bewaard
tot de manager opnieuw start.

## Eigen Recyclarr-configuratie beschermen

Open **Catalogus → Recyclarr → Instellingen** en schakel **Handmatige
configuratie** in. Bewerkte YAML opslaan schakelt deze modus ook automatisch in.
De YAML blijft dan exact behouden, inclusief adressen en API-sleutels, bij
Auto-koppelen, synchroniseren en herstarten. Schakel de handmatige modus
expliciet uit om profielen opnieuw te genereren of de standaardconfiguratie
terug te zetten. Pas in de handmatige modus gewijzigde adressen en sleutels zelf
aan. Eerder opgeslagen handmatige bewerkingen worden als handmatige modus herkend.

## Versleutelde HTTPS/WebDAV-back-ups

Ga naar **Instellingen → Back-ups → Versleutelde externe back-ups**.

1. Maak op een andere server een WebDAV-map, bijvoorbeeld bij Nextcloud of op
   een externe NAS. De gebruikte account moet bestanden kunnen uploaden en lezen.
2. Vul het HTTPS-adres van de map en de inloggegevens in. Zet geen wachtwoord,
   queryparameters of fragment in het adres. TLS-certificaten worden altijd
   gecontroleerd; doorverwijzingen worden geweigerd.
3. Kies een versleutelingswachtwoord van minimaal 16 tekens en **bewaar een kopie
   buiten deze server**. Een vervangende server heeft hetzelfde wachtwoord nodig.
   Na een wachtwoordwijziging blijven oudere kopieën hun oude wachtwoord vereisen.
4. Schakel **Nieuwe back-ups automatisch exporteren** in en sla op. Nieuwe
   handmatige en geplande back-ups worden daarna extern gekopieerd. Vul voor een
   bestaande lokale back-up de bestandsnaam in en kies **Versleutelde kopie
   exporteren**.

De versleuteling gebeurt vóór verzending met AES-256-GCM en een per archief
met PBKDF2-HMAC-SHA256 afgeleide sleutel: 600.000 iteraties, een willekeurige salt
en nonce. Het externe bestand eindigt op `.tar.gz.aioenc`. Na het uploaden haalt
AIO de versleutelde kopie opnieuw op en vergelijkt het de controlegetallen.
Inloggegevens en het versleutelingswachtwoord staan in de versleutelde
sleutelopslag en worden niet teruggegeven door de instellingen-API.

De bestandslimiet is 20 GiB. Verbindings- en leeswachttijden zijn begrensd. Het
lokale bewaarbeleid blijft gelden. **Externe kopieën worden niet automatisch
opgeruimd**; stel daarvoor een bewaarbeleid in op de WebDAV-server. Bewaar de
externe bestandsnamen bij je herstelnotities. AIO doorzoekt de externe map niet.

Een mislukte overdracht laat de lokale back-up beschikbaar en verschijnt als
fout bij Back-ups en in de incidentgeschiedenis. Een lokale back-up die lukt,
wordt niet ten onrechte als een geslaagde externe kopie gemeld.

### Herstel oefenen

1. Stel op de herstellende manager dezelfde bestemming en het oorspronkelijke
   versleutelingswachtwoord in. Automatisch exporteren hoeft hiervoor niet aan.
2. Vul de exacte `.tar.gz.aioenc`-naam in en kies **Externe kopie importeren**.
3. AIO downloadt, ontsleutelt en controleert het bestand. Het krijgt een nieuwe
   lokale naam; een bestaande back-up wordt niet overschreven.
4. Vul de geïmporteerde `.tar.gz`-naam in en kies **Herstel veilig testen**. De
   bestanden worden in een tijdelijke map uitgepakt en met het manifest
   vergeleken. Actieve apps en instellingen blijven ongemoeid.
5. Kies voor echt herstel de geïmporteerde back-up in de gewone back-uplijst.
   Vernieuw die lijst zo nodig. Dit blijft een afzonderlijke handeling.

Een geslaagde hersteltest controleert het archiefherstel, niet of elke externe
app op een vervangende server kan starten. Controleer daar ook rechten, gekoppelde
mappen en app-versies. AIO benadert geen WebDAV-bestemming totdat je deze hebt
ingesteld en een import/export aanvraagt of automatisch exporteren inschakelt.

## Meldingen en incidentgeschiedenis

Bij **Instellingen → Meldingen** stel je de opslaggrenzen voor waarschuwing en
herstel in. De herstelgrens moet lager zijn om herhaalde meldingen rond één
percentage te voorkomen. Voor mislukte back-ups, overdrachten, hersteltests en
updates zijn er aparte keuzes voor de bestaande e-mail- en Discordkanalen.

**Recente incidenten** bewaart de laatste 100 gebeurtenissen, ook na een
herstart en wanneer de verzendkanalen uitstaan. De kanaalkeuzes bepalen of een
melding wordt verstuurd; ze wissen de lokale geschiedenis niet. Kies
**Vernieuwen** om nieuwe gebeurtenissen op te halen.
