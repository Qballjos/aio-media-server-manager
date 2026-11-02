# Beta-review: verbeterpunten

Beoordeelde basis: branch `beta`, commit `e409be3`.

Dit is een puntenlijst op basis van statische broncodecontrole. De genoemde
foutpaden zijn niet als live aanval of storing gereproduceerd. Alle punten
staan open; dit document voert geen oplossingen door. Regelverwijzingen gelden
voor de beoordeelde commit.

## Prioriteit 1 — beveiliging en herstel

- [ ] **Backupbeheer tijdens setup beveiligen.**
  - Bron: `api/routers/backups.py:40–42`, upload/download/restore/delete.
  - Zolang setup vereist is, wordt authenticatie overgeslagen. Dit geldt ook
    wanneer de authenticatieconfiguratie ontbreekt of onleesbaar/corrupt is.
  - Risico: een partij die de API in die toestand kan bereiken, kan backups
    downloaden, uploaden, herstellen of verwijderen.
  - Aanpak: afzonderlijke herstelmodus met bootstrapbewijs en begrensde toegang.
  - Acceptatie: zonder bewijs geen backupbeheer vóór setup; na setup alleen
    geauthenticeerde beheerders. Test ook corrupte en ontbrekende authconfiguratie.

- [ ] **Restorepaden valideren vóór elke filesystembewerking.**
  - Bron: `core/backup_manager.py:460–465`.
  - SQLite-bijbestanden worden verwijderd voordat de extractiefilter het
    archiefpad controleert. Traversal of absolute paden kunnen hierdoor buiten
    de configuratiemap uitkomen, binnen de rechten van het backendproces.
  - Aanpak: containment en toegestane paden controleren vóór verwijderen,
    extractie en eigenaarswijzigingen; bestaande symlinkouders meenemen.
  - Acceptatie: kwaadaardige archieven kunnen geen bestanden buiten de
    configuratiemap wijzigen of verwijderen, ook geen SQLite-bijbestanden.

- [ ] **Restart-watcher bestand maken tegen fouten per applicatie.**
  - Bron: `core/supervisor.py:562–578`.
  - Andere startfouten dan `VpnIsolationError` beëindigen de gezamenlijke watcher.
  - Aanpak: fouten per proces afhandelen, expliciete foutstatus bewaren en een
    volgende poging plannen zonder andere apps hun bewaking te ontnemen.
  - Acceptatie: een ontbrekend executable bij één app verhindert de automatische
    herstart van een andere app niet; VPN-weigeringen blijven veilig afgehandeld.

- [ ] **Vorige installatie behouden wanneer rollback mislukt.**
  - Bron: `core/installer/installer.py:544–568`.
  - De `finally`-opruiming verwijdert de vorige installatie ook als het
    terugplaatsen daarvan mislukt.
  - Aanpak: de herstelkopie alleen verwijderen na bevestigde activatie of
    bevestigd herstel. Bij herstelproblemen de kopie en locatie behouden.
  - Acceptatie: foutinjectie op activatie én terugplaatsen laat een intacte,
    vindbare herstelkopie achter.

## Prioriteit 2 — betrouwbaarheid en sessiebeveiliging

- [ ] **Synchrone updatechecks van de API-eventloop halen.**
  - Bron: `core/update_schedule.py:297,338,357`; netwerkwerk in
    `core/installer/github.py`.
  - Risico: langzame HTTP-aanroepen en retries houden API en bewaking op.
  - Aanpak: workerthreads of async HTTP gebruiken, met begrensde timeouts.
  - Acceptatie: API en bewaking blijven responsief bij vertraagde of falende
    updatechecks, inclusief rate limiting.

- [ ] **Gedeeltelijk of mislukt herstel eerlijk rapporteren.**
  - Bron: `core/updater.py:134–155`.
  - Na fouten bij configuratieherstel of herstart wordt toch `rolled_back`
    geretourneerd met de melding dat de vorige versie terugstaat.
  - Aanpak: aparte statussen voor volledig herstel, gedeeltelijk herstel en
    `rollback_failed`; binary-, configuratie- en processtatus onderscheiden.
  - Acceptatie: falend snapshotherstel of falende herstart kan niet als volledig
    geslaagde rollback eindigen. Test met een daemon en post-update healthcheck.

- [ ] **Beheersessies server-side kunnen intrekken.**
  - Bron: `core/auth.py:32,178–189,221–225,288–307`;
    `api/routers/auth.py:189–193`.
  - Een reeds buitgemaakt JWT blijft na wachtwoordwijziging en logout geldig
    tot zijn vervaldatum; de huidige geldigheid is zeven dagen.
  - Aanpak: sessierevocation of een gecontroleerde account-/tokenversie.
  - Acceptatie: beveiligingswijzigingen trekken oude tokens in volgens een
    expliciet beleid; logout maakt de betreffende sessie ongeldig.

- [ ] **Secure-cookies voor HTTPS ondersteunen.**
  - Bron: `core/auth.py:233–252`.
  - Cookies worden altijd met `secure=False` gezet. Bij HTTP-verkeer naar
    dezelfde host kan het sessietoken onderschept worden.
  - Aanpak: expliciete TLS-modus met Secure-cookies, correct proxyvertrouwen
    en documentatie over HTTPS-afdwinging. LAN-HTTP bewust ondersteunen.
  - Acceptatie: HTTPS-modus geeft Secure-cookies; tests dekken ook proxygebruik
    en het expliciet gekozen LAN-HTTP-gedrag.

## Prioriteit 3 — onderhoudbaarheid en testdekking

- [ ] **Grote frontendcomponenten opsplitsen.**
  - `frontend/src/HomepagePanel.vue`: 4.292 regels.
  - `frontend/src/SettingsPanel.vue`: 3.551 regels.
  - Secties en widgets isoleren; polling, data-ophalen en formulierstatus in
    gerichte composables onderbrengen. Gedrag behouden met regressietests.

- [ ] **Grote backendmodules per verantwoordelijkheid opdelen.**
  - `core/vpn.py`: 2.731 regels; `core/homepage.py`: 2.493 regels.
  - Netwerkbeheer, status, integraties en presentatie afzonderlijk testbaar maken.
  - Geen volledige herschrijving: kleine stappen met bestaande interfaces.

- [ ] **Foutinjectietests toevoegen voor alle bovenstaande foutpaden.**
  - Vooral dubbele fouten: mislukte update gevolgd door mislukte rollback,
    corrupte authconfiguratie, falende spawn en vertraagde versiechecks.
  - Daemonherstart en post-update healthchecks daadwerkelijk meenemen; tests
    met uitsluitend `daemon=False` dekken deze paden niet.

- [ ] **Volledige tests en build in een passende ontwikkelomgeving uitvoeren.**
  - Bij deze inspectie ontbraken Python `pytest` en frontenddependencies.
  - Frontendtestpoging: 30 geslaagd; 6 testbestanden konden niet laden wegens
    ontbrekende Vue/Vue-i18n-packages. Dit bewijst geen zes projectfouten.
  - Alle bijgehouden Python-bestanden konden zonder syntaxfouten worden geparseerd.
  - Nog te verifiëren: volledige Python-suite, frontend-suite, productiebuild
    en geïsoleerde appliance-smoketest. Geen mediaservices zijn gestart.

## Behouden sterke punten

- Duidelijke appliance-opzet: één manager voor installatie, beheer en koppelingen.
- Scheiding tussen API-routes, applicatieplugins, supervisor, installer en updater.
- Staging, checksums, snapshots en aandacht voor VPN-isolatie en crashloops.
- Bcrypt, CSRF-controle, loginratelimiting en beperkte/intrekbare TV-tokens.
- Gerichte testbestanden: 60 voor Python en 12 voor de frontend; aantallen zijn
  geen bewijs van volledige dekking of een geslaagde testrun.

## Aanbevolen volgorde

1. Backupbeveiliging en veilige restore.
2. Restart-watcher en behoud van herstelkopieën.
3. Waarheidsgetrouwe rollbackstatus en niet-blokkerende updatechecks.
4. Sessierevocation en HTTPS-cookiebeleid.
5. Gerichte refactors en bredere foutinjectie-/integratietests.

Eindoordeel: een bruikbare basis met duidelijke productwaarde. Eerst stabiliseren
en herstelpaden aantoonbaar betrouwbaar maken; daarna nieuwe functies uitbreiden.
