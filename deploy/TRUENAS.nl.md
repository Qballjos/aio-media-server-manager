# TrueNAS: AIO stap voor stap installeren

Deze route gebruikt het **Custom App-formulier** van TrueNAS SCALE 24.10 of nieuwer. Je begint met AIO en Jellyfin; extra apps en hun netwerkpoorten kun je later toevoegen.

## Dit heb je nodig

- Toegang tot de TrueNAS-webinterface met rechten om apps en opslagmappen te maken.
- Een bestaande opslagpool. Maak of formatteer geen pool om alleen AIO te installeren.
- Apps is op je TrueNAS ingericht. Als Apps nog om een opslagpool vraagt, rond die stap eerst af.

## 1. Maak drie eigen mappen voor AIO

Open **Datasets** en klik op de bestaande opslagpool waarop je AIO wilt bewaren. Kies **Add Dataset** en maak achtereenvolgens aio-config, aio-data en aio-backups onder die pool. Een dataset is hier een aparte opslagmap die TrueNAS zelf beheert.

Noteer van elke dataset het volledige pad dat TrueNAS toont. Bij een pool die media heet zijn dat /mnt/media/aio-config, /mnt/media/aio-data en /mnt/media/aio-backups. Gebruik de naam van jouw pool, niet het voorbeeld media.

**Controle:** je ziet drie nieuwe datasets. Kies geen bestaande map met andere gegevens voor deze stappen.

## 2. Noteer het account voor de app

Open **Credentials → Local Users / Users**, zoek apps en noteer het gebruikersnummer en groepsnummer. Standaard zijn ze vaak 568, maar neem de getallen die jouw scherm toont. Hiermee geef je de app toegang tot de mappen; het zijn geen wachtwoorden.

**Controle:** je hebt twee nummers genoteerd. De maptoegang stel je hieronder in het app-formulier in; wijzig niet de rechten van de hele pool.

## 3. Open het Custom App-formulier

Ga naar **Apps → Discover Apps → Custom App**. Kies het gewone formulier, niet Install via YAML. De knopnamen kunnen per TrueNAS-versie iets verschillen.

Vul in:

| Veld | Waarde |
|---|---|
| Application name | aio-media-manager |
| Image repository | ghcr.io/qballjos/aio-media-server-manager |
| Image tag | latest |

**Controle:** repository en tag staan in de juiste velden; zet :latest niet nogmaals achter de repository als het formulier een apart tagveld heeft.

## 4. Koppel de drie mappen

Voeg bij **Storage → Host Path** drie koppelingen toe. Links kies je het echte datasetpad op de NAS, rechts vul je de onderstaande naam voor binnen AIO in:

| Map op jouw NAS | Mount path in AIO |
|---|---|
| Het pad van aio-config | /config |
| Het pad van aio-data | /data |
| Het pad van aio-backups | /backups |

Laat elke koppeling schrijfbaar. Doe bij elk van de drie **Host Path**-koppelingen het volgende: vink **Enable ACL** aan, klik bij ACL Entries op **Add**, kies **ID Type = User**, vul bij **ID** het genoteerde apps-gebruikersnummer in en kies **Access = Full Control**. Doe dit alleen voor de drie nieuwe AIO-datasets. ACL betekent hier de lijst met accounts die een map mogen gebruiken. Ontbreken deze velden? Volg eerst de TrueNAS-uitleg voor jouw versie.

**Controle:** er staan drie verschillende NAS-paden; /config, /data en /backups zijn precies zo gespeld.

## 5. Vul de basisinstellingen in

Voeg bij **Environment variables** toe:

| Naam | Waarde |
|---|---|
| PUID | Het apps-gebruikersnummer dat je noteerde |
| PGID | Het apps-groepsnummer dat je noteerde |
| AMM_DOWNLOAD_DIR | /data/downloads |
| AMM_MEDIA_DIR | /data/media |

Voeg bij **Port forwarding** TCP-poort **8080 naar 8080** toe voor AIO, en **8096 naar 8096** voor Jellyfin. Laat VPN, GPU en andere extra opties voorlopig uit.

**Controle:** je hebt twee poortkoppelingen. Als een poort al wordt gebruikt, stop dan en lees Geavanceerd in plaats van een willekeurige waarde te kiezen.

## 6. Installeer en open AIO

Klik **Install** en wacht tot de app Running toont. Open daarna zelf een nieuw tabblad met **http://TRUENAS-IP:8080**, waarbij je het echte IP van je TrueNAS gebruikt. Een WebUI-knop is niet in elke versie of installatiemethode aanwezig.

**Controle:** maak het AIO-beheerdersaccount. Kies eerst alleen Jellyfin in de wizard en open daarna Jellyfin vanuit de AIO-catalogus. Meer apps voeg je later toe met de benodigde poorten uit de geavanceerde naslag.

Na installatie: [zo gebruik je het dashboard](../docs/USAGE.md).

## 7. Maak de mediamap bereikbaar vanaf je computer

Om een eerste film te kopiëren heb je naast AIO ook bestandstoegang nodig. Gebruik een normaal TrueNAS-bestandsaccount, niet root of apps. Heb je dat nog niet? Maak het onder **Credentials → Users → Add**, stel een wachtwoord in en schakel SMB-/bestandsdeling voor dat account in.

1. Open **Datasets → aio-data → Permissions → Edit ACL**. Voeg jouw bestandsgebruiker toe met **Modify** en overerving naar bestanden/submappen. Laat de bestaande toegang voor apps staan; vervang niet de hele lijst. Vink bij opslaan **Apply permissions recursively** aan, zodat ook de al gemaakte submappen deze toegang krijgen. Pas dit alleen op aio-data toe.
2. Open **Shares → Windows (SMB) Shares → Add**. Kies het echte pad van aio-data, noem de share **aio-media** en sla op. Start de SMB-service als TrueNAS dat vraagt.
3. Open op Windows **Verkenner** en vul `\\TRUENAS-IP\aio-media` in, niet in de browser. Op een Mac kies je **Finder → Ga → Verbind met server** en `smb://TRUENAS-IP/aio-media`. Gebruik je echte IP en meld aan met je bestandsaccount.
4. Open media → movies en kopieer daar één eigen film naartoe. AIO maakt deze submappen wanneer de app start. Deel config en back-ups niet via deze share.

**Controle:** de film staat zichtbaar op je NAS. Ga daarna naar [je eerste film afspelen](../docs/USAGE.md#first-media).


## Als het niet lukt

| Wat zie je? | Wat doe je? |
|---|---|
| Het formulier ziet er anders uit | Controleer je TrueNAS-versie. Deze route is voor de Docker-gebaseerde Apps vanaf 24.10; gebruik de officiële TrueNAS-hulp of Geavanceerd. |
| Permission denied | Controleer de drie nieuwe datasets en de apps-gebruiker. Pas niet de rechten van de hele pool aan. |
| AIO is actief maar opent niet | Gebruik het TrueNAS-IP met :8080 en controleer de poortkoppeling. |
| Extra app opent niet | Deze basisroute publiceert alleen AIO en Jellyfin. Voeg voor een extra app de poort toe volgens Geavanceerd. |

## Geavanceerd

Voor andere opslaglocaties, SSD-instellingen, bestaande installaties en technische opties: [TRUENAS — Geavanceerd](TRUENAS_ADVANCED.md).

[Officiële producthulp: TrueNAS](https://www.truenas.com/docs/scale/25.04/scaleuireference/apps/installcustomappscreens/).

[TrueNAS: app storage and folder access](https://apps.truenas.com/getting-started/app-storage/).
