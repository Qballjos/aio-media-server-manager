# Cloudflare Tunnel

Atteignez AIO (et des apps facultatives comme Sonarr ou Jellyfin) depuis Internet **sans ouvrir de ports** sur votre routeur.

En clair : un petit programme (`cloudflared`) tourne **dans AIO**, appelle Cloudflare vers l’extérieur, et Cloudflare sert `https://your-name.yourdomain.com`. Votre pare-feu domestique reste fermé au trafic entrant.

N’installez **pas** un second conteneur Docker Cloudflare ni un service `cloudflared` sur le même hôte pour le même tunnel — AIO le fait déjà tourner.

Aide officielle Cloudflare : [Create a tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/) · [Tunnel token](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/remote-tunnel-permissions/#get-the-tunnel-token).

Votre interface LAN sur `http://YOUR-SERVER-IP:8080` fonctionne encore quand le tunnel est coupé.

---

## Ce qu’il vous faut

- Un domaine dont le DNS est chez Cloudflare
- Le droit de créer des tunnels (**Networking → Tunnels**)
- AIO déjà installé et passé par la première exécution

---

## Étape 1 — Créer le tunnel

1. Connectez-vous sur [dash.cloudflare.com](https://dash.cloudflare.com/).
2. Ouvrez **Networking → Tunnels**  
   (certains comptes affichent encore **Zero Trust → Networks → Tunnels** — le même endroit).
3. **Create a tunnel** → type de connecteur **Cloudflared**.
4. Donnez-lui un nom clair, par exemple `aio-media-manager`.
5. **Create Tunnel**.

---

## Étape 2 — Ne copier que le jeton

Cloudflare affiche des commandes d’installation pour Docker, Windows, et ainsi de suite. **Ne les lancez pas sur votre NAS.** Il vous faut seulement la chaîne du jeton.

1. Restez sur la page d’installation / **Overview** du tunnel.
2. Choisissez n’importe quel système pour qu’une commande apparaisse (ou plus tard : tunnel → **Overview** → **Add a replica**).
3. Vous verrez quelque chose comme :

   ```bash
   cloudflared service install eyJhIjoiNWFiNGU5Z...very-long...
   ```

4. Copiez **seulement** la partie qui commence par `eyJ` (longue chaîne de type JWT).  
   Traitez-la comme un mot de passe — quiconque l’a peut faire tourner votre tunnel.

**Jeton perdu ?** Tunnel → **Overview** → **Add a replica** → copiez `eyJ…` à nouveau.  
**Divulgué ?** Utilisez **Refresh token**, collez le nouveau dans AIO et enregistrez.

---

## Étape 3 — Coller le jeton connecteur dans AIO

1. Ouvrez `http://YOUR-SERVER-IP:8080`.
2. **Réglages → Réseau → Cloudflare Tunnel**
3. Activez **Activer le tunnel**, collez le jeton `eyJ…` et enregistrez.
4. Le statut doit afficher **Enabled**, **Token saved**, **Tunnel up** et **cloudflared ready**.  
   La pastille **CF** de l’en-tête passe au vert/bleu quand tout va bien.

Au démarrage du conteneur, AIO démarre d’abord le VPN (s’il est activé) et les apps du catalogue, puis `cloudflared` en dernier pour qu’il ne sonde pas des origines encore en démarrage. Le tableau de bord reste joignable pendant ce temps. Après l’assistant de première exécution, le tunnel démarre toujours dès que vous terminez (avant ou avec le VPN), pour pouvoir publier les noms d’hôte tout de suite.

Bloqué sur **Tunnel down** ? Regardez les journaux cloudflared dans Catalogue/Diagnostic, l’accès sortant vers Cloudflare (port **7844**), et qu’aucun autre processus n’utilise le même jeton.

---

## Étape 4 — Publier les applications (pour qu’Ouvrir l’interface marche à distance)

Cloudflare ne sert que **HTTPS sur le port 443**. Vous ne pouvez pas ouvrir `https://media.example.com:8989`.  
Chaque app a besoin de son propre **nom d’hôte public**, par exemple `https://sonarr.example.com`, mappé vers `http://127.0.0.1:8989` **dans** le conteneur AIO.

**Jellyfin :** le tunnel pointe vers un nginx local sur **8097** qui copie `CF-Connecting-IP` vers `X-Forwarded-For`. Sans cela, Jellyfin voit chaque client tunnel comme `127.0.0.1` (local) et ignore la limite de débit distante / le transcodage Auto. Le LAN reste sur **8096**.

Dans Cloudflare, ce sont des **[Published applications](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/#2a-publish-an-application)** (nom d’hôte → service) — pas des routes CIDR de réseau privé du tunnel.

### Le plus simple : le faire dans AIO

Une fois le jeton connecteur enregistré (étape 3) :

1. **Réglages → Réseau → Sous-domaines publics**
2. Mettez **Domaine public des apps** sur votre zone (par exemple `example.com` ou `example.co.uk`).
3. Créez un jeton d’API comme Cloudflare le documente ([Create API token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)) :
   - **My Profile → API Tokens** (utilisateur) ou **Manage Account → Account API Tokens**
   - **Create Token** → partez du modèle **Edit zone DNS**
   - Gardez **Zone → DNS → Edit**, limité à votre zone
   - Ajoutez **Account → Cloudflare Tunnel → Edit** (et de préférence **Zone → Zone → Read**)
   - Continuez jusqu’au résumé → Create Token (copiez le secret une fois)
4. Collez ce jeton d’API sous **Sous-domaines publics**  
   (ce n’est **pas** le jeton connecteur `eyJ…` de l’étape 3, et **pas** la Global API Key).
   Si Cloudflare renvoie **Invalid access token**, effacez le jeton enregistré et collez un **API Token** neuf depuis Create Token.
5. Activez **Exposer** par app, modifiez les libellés de sous-domaine si vous voulez, **enregistrez**, puis **Publier vers Cloudflare**.

**Enregistrer** met à jour les liens Ouvrir l’interface et les widgets de l’accueil. **Publier** écrit les published applications dans le tunnel et crée des CNAME DNS proxifiés (`<subdomain>.yourzone` → `<tunnel-id>.cfargotunnel.com`).

Cibles de service habituelles (dans AIO) :

| Nom d’hôte | Pointe vers (dans AIO) |
|----------|-------------------------|
| `media.example.com` (AIO) | `http://127.0.0.1:8080` |
| `qbittorrent.example.com` | `http://127.0.0.1:8081` |
| `shelfmark.example.com` | `http://127.0.0.1:8084` |
| `sabnzbd.example.com` | `http://127.0.0.1:8085` |
| `jellyfin.example.com` | `http://127.0.0.1:8097` (shim CF → Jellyfin `:8096`) |
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

Flaresolverr et Recyclarr ne sont pas proposés comme noms d’hôte publics. Recyclarr est une synchro en ligne de commande. Flaresolverr est utilisé dans l’appliance par Prowlarr. Plus de ports : [Installer → Ports](../docs/INSTALL.md#ports).

### Ou : publier à la main dans Cloudflare

**Networking → Tunnels** → votre tunnel → **Routes** → **Published application**.  
L’URL de service doit être `http://127.0.0.1:PORT` dans AIO. Alignez ensuite les mêmes libellés sous AIO **Sous-domaines publics** → **enregistrer**, pour qu’Ouvrir l’interface et l’accueil concordent.

**Comportement de la publication**

- AIO ne change que les noms d’hôte qu’il a publiés (ou que vous activez maintenant). Les noms d’hôte faits à la main dans le tableau de bord et jamais publiés depuis AIO restent.
- Couper une app et republier retire le nom d’hôte d’ingress ; le nom DNS peut rester (vous obtenez alors une 404 du tunnel).
- Changer le port d’écoute d’une app met à jour le service du tunnel quand un jeton d’API est enregistré.
- À la maison, `http://nas-ip:8080` ouvre encore les apps en `http://nas-ip:port`, même si un domaine public est défini.

**Important :** les noms d’hôte publiés sont sur Internet public tant que vous n’ajoutez pas [Cloudflare Access](CLOUDFLARE_ACCESS.md). Placez Access devant les apps *Arr, les clients de téléchargement et Seerr. Laissez le tableau de bord AIO, Jellyfin et Plex sur leur propre connexion. AIO peut créer ces applications Access après que vous avez ajouté une méthode de connexion dans Zero Trust.

SABnzbd bloque par défaut les Hosts publics inconnus (`External internet access denied`). AIO règle `inet_exposure` et ajoute votre nom d’hôte SABnzbd publié à `host_whitelist` au démarrage / Liaison auto / Publier. Après avoir activé `sabnzbd` sous Sous-domaines publics, redémarrez SABnzbd ou lancez Liaison auto une fois si la page refuse encore l’accès.

---

## Facultatif : fichier de jeton sur le disque (SSH / Compose)

Pratique pour les installations pilotées par l’environnement. Les chemins sont du côté **hôte** de `/config` :

| Plateforme | Dossier pour `tunnel.token` |
|----------|---------------------------|
| Linux ordinaire | `/opt/aio-media-manager/config/cloudflare/` |
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

Activez-le ensuite dans **Réglages → Réseau** (préférable — il est enregistré dans `amm_config.json` et survit aux redémarrages du conteneur, même si Compose a encore `AMM_CLOUDFLARE_TUNNEL_ENABLED=false`), ou définissez ceci et recréez :

```bash
AMM_CLOUDFLARE_TUNNEL_ENABLED=true
AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE=/config/cloudflare/tunnel.token
```

Gardez **un** seul service AIO dans Compose — pas de conteneur `cloudflare/cloudflared` séparé.

---

## Linux natif (sans Docker)

Installez le binaire `cloudflared` si vous n’êtes pas sur l’image GHCR, mais **ne** lancez **pas** `cloudflared service install` — AIO démarre le processus :

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared
```

Activez le tunnel dans Réglages (ou via l’environnement) et démarrez `aio-media-manager.service`.

---

## Vérifier que ça marche

1. Cloudflare : statut du tunnel **Healthy**
2. AIO : Réglages → Réseau → tunnel **connecté**
3. Depuis les données mobiles (ou un autre réseau) : ouvrez `https://media.example.com` (votre nom d’hôte)
4. Contrôle d’API facultatif (ne renvoie pas le jeton) : `GET /api/cloudflare/tunnel/status`

---

## IP de reverse proxy de confiance

**Réglages → Réseau → IP de reverse proxy de confiance** (`AMM_TRUSTED_PROXIES`).

Cela dit à AIO quels proxys proches peuvent envoyer des en-têtes `X-Forwarded-*` (vraie IP client et https plutôt que http).

| Votre installation | Ce que vous mettez |
|------------|-------------|
| LAN seulement | **Laisser vide** |
| Cloudflare Tunnel seulement (jeton dans AIO) | **Laisser vide** — AIO fait déjà confiance au `cloudflared` local |
| nginx / Caddy / Traefik devant AIO | L’IP de ce proxy (telle qu’AIO la voit), par exemple `172.17.0.1` |

Ce n’est **pas** une liste des IP edge publiques de Cloudflare. Avec un tunnel, le trafic arrive du `cloudflared` local.  
Ne mettez pas `*` sauf si vous comprenez le risque d’usurpation. Redémarrez le conteneur après avoir changé ce champ.

Porte de connexion Access : [CLOUDFLARE_ACCESS.md](CLOUDFLARE_ACCESS.md) — les proxys de confiance ne remplacent pas Access.

---

## Dépannage

| Symptôme | À vérifier |
|---------|----------------|
| Pas connecté | `eyJ…` complet collé ; un seul `cloudflared` utilise ce jeton |
| 502 sur le nom d’hôte | Le service doit être `http://127.0.0.1:PORT` dans AIO, pas une IP du LAN. Juste après le boot, attendez que le Catalogue montre l’app **active** — cloudflared démarre après les apps, mais une app très lente peut encore donner un 502 un instant |
| Ouvrir l’interface échoue via le tunnel | Ajoutez une Published application pour `https://app.your.domain` ; définissez **Domaine public des apps** dans AIO ; n’attendez pas `:8989` sur le nom d’hôte du gestionnaire |
| Ça marche sur le LAN, pas à distance | Pare-feu sortant / port **7844** ; CNAME DNS vers `<tunnel-id>.cfargotunnel.com` et l’ingress de la published application |
| Connexion ou cookies bizarres | Laissez les proxys de confiance vides pour un tunnel seul |
| Champ du jeton vide après enregistrement | Normal — stocké sur le disque, jamais réaffiché |
| Connection refused dans les journaux cloudflared à chaque boot | Tirez une image actuelle et **recréez** le conteneur. Les anciennes builds démarraient le tunnel avant les apps ; les builds actuelles le démarrent en dernier |

---

## Liste courte

1. Créez le tunnel dans Cloudflare.
2. Copiez `eyJ…` — ne lancez **pas** l’installateur de Cloudflare sur le NAS.
3. Collez le jeton dans AIO → activer le tunnel → enregistrer.
4. Publiez les noms d’hôte depuis AIO (**Sous-domaines publics** → enregistrer → Publier vers Cloudflare), ou ajoutez des Published applications dans le tableau de bord Cloudflare et enregistrez les mêmes libellés dans AIO.
5. Laissez les proxys de confiance vides, sauf si vous faites aussi tourner nginx/Caddy devant.
6. Confirmez Healthy / connecté, puis ouvrez l’URL HTTPS.
7. Placez *Arr, les clients de téléchargement et Seerr derrière [Cloudflare Access](CLOUDFLARE_ACCESS.md). Laissez AIO, Jellyfin et Plex sur leur propre connexion.
