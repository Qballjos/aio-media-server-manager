# Cloudflare Tunnel

Bereik AIO (en optionele apps zoals Sonarr of Jellyfin) vanaf internet **zonder poorten open te zetten** op je router.

In gewone woorden: een klein programma (`cloudflared`) draait **in AIO**, belt naar buiten naar Cloudflare, en Cloudflare serveert `https://your-name.yourdomain.com`. Je thuisfirewall blijft dicht voor inkomend verkeer.

Installeer **geen** tweede Cloudflare-Docker-container of `cloudflared`-service op dezelfde host voor dezelfde tunnel — AIO draait die al.

Officiële hulp van Cloudflare: [Create a tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/) · [Tunnel token](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/remote-tunnel-permissions/#get-the-tunnel-token).

Je LAN-interface op `http://YOUR-SERVER-IP:8080` werkt nog steeds als de tunnel uit staat.

---

## Wat je nodig hebt

- Een domein waarvan de DNS bij Cloudflare staat
- Rechten om tunnels te maken (**Networking → Tunnels**)
- AIO al geïnstalleerd en door de eerste start heen

---

## Stap 1 — Maak de tunnel

1. Meld je aan op [dash.cloudflare.com](https://dash.cloudflare.com/).
2. Open **Networking → Tunnels**  
   (sommige accounts tonen nog **Zero Trust → Networks → Tunnels** — dezelfde plek).
3. **Create a tunnel** → connectortype **Cloudflared**.
4. Geef een duidelijke naam, bijvoorbeeld `aio-media-manager`.
5. **Create Tunnel**.

---

## Stap 2 — Kopieer alleen de token

Cloudflare toont installatiecommando’s voor Docker, Windows, enzovoort. **Draai die niet op je NAS.** Je hebt alleen de tokenreeks nodig.

1. Blijf op de setup- / **Overview**-pagina van de tunnel.
2. Kies een willekeurig besturingssysteem zodat er een commando verschijnt (of later: tunnel → **Overview** → **Add a replica**).
3. Je ziet iets als:

   ```bash
   cloudflared service install eyJhIjoiNWFiNGU5Z...very-long...
   ```

4. Kopieer **alleen** het deel dat met `eyJ` begint (lange JWT-achtige reeks).  
   Behandel die als een wachtwoord — wie hem heeft, kan je tunnel draaien.

**Token kwijt?** Tunnel → **Overview** → **Add a replica** → kopieer `eyJ…` opnieuw.  
**Gelekt?** Gebruik **Refresh token**, plak de nieuwe in AIO en sla op.

---

## Stap 3 — Plak de connectortoken in AIO

1. Open `http://YOUR-SERVER-IP:8080`.
2. **Instellingen → Netwerk → Cloudflare Tunnel**
3. Zet **Tunnel inschakelen** aan, plak de `eyJ…`-token en sla op.
4. De status hoort **Enabled**, **Token saved**, **Tunnel up** en **cloudflared ready** te tonen.  
   De **CF**-pil in de kop wordt groen/blauw als alles gezond is.

Bij containerboot brengt AIO eerst de VPN (als die aan staat) en de catalogus-apps omhoog, en start `cloudflared` als laatste zodat die geen origins raakt die nog starten. Het dashboard is bereikbaar terwijl dat nog loopt. Na de wizard van de eerste start start de tunnel nog steeds meteen als je klaar bent (vóór of samen met de VPN), zodat je hostnamen meteen kunt publiceren.

Blijft het op **Tunnel down** hangen? Kijk in de cloudflared-logs bij Catalogus/Diagnose, of uitgaand verkeer naar Cloudflare (poort **7844**) mag, en of niets anders dezelfde token gebruikt.

---

## Stap 4 — Apps publiceren (zodat Interface openen op afstand werkt)

Cloudflare serveert alleen **HTTPS op poort 443**. Je kunt `https://media.example.com:8989` niet openen.  
Elke app heeft een eigen **publieke hostnaam** nodig, bijvoorbeeld `https://sonarr.example.com`, gemapt naar `http://127.0.0.1:8989` **in** de AIO-container.

**Jellyfin:** de tunnel wijst naar een localhost-nginx op **8097** die `CF-Connecting-IP` naar `X-Forwarded-For` kopieert. Zonder dat ziet Jellyfin elke tunnelclient als `127.0.0.1` (lokaal) en slaat remote bitratelimiet / Auto-transcode over. LAN blijft **8096** gebruiken.

In Cloudflare heten dat **[Published applications](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/#2a-publish-an-application)** (hostnaam → service) — geen private-network Tunnel-CIDR-routes.

### Het makkelijkst: doe het in AIO

Nadat de connectortoken is opgeslagen (stap 3):

1. **Instellingen → Netwerk → Publieke subdomeinen**
2. Zet **Publiek app-domein** op je zone (bijvoorbeeld `example.com` of `example.co.uk`).
3. Maak een API-token zoals Cloudflare het beschrijft ([Create API token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)):
   - **My Profile → API Tokens** (gebruiker) of **Manage Account → Account API Tokens**
   - **Create Token** → begin bij het sjabloon **Edit zone DNS**
   - Houd **Zone → DNS → Edit**, beperkt tot je zone
   - Voeg **Account → Cloudflare Tunnel → Edit** toe (en bij voorkeur **Zone → Zone → Read**)
   - Ga door naar de samenvatting → Create Token (kopieer het geheim één keer)
4. Plak die API-token onder **Publieke subdomeinen**  
   (dit is **niet** de `eyJ…`-connectortoken uit stap 3, en **niet** de Global API Key).
   Als Cloudflare **Invalid access token** teruggeeft, wis de opgeslagen token en plak een verse **API Token** uit Create Token.
5. Zet **Vrijgeven** per app aan, pas subdomeinlabels aan als je wilt, **opslaan**, en daarna **Publiceren naar Cloudflare**.

**Opslaan** werkt de links voor Interface openen en de Start-widgets bij. **Publiceren** schrijft published applications in de tunnel en maakt geproxiede DNS-CNAME’s (`<subdomain>.yourzone` → `<tunnel-id>.cfargotunnel.com`).

Gebruikelijke servicedoelen (in AIO):

| Hostnaam | Wijst naar (in AIO) |
|----------|-------------------------|
| `media.example.com` (AIO) | `http://127.0.0.1:8080` |
| `qbittorrent.example.com` | `http://127.0.0.1:8081` |
| `shelfmark.example.com` | `http://127.0.0.1:8084` |
| `sabnzbd.example.com` | `http://127.0.0.1:8085` |
| `jellyfin.example.com` | `http://127.0.0.1:8097` (CF-origin-shim → Jellyfin `:8096`) |
| `seerr.example.com` | `http://127.0.0.1:5055` |
| `grimmory.example.com` | `http://127.0.0.1:6060` |
| `bazarr.example.com` | `http://127.0.0.1:6767` |
| `nzbget.example.com` | `http://127.0.0.1:6789` |
| `radarr.example.com` | `http://127.0.0.1:7878` |
| `lidarr.example.com` | `http://127.0.0.1:8686` |
| `sonarr.example.com` | `http://127.0.0.1:8989` |
| `prowlarr.example.com` | `http://127.0.0.1:9696` |
| `neutarr.example.com` | `http://127.0.0.1:9705` |
| `plex.example.com` | `http://127.0.0.1:32400` |

Flaresolverr en Recyclarr worden niet als publieke hostnamen aangeboden. Recyclarr is een opdrachtregel-sync. Flaresolverr wordt in het apparaat door Prowlarr gebruikt. Meer poorten: [Installeren → Poorten](../docs/INSTALL.md#ports).

### Of: zelf publiceren in Cloudflare

**Networking → Tunnels** → jouw tunnel → **Routes** → **Published application**.  
De service-URL moet `http://127.0.0.1:PORT` in AIO zijn. Zet daarna dezelfde labels onder AIO **Publieke subdomeinen** → **opslaan**, zodat Interface openen en Start hetzelfde zeggen.

**Gedrag van publiceren**

- AIO wijzigt alleen hostnamen die het zelf heeft gepubliceerd (of die je nu aanzet). Hostnamen die je met de hand in het dashboard hebt gemaakt en nooit vanuit AIO hebt gepubliceerd, blijven staan.
- Een app uitzetten en opnieuw publiceren verwijdert de ingress-hostnaam; de DNS-naam kan blijven (dan krijg je een tunnel-404).
- De luisterpoort van een app wijzigen werkt de tunnelservice bij als er een API-token is opgeslagen.
- Thuis opent `http://nas-ip:8080` apps nog steeds als `http://nas-ip:port`, ook als er een publiek domein is ingesteld.

**Belangrijk:** gepubliceerde hostnamen staan op het publieke internet tot je [Cloudflare Access](CLOUDFLARE_ACCESS.md) toevoegt. Zet Access vóór de *Arr-apps, de downloadclients en Seerr. Laat het AIO-dashboard, Jellyfin en Plex op hun eigen aanmelding. AIO kan die Access-applicaties maken nadat je een aanmeldmethode in Zero Trust hebt toegevoegd.

SABnzbd blokkeert onbekende publieke Hosts standaard (`External internet access denied`). AIO zet `inet_exposure` en voegt je gepubliceerde SABnzbd-hostnaam toe aan `host_whitelist` bij start / Auto-koppelen / Publiceren. Nadat je `sabnzbd` onder Publieke subdomeinen hebt aangezet, herstart SABnzbd of draai Auto-koppelen één keer als de pagina toegang nog weigert.

---

## Optioneel: tokenbestand op schijf (SSH / Compose)

Handig voor installs die via de omgeving lopen. De paden zijn aan de **host**-kant van `/config`:

| Platform | Map voor `tunnel.token` |
|----------|---------------------------|
| Gewone Linux | `/opt/aio-media-manager/config/cloudflare/` |
| Unraid | `/mnt/user/appdata/aio-media-manager/cloudflare/` |
| Synology | `/volume1/docker/aio-media-manager/config/cloudflare/` |

```bash
ssh user@host
CONFIG=/opt/aio-media-manager/config
sudo mkdir -p "$CONFIG/cloudflare"
sudo tee "$CONFIG/cloudflare/tunnel.token" >/dev/null <<'EOF'
eyJ...paste-token...
EOF
sudo chmod 600 "$CONFIG/cloudflare/tunnel.token"
sudo chown "${PUID:-1000}:${PGID:-1000}" "$CONFIG/cloudflare/tunnel.token"
```

Zet hem daarna aan bij **Instellingen → Netwerk** (voorkeur — hij wordt in `amm_config.json` bewaard en overleeft containerherstarts, ook als compose nog `AMM_CLOUDFLARE_TUNNEL_ENABLED=false` heeft), of zet dit en maak opnieuw aan:

```bash
AMM_CLOUDFLARE_TUNNEL_ENABLED=true
AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE=/config/cloudflare/tunnel.token
```

Houd **één** AIO-service in Compose — geen aparte `cloudflare/cloudflared`-container.

---

## Native Linux (geen Docker)

Installeer het `cloudflared`-binary als je niet op de GHCR-image zit, maar draai **niet** `cloudflared service install` — AIO start het proces:

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared
```

Zet de tunnel aan in Instellingen (of via de omgeving) en start `aio-media-manager.service`.

---

## Controleren of het werkt

1. Cloudflare: tunnelstatus **Healthy**
2. AIO: Instellingen → Netwerk → tunnel **verbonden**
3. Vanaf mobiele data (of een ander netwerk): open `https://media.example.com` (jouw hostnaam)
4. Optionele API-check (geeft de token niet terug): `GET /api/cloudflare/tunnel/status`

---

## Vertrouwde reverse-proxy-IP’s

**Instellingen → Netwerk → Vertrouwde reverse-proxy-IP’s** (`AMM_TRUSTED_PROXIES`).

Dit vertelt AIO welke nabije proxy’s `X-Forwarded-*`-headers mogen sturen (echt client-IP en https tegenover http).

| Jouw opstelling | Wat je invult |
|------------|-------------|
| Alleen LAN | **Leeg laten** |
| Alleen Cloudflare Tunnel (token in AIO) | **Leeg laten** — AIO vertrouwt lokale `cloudflared` al |
| nginx / Caddy / Traefik vóór AIO | Het IP van die proxy (zoals AIO het ziet), bijvoorbeeld `172.17.0.1` |

Dit is **geen** lijst van de publieke edge-IP’s van Cloudflare. Met een tunnel komt verkeer van lokale `cloudflared`.  
Zet geen `*` tenzij je het spoofingrisico begrijpt. Herstart de container nadat je dit veld wijzigt.

Aanmeldpoort van Access: [CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md) — vertrouwde proxy’s vervangen Access niet.

---

## Problemen oplossen

| Verschijnsel | Wat je controleert |
|---------|----------------|
| Niet verbonden | Volledige `eyJ…` geplakt; maar één `cloudflared` gebruikt die token |
| 502 op de hostnaam | De service moet `http://127.0.0.1:PORT` in AIO zijn, geen LAN-IP. Direct na boot: wacht tot Catalogus de app als **actief** toont — cloudflared start na de apps, maar een trage app kan kort een 502 geven |
| Interface openen faalt via de tunnel | Voeg een Published application toe voor `https://app.your.domain`; zet **Publiek app-domein** in AIO; verwacht geen `:8989` op de hostnaam van de manager |
| Werkt op het LAN, niet op afstand | Uitgaande firewall / poort **7844**; DNS-CNAME naar `<tunnel-id>.cfargotunnel.com` en ingress van de published application |
| Vreemde aanmelding/cookies | Laat vertrouwde proxy’s leeg bij alleen een tunnel |
| Tokenveld leeg na opslaan | Normaal — op schijf bewaard, nooit opnieuw getoond |
| Connection refused in de cloudflared-logs bij elke boot | Haal een actuele image en **maak de container opnieuw aan**. Oudere builds startten de tunnel vóór de apps; huidige builds starten hem als laatste |

---

## Korte checklist

1. Maak de tunnel in Cloudflare.
2. Kopieer `eyJ…` — draai het installatieprogramma van Cloudflare **niet** op de NAS.
3. Plak de token in AIO → tunnel inschakelen → opslaan.
4. Publiceer hostnamen vanuit AIO (**Publieke subdomeinen** → opslaan → Publiceren naar Cloudflare), of voeg Published applications toe in het Cloudflare-dashboard en sla dezelfde labels op in AIO.
5. Laat vertrouwde proxy’s leeg, tenzij je ook nginx/Caddy ervoor draait.
6. Bevestig Healthy / verbonden en open daarna de HTTPS-URL.
7. Zet *Arr, de downloadclients en Seerr achter [Cloudflare Access](CLOUDFLARE_ACCESS.md). Laat AIO, Jellyfin en Plex op hun eigen aanmelding.
