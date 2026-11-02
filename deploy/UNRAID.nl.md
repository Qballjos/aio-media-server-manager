# Unraid: AIO stap voor stap installeren

Je laat Unraid één AIO-container maken. Deze beginnersroute gebruikt de standaard SSD-pool **cache** voor downloads. Films en series blijven op je gewone opslagschijven.

## Dit heb je nodig

- Toegang tot de Unraid-webpagina van je server.
- De array staat gestart en Docker is ingeschakeld.
- Een SSD/NVMe-pool met de naam **cache**, met genoeg vrije ruimte voor je downloads. Een pool is de groep schijven die Unraid onder een eigen naam toont.

## 1. Controleer de server in je browser

Open de Unraid-webpagina en ga naar **Main**. Controleer dat de array gestart is. Zoek bij de pools naar **cache** en controleer dat deze actief is.

Staat er geen SSD-pool, of heet die anders? Ga dan naar [Unraid: geavanceerd](UNRAID_ADVANCED.md). Ga niet zelf paden raden of schijven formatteren om deze stappen te volgen.

**Controle:** je ziet de actieve pool cache en een tabblad **Docker**. Ontbreekt Docker? Controleer **Settings → Docker → Enable Docker**.

## 2. Open de terminal van Unraid

Klik in de bovenbalk van de Unraid-webpagina op het terminalpictogram **>_**. Je krijgt een venster met een opdrachtregel. Deze terminal draait al op de server; je hoeft niet vanaf je laptop via SSH te verbinden.

Kopieer het volgende blok, plak het in dat venster en druk op Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/install.sh | sh
```

Dit bereidt de mappen en het AIO-sjabloon voor. Het installeert nog geen aparte Sonarr- of downloadcontainers.

**Controle:** je ziet **Unraid template ready**. Zie je een fout over bestaande downloads? Stop hier en volg de geavanceerde gids; voeg geen nieuwe opslagkoppelingen toe over bestaande bestanden.

## 3. Voeg AIO toe

Sluit de terminal en ga naar **Docker → Add Container**. Open bovenaan de lijst **Template** en kies **my-aio-media-manager** of **aio-media-manager**.

Laat de aangemaakte opslagpaden staan. Laat **PUID = 99** en **PGID = 100** staan; dat zijn de standaardgebruiker en -groep voor deze installatie. Kies je tijdzone bij **TZ**, bijvoorbeeld **Europe/Amsterdam**.

Klik op **Apply / Toepassen** en wacht tot het downloaden klaar is.

**Controle:** op het Docker-tabblad staat één container **aio-media-manager**, met status actief / started.

## 4. Controleer de downloadopslag

Open **Shares → aio-download-cache**. Controleer dat **Primary storage** de pool **cache** is en **Secondary storage** op **None** staat. In oudere Unraid-versies heet dit **Use cache pool: Only**.

Je hoeft niets te veranderen als dit al klopt. De SSD bewaart het werk tijdens downloaden en uitpakken. De mediabibliotheek en afgeronde torrents blijven op de array.

**Controle:** aio-download-cache wordt niet door Mover naar de array verplaatst.

## 5. Open AIO

Klik op het AIO-icoon bij Docker en kies **WebUI**. Je kunt ook **http://SERVER-IP:8080** openen met het IP-adres van je Unraid-server.

**Controle:** je ziet de pagina om een AIO-beheerdersaccount te maken. Maak het account en kies de gewenste apps in de wizard. Voeg die apps niet nogmaals toe via Unraid Apps.

Na installatie: [zo gebruik je het dashboard](../docs/USAGE.md).

## 6. Kopieer je eerste film

Heb je al een eigen Unraid-bestandsaccount? Gebruik dat. Anders maak je onder **Users → Add User** een normale gebruiker met wachtwoord; gebruik root niet voor bestandsdeling.

1. Open **Shares → aio-media-manager → SMB Security Settings**. Zet Export op Yes en Security op Private. Geef jouw bestandsgebruiker lees-/schrijftoegang en laat andere gebruikers zonder toegang, tenzij je bewust met hen wilt delen.
2. Open op Windows Verkenner met `\\SERVER-IP\aio-media-manager`. Op een Mac kies je Finder → Ga → Verbind met server en `smb://SERVER-IP/aio-media-manager`. Gebruik het echte IP van je Unraid-server.
3. Meld aan met je bestandsgebruiker, open media → movies en kopieer daar één eigen film naartoe.

**Controle:** het bestand staat op de server in media/movies. Ga verder met [je eerste film afspelen](../docs/USAGE.md#first-media).

## Als het niet lukt

| Wat zie je? | Wat doe je? |
|---|---|
| Het sjabloon staat niet in de lijst | Controleer of de voorbereidingsopdracht eindigde met Unraid template ready. Vernieuw het Docker-tabblad. |
| De pool heet anders of bestaat niet | Gebruik de geavanceerde gids voor een andere pool of een installatie zonder SSD; de standaardopdracht stopt bewust. |
| AIO opent niet | Controleer de containerstatus en het serveradres. Bij een poortconflict volg je de uitleg in de geavanceerde gids. |

## Geavanceerd

Voor andere opslaglocaties, SSD-instellingen, bestaande installaties en technische opties: [UNRAID — Geavanceerd](UNRAID_ADVANCED.md).

[Officiële producthulp: Unraid](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/).
