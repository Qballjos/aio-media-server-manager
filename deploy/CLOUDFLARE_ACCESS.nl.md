# Cloudflare Access (aanmeldpoort)

Gebruik beide deuren. Cloudflare Access is de extra aanmelding vóór de *Arr-apps, de downloadclients en Seerr. Het AIO-dashboard, Jellyfin en Plex houden de aanmelding die ze al hebben.

Access vervangt het wachtwoord van Sonarr of het account van Seerr niet. Het vraagt alleen wie je bent **voordat** die pagina laadt. Adressen op je thuisnetwerk (`http://nas-ip:8989`) slaan Access over. Aanroepen binnen AIO op `127.0.0.1` ook.

Publiceer eerst de hostnamen: [Cloudflare Tunnel](CLOUDFLARE.md).

Officiële docs van Cloudflare: [Self-hosted apps](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/) · [Policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/) · [Identity providers](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/).

---

## Welke hostnaam welke aanmelding krijgt

| Hostnaam (voorbeeld) | Aanmelding | Waarom |
|--------------------|-------|-----|
| `media.example.com` (AIO) | Het eigen account van AIO | Hetzelfde idee als Jellyfin en Plex: één aanmelding die je al hebt gemaakt |
| `jellyfin` / `plex` | Het eigen account van die app | Telefoon- en tv-apps kunnen een Access-pagina niet afmaken |
| `sonarr` / `radarr` / `lidarr` / `prowlarr` / `bazarr` | Cloudflare Access, daarna het app-wachtwoord | Beheerinterfaces. Browsers kunnen de Access-pagina aan |
| `qbittorrent` / `sabnzbd` / `nzbget` | Cloudflare Access, daarna het app-wachtwoord | Downloadclients, hetzelfde als *Arr |
| `seerr` | Cloudflare Access, daarna het eigen account van Seerr | Aanvraagscherm in de browser |

Shelfmark, Grimmory en NeutArr blijven op hun eigen aanmelding, tenzij je er zelf een Access-applicatie voor toevoegt.

Zet de AIO-hostnaam, Jellyfin of Plex niet op een Access-applicatie. Een wildcard `*.example.com` pakt die ook. AIO maakt één applicatie per beschermde hostnaam.

---

## 1. Open Zero Trust

1. Meld je aan op [dash.cloudflare.com](https://dash.cloudflare.com/).
2. Open **Zero Trust**. Heeft dit account nog geen Zero Trust-organisatie, maak er dan een en kies een teamnaam. Het gratis plan is genoeg voor een huishouden. Zie [Create a Zero Trust organization](https://developers.cloudflare.com/cloudflare-one/setup/).

De teamnaam is de `<your-team-name>` in de Google-redirect-URL hieronder. Je vindt hem onder **Settings → Team name and domain**.

---

## 2. Voeg zelf de aanmeldmethode toe

Kies er één. Je kunt later een tweede toevoegen. AIO maakt dit niet voor je.

### Cloudflare-account (gebruikt de MFA van dat account)

Nieuwe Zero Trust-organisaties hebben de [Cloudflare identity provider](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/cloudflare/) al. Mensen melden zich aan met hun Cloudflare-account. Meervoudige authenticatie is de 2FA die al op die Cloudflare-gebruiker staat, geen aparte schakelaar in Access.

1. **Zero Trust → Integrations → Identity providers**.
2. Ontbreekt **Cloudflare**: **Add new identity provider → Cloudflare**.
3. Zet **Restrict to account members** aan en kies **Save**.

Met die schakelaar aan kan een vreemde die toevallig een Cloudflare-account heeft niet aanmelden. Voeg de mensen die Sonarr mogen openen toe als leden van dit Cloudflare-account, en laat ze 2FA aanzetten op hun Cloudflare-gebruiker.

### Google

Volg [Google](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google/). In het kort:

1. Maak in Google Cloud een OAuth-client van het type **Web application**.
2. Authorized JavaScript origin:

   ```text
   https://<your-team-name>.cloudflareaccess.com
   ```

3. Authorized redirect URI:

   ```text
   https://<your-team-name>.cloudflareaccess.com/cdn-cgi/access/callback
   ```

4. Kopieer de client-ID en het client secret.
5. **Zero Trust → Integrations → Identity providers → Add new identity provider → Google**. Plak beide waarden en kies **Save**.
6. Kies **Test** naast Google.

Een Google-aanmelding op zich laat elk Google-account door. De Allow-policy in het volgende onderdeel moet de adressen noemen die naar binnen mogen.

Google Workspace (groepen uit een organisatie) is een andere provider: [Google Workspace](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google-workspace/).

### One-time PIN

Gebruik dit als mensen een code per e-mail moeten krijgen en je geen Google- of Cloudflare-account wilt. Zie [One-time PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/).

1. **Zero Trust → Integrations → Identity providers → Add new identity provider → One-time PIN**.
2. De Allow-policy moet die e-mailadressen noemen. Een policy die alleen “One-time PIN” zegt, laat iedereen die een mailbox kan lezen een code aanvragen.

---

## 3. Wie naar binnen mag

Access weigert iedereen tot een Allow-policy overeenkomt.

| Veld | Waarde |
|-------|--------|
| Policy name | `Admins` |
| Action | **Allow** |
| Include | **Emails** → de adressen die Sonarr en de downloadclients mogen openen |

Gebruik je de Cloudflare identity provider met **Restrict to account members**, dan kun je in plaats daarvan **Login methods → Cloudflare** opnemen.

Je hebt geen aparte Block-regel nodig. Geen overeenkomst betekent weigeren.

---

## 4. Access toevoegen vanuit AIO

Als de aanmeldmethode er is, maakt AIO de Access-applicaties. De aanmeldmethode zelf maakt AIO niet.

1. **Instellingen → Netwerk → Publieke subdomeinen**.
2. Zet **Vrijgeven** aan voor de *Arr-apps, downloadclients en Seerr die op internet mogen. Laat Jellyfin, Plex en AIO van Access af (die staan op **Eigen aanmelding**).
3. **Publiceren naar Cloudflare** eerst, zodat de hostnamen bestaan.
4. Onder **E-mailadressen voor Cloudflare Access** de adressen die binnen mogen. Laat de lijst leeg alleen als de enige aanmeldmethode Cloudflare is met **Restrict to account members**.
5. **Cloudflare Access toevoegen**.

Het API-token heeft twee extra rechten nodig, bovenop zone DNS Edit en Cloudflare Tunnel Edit:

- **Access: Apps and Policies → Write**
- **Access: Organizations, Identity Providers, and Groups → Read**

AIO schrijft één Allow-policy met de naam `AIO Access` en één self-hosted applicatie per vrijgegeven beschermde hostnaam. De sessie duurt 8 uur voor *Arr en downloadclients, en 24 uur voor Seerr. De knop nog een keer uitvoeren werkt die applicaties bij. **Vrijgeven** uit en de knop opnieuw haalt alleen de Access-applicaties weg die AIO heeft gemaakt.

Met de hand: **Access controls → Applications → Create → Self-hosted**, één hostnaam per keer, de Allow-policy koppelen, en `media`, `jellyfin` en `plex` overslaan.

---

## 5. Test het

1. Open een privévenster.
2. Ga naar `https://sonarr.example.com`. Je hoort eerst **Cloudflare Access** te zien, daarna de eigen aanmelding van Sonarr.
3. Ga naar `https://seerr.example.com`. Je hoort eerst **Cloudflare Access** te zien, daarna Seerr.
4. Ga naar `https://jellyfin.example.com` en `https://media.example.com`. Je hoort de aanmelding van Jellyfin en die van AIO te zien, zonder Access-pagina ervoor.
5. Op thuis-wifi opent `http://nas-ip:8989` Sonarr nog steeds zonder Access. Gebruik dat alleen thuis.

---

## Problemen oplossen

| Verschijnsel | Controleer |
|---------|--------|
| Geen Access-aanmelding op Sonarr | Die hostnaam ontbreekt in Access, of een typefout |
| Access-aanmelding op Jellyfin, Plex of AIO | Haal die hostnaam uit de Access-applicatie. Een wildcard `*` veroorzaakt dit |
| Aanmeldlus | Overlappende Access-apps, of Google Workspace dat een Google-pagina beschermt. Probeer één app |
| 403 na aanmelden | De Allow-policy past niet bij dit e-mailadres of Cloudflare-account |
| Elk Google-account kan naar binnen | De policy neemt de Google-aanmeldmethode op en noemt geen e-mailadressen |
| *Arr binnen AIO praat niet meer met elkaar | Dat hoort niet. Browser-Access raakt aanroepen op `127.0.0.1` niet |

---

## Korte checklist

1. Tunnel aan en hostnamen gepubliceerd ([Tunnelgids](CLOUDFLARE.md)).
2. Voeg een aanmeldmethode toe: Cloudflare-account, Google of One-time PIN.
3. Allow-policy beperkt tot je beheeradressen, of tot leden van dit Cloudflare-account.
4. **Cloudflare Access toevoegen** in AIO voor elke vrijgegeven *Arr-app, downloadclient en Seerr.
5. Laat AIO, Jellyfin en Plex op hun eigen aanmelding.
6. Test Sonarr en Seerr in een privévenster, en daarna Jellyfin en het AIO-dashboard.
