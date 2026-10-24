# Unraid

Installeer **één** AIO-container. Voeg geen Community Applications-sjablonen toe voor Sonarr, Radarr of downloadclients — AIO draait die zelf.

**Sjablonen in deze repo**

| Bestand | Doel |
|------|---------|
| [`unraid/templates/aio-media-manager.xml`](unraid/templates/aio-media-manager.xml) | Docker-sjabloon (poorten, paden, env) |
| [`unraid/ca_profile.xml`](unraid/ca_profile.xml) | Profiel van de Community Applications-beheerder |
| [`unraid.xml`](unraid.xml) | Ouder pad voor hetzelfde sjabloon (compatibiliteit) |

## Mappen maken via SSH

Zet SSH aan (**Settings → Management Access**) en daarna:

```bash
ssh root@<unraid-ip>
```

Downloads en media staan op de **user share** `aio-media-manager` (zichtbaar in Shares / de bestandsbrowser). Config blijft in appdata.

```bash
mkdir -p \
  /mnt/user/appdata/aio-media-manager/vpn \
  /mnt/user/backups/aio-media-manager \
  /mnt/user/aio-media-manager/downloads \
  /mnt/user/aio-media-manager/media

chown -R 99:100 \
  /mnt/user/appdata/aio-media-manager \
  /mnt/user/backups/aio-media-manager \
  /mnt/user/aio-media-manager
```

`/mnt/user/backups/aio-media-manager` ontvangt de configuratieback-ups. Gebruik een share die op de array staat (niet alleen de cache-pool), zodat een cachestoring de back-ups niet meeneemt.

Series, films, anime, muziek, boeken, strips, complete/incomplete downloads, torrentcategorieën en transcode-caches worden bij de eerste start in deze mounts aangemaakt.

`99:100` is Unraid `nobody`/`users` (PUID 99, PGID 100). Gebruik je een eigen share-gebruiker, draai dan `id thatuser` en `chown` naar die UID:GID.

Voor hardlinks houd je downloads en media als submappen van **één** cache- of schijfpad (niet twee `/mnt/user`-FUSE-shares), bijvoorbeeld een cache-only share met de naam `aio-media-manager`:

```bash
mkdir -p /mnt/cache/aio-media-manager/downloads /mnt/cache/aio-media-manager/media
chown -R 99:100 /mnt/cache/aio-media-manager
```

Bind `/data` daarna aan `/mnt/cache/aio-media-manager` (dezelfde share, schijfpad) in plaats van `/mnt/user/aio-media-manager`.

## Installeren vanuit het sjabloon (jouw server)

### Optie A — lokaal gebruikerssjabloon

1. Kopieer de XML naar de flashdrive:

   ```bash
   mkdir -p /boot/config/plugins/dockerMan/templates-user
   curl -fsSL \
     -o /boot/config/plugins/dockerMan/templates-user/my-aio-media-manager.xml \
     https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/templates/aio-media-manager.xml
   ```

2. Docker → **Add Container** → kies **aio-media-manager** (of `my-aio-media-manager`) in de lijst Template.
3. Bevestig paden, `PUID`/`PGID` en `TZ`, en klik op Apply.
4. Open `http://<unraid-ip>:8080` en doorloop de wizard.

### Optie B — handmatig Add Container

1. Docker → Add Container → geavanceerde weergave.
2. Repository: `ghcr.io/qballjos/aio-media-server-manager:latest`
3. Network: `bridge` (of `host` als je elke app-WebUI op het Unraid-IP wilt).
4. Privileged: **On** (nodig voor de VPN-isolatie van qBittorrent).
5. Extra parameters: `--cap-add=NET_ADMIN --cap-add=SYS_MODULE`
6. Optioneel apparaat: `/dev/dri` voor Intel/AMD-transcoden (overslaan als het ontbreekt).
7. Poorten (TCP): publiceer **8080** voor de manager en de kind-WebUI’s die je hebt geïnstalleerd (Sonarr **8989**, Radarr **7878**, qBittorrent **8081**, SABnzbd **8085**, Jellyfin **8096**, Prowlarr **9696**, Seerr **5055**, Plex **32400**, …). Volledige lijst: [INSTALL.md](../docs/INSTALL.md#ports). Of gebruik Network `host`.
8. Paden:
   - `/config` → `/mnt/user/appdata/aio-media-manager`
   - `/data` → `/mnt/user/aio-media-manager`
   - `/backups` → `/mnt/user/backups/aio-media-manager`
   - `/host/sys` → `/sys` (alleen-lezen). De serverkaart op Start toont dan het netwerkverkeer van de server. Het sjabloon noemt dit **Host sys** (geavanceerd). Zonder die regel is de grafiek alleen het verkeer van deze container.
9. Variabelen: `PUID=99`, `PGID=100`, `TZ=<IANA timezone>`, `AMM_DOWNLOAD_DIR=/data/downloads`, `AMM_MEDIA_DIR=/data/media`. Optioneel: `GITHUB_TOKEN`.

Na het bijwerken van de image maak je de container opnieuw aan, zodat toegevoegde WebUI-poortmappings gelden.

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

Geef de voorkeur aan `/mnt/cache/aio-media-manager` of één schijfpad voor downloads en media als hardlinks ertoe doen. `/mnt/user` (FUSE) mengen met een schijfshare kan atomaire verplaatsingen breken.

## Updates

Wijzig de repository-tag of gebruik de containerupdate van Unraid, en maak daarna opnieuw aan zodat nieuwe poorten en de Host sys-mount gelden. Images worden vanaf `main` gepubliceerd als `:latest` en vanaf git-tags als semver. Dat werkt AIO bij. Geïnstalleerde apps werk je bij via **Instellingen → Updates** (schema’s staan standaard uit).
