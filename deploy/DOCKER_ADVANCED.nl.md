# Docker — Geavanceerd

!!! info "Geavanceerd"
    Dit is de technische naslag. Volg voor je eerste installatie de beginnershandleiding. [Beginnershandleiding](DOCKER.md).

Dit is de gewone manier om AIO te draaien: **één container** die de manager en elke app die je aanzet start.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
**Werkt op:** `linux/amd64` en `linux/arm64`  
(Op ARM is Flaresolverr niet beschikbaar — die heeft x86_64 nodig.)

---

## 1. Controleer de server

Voer de opdrachten uit op de server waarop AIO moet draaien. Verbind zo nodig eerst via SSH met je eigen gebruikersnaam en serveradres.

```bash
docker info
docker compose version
git --version
```

Verwacht: informatie over een actieve Docker-engine, een Compose-versie en een Git-versie. Ontbreekt iets of krijg je een rechtenfout? Los dat eerst op via de instructies van je host. Gebruik op een NAS de bijbehorende [platformgids](README.md) en installeer geen tweede Docker-engine.

## 2. Haal de bestanden op en maak mappen

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git
cd aio-media-server-manager
id
export PUID="$(id -u)"
export PGID="$(id -g)"
export AMM_DATA_HOST="${HOME}/aio-media-manager"
mkdir -p config/vpn backups "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media"
sudo chown -R "${PUID}:${PGID}" config backups "${AMM_DATA_HOST}"
```

Blijf hierna in de map met `docker-compose.yml`. Deze opdrachten maken `config/` en `backups/` in de projectmap, plus downloads en media in je thuismap. De standaard Compose-koppelingen wijzen naar **deze** mappen, niet naar `/opt/aio-media-manager/config`.

## 3. Controleer docker-compose.yml

Open het bestand in een teksteditor. Zet PUID en PGID op de uid/gid uit `id`; de waarden in het bestand zijn standaard 1000:1000. Alleen de shellvariabelen exporteren overschrijft deze vaste Compose-waarden niet. Zet TZ op je tijdzone, bijvoorbeeld Europe/Amsterdam. Houd de mapkoppelingen eerst gelijk. Kies voor back-ups later liefst een andere schijf.

!!! tip "sudo"
    Gebruik je sudo? Omgevingsvariabelen kunnen verdwijnen en HOME kan /root worden. Geef je datamap dan expliciet mee: `sudo env AMM_DATA_HOST="$AMM_DATA_HOST" docker compose up -d`. Gebruik dezelfde map bij updates.

## 4. Start AIO

```bash
docker compose pull
docker compose up -d
docker compose ps
```

Verwacht: één actieve container met de naam aio-media-manager. Het eerste downloaden van de image kan enkele minuten duren. Open `http://JOUW-SERVER-IP:8080` met je echte serveradres, maak het beheerdersaccount en rond de wizard af. Lees daarna [Het dashboard gebruiken](../docs/USAGE.md). Bij fouten: `docker compose logs --tail=100`. Bij een poortconflict wijzig je de **hostkant** van de poortkoppeling, maak je de container opnieuw aan en open je de nieuwe poort.

## Later bijwerken

```bash
docker compose pull
docker compose up -d --force-recreate
```

De container kan zijn eigen image niet vervangen. Instellingen → Updates meldt een `:nightly`-installatie alleen wanneer `:nightly` is verschoven, en een `:latest`-installatie alleen wanneer `:latest` is verschoven. Ophalen doe je nog steeds die tag op de host. Geïnstalleerde apps (Sonarr, Seerr en de rest) werk je bij via **Instellingen → Updates**, één voor één of allemaal tegelijk. Die schema’s staan standaard uit. De container opnieuw aanmaken werkt ze niet bij.

Gepubliceerde images lezen hun versie en commit uit buildgegevens in het image. Oude waarden voor `AMM_VERSION` of `AMM_GIT_SHA` in Compose kunnen die identiteit niet overschrijven of een onterechte updatemelding veroorzaken. Een broncode-installatie zonder imagegegevens accepteert deze variabelen nog wel.

**Ouder compose-bestand dat alleen poort 8080 publiceerde?** Kopieer de huidige `ports:`-lijst uit deze repo en maak opnieuw aan, anders falen de **Interface openen**-links van kind-apps op het LAN.

**`/backups` later toevoegen:** maak de hostmap, voeg `- /path/to/backups:/backups` toe onder `volumes:` en maak opnieuw aan. Oude back-ups onder `/config/backups` blijven herstelbaar tot je ze verwijdert.

**Hostnetwerkverkeer op Start:** voeg `- /sys:/host/sys:ro` toe onder `volumes:` en maak opnieuw aan. Zonder die regel toont Start alleen het eigen verkeer van de container.

Een optionele `GITHUB_TOKEN` (compose of Instellingen → Updates) verhoogt de GitHub-API-limiet. Commit de token niet.

### Bouwen vanuit deze checkout

```bash
docker compose up -d --build
```

### Ontwikkel- / testomgeving

```bash
./scripts/test-env.sh up
```

Zie [CONTRIBUTING.md](../CONTRIBUTING.md).

### Hardware-transcoden (Intel/AMD)

De image bevat **jellyfin-ffmpeg** (met Intel iHD / VA-API-drivers). Map de host-rendernode, maak de container opnieuw aan na een pull met die build, en zet in Jellyfin **Intel Quick Sync** (of VAAPI) aan onder Playback → Transcoding.

```bash
docker compose -f docker-compose.yml -f compose.gpu.yml up -d
```

---

## 3. Gewoon `docker run` (alternatief)

```bash
docker pull ghcr.io/qballjos/aio-media-server-manager:latest

docker run -d --name aio-media-manager --restart unless-stopped \
  --privileged \
  --cap-add NET_ADMIN --cap-add SYS_MODULE \
  --device /dev/dri:/dev/dri \
  -p 8080:8080 \
  -p 8081:8081 -p 8084:8084 -p 8085:8085 -p 8096:8096 \
  -p 8191:8191 -p 5055:5055 -p 6060:6060 \
  -p 6767:6767 -p 6789:6789 \
  -p 7878:7878 -p 8686:8686 -p 8989:8989 -p 9696:9696 -p 9705:9705 -p 11011:11011 \
  -p 32400:32400 \
  -e PUID="${PUID}" -e PGID="${PGID}" \
  -e TZ=UTC \
  -v /opt/aio-media-manager/config:/config \
  -v "${HOME}/aio-media-manager:/data" \
  -v /opt/aio-media-manager/backups:/backups \
  -v /sys:/host/sys:ro \
  -e AMM_DOWNLOAD_DIR=/data/downloads \
  -e AMM_MEDIA_DIR=/data/media \
  ghcr.io/qballjos/aio-media-server-manager:latest
```

Laat `--device /dev/dri` weg als de host geen Intel/AMD-GPU heeft (Docker Desktop op een Mac, veel VPS-hosts). Of gebruik `--network host` in plaats van elke `-p` te noemen.

Volledige poortenlijst: [Installeren → Poorten](../docs/REFERENCE.md#ports).

---

## Privé-GHCR-image

Als pull faalt omdat het package privé is:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker pull ghcr.io/qballjos/aio-media-server-manager:latest
```

Op GitHub kun je het package ook publiek maken onder **Packages → settings → Change visibility**.

---

## Optionele VPN

Voor verkeer van qBittorrent / Prowlarr / Flaresolverr:

```bash
sudo mkdir -p /opt/aio-media-manager/config/vpn
sudo chown -R "${PUID}:${PGID}" /opt/aio-media-manager/config/vpn
# copy wg0.conf or an OpenVPN profile into that folder
```

1. Zet `AMM_VPN_ENABLED=true` (en `AMM_VPN_ENFORCE=true` als torrents niet zonder VPN mogen draaien).
2. Laat Usenet-clients buiten de VPN — die gebruiken het gewone netwerk.
3. Sla het profiel op bij **Instellingen → VPN** (of mount het en zet het via env aan), en **maak de container opnieuw aan** zodat WireGuard bij boot omhoog komt.

Privileged mode is nodig voor `/dev/net/tun` en de VPN-uid-routing (WireGuard in de hoofd-netwerknamespace; torrent-apps draaien als aparte uid). Synology heeft vaak **wireguard-go** uit de image nodig als de host geen WireGuard-kernelmodule heeft — zie [SYNOLOGY.md](SYNOLOGY.md).

### Wat AIO doet zolang de VPN aan staat

- Die drie apps starten pas na een live WireGuard-handshake. Is de tunnel bij boot down, dan wachten ze; AIO probeert de VPN met backoff opnieuw en start ze als hij omhoog is. Een handmatige VPN-**Stop** annuleert die poging.
- DNS voor die apps gaat via een kleine caching-forwarder in AIO (`127.0.0.153`), gebonden aan de tunnelinterface zodat lookups niet op het huis-WAN lekken. Hij vraagt meerdere publieke resolvers parallel en kan een recent antwoord geven als upstream even stil is — zo blijven Prowlarr-indexers niet hangen op één timeout. Andere apps (Sonarr, Radarr, SABnzbd, …) houden de container-resolver.
- Usenet-verkeer gebruikt de tunnel nooit.

---

## Reverse proxy of Cloudflare

- **Geen proxy nodig** voor gebruik op het thuisnetwerk via `http://server-ip:8080`.
- Eigen Traefik/Caddy/Nginx: zet `AMM_TRUSTED_PROXIES` en optioneel `AMM_ROOT_PATH`.
- **Cloudflare Tunnel** (geen inkomende poorten): [CLOUDFLARE.md](CLOUDFLARE.md).  
  `cloudflared` draait **in** deze container — voeg geen tweede Cloudflare-service toe.
