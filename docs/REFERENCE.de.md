# Fortgeschritten: Ports und Einstellungen

[Einsteigeranleitung](INSTALL.md) · [Fortgeschritten](ADVANCED.md)

## Ports {#ports}

Die Oberfläche des Managers nutzt **8080**. Kind-Apps lauschen im selben Container. Compose und NAS-Vorlagen veröffentlichen diese Ports auf dem Host, damit **Oberfläche öffnen** funktioniert (`http://YOUR-IP:8989` für Sonarr und so weiter). Host-Netzwerk ist eine Alternative, wenn Sie nicht jeden Port mappen wollen.

| Anwendung | Standardport |
|-------------|--------------|
| <img src="__AIO_ASSET__/assets/logo-aio-media-manager.png" alt="" class="aio-app-icon" /> Manager-Oberfläche | 8080 |
| <img src="__AIO_ASSET__/assets/app-icons/qbittorrent.svg" alt="" class="aio-app-icon" /> qBittorrent | 8081 |
| <img src="__AIO_ASSET__/assets/app-icons/shelfmark.png" alt="" class="aio-app-icon" /> Shelfmark | 8084 |
| <img src="__AIO_ASSET__/assets/app-icons/sabnzbd.svg" alt="" class="aio-app-icon" /> SABnzbd | 8085 |
| <img src="__AIO_ASSET__/assets/app-icons/jellyfin.svg" alt="" class="aio-app-icon" /> Jellyfin | 8096 |
| <img src="__AIO_ASSET__/assets/app-icons/flaresolverr.png" alt="" class="aio-app-icon" /> Flaresolverr | 8191 (nur x86_64) |
| <img src="__AIO_ASSET__/assets/app-icons/bazarr.svg" alt="" class="aio-app-icon" /> Bazarr | 6767 |
| <img src="__AIO_ASSET__/assets/app-icons/nzbget.svg" alt="" class="aio-app-icon" /> NZBGet | 6789 |
| <img src="__AIO_ASSET__/assets/app-icons/lidarr.svg" alt="" class="aio-app-icon" /> Lidarr | 8686 |
| <img src="__AIO_ASSET__/assets/app-icons/sonarr.svg" alt="" class="aio-app-icon" /> Sonarr | 8989 |
| <img src="__AIO_ASSET__/assets/app-icons/radarr.svg" alt="" class="aio-app-icon" /> Radarr | 7878 |
| <img src="__AIO_ASSET__/assets/app-icons/prowlarr.svg" alt="" class="aio-app-icon" /> Prowlarr | 9696 |
| <img src="__AIO_ASSET__/assets/app-icons/seerr.svg" alt="" class="aio-app-icon" /> Seerr | 5055 |
| <img src="__AIO_ASSET__/assets/app-icons/grimmory.svg" alt="" class="aio-app-icon" /> Grimmory | 6060 |
| <img src="__AIO_ASSET__/assets/app-icons/neutarr.svg" alt="" class="aio-app-icon" /> NeutArr | 9705 |
| <img src="__AIO_ASSET__/assets/app-icons/recyclarr.svg" alt="" class="aio-app-icon" /> Recyclarr | keine (nur CLI) |
| <img src="__AIO_ASSET__/assets/app-icons/plex.svg" alt="" class="aio-app-icon" /> Plex | 32400 |

## Häufige Umgebungsvariablen

Kopieren Sie [`.env.example`](../.env.example) für native Installationen. Vieles davon lässt sich später auch unter **Einstellungen** setzen.

| Variable | Zweck |
|----------|---------|
| `PUID` / `PGID` | Benutzer, als der die Apps laufen (muss zum Ordnerbesitzer passen) |
| `TZ` / `AMM_TIMEZONE` | Zeitzone für Protokolle und Zeitpläne |
| `AMM_DOWNLOAD_DIR` / `AMM_MEDIA_DIR` | Pfade im Container (Host-Mounts ändern Sie in Compose) |
| `GITHUB_TOKEN` | Optional; höheres GitHub-API-Limit für Updates |
| `AMM_CLOUDFLARE_TUNNEL_*` | Optionaler Tunnel für Fernzugriff (`cloudflared` startet nach den Apps beim Boot) |
| `AMM_VPN_*` | Optionales VPN für qBittorrent, Prowlarr und Flaresolverr (sie warten auf den Tunnel; lokaler DNS-Cache für diese Apps) |
