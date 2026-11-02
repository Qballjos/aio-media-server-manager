# Docker op Linux: AIO stap voor stap installeren

Deze route gebruikt een **Linux-server waarop Docker al werkt**. Gebruik je Unraid, Synology of TrueNAS? Kies dan eerst [jouw eigen platform](README.md); voer deze opdrachten daar niet óók uit.

## Dit heb je nodig

- Een Linux-server met Docker, Docker Compose en Git. [Docker installeren](https://docs.docker.com/engine/install/) is een aparte stap als dat nog ontbreekt.
- Een account waarmee Docker-opdrachten al werken.
- Een computer op hetzelfde netwerk om het dashboard te openen.

## 1. Open een opdrachtvenster op de server

Werk je op de server zelf? Open daar **Terminal**. Staat de server elders? Open Terminal op je Mac of Windows Terminal op Windows en verbind met `ssh GEBRUIKER@SERVER-IP`. Vervang beide delen door je eigen gebruikersnaam en het serveradres. Na de verbinding voer je de volgende blokken op de server uit.

Voer dit controleblok in:

```bash
docker info
docker compose version
git --version
```

**Controle:** Docker toont serverinformatie en de andere opdrachten een versie. Staat er command not found of permission denied? Rond eerst de Docker-/Git-installatie en toegang af; ga niet door met de volgende stap.

## 2. Haal de AIO-bestanden op

Kopieer dit blok naar hetzelfde terminalvenster:

Staat hier al een map aio-media-server-manager? Voer dit blok dan niet uit; bewaar de map en gebruik [Geavanceerd](DOCKER_ADVANCED.md). Elke volgende regel draait alleen als de vorige is gelukt.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git &&
cd aio-media-server-manager &&
export AMM_DATA_HOST="${HOME}/aio-media-manager" &&
mkdir -p config/vpn backups "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media" &&
sed -i -e "s/PUID: \"1000\"/PUID: \"$(id -u)\"/" -e "s/PGID: \"1000\"/PGID: \"$(id -g)\"/" docker-compose.yml
```

Dit downloadt de projectmap, maakt de benodigde mappen en zet de gebruiker voor AIO automatisch op je huidige Linux-account. Je hoeft hiervoor geen nummers te zoeken of een bestand te bewerken.

**Controle:** er zijn geen foutmeldingen en je staat nu in de map aio-media-server-manager. Die map bevat docker-compose.yml. Bewaar deze map: config bevat je instellingen en backups je opgeslagen instellingenback-ups. Je media staan apart in de map aio-media-manager in je persoonlijke map. Bestond de projectmap al? Verwijder die niet; lees eerst de geavanceerde gids.

## 3. Start AIO

Voer in dezelfde projectmap uit:

```bash
docker compose pull
docker compose up -d
docker compose ps
```

De eerste opdracht haalt de AIO-software op; dat kan enkele minuten duren. De tweede start AIO op de achtergrond. De derde toont de status.

**Controle:** je ziet één container aio-media-manager met status Up of Running. Sluit de terminal gerust af als alles werkt; AIO blijft actief.

## 4. Open het dashboard

Open op je computer **http://SERVER-IP:8080** met het echte adres van je Linux-server. Bijvoorbeeld http://192.168.1.50:8080 als dat jouw serveradres is.

**Controle:** je ziet AIO’s account-aanmaakscherm. Maak een beheerdersaccount en kies de benodigde apps in de wizard. Je installeert die apps alleen in AIO, niet als extra Docker-containers.

Na installatie: [zo gebruik je het dashboard](../docs/USAGE.md).

## Als het niet lukt

| Wat zie je? | Wat doe je? |
|---|---|
| Docker geeft een rechtenfout | Ga terug naar de Docker-installatie/toegang van je Linux-server. Ga niet willekeurig alle opdrachten als root uitvoeren. |
| De projectmap bestaat al | Stop hier. Bewaar de map en gebruik de uitleg voor bestaande installaties in Geavanceerd. |
| AIO start niet | Voer in de projectmap `docker compose logs --tail=100` uit en bewaar de fout. Poortconflict? Zie Geavanceerd. |
| De browser verbindt niet | Controleer de status met docker compose ps, het server-IP en :8080. Gebruik je thuisnetwerk. |

## Geavanceerd

Voor andere opslaglocaties, SSD-instellingen, bestaande installaties en technische opties: [DOCKER — Geavanceerd](DOCKER_ADVANCED.md).
