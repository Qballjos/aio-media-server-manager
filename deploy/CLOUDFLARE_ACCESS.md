# Cloudflare Access (login gate)

Use both doors. Cloudflare Access is the extra login in front of the *Arr apps, the download clients, and Seerr. The AIO dashboard, Jellyfin, and Plex keep the login they already have.

Access does not replace Sonarr’s password or Seerr’s account. It only asks who you are **before** that page loads. Addresses on your home network (`http://nas-ip:8989`) skip Access. Calls inside AIO on `127.0.0.1` skip it too.

Publish the hostnames first: [Cloudflare Tunnel](CLOUDFLARE.md).

Official Cloudflare docs: [Self-hosted apps](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/) · [Policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/) · [Identity providers](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/).

---

## Which hostname gets which login

| Hostname (example) | Login | Why |
|--------------------|-------|-----|
| `media.example.com` (AIO) | AIO’s own account | Same idea as Jellyfin and Plex: one login you already set up |
| `jellyfin` / `plex` | That app’s own account | Phone and TV apps cannot complete an Access page |
| `sonarr` / `radarr` / `lidarr` / `prowlarr` / `bazarr` | Cloudflare Access, then the app password | Admin UIs. Browsers handle the Access page |
| `qbittorrent` / `sabnzbd` / `nzbget` | Cloudflare Access, then the app password | Download clients, same as *Arr |
| `seerr` | Cloudflare Access, then Seerr’s own account | Request UI in the browser |

Shelfmark, Grimmory, and NeutArr stay on their own login unless you add an Access application for them yourself.

Do not put the AIO hostname, Jellyfin, or Plex on an Access application. A wildcard `*.example.com` would catch them too. AIO creates one application per protected hostname.

---

## 1. Open Zero Trust

1. Sign in at [dash.cloudflare.com](https://dash.cloudflare.com/).
2. Open **Zero Trust**. If this account has no Zero Trust organization yet, create one and pick a team name. The free plan is enough for a household. See [Create a Zero Trust organization](https://developers.cloudflare.com/cloudflare-one/setup/).

The team name is the `<your-team-name>` in the Google redirect URL below. Find it under **Settings → Team name and domain**.

---

## 2. Add the login method yourself

Pick one. You can add another later. AIO does not create this for you.

### Cloudflare account (uses the MFA on that account)

New Zero Trust organizations already have the [Cloudflare identity provider](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/cloudflare/). People sign in with their Cloudflare account. Multi-factor authentication is the 2FA already on that Cloudflare user, not a separate switch inside Access.

1. **Zero Trust → Integrations → Identity providers**.
2. If **Cloudflare** is missing: **Add new identity provider → Cloudflare**.
3. Turn on **Restrict to account members**, then **Save**.

With that switch on, a stranger who merely owns some Cloudflare account cannot sign in. Add the people who should reach Sonarr as members of this Cloudflare account, and have them turn on 2FA on their Cloudflare user.

### Google

Follow [Google](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google/). In short:

1. In Google Cloud, create an OAuth client of type **Web application**.
2. Authorized JavaScript origin:

   ```text
   https://<your-team-name>.cloudflareaccess.com
   ```

3. Authorized redirect URI:

   ```text
   https://<your-team-name>.cloudflareaccess.com/cdn-cgi/access/callback
   ```

4. Copy the client ID and client secret.
5. **Zero Trust → Integrations → Identity providers → Add new identity provider → Google**. Paste both values and **Save**.
6. Select **Test** next to Google.

A Google login by itself lets any Google account through. The Allow policy in the next section must list the addresses that may enter.

Google Workspace (groups from an organization) is a different provider: [Google Workspace](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google-workspace/).

### One-time PIN

Use this when people should get a code by email and you do not want a Google or Cloudflare account. See [One-time PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/).

1. **Zero Trust → Integrations → Identity providers → Add new identity provider → One-time PIN**.
2. The Allow policy must list those email addresses. A policy that only says “One-time PIN” lets anyone who can read a mailbox request a code.

---

## 3. Who is allowed in

Access denies everyone until an Allow policy matches.

| Field | Value |
|-------|--------|
| Policy name | `Admins` |
| Action | **Allow** |
| Include | **Emails** → the addresses that may open Sonarr and the download clients |

If you use the Cloudflare identity provider with **Restrict to account members**, you can instead include **Login methods → Cloudflare**.

You do not need a separate Block rule. No match means deny.

---

## 4. Add Access from AIO

After the login method exists, AIO creates the Access applications. It does not create the login method.

1. **Settings → Network → Public subdomains**.
2. Turn on **Expose** for the *Arr apps, download clients, and Seerr you want on the internet. Leave Jellyfin, Plex, and AIO off Access (they are marked **Own login**).
3. **Publish to Cloudflare** first, so the hostnames exist.
4. Under **Cloudflare Access emails**, list the addresses that may enter. Leave the list empty only when the only login method is Cloudflare with **Restrict to account members**.
5. **Add Cloudflare Access**.

The API token needs two extra permissions, on top of zone DNS Edit and Cloudflare Tunnel Edit:

- **Access: Apps and Policies → Write**
- **Access: Organizations, Identity Providers, and Groups → Read**

AIO writes one Allow policy named `AIO Access` and one self-hosted application per exposed protected hostname. Session length is 8 hours for *Arr and download clients, and 24 hours for Seerr. Running the button again updates those applications. Turning **Expose** off and running it again deletes only the Access applications AIO created.

To do the same by hand: **Access controls → Applications → Create → Self-hosted**, one hostname at a time, attach the Allow policy, and skip `media`, `jellyfin`, and `plex`.

---

## 5. Test it

1. Open a private window.
2. Visit `https://sonarr.example.com`. You should see **Cloudflare Access** first, then Sonarr’s own login.
3. Visit `https://seerr.example.com`. You should see **Cloudflare Access** first, then Seerr.
4. Visit `https://jellyfin.example.com` and `https://media.example.com`. You should see Jellyfin’s login and AIO’s login, with no Access page in front.
5. From home wifi, `http://nas-ip:8989` still opens Sonarr without Access. Use that only at home.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| No Access login on Sonarr | That hostname is missing from Access, or a typo |
| Access login on Jellyfin, Plex, or AIO | Remove that hostname from the Access application. A `*` wildcard causes this |
| Login loop | Overlapping Access apps, or Google Workspace protecting a Google-hosted page. Try one app |
| 403 after login | The Allow policy does not match this email or Cloudflare account |
| Any Google account can enter | The policy includes the Google login method and does not list emails |
| *Arr inside AIO stops talking to each other | It should not. Browser Access does not affect calls on `127.0.0.1` |

---

## Quick checklist

1. Tunnel up and hostnames published ([Tunnel guide](CLOUDFLARE.md)).
2. Add a login method: Cloudflare account, Google, or One-time PIN.
3. Allow policy limited to your admin emails, or to members of this Cloudflare account.
4. **Add Cloudflare Access** in AIO for each exposed *Arr app, download client, and Seerr.
5. Leave AIO, Jellyfin, and Plex on their own login.
6. Test Sonarr and Seerr in a private window, then test Jellyfin and the AIO dashboard.
