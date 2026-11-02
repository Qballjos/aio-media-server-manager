# Cloudflare Tunnel

Erreichen Sie AIO (und optionale Apps wie Sonarr oder Jellyfin) aus dem Internet, **ohne Ports** an Ihrem Router zu öffnen.

In einfachen Worten: ein kleines Programm (`cloudflared`) läuft **in AIO**, wählt sich zu Cloudflare hinaus, und Cloudflare liefert `https://your-name.yourdomain.com` aus. Ihre Heim-Firewall bleibt für eingehenden Verkehr geschlossen.

Installieren Sie **keinen** zweiten Cloudflare-Docker-Container oder `cloudflared`-Dienst auf demselben Host für denselben Tunnel — AIO führt ihn bereits aus.

Offizielle Cloudflare-Hilfe: [Create a tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/) · [Tunnel token](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/remote-tunnel-permissions/#get-the-tunnel-token).

Ihre LAN-Oberfläche unter `http://YOUR-SERVER-IP:8080` funktioniert weiter, wenn der Tunnel aus ist.

---

## Was Sie brauchen

- Eine Domain, deren DNS bei Cloudflare liegt
- Rechte, Tunnel anzulegen (**Networking → Tunnels**)
- AIO bereits installiert und durch die Ersteinrichtung

---

## Schritt 1 — Tunnel anlegen

1. Melden Sie sich unter [dash.cloudflare.com](https://dash.cloudflare.com/) an.
2. Öffnen Sie **Networking → Tunnels**  
   (manche Konten zeigen noch **Zero Trust → Networks → Tunnels** — derselbe Ort).
3. **Create a tunnel** → Connectortyp **Cloudflared**.
4. Benennen Sie ihn klar, z. B. `aio-media-manager`.
5. **Create Tunnel**.

---

## Schritt 2 — Nur das Token kopieren

Cloudflare zeigt Installationsbefehle für Docker, Windows und so weiter. **Führen Sie die nicht auf Ihrem NAS aus.** Sie brauchen nur die Token-Zeichenkette.

1. Bleiben Sie auf der Einrichtungs- / **Overview**-Seite des Tunnels.
2. Wählen Sie ein beliebiges Betriebssystem, damit ein Befehl erscheint (oder später: Tunnel → **Overview** → **Add a replica**).
3. Sie sehen etwas wie:

   ```bash
   cloudflared service install eyJhIjoiNWFiNGU5Z...very-long...
   ```

4. Kopieren Sie **nur** den Teil, der mit `eyJ` beginnt (lange JWT-artige Zeichenkette).  
   Behandeln Sie ihn wie ein Passwort — wer ihn hat, kann Ihren Tunnel betreiben.

**Token verloren?** Tunnel → **Overview** → **Add a replica** → `eyJ…` erneut kopieren.  
**Durchgesickert?** Nutzen Sie **Refresh token**, fügen Sie das neue in AIO ein und speichern Sie.

---

## Schritt 3 — Connector-Token in AIO einfügen

1. Öffnen Sie `http://YOUR-SERVER-IP:8080`.
2. **Einstellungen → Netzwerk → Cloudflare Tunnel**
3. Schalten Sie **Tunnel aktivieren** ein, fügen Sie das `eyJ…`-Token ein und speichern Sie.
4. Der Status sollte **Enabled**, **Token saved**, **Tunnel up** und **cloudflared ready** zeigen.  
   Die **CF**-Pille in der Kopfzeile wird grün/blau, wenn alles gesund ist.

Beim Container-Boot startet AIO zuerst das VPN (falls aktiv) und die Katalog-Apps, dann `cloudflared` zuletzt, damit er keine Origins abfragt, die noch starten. Das Dashboard ist erreichbar, während das noch läuft. Nach dem Assistenten der Ersteinrichtung startet der Tunnel weiterhin sofort, wenn Sie fertig sind (vor oder mit dem VPN), damit Sie Hostnamen gleich veröffentlichen können.

Bleibt es bei **Tunnel down**? Prüfen Sie die cloudflared-Protokolle unter Katalog/Diagnose, ausgehenden Zugriff auf Cloudflare (Port **7844**) und dass nichts anderes dasselbe Token nutzt.

---

## Schritt 4 — Anwendungen veröffentlichen (damit Oberfläche öffnen aus der Ferne funktioniert)

Cloudflare liefert nur **HTTPS auf Port 443**. Sie können `https://media.example.com:8989` nicht öffnen.  
Jede App braucht einen eigenen **öffentlichen Hostnamen**, z. B. `https://sonarr.example.com`, abgebildet auf `http://127.0.0.1:8989` **im** AIO-Container.

**Jellyfin:** der Tunnel zeigt auf ein localhost-nginx auf **8097**, das `CF-Connecting-IP` nach `X-Forwarded-For` kopiert. Ohne das sieht Jellyfin jeden Tunnel-Client als `127.0.0.1` (lokal) und überspringt Remote-Bitrate / Auto-Transcode. LAN bleibt bei **8096**.

In Cloudflare heißen das **[Published applications](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/#2a-publish-an-application)** (Hostname → Dienst) — keine Private-Network-Tunnel-CIDR-Routen.

### Am einfachsten: in AIO erledigen

Nachdem das Connector-Token gespeichert ist (Schritt 3):

1. **Einstellungen → Netzwerk → Öffentliche Subdomains**
2. Setzen Sie **Öffentliche App-Domain** auf Ihre Zone (z. B. `example.com` oder `example.co.uk`).
3. Legen Sie ein API-Token so an, wie Cloudflare es beschreibt ([Create API token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)):
   - **My Profile → API Tokens** (Benutzer) oder **Manage Account → Account API Tokens**
   - **Create Token** → starten Sie von der Vorlage **Edit zone DNS**
   - Behalten Sie **Zone → DNS → Edit**, beschränkt auf Ihre Zone
   - Fügen Sie **Account → Cloudflare Tunnel → Edit** hinzu (und möglichst **Zone → Zone → Read**)
   - Weiter zur Zusammenfassung → Create Token (das Geheimnis einmal kopieren)
4. Fügen Sie dieses API-Token unter **Öffentliche Subdomains** ein  
   (das ist **nicht** das `eyJ…`-Connector-Token aus Schritt 3 und **nicht** der Global API Key).
   Wenn Cloudflare **Invalid access token** zurückgibt, löschen Sie das gespeicherte Token und fügen Sie ein frisches **API Token** aus Create Token ein.
5. Schalten Sie **Freigeben** je App ein, ändern Sie Subdomain-Beschriftungen wenn Sie wollen, **speichern**, dann **Bei Cloudflare veröffentlichen**.

**Speichern** aktualisiert die Links für Oberfläche öffnen und die Start-Widgets. **Veröffentlichen** schreibt Published applications in den Tunnel und legt geproxte DNS-CNAMEs an (`<subdomain>.yourzone` → `<tunnel-id>.cfargotunnel.com`).

Übliche Dienstziele (in AIO):

| Hostname | Zeigt auf (in AIO) |
|----------|-------------------------|
| `media.example.com` (AIO) | `http://127.0.0.1:8080` |
| `qbittorrent.example.com` | `http://127.0.0.1:8081` |
| `shelfmark.example.com` | `http://127.0.0.1:8084` |
| `sabnzbd.example.com` | `http://127.0.0.1:8085` |
| `jellyfin.example.com` | `http://127.0.0.1:8097` (CF-Origin-Shim → Jellyfin `:8096`) |
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

Flaresolverr und Recyclarr werden nicht als öffentliche Hostnamen angeboten. Recyclarr ist eine Kommandozeilen-Synchronisation. Flaresolverr wird im Gerät von Prowlarr genutzt. Weitere Ports: [Installieren → Ports](../docs/INSTALL.md#ports).

### Oder: von Hand in Cloudflare veröffentlichen

**Networking → Tunnels** → Ihr Tunnel → **Routes** → **Published application**.  
Die Dienst-URL muss `http://127.0.0.1:PORT` in AIO sein. Gleichen Sie danach dieselben Beschriftungen unter AIO **Öffentliche Subdomains** → **speichern** ab, damit Oberfläche öffnen und Start übereinstimmen.

**Verhalten beim Veröffentlichen**

- AIO ändert nur Hostnamen, die es selbst veröffentlicht hat (oder die Sie jetzt einschalten). Von Hand im Dashboard angelegte Hostnamen, die Sie nie aus AIO veröffentlicht haben, bleiben.
- Eine App auszuschalten und erneut zu veröffentlichen entfernt den Ingress-Hostnamen; der DNS-Name kann bleiben (dann bekommen Sie eine Tunnel-404).
- Den Lauschport einer App zu ändern aktualisiert den Tunnel-Dienst, wenn ein API-Token gespeichert ist.
- Zu Hause öffnet `http://nas-ip:8080` Apps weiter als `http://nas-ip:port`, auch wenn eine öffentliche Domain gesetzt ist.

**Wichtig:** veröffentlichte Hostnamen stehen im öffentlichen Internet, bis Sie [Cloudflare Access](CLOUDFLARE_ACCESS.md) ergänzen. Setzen Sie Access vor die *Arr-Apps, die Download-Clients und Seerr. Lassen Sie das AIO-Dashboard, Jellyfin und Plex bei ihrer eigenen Anmeldung. AIO kann diese Access-Anwendungen anlegen, nachdem Sie eine Anmeldemethode in Zero Trust hinzugefügt haben.

SABnzbd blockiert unbekannte öffentliche Hosts standardmäßig (`External internet access denied`). AIO setzt `inet_exposure` und fügt Ihren veröffentlichten SABnzbd-Hostnamen zu `host_whitelist` hinzu bei Start / Auto-Verknüpfung / Veröffentlichen. Nachdem Sie `sabnzbd` unter Öffentliche Subdomains eingeschaltet haben, starten Sie SABnzbd neu oder führen Sie Auto-Verknüpfung einmal aus, wenn die Seite den Zugriff noch verweigert.

---

## Optional: Tokendatei auf der Platte (SSH / Compose)

Praktisch für umgebungsgetriebene Installationen. Die Pfade liegen auf der **Host**-Seite von `/config`:

| Plattform | Ordner für `tunnel.token` |
|----------|---------------------------|
| Gewöhnliches Linux | `/opt/aio-media-manager/config/cloudflare/` |
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

Aktivieren Sie ihn danach unter **Einstellungen → Netzwerk** (bevorzugt — er wird in `amm_config.json` gespeichert und überlebt Container-Neustarts, auch wenn Compose noch `AMM_CLOUDFLARE_TUNNEL_ENABLED=false` hat), oder setzen Sie dies und erstellen Sie neu:

```bash
AMM_CLOUDFLARE_TUNNEL_ENABLED=true
AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE=/config/cloudflare/tunnel.token
```

Halten Sie **einen** AIO-Dienst in Compose — keinen eigenen `cloudflare/cloudflared`-Container.

---

## Natives Linux (ohne Docker)

Installieren Sie das `cloudflared`-Binary, wenn Sie nicht auf dem GHCR-Image sind, aber führen Sie **nicht** `cloudflared service install` aus — AIO startet den Prozess:

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared
```

Aktivieren Sie den Tunnel in den Einstellungen (oder über die Umgebung) und starten Sie `aio-media-manager.service`.

---

## Prüfen, ob es funktioniert

1. Cloudflare: Tunnelstatus **Healthy**
2. AIO: Einstellungen → Netzwerk → Tunnel **verbunden**
3. Über Mobilfunk (oder ein anderes Netz): öffnen Sie `https://media.example.com` (Ihren Hostnamen)
4. Optionale API-Prüfung (gibt das Token nicht zurück): `GET /api/cloudflare/tunnel/status`

---

## Vertrauenswürdige Reverse-Proxy-IPs

**Einstellungen → Netzwerk → Vertrauenswürdige Reverse-Proxy-IPs** (`AMM_TRUSTED_PROXIES`).

Das sagt AIO, welche nahen Proxys `X-Forwarded-*`-Header senden dürfen (echte Client-IP und https gegenüber http).

| Ihre Einrichtung | Was Sie eintragen |
|------------|-------------|
| Nur LAN | **Leer lassen** |
| Nur Cloudflare Tunnel (Token in AIO) | **Leer lassen** — AIO vertraut lokalem `cloudflared` bereits |
| nginx / Caddy / Traefik vor AIO | Die IP dieses Proxys (wie AIO sie sieht), z. B. `172.17.0.1` |

Das ist **keine** Liste der öffentlichen Edge-IPs von Cloudflare. Mit einem Tunnel kommt der Verkehr von lokalem `cloudflared`.  
Setzen Sie kein `*`, außer Sie verstehen das Spoofing-Risiko. Starten Sie den Container neu, nachdem Sie dieses Feld geändert haben.

Anmeldetor von Access: [CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md) — vertrauenswürdige Proxys ersetzen Access nicht.

---

## Fehlersuche

| Symptom | Was Sie prüfen |
|---------|----------------|
| Nicht verbunden | Vollständiges `eyJ…` eingefügt; nur ein `cloudflared` nutzt dieses Token |
| 502 auf dem Hostnamen | Der Dienst muss `http://127.0.0.1:PORT` in AIO sein, keine LAN-IP. Kurz nach dem Boot warten, bis der Katalog die App als **aktiv** zeigt — cloudflared startet nach den Apps, aber eine sehr langsame App kann kurz 502 liefern |
| Oberfläche öffnen scheitert über den Tunnel | Fügen Sie eine Published application für `https://app.your.domain` hinzu; setzen Sie **Öffentliche App-Domain** in AIO; erwarten Sie kein `:8989` auf dem Hostnamen des Managers |
| Funktioniert im LAN, nicht aus der Ferne | Ausgehende Firewall / Port **7844**; DNS-CNAME auf `<tunnel-id>.cfargotunnel.com` und Ingress der Published application |
| Seltsame Anmeldung/Cookies | Lassen Sie vertrauenswürdige Proxys bei nur einem Tunnel leer |
| Tokenfeld nach dem Speichern leer | Normal — auf der Platte gespeichert, nie wieder angezeigt |
| Connection refused in den cloudflared-Logs bei jedem Boot | Holen Sie ein aktuelles Image und **legen Sie den Container neu an**. Ältere Builds starteten den Tunnel vor den Apps; aktuelle Builds starten ihn zuletzt |

---

## Kurze Checkliste

1. Legen Sie den Tunnel in Cloudflare an.
2. Kopieren Sie `eyJ…` — führen Sie das Installationsprogramm von Cloudflare **nicht** auf dem NAS aus.
3. Fügen Sie das Token in AIO ein → Tunnel aktivieren → speichern.
4. Veröffentlichen Sie Hostnamen aus AIO (**Öffentliche Subdomains** → speichern → Bei Cloudflare veröffentlichen), oder fügen Sie Published applications im Cloudflare-Dashboard hinzu und speichern Sie dieselben Beschriftungen in AIO.
5. Lassen Sie vertrauenswürdige Proxys leer, außer Sie betreiben auch nginx/Caddy davor.
6. Bestätigen Sie Healthy / verbunden und öffnen Sie dann die HTTPS-URL.
7. Setzen Sie *Arr, die Download-Clients und Seerr hinter [Cloudflare Access](CLOUDFLARE_ACCESS.md). Lassen Sie AIO, Jellyfin und Plex bei ihrer eigenen Anmeldung.
