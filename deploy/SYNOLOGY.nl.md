# Synology

Draai AIO als **één** Container Manager-**project**. Voeg geen extra services of losse Sonarr-/Radarr-/downloadcontainers ernaast toe.

**Image:** `ghcr.io/qballjos/aio-media-server-manager:latest`  
Je DSM moet `linux/amd64`- of `linux/arm64`-images kunnen draaien.

## Mappen en het project maken (SSH)

Zet SSH aan (**Configuratiescherm → Terminal en SNMP → SSH-service inschakelen**) en daarna:

```bash
ssh admin@<nas-ip>
```

Het installatiescript maakt `/volume1/docker/aio-media-manager` (met `config/` en `backups/`) en een databoom in de **DSM-gebruikershome** (`File Station → Home → aio-media-manager` met `downloads/` en `media/`). Dat pad is een echte gebruikershome, dus DSM kan het tonen. Een kale map `/volume1/data` is geen gedeelde map en verschijnt niet in File Station; het script opnieuw draaien verplaatst die boom naar home als hij nog bestaat. Downloads en media blijven één bind (`/data`), zodat *Arr kan hardlinken. Config-back-ups gaan naar de `/backups`-mount; neem die map op in een Hyper Backup-taak, of wijs `BACKUPS=` naar een ander volume.

User Home Service moet aan staan (Configuratiescherm → Gebruiker en groep → Geavanceerd). SSH als de DSM-gebruiker wiens Home de bibliotheken moet bevatten, of zet `HOME_USER=`.

```bash
id
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
```

Als SSH `admin` is maar Home van een andere DSM-gebruiker moet zijn:

```bash
id media
sudo HOME_USER=media PUID=1026 PGID=100 sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Ander volume of andere paden:

```bash
sudo VOLUME=/volume2 \
     HOME_USER=media \
     BACKUPS=/volume1/backups/aio-media-manager \
     PUID=1026 PGID=100 \
     sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Om bibliotheken op een gedeelde DSM-map te houden in plaats van Home, zet je `DATA=` op die map (nog steeds één ouder voor `downloads` en `media`):

```bash
sudo DATA=/volume1/media/aio-media-manager \
     PUID=1026 PGID=100 \
     sh -c 'curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sh'
```

Het gegenereerde bestand is `/volume1/docker/aio-media-manager/docker-compose.yml` (geen `build:`-sleutel — Container Manager haalt GHCR op). Een statische kopie staat in [`synology/docker-compose.yml`](synology/docker-compose.yml).

Als GHCR privé is: `sudo docker login ghcr.io` voordat je het project start.

## Importeren in Container Manager

1. Open **Container Manager → Project → Maken**.
2. **Projectnaam:** `aio-media-manager`
3. **Pad:** `/volume1/docker/aio-media-manager` (dezelfde map die het script gebruikte).
4. **Bron:** gebruik het **bestaande** `docker-compose.yml` (plak geen tweede compose-bestand en voeg geen extra services toe).
5. Start het project.

De interface hoort één service `aio-media-manager` te tonen. Open `http://<nas-ip>:8080` voor de manager. **Interface openen** op cataloguskaarten gebruikt de app-poorten (Sonarr `8989`, Radarr `7878`, …), die het project-compose nu publiceert. Als je compose vóór die wijziging hebt gegenereerd, kopieer dan de `ports:`-lijst uit [`synology/docker-compose.yml`](synology/docker-compose.yml) naar het projectbestand en maak de container opnieuw aan.

Het installatiescript mount host-`/sys` ook alleen-lezen op `/host/sys`, zodat de serverkaart op Start het netwerkverkeer van de NAS toont. Als het project-compose daarvóór is gegenereerd, voeg `- /sys:/host/sys:ro` toe onder `volumes:` en maak opnieuw aan. Zonder die regel is de grafiek alleen het verkeer van deze container. Geïnstalleerde apps werk je later bij via **Instellingen → Updates** (schema’s staan standaard uit). Het project opnieuw aanmaken werkt AIO bij.

Om vanuit SSH te starten in plaats van de interface:

```bash
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml pull
sudo docker compose -f /volume1/docker/aio-media-manager/docker-compose.yml up -d
```

Daarna toont Container Manager het nog steeds als het projectpad overeenkomt.

## Hardware-transcoden

Als `/dev/dri` bestaat, voeg dit blok toe onder `aio-media-manager` in het project-compose-bestand, maak daarna opnieuw aan en start het project:

```yaml
    devices:
      - /dev/dri:/dev/dri
```

```bash
ls -l /dev/dri
```

## VPN (qBittorrent, Prowlarr, Flaresolverr)

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/vpn
# scp wg0.conf into that directory
```

Zet `AMM_VPN_ENABLED=true` in het project-compose en start het project opnieuw. Zolang de VPN aan staat, kunnen Prowlarr, qBittorrent en Flaresolverr het huis-WAN niet gebruiken: ze gaan alleen via de tunnel naar buiten. Is de tunnel bij boot down, dan wachten ze; AIO probeert de VPN opnieuw en start ze als de handshake terug is. Een lokale DNS-cache voor die apps (gebonden aan de tunnel) vermindert indexer-fouten door korte DNS-timeouts. De kernel van Synology heeft vaak geen WireGuard-module; de appliance-image bevat **wireguard-go** als terugval en maakt `/dev/net/tun` aan als die ontbreekt. Dat werkt alleen als het project `privileged: true` blijft (het installatiescript zet dat). Maak de container opnieuw aan nadat je een actuele image hebt opgehaald, en sla de VPN daarna op bij **Instellingen → Netwerk**. OpenVPN gebruikt dezelfde device-node en heeft ook privileged mode nodig. Op DSM kan Synology-ACL de VPN-app-uid (910) na `chown` blokkeren; als die apps hun configmap niet kunnen schrijven, wis de ACL op het hostpad zoals de logs beschrijven.

## Cloudflare Tunnel

Voeg geen tweede projectservice toe. Schrijf de token op de NAS en zet de tunnel daarna aan bij **Instellingen → Netwerk** (bewaard over herstarts heen). Optioneel zet je `AMM_CLOUDFLARE_TUNNEL_ENABLED=true` in het project-compose. Zie [CLOUDFLARE.md](CLOUDFLARE.md).

```bash
sudo mkdir -p /volume1/docker/aio-media-manager/config/cloudflare
sudo tee /volume1/docker/aio-media-manager/config/cloudflare/tunnel.token >/dev/null <<'EOF'
eyJ...paste-token...
EOF
sudo chmod 600 /volume1/docker/aio-media-manager/config/cloudflare/tunnel.token
```

## Rechten

`PUID`/`PGID` in het compose-bestand moeten overeenkomen met de `chown` die het script heeft toegepast. Als apps niet kunnen schrijven, herstel het eigendom via SSH in plaats van als root te draaien.
