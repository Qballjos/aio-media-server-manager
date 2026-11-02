# Synology: AIO stap voor stap installeren

Deze route is voor een **nieuwe installatie**. Je maakt één project in Container Manager. Je hoeft geen instellingenbestand te schrijven en geen losse mediatools te installeren.

## Dit heb je nodig

- Een Synology NAS waarop **Container Manager** beschikbaar is in Package Center.
- Je eigen DSM-gebruikersnaam en wachtwoord, met beheerdersrechten. Gebruik niet zomaar de voorbeeldnaam `admin`.
- Een computer op hetzelfde thuisnetwerk. Houd DSM in je browser open.

## 1. Installeer Container Manager

Open DSM in je browser. Ga naar **Package Center**, zoek **Container Manager** en klik op **Installeren**. Rond de installatie af en open het pakket.

**Controle:** open File Station. Er moet nu een gedeelde map **docker** zijn. Maak deze map niet vooraf zelf. Deze beginnersroute gebruikt de standaardlocatie op volume1; staat docker op een ander volume, gebruik dan de [geavanceerde Synology-gids](SYNOLOGY_ADVANCED.md).

## 2. Zet de persoonlijke map en SSH aan

Ga in DSM naar **Configuratiescherm → Gebruiker en groep → Geavanceerd**. Schakel de **gebruikerbasismapservice / User Home Service** in. Die geeft jouw DSM-account een persoonlijke map voor downloads en media.

Ga daarna naar **Configuratiescherm → Terminal en SNMP → Terminal** en schakel **SSH-service inschakelen** in. Laat poort **22** staan en klik op **Toepassen**.

**Controle:** in File Station zie je **home**. In Terminal en SNMP staat SSH aangevinkt.

## 3. Maak vanaf je computer verbinding met de NAS

Open **Terminal** op een Mac of **Windows Terminal / PowerShell** op Windows. Dit is de app waarin je opdrachten typt; niet de adresbalk van je browser.

Typ `ssh GEBRUIKERSNAAM@NAS-IP`. Vervang beide delen. Voor gebruiker `alex` en NAS-adres `192.168.1.50` wordt dat:

```bash
ssh alex@192.168.1.50
```

Gebruik je eigen gegevens, niet dit voorbeeldadres. Het NAS-adres vind je in de adresbalk van DSM of bij **Configuratiescherm → Netwerk → Netwerkinterface**. Bevestig de eerste verbinding alleen als het adres klopt. Voer je DSM-wachtwoord in. Tijdens het typen verschijnen geen tekens; dat is normaal.

**Controle:** de opdrachtregel toont nu de naam van je NAS. Vanaf nu draaien de volgende opdrachten op de NAS.

## 4. Laat AIO de projectbestanden maken

Kopieer dit hele blok naar het terminalvenster waarin je met de NAS bent verbonden en druk op Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
```

Dit haalt het voorbereidingsscript op en maakt de mappen en het projectbestand. Het start AIO nog niet. Vraagt sudo om een wachtwoord? Gebruik opnieuw je DSM-wachtwoord.

**Controle:** het script eindigt met **Container Manager project files are ready**. Noteer de regel **Compose** en de projectmap die daar staat. Zie je een fout? Ga niet verder met een half aangemaakt project.

## 5. Maak het project in Container Manager

Ga terug naar DSM. Open **Container Manager → Project → Maken / Create**.

1. Naam: **aio-media-manager**.
2. Pad: kies de projectmap die het script heeft getoond; standaard **docker → aio-media-manager**.
3. Gebruik het **bestaande docker-compose.yml** in die map. Vraagt jouw DSM om uploaden? Selecteer dat aangemaakte bestand; maak geen tweede bestand met andere instellingen.
4. Laat de gegenereerde instellingen staan en rond de wizard af. Start het project.

**Controle:** het project bevat één container met de naam **aio-media-manager**. De status wordt actief. Het downloaden van de eerste versie kan enkele minuten duren.

## 6. Open je nieuwe dashboard

Open een nieuw browsertabblad met **http://NAS-IP:8080**. Voor de voorbeeld-NAS is dat `http://192.168.1.50:8080`; gebruik jouw eigen adres.

**Controle:** AIO vraagt om een beheerdersaccount. Maak dat aan en rond de wizard af. De apps kies je daar; je hoeft niet alle apps te installeren. Je bestanden komen standaard in **File Station → home → aio-media-manager**.

Je kunt de SSH-verbinding daarna afsluiten met `exit`. SSH weer uitschakelen in DSM stopt AIO niet.

Na installatie: [zo gebruik je het dashboard](../docs/USAGE.md).

## Als het niet lukt

| Wat zie je? | Wat doe je? |
|---|---|
| Container Manager ontbreekt in Package Center | Controleer bij Synology of jouw model het pakket ondersteunt. Maak niet handmatig een docker-map als vervanging. |
| Er staat Permission denied of het script stopt | Controleer je DSM-account, of Container Manager actief is en of de map docker bestaat. Bewaar de precieze foutmelding. |
| De browser kan AIO niet openen | Controleer dat het project actief is. Gebruik het NAS-adres, niet het adres van je laptop, met :8080 erachter. |

## Geavanceerd

Voor andere opslaglocaties, SSD-instellingen, bestaande installaties en technische opties: [SYNOLOGY — Geavanceerd](SYNOLOGY_ADVANCED.md).

[Officiële producthulp: Synology](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project?version=7).
