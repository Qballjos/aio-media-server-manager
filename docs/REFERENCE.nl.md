# Geavanceerd: poorten en instellingen

[Beginnershandleiding](INSTALL.md) · [Geavanceerd](ADVANCED.md)

## Poorten {#ports}

De interface van de manager gebruikt **8080**. Kind-apps luisteren in dezelfde container. Compose en NAS-sjablonen publiceren die poorten op de host, zodat **Interface openen** werkt (`http://YOUR-IP:8989` voor Sonarr, enzovoort). Host-netwerk is een alternatief als je niet elke poort wilt mappen.

| Applicatie | Standaardpoort |
|-------------|--------------|
| <img src="__AIO_ASSET__/assets/logo-aio-media-manager.png" alt="" class="aio-app-icon" /> Manager-UI | 8080 |
| <img src="__AIO_ASSET__/assets/app-icons/qbittorrent.svg" alt="" class="aio-app-icon" /> qBittorrent | 8081 |
| <img src="__AIO_ASSET__/assets/app-icons/shelfmark.png" alt="" class="aio-app-icon" /> Shelfmark | 8084 |
| <img src="__AIO_ASSET__/assets/app-icons/sabnzbd.svg" alt="" class="aio-app-icon" /> SABnzbd | 8085 |
| <img src="__AIO_ASSET__/assets/app-icons/jellyfin.svg" alt="" class="aio-app-icon" /> Jellyfin | 8096 |
| <img src="__AIO_ASSET__/assets/app-icons/flaresolverr.png" alt="" class="aio-app-icon" /> Flaresolverr | 8191 (alleen x86_64) |
| <img src="__AIO_ASSET__/assets/app-icons/bazarr.svg" alt="" class="aio-app-icon" /> Bazarr | 6767 |
| <img src="__AIO_ASSET__/assets/app-icons/nzbget.svg" alt="" class="aio-app-icon" /> NZBGet | 6789 |
| <img src="__AIO_ASSET__/assets/app-icons/lidarr.svg" alt="" class="aio-app-icon" /> Lidarr | 8686 |
| <img src="__AIO_ASSET__/assets/app-icons/sonarr.svg" alt="" class="aio-app-icon" /> Sonarr | 8989 |
| <img src="__AIO_ASSET__/assets/app-icons/radarr.svg" alt="" class="aio-app-icon" /> Radarr | 7878 |
| <img src="__AIO_ASSET__/assets/app-icons/prowlarr.svg" alt="" class="aio-app-icon" /> Prowlarr | 9696 |
| <img src="__AIO_ASSET__/assets/app-icons/seerr.svg" alt="" class="aio-app-icon" /> Seerr | 5055 |
| <img src="__AIO_ASSET__/assets/app-icons/grimmory.svg" alt="" class="aio-app-icon" /> Grimmory | 6060 |
| <img src="__AIO_ASSET__/assets/app-icons/neutarr.svg" alt="" class="aio-app-icon" /> NeutArr | 9705 |
| <img src="__AIO_ASSET__/assets/app-icons/recyclarr.svg" alt="" class="aio-app-icon" /> Recyclarr | geen (alleen CLI) |
| <img src="__AIO_ASSET__/assets/app-icons/plex.svg" alt="" class="aio-app-icon" /> Plex | 32400 |

## Veelgebruikte omgevingsvariabelen

Kopieer [`.env.example`](../.env.example) voor native installs. Veel hiervan kun je later ook in **Instellingen** zetten.

| Variabele | Doel |
|----------|---------|
| `PUID` / `PGID` | Gebruiker waaronder de apps draaien (gelijk aan de mapeigenaar) |
| `TZ` / `AMM_TIMEZONE` | Tijdzone voor logs en schema’s |
| `AMM_DOWNLOAD_DIR` / `AMM_MEDIA_DIR` | Paden in de container (host-mounts wijzig je in compose) |
| `GITHUB_TOKEN` | Optioneel; hogere GitHub-API-limiet voor updates |
| `AMM_CLOUDFLARE_TUNNEL_*` | Optionele tunnel voor toegang van buitenaf (`cloudflared` start na de apps bij boot) |
| `AMM_VPN_*` | Optionele VPN voor qBittorrent, Prowlarr en Flaresolverr (ze wachten op de tunnel; lokale DNS-cache voor die apps) |
