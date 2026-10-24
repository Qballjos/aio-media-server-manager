# Cloudflare Access (porte de connexion)

Utilisez les deux portes. Cloudflare Access est la connexion supplémentaire devant les apps *Arr, les clients de téléchargement et Seerr. Le tableau de bord AIO, Jellyfin et Plex gardent la connexion qu’ils ont déjà.

Access ne remplace pas le mot de passe de Sonarr ni le compte de Seerr. Il demande seulement qui vous êtes **avant** que cette page se charge. Les adresses de votre réseau local (`http://nas-ip:8989`) passent à côté d’Access. Les appels à l’intérieur d’AIO sur `127.0.0.1` aussi.

Publiez d’abord les noms d’hôte : [Cloudflare Tunnel](CLOUDFLARE.md).

Docs officielles Cloudflare : [Self-hosted apps](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/) · [Policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/) · [Identity providers](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/).

---

## Quel nom d’hôte reçoit quelle connexion

| Nom d’hôte (exemple) | Connexion | Pourquoi |
|--------------------|-------|-----|
| `media.example.com` (AIO) | Le compte propre d’AIO | La même idée que Jellyfin et Plex : une connexion que vous avez déjà créée |
| `jellyfin` / `plex` | Le compte propre de cette app | Les apps téléphone et TV ne peuvent pas terminer une page Access |
| `sonarr` / `radarr` / `lidarr` / `prowlarr` / `bazarr` | Cloudflare Access, puis le mot de passe de l’app | Interfaces d’administration. Les navigateurs gèrent la page Access |
| `qbittorrent` / `sabnzbd` / `nzbget` | Cloudflare Access, puis le mot de passe de l’app | Clients de téléchargement, comme *Arr |
| `seerr` | Cloudflare Access, puis le compte propre de Seerr | Interface de demandes dans le navigateur |

Shelfmark, Grimmory et NeutArr restent sur leur propre connexion, sauf si vous ajoutez vous-même une application Access pour eux.

Ne mettez pas le nom d’hôte AIO, Jellyfin ou Plex sur une application Access. Un joker `*.example.com` les prendrait aussi. AIO crée une application par nom d’hôte protégé.

---

## 1. Ouvrir Zero Trust

1. Connectez-vous sur [dash.cloudflare.com](https://dash.cloudflare.com/).
2. Ouvrez **Zero Trust**. Si ce compte n’a pas encore d’organisation Zero Trust, créez-en une et choisissez un nom d’équipe. Le plan gratuit suffit pour un foyer. Voir [Create a Zero Trust organization](https://developers.cloudflare.com/cloudflare-one/setup/).

Le nom d’équipe est le `<your-team-name>` dans l’URL de redirection Google ci-dessous. Vous le trouvez sous **Settings → Team name and domain**.

---

## 2. Ajouter vous-même la méthode de connexion

Choisissez-en une. Vous pourrez en ajouter une autre plus tard. AIO ne la crée pas pour vous.

### Compte Cloudflare (utilise la MFA de ce compte)

Les nouvelles organisations Zero Trust ont déjà le [Cloudflare identity provider](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/cloudflare/). Les gens se connectent avec leur compte Cloudflare. L’authentification multifacteur est la 2FA déjà présente sur cet utilisateur Cloudflare, pas un interrupteur séparé dans Access.

1. **Zero Trust → Integrations → Identity providers**.
2. Si **Cloudflare** manque : **Add new identity provider → Cloudflare**.
3. Activez **Restrict to account members**, puis **Save**.

Avec cet interrupteur, un inconnu qui possède seulement un compte Cloudflare ne peut pas se connecter. Ajoutez les personnes qui doivent ouvrir Sonarr comme membres de ce compte Cloudflare, et faites-leur activer la 2FA sur leur utilisateur Cloudflare.

### Google

Suivez [Google](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google/). En bref :

1. Dans Google Cloud, créez un client OAuth de type **Web application**.
2. Authorized JavaScript origin :

   ```text
   https://<your-team-name>.cloudflareaccess.com
   ```

3. Authorized redirect URI :

   ```text
   https://<your-team-name>.cloudflareaccess.com/cdn-cgi/access/callback
   ```

4. Copiez l’identifiant client et le secret client.
5. **Zero Trust → Integrations → Identity providers → Add new identity provider → Google**. Collez les deux valeurs et **Save**.
6. Choisissez **Test** à côté de Google.

Une connexion Google seule laisse passer n’importe quel compte Google. La politique Allow de la section suivante doit citer les adresses autorisées à entrer.

Google Workspace (groupes d’une organisation) est un autre fournisseur : [Google Workspace](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google-workspace/).

### One-time PIN

Utilisez ceci quand les gens doivent recevoir un code par e-mail et que vous ne voulez pas de compte Google ou Cloudflare. Voir [One-time PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/).

1. **Zero Trust → Integrations → Identity providers → Add new identity provider → One-time PIN**.
2. La politique Allow doit citer ces adresses e-mail. Une politique qui dit seulement « One-time PIN » laisse toute personne capable de lire une boîte mail demander un code.

---

## 3. Qui a le droit d’entrer

Access refuse tout le monde tant qu’une politique Allow ne correspond pas.

| Champ | Valeur |
|-------|--------|
| Policy name | `Admins` |
| Action | **Allow** |
| Include | **Emails** → les adresses qui peuvent ouvrir Sonarr et les clients de téléchargement |

Si vous utilisez le Cloudflare identity provider avec **Restrict to account members**, vous pouvez à la place inclure **Login methods → Cloudflare**.

Vous n’avez pas besoin d’une règle Block séparée. Pas de correspondance veut dire refus.

---

## 4. Ajouter Access depuis AIO

Une fois la méthode de connexion en place, AIO crée les applications Access. AIO ne crée pas la méthode de connexion.

1. **Réglages → Réseau → Sous-domaines publics**.
2. Activez **Exposer** pour les apps *Arr, les clients de téléchargement et Seerr qui doivent être sur Internet. Laissez Jellyfin, Plex et AIO hors d’Access (ils sont marqués **Connexion propre**).
3. **Publier vers Cloudflare** d’abord, pour que les noms d’hôte existent.
4. Sous **Adresses e-mail pour Cloudflare Access**, les adresses autorisées. Laissez la liste vide seulement si la seule méthode est Cloudflare avec **Restrict to account members**.
5. **Ajouter Cloudflare Access**.

Le jeton d’API a besoin de deux droits en plus, en plus de zone DNS Edit et Cloudflare Tunnel Edit :

- **Access: Apps and Policies → Write**
- **Access: Organizations, Identity Providers, and Groups → Read**

AIO écrit une politique Allow nommée `AIO Access` et une application self-hosted par nom d’hôte protégé exposé. La session dure 8 heures pour *Arr et les clients de téléchargement, et 24 heures pour Seerr. Relancer le bouton met ces applications à jour. Désactiver **Exposer** et relancer ne supprime que les applications Access créées par AIO.

À la main : **Access controls → Applications → Create → Self-hosted**, un nom d’hôte à la fois, attacher la politique Allow, et sauter `media`, `jellyfin` et `plex`.

---

## 5. Le tester

1. Ouvrez une fenêtre privée.
2. Visitez `https://sonarr.example.com`. Vous devez voir **Cloudflare Access** d’abord, puis la connexion propre de Sonarr.
3. Visitez `https://seerr.example.com`. Vous devez voir **Cloudflare Access** d’abord, puis Seerr.
4. Visitez `https://jellyfin.example.com` et `https://media.example.com`. Vous devez voir la connexion de Jellyfin et celle d’AIO, sans page Access devant.
5. Sur le wifi de la maison, `http://nas-ip:8989` ouvre encore Sonarr sans Access. Ne l’utilisez qu’à la maison.

---

## Dépannage

| Symptôme | Vérifier |
|---------|--------|
| Pas de connexion Access sur Sonarr | Ce nom d’hôte manque dans Access, ou une faute de frappe |
| Connexion Access sur Jellyfin, Plex ou AIO | Retirez ce nom d’hôte de l’application Access. Un joker `*` provoque cela |
| Boucle de connexion | Apps Access qui se chevauchent, ou Google Workspace qui protège une page Google. Essayez une seule app |
| 403 après connexion | La politique Allow ne correspond pas à cet e-mail ou à ce compte Cloudflare |
| N’importe quel compte Google peut entrer | La politique inclut la méthode Google et ne cite pas d’e-mails |
| Les *Arr dans AIO ne se parlent plus | Cela ne devrait pas arriver. Access dans le navigateur n’affecte pas les appels sur `127.0.0.1` |

---

## Liste courte

1. Tunnel actif et noms d’hôte publiés ([Guide du tunnel](CLOUDFLARE.md)).
2. Ajoutez une méthode de connexion : compte Cloudflare, Google ou One-time PIN.
3. Politique Allow limitée à vos adresses d’administration, ou aux membres de ce compte Cloudflare.
4. **Ajouter Cloudflare Access** dans AIO pour chaque app *Arr exposée, chaque client de téléchargement et Seerr.
5. Laissez AIO, Jellyfin et Plex sur leur propre connexion.
6. Testez Sonarr et Seerr dans une fenêtre privée, puis Jellyfin et le tableau de bord AIO.
