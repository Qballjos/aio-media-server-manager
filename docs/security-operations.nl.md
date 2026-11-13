# Beheersessies, HTTPS en noodherstel

## Beheersessies

Beheersessies worden lokaal geregistreerd en blijven na een herstart geldig.
Uitloggen trekt de betreffende sessie in, inclusief kopieën van het toegangstoken.
Een wachtwoordwijziging maakt alle eerdere beheersessies ongeldig; een gewijzigde
beheerdersnaam maakt eerdere tokens ook ongeldig. Na bijwerken vanaf een versie
zonder sessieregistratie moet je opnieuw inloggen.

Tv- en Homey-koppelingen houden hun eigen intrekbare toegang. Sessieregistraties
worden niet in configuratieback-ups opgenomen.

## HTTPS en proxy’s

Zet `AMM_SECURE_COOKIES=true` in de serveromgeving als je de manager via HTTPS
opent, ook achter een reverse proxy of Cloudflare Tunnel. De sessie- en
CSRF-cookies worden dan alleen via HTTPS verstuurd. De standaardwaarde `false`
ondersteunt HTTP op het lokale netwerk.

Stel `AMM_TRUSTED_PROXIES` alleen in op de adressen van de daadwerkelijke proxy’s
en dwing HTTPS op die proxy af. Doorgestuurde headers veranderen de
cookiebeveiliging niet automatisch. Herstart de manager na het aanpassen van
deze omgevingsvariabelen.

## VPN-profielen opslaan

Geüploade en geplakte VPN-profielen worden alleen binnen `AMM_CONFIG_DIR/vpn`
geschreven. Externe paden, `..` en symlinkroutes naar buiten worden vooraf geweigerd.
Vervanging gebeurt atomisch met een privébestand met rechten `0600`.
Externe profielen blijven selecteerbaar via `AMM_VPN_CONFIG` of het padveld in
Instellingen, maar kunnen niet via uploaden worden overschreven.

## Bestanden met inloggegevens van applicaties

De INI van SABnzbd en de YAML van Recyclarr bevatten leesbare inloggegevens die
deze applicaties nodig hebben. De manager schrijft via privébestanden en vervangt
de configuratie atomisch met rechten `0600`, met behoud van de bestaande eigenaar.
Bij het starten houdt SABnzbd PUID/PGID als eigenaar en krijgt alleen de eigenaar
toegang tot het bestand. Bestaande bestanden krijgen deze rechten wanneer de
manager ze opnieuw configureert. De inhoud wordt hiermee niet versleuteld.
Bescherm ook het configuratievolume en de back-ups daarvan.

Bij fouten in back-ups en applicatie-instellingen geeft de API veilige uitleg
in plaats van ongecontroleerde foutdetails. Bewuste debugrapporten achter een
toegangstoken behouden hun eigen diagnose- en afschermingsgedrag.

## Back-ups herstellen zonder werkend account

Back-upbeheer vereist een beheerderslogin, ook op een nieuwe server. Maak op
een nieuwe server eerst het account aan om de gewone back-upinterface te gebruiken.
Een onleesbaar accountbestand, of een ontbrekend bestand terwijl er al een
sessiegeheim bestaat, kan niet via de openbare accountinstallatie worden vervangen.

Voor noodherstel kan de serverbeheerder `AMM_BACKUP_RECOVERY_TOKEN` instellen op
een willekeurig geheim van minimaal 32 tekens en de manager herstarten. Stuur dit
mee in de HTTP-header `X-AIO-Recovery-Token`. Dit werkt alleen zolang de manager
een beheerdersaccount nodig heeft en staat het volgende toe:

- Back-ups en details bekijken, en de voortgang opvragen.
- Een archief uploaden, controleren en herstellen.

Een back-up aanmaken, downloaden of verwijderen is met deze herstelcode niet
toegestaan. Dit is een herstelroute via de API; de gewone interface stuurt deze
header niet mee. Gebruik HTTPS of een lokale verbinding, verwijder de variabele
na herstel en herstart de manager. Zodra een werkend account is hersteld,
verleent de herstelcode geen toegang meer. Zet de code niet in adressen of logs.

## Bescherming tijdens herstel en updates

AIO controleert de gekozen archiefpaden vóór het verwijderen van SQLite-
bijbestanden en vóór het schrijven van configuratie. Absolute paden, paden die
naar boven ontsnappen en ontsnappende symbolische koppelingen worden geweigerd.

Na een mislukte update worden programmaherstel, configuratieherstel en procesherstel
apart gerapporteerd. Een behouden `.APP.pre-update`-installatie moet de beheerder
eerst controleren en afhandelen voordat een nieuwe update deze mag vervangen.
Het resultaat vermeldt de herstelkopie en de configuratiesnapshot. Als de
archiefactivatie én het terugplaatsen mislukken, blijft ook de
`.APP.previous-*`-kopie bewaard.

Zie [externe back-ups en hersteltests](operations.md) voor een herstelprocedure.
