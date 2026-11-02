# Unraid

Installeer **één** AIO-container. Voeg geen Community Applications-sjablonen toe voor Sonarr, Radarr of downloadclients — AIO draait die zelf.

**Sjablonen in deze repo**

| Bestand | Doel |
|------|---------|
| [`unraid/templates/aio-media-manager.xml`](unraid/templates/aio-media-manager.xml) | Docker-sjabloon (poorten, paden, env) |
| [`unraid/ca_profile.xml`](unraid/ca_profile.xml) | Profiel van de Community Applications-beheerder |
| [`unraid.xml`](unraid.xml) | Ouder pad voor hetzelfde sjabloon (compatibiliteit) |

## SSD-downloadopslag voorbereiden

Start de array met een gekoppelde SSD/NVMe-pool en voer als root uit:

```bash
ssh root@<unraid-ip>
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/install.sh | sh
```

Het script controleert de pool voordat het mappen maakt en installeert het lokale Docker-sjabloon. Voor een andere pool: download het script en voer het uit met `CACHE_ROOT=/mnt/fast sh /tmp/amm-install.sh`. De share `aio-download-cache` blijft alleen op die pool (geen secundaire opslag, geen Mover naar de array). Onvolledige downloads en Usenet-uitpakken gebruiken de SSD; afgeronde torrents en de mediabibliotheek blijven onder `/mnt/user/aio-media-manager` op de array. Imports tussen SSD en HDD kopiëren bestanden. Houd voldoende SSD-ruimte vrij voor downloaden plus uitpakken en stel een vrije-ruimtelimiet in de downloaders in. Bestaande downloadmappen met bestanden of symlinks worden geweigerd: stop AIO, kopieer en verifieer de bestanden en pas daarna de mounts toe. Zonder pool stopt het script; verwijder voor een bewuste HDD-installatie beide SSD-mounts uit het sjabloon. Zie [volledige opslaginstructies](UNRAID.md).

## Installeren vanuit het sjabloon (jouw server)

### Optie A — lokaal gebruikerssjabloon

1. Voer eerst het voorbereidingsscript hierboven uit; het installeert het lokale gebruikerssjabloon met de gekozen poolpaden.

2. Docker → **Add Container** → kies **aio-media-manager** (of `my-aio-media-manager`) in de lijst Template.
3. Bevestig paden, `PUID`/`PGID` en `TZ`, en klik op Apply.
4. Open `http://<unraid-ip>:8080` en doorloop de wizard.

### Optie B — handmatig Add Container

1. Docker → Add Container → geavanceerde weergave.
2. Repository: `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Network: `bridge` (of `host` als je elke app-WebUI op het Unraid-IP wilt).
4. Privileged: **On** (nodig voor de VPN-isolatie van qBittorrent / Prowlarr / Flaresolverr). Met VPN aan wachten die apps op een live WireGuard-handshake; AIO cached hun DNS via de tunnel zodat korte haperingen Prowlarr-indexers niet offline gooien. Details: [DOCKER.md](DOCKER.md#optionele-vpn).
5. Extra parameters: `--cap-add=NET_ADMIN --cap-add=SYS_MODULE`
6. Optioneel apparaat: `/dev/dri` voor Intel/AMD-transcoden (overslaan als het ontbreekt).
7. Poorten (TCP): publiceer **8080** voor de manager en de kind-WebUI’s die je hebt geïnstalleerd (Sonarr **8989**, Radarr **7878**, qBittorrent **8081**, SABnzbd **8085**, Jellyfin **8096**, Prowlarr **9696**, Seerr **5055**, Plex **32400**, …). Volledige lijst: [INSTALL.md](../docs/INSTALL.md#ports). Of gebruik Network `host`.
8. Paden:
   - `/config` → `/mnt/user/appdata/aio-media-manager`
   - `/data` → `/mnt/user/aio-media-manager`
   - `/data/downloads/incomplete` → `/mnt/cache/aio-download-cache/incomplete`
   - `/data/downloads/complete` → `/mnt/cache/aio-download-cache/complete`
   - `/backups` → `/mnt/user/backups/aio-media-manager`
   - `/host/sys` → `/sys` (alleen-lezen). De serverkaart op Start toont dan het netwerkverkeer van de server. Het sjabloon noemt dit **Host sys** (geavanceerd). Zonder die regel is de grafiek alleen het verkeer van deze container.
9. Variabelen: `PUID=99`, `PGID=100`, `TZ=<IANA timezone>`, `AMM_DOWNLOAD_DIR=/data/downloads`, `AMM_MEDIA_DIR=/data/media`. Optioneel: `GITHUB_TOKEN`.

Na het bijwerken van de image maak je de container opnieuw aan, zodat toegevoegde WebUI-poortmappings gelden.

??? note "Voor beheerders: een sjabloon publiceren (niet nodig om AIO te installeren)"

    ## Publiceren naar Community Applications (publieke winkel)

    Community Apps host **jouw** bestanden niet. Jij houdt een publieke GitHub-repo met sjablonen; de CA-scanner van Lime Technology indexeert die nadat je hem indient.

    ### 1. Een sjablonen-repository voorbereiden

    Aanbevolen: een **eigen publieke repo** (bijvoorbeeld `Qballjos/unraid-templates`) waarvan de root er zo uitziet:

    ```text
    ca_profile.xml
    templates/aio-media-manager.xml
    ```

    Kopieer vanuit dit project:

    ```bash
    # from a clone of aio-media-server-manager
    mkdir -p ../unraid-templates/templates
    cp deploy/unraid/ca_profile.xml ../unraid-templates/
    cp deploy/unraid/templates/aio-media-manager.xml ../unraid-templates/templates/
    ```

    Daarna:

    1. Maak de publieke GitHub-repo en push `main`.
    2. Bewerk `templates/aio-media-manager.xml` en zet `<TemplateURL>` op de **raw**-URL van dat bestand in de nieuwe repo (moet overeenkomen met het echte pad op `main`).
    3. Houd `<Repository>` op `ghcr.io/qballjos/aio-media-server-manager:latest` (de image blijft op GHCR; alleen de sjabloon-XML staat in de sjablonen-repo).
    4. Optioneel: open een ondersteuningsthread op het Unraid-forum en zet de URL in `ca_profile.xml` bij `<Forum>` en in de `<Support>`-tags van het sjabloon (GitHub Issues is een prima begin).

    Je *kunt* in plaats daarvan de hoofdrepo van de app indienen als de XML vindbaar is en elke app een `<Repository>`-tag heeft, maar een kleine eigen sjablonen-repo is wat CA-beheerders meestal verwachten.

    ### 2. Indienen

    1. Meld je aan op **[https://ca.unraid.net/submit](https://ca.unraid.net/submit)** met je Unraid- / forumaccount.
    2. Registreer de **GitHub-repository-URL** (de sjablonen-repo).
    3. Draai **Validate** en daarna **Scan**. Herstel gemelde XML-problemen.
    4. Wacht op moderatie. Na goedkeuring verschijnt de app voor iedereen onder het tabblad Apps.

    Nuttige docs:

    - [Submission help](https://ca.unraid.net/submit/help)
    - [Repository XML format](https://ca.unraid.net/submit/help/repository-xml)
    - [XML field reference](https://ca.unraid.net/submit/help/xml-field-reference)
    - [Browse catalog](https://ca.unraid.net/apps) (controleer eerst op naamconflicten)

    Gebruik **niet** de afgeschafte aanvraagstroom `selfhosters/unRAID-CA-templates`.

    ### 3. Nadat hij vermeld staat

    - Lever updates door een nieuwe container-image te publiceren (`:latest` of semver-tags). Gebruikers werken bij via de Docker-update van Unraid — je hoeft het sjabloon meestal **niet** bij elke release te verhogen.
    - Wijzig de sjabloon-XML alleen als poorten, paden of env-variabelen veranderen; CA leest `<TemplateURL>` opnieuw bij een verversing.

    ### Privé / alleen voor jezelf (niet de publieke winkel)

    Om je eigen GitHub-sjablonen te gebruiken zonder CA-goedkeuring, voeg je de repo-URL toe aan:

    ```text
    /boot/config/plugins/dockerMan/template-repos
    ```

    (één URL per regel). De sjablonen verschijnen dan onder Docker → Add Container. Dat zet de app **niet** in de publieke Community Applications-catalogus.

## FUSE / hardlinks

SSD-downloads en array-media staan op verschillende bestandssystemen: imports kopiëren bestanden. Afgeronde torrents en de bibliotheek blijven onder `/data`; hardlinks vereisen hetzelfde fysieke bestandssysteem. Meng bij migratie geen `/mnt/user`- en `/mnt/disk*`-paden naar dezelfde bestanden.

## Updates

Wijzig de repository-tag of gebruik de containerupdate van Unraid, en maak daarna opnieuw aan zodat nieuwe poorten en de Host sys-mount gelden. Images worden vanaf `main` gepubliceerd als `:latest` en vanaf git-tags als semver. Dat werkt AIO bij. Geïnstalleerde apps werk je bij via **Instellingen → Updates** (schema’s staan standaard uit).
