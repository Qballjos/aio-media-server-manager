# Unraid

Installieren Sie **einen** AIO-Container. Fügen Sie keine Community-Applications-Vorlagen für Sonarr, Radarr oder Download-Clients hinzu — AIO führt die selbst aus.

**Vorlagen in diesem Repo**

| Datei | Zweck |
|------|---------|
| [`unraid/templates/aio-media-manager.xml`](unraid/templates/aio-media-manager.xml) | Docker-Vorlage (Ports, Pfade, Umgebung) |
| [`unraid/ca_profile.xml`](unraid/ca_profile.xml) | Profil des Community-Applications-Betreuers |
| [`unraid.xml`](unraid.xml) | Älterer Pfad für dieselbe Vorlage (Kompatibilität) |

## SSD-Downloadspeicher vorbereiten

Starten Sie das Array mit einem eingebundenen SSD/NVMe-Pool und führen Sie als root aus:

```bash
ssh root@<unraid-ip>
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/install.sh | sh
```

Das Skript prüft den Pool vor dem Anlegen der Ordner und installiert die lokale Docker-Vorlage. Für einen anderen Pool laden Sie das Skript herunter und starten es mit `CACHE_ROOT=/mnt/fast sh /tmp/amm-install.sh`. Die Freigabe `aio-download-cache` bleibt ausschließlich auf diesem Pool (kein sekundärer Speicher, kein Mover zum Array). Unvollständige Downloads und das Entpacken von Usenet-Dateien nutzen die SSD; fertige Torrents und die Medienbibliothek bleiben unter `/mnt/user/aio-media-manager` auf dem Array. SSD-HDD-Importe kopieren Dateien. Halten Sie Platz für Downloads und Entpacken frei und konfigurieren Sie eine Freiplatzgrenze in den Downloadern. Vorhandene Downloadordner mit Dateien oder Symlinks werden abgelehnt: AIO stoppen, Dateien kopieren und prüfen, dann die Mounts anwenden. Ohne Pool stoppt das Skript; für eine bewusste HDD-Installation entfernen Sie beide SSD-Mounts aus der Vorlage. Siehe [vollständige Speicheranleitung](UNRAID.md).

## Aus der Vorlage installieren (Ihr Server)

### Option A — lokale Benutzervorlage

1. Führen Sie zuerst das Vorbereitungsskript oben aus; es installiert die lokale Benutzervorlage mit den gewählten Poolpfaden.

2. Docker → **Add Container** → wählen Sie **aio-media-manager** (oder `my-aio-media-manager`) in der Liste Template.
3. Bestätigen Sie Pfade, `PUID`/`PGID` und `TZ`, dann Apply.
4. Öffnen Sie `http://<unraid-ip>:8080` und durchlaufen Sie den Assistenten.

### Option B — Add Container von Hand

1. Docker → Add Container → erweiterte Ansicht.
2. Repository: `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Network: `bridge` (oder `host`, wenn jede App-WebUI auf der Unraid-IP liegen soll).
4. Privileged: **On** (nötig für die VPN-Isolation von qBittorrent / Prowlarr / Flaresolverr). Mit VPN an warten diese Apps auf einen Live-WireGuard-Handshake; AIO cached ihre DNS über den Tunnel, damit kurze Aussetzer Prowlarr-Indexer nicht offline schalten. Details: [DOCKER.md](DOCKER.md#optionales-vpn).
5. Extra parameters: `--cap-add=NET_ADMIN --cap-add=SYS_MODULE`
6. Optionales Gerät: `/dev/dri` für Intel/AMD-Transkodierung (weglassen, wenn es fehlt).
7. Ports (TCP): veröffentlichen Sie **8080** für den Manager und die installierten Kind-WebUIs (Sonarr **8989**, Radarr **7878**, qBittorrent **8081**, SABnzbd **8085**, Jellyfin **8096**, Prowlarr **9696**, Seerr **5055**, Plex **32400**, …). Vollständige Liste: [INSTALL.md](../docs/INSTALL.md#ports). Oder Network `host`.
8. Pfade:
   - `/config` → `/mnt/user/appdata/aio-media-manager`
   - `/data` → `/mnt/user/aio-media-manager`
   - `/data/downloads/incomplete` → `/mnt/cache/aio-download-cache/incomplete`
   - `/data/downloads/complete` → `/mnt/cache/aio-download-cache/complete`
   - `/backups` → `/mnt/user/backups/aio-media-manager`
   - `/host/sys` → `/sys` (nur lesend). Die Server-Karte auf Start zeigt dann den Netzwerkverkehr des Servers. Die Vorlage nennt das **Host sys** (erweitert). Ohne diese Zeile ist die Grafik nur der Verkehr dieses Containers.
9. Variablen: `PUID=99`, `PGID=100`, `TZ=<IANA timezone>`, `AMM_DOWNLOAD_DIR=/data/downloads`, `AMM_MEDIA_DIR=/data/media`. Optional: `GITHUB_TOKEN`.

Nach dem Aktualisieren des Images erstellen Sie den Container neu, damit hinzugefügte WebUI-Portzuordnungen gelten.

??? note "Für Maintainer: Vorlage veröffentlichen (nicht zur Installation nötig)"

    ## In Community Applications veröffentlichen (öffentlicher Katalog)

    Community Apps hostet **Ihre** Dateien nicht. Sie halten ein öffentliches GitHub-Repo mit Vorlagen; der CA-Scanner von Lime Technology indexiert es, nachdem Sie es einreichen.

    ### 1. Ein Vorlagen-Repository vorbereiten

    Empfohlen: ein **eigenes öffentliches Repo** (zum Beispiel `Qballjos/unraid-templates`), dessen Wurzel so aussieht:

    ```text
    ca_profile.xml
    templates/aio-media-manager.xml
    ```

    Aus diesem Projekt kopieren:

    ```bash
    # from a clone of aio-media-server-manager
    mkdir -p ../unraid-templates/templates
    cp deploy/unraid/ca_profile.xml ../unraid-templates/
    cp deploy/unraid/templates/aio-media-manager.xml ../unraid-templates/templates/
    ```

    Dann:

    1. Legen Sie das öffentliche GitHub-Repo an und pushen Sie `main`.
    2. Bearbeiten Sie `templates/aio-media-manager.xml` und setzen Sie `<TemplateURL>` auf die **raw**-URL dieser Datei im neuen Repo (muss zum echten Pfad auf `main` passen).
    3. Lassen Sie `<Repository>` bei `ghcr.io/qballjos/aio-media-server-manager:latest` (das Image bleibt auf GHCR; nur die Vorlagen-XML liegt im Vorlagen-Repo).
    4. Optional: öffnen Sie einen Support-Thread im Unraid-Forum und tragen Sie die URL in `ca_profile.xml` bei `<Forum>` und in den `<Support>`-Tags der Vorlage ein (GitHub Issues reicht zum Start).

    Sie *können* stattdessen das Haupt-Repo der App einreichen, wenn die XML auffindbar ist und jede App ein `<Repository>`-Tag hat, aber ein kleines eigenes Vorlagen-Repo ist, was CA-Betreuer meist erwarten.

    ### 2. Einreichen

    1. Melden Sie sich unter **[https://ca.unraid.net/submit](https://ca.unraid.net/submit)** mit Ihrem Unraid- / Forenkonto an.
    2. Registrieren Sie die **GitHub-Repository-URL** (das Vorlagen-Repo).
    3. Führen Sie **Validate** und danach **Scan** aus. Beheben Sie gemeldete XML-Probleme.
    4. Warten Sie auf die Moderation. Nach der Freigabe erscheint die App für alle unter dem Reiter Apps.

    Hilfreiche Docs:

    - [Submission help](https://ca.unraid.net/submit/help)
    - [Repository XML format](https://ca.unraid.net/submit/help/repository-xml)
    - [XML field reference](https://ca.unraid.net/submit/help/xml-field-reference)
    - [Browse catalog](https://ca.unraid.net/apps) (prüfen Sie zuerst Namenskollisionen)

    Nutzen Sie **nicht** den eingestellten Anfrageweg `selfhosters/unRAID-CA-templates`.

    ### 3. Nach der Aufnahme

    - Liefern Sie Updates, indem Sie ein neues Container-Image veröffentlichen (`:latest` oder Semver-Tags). Nutzer aktualisieren über das Docker-Update von Unraid — die Vorlage müssen Sie in der Regel **nicht** bei jeder Veröffentlichung anheben.
    - Ändern Sie die Vorlagen-XML nur, wenn sich Ports, Pfade oder Umgebungsvariablen ändern; CA liest `<TemplateURL>` beim Aktualisieren neu.

    ### Privat / nur für sich (nicht der öffentliche Katalog)

    Um eigene GitHub-Vorlagen ohne CA-Freigabe zu nutzen, hängen Sie die Repo-URL an:

    ```text
    /boot/config/plugins/dockerMan/template-repos
    ```

    (eine URL pro Zeile). Die Vorlagen erscheinen dann unter Docker → Add Container. Das listet die App **nicht** im öffentlichen Community-Applications-Katalog.

## FUSE / hardlinks

SSD-Downloads und Array-Medien liegen auf verschiedenen Dateisystemen: Importe kopieren Dateien. Fertige Torrents und die Bibliothek bleiben unter `/data`; Hardlinks erfordern dasselbe physische Dateisystem. Mischen Sie bei Migrationen keine `/mnt/user`- und `/mnt/disk*`-Pfade derselben Dateien.

## Updates

Ändern Sie das Repository-Tag oder nutzen Sie das Container-Update von Unraid und erstellen Sie danach neu, damit neue Ports und der Host-sys-Mount gelten. Images werden von `main` als `:latest` und von Git-Tags als Semver veröffentlicht. Das aktualisiert AIO. Installierte Apps aktualisieren Sie unter **Einstellungen → Updates** (Zeitpläne standardmäßig aus).
