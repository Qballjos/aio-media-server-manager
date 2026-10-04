# Secure AIO apps with Cloudflare Access

Published tunnel hostnames (`https://sonarr.example.com`, …) are on the public internet. **Cloudflare Access** adds a login gate in front of them so only people you allow can reach the app UI.

This guide is for AIO Media Server Manager after you have:

1. A working Cloudflare Tunnel (see [CLOUDFLARE.md](CLOUDFLARE.md)).
2. App hostnames published (Settings → Network → **Public subdomains** → Publish, or manual tunnel routes).

Official Cloudflare docs: [Self-hosted public applications](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/) · [Access policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/).

---

## What Access does (and does not)

| Does | Does not |
|------|----------|
| Show a Cloudflare login before the app loads | Replace Sonarr/Jellyfin/qBittorrent’s own passwords |
| Allow only emails / IdP groups you choose | Protect LAN `http://192.168.x.x:port` (Access is for public hostnames) |
| Work for every published hostname you attach | Automatically cover new subdomains until you add them to an Access app |

Keep strong app logins too. Access is the outer door; app auth is still useful.

---

## 1. Prerequisites

- Domain on Cloudflare (full setup recommended).
- Tunnel healthy in AIO (header **CF** pill / Settings → Network).
- At least one published hostname, e.g. `media.example.com`, `sonarr.example.com`.
- A Cloudflare Zero Trust / Cloudflare One account (free tier is enough for a household).

---

## 2. Prefer Access before leaving apps open

Best order:

1. Publish hostnames from AIO (or the tunnel dashboard).
2. **Create Access applications + Allow policies** (this document).
3. Share the HTTPS links with your household.

If you publish first without Access, anyone who guesses the hostname can hit the login page of Sonarr/qBittorrent until Access is on.

---

## 3. One-time login method (household / One-time PIN)

Simplest setup with no Google/Microsoft IdP:

1. Open [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → your account.
2. Go to **Settings → Authentication**.
3. Under **Login methods**, ensure **One-time PIN** (email) is enabled.  
   Users receive a code by email when they sign in.

You can also enable Google, GitHub, Microsoft, etc., and use those in policies later.

---

## 4. Create an Access application (per hostname or wildcard)

### Option A — one Access app per AIO service (clearest)

Repeat for each published hostname you care about (`media`, `sonarr`, `jellyfin`, `qbittorrent`, …):

1. Go to **Access controls → Applications** → **Create new application**.
2. Choose **Self-hosted and private**.
3. Select **Add public hostname**.
4. Pick your domain and enter the subdomain (e.g. subdomain `sonarr`, domain `example.com` → `sonarr.example.com`).  
   For multi-part zones use the full zone (e.g. `example.co.uk`).
5. Under **Access policies**, create or attach an Allow policy (next section).
6. Identity providers: enable **One-time PIN** and/or your SSO IdP.
7. **Session Duration**: e.g. 24 hours for home use (shorter for admin tools).
8. Select **Create**.

### Option B — one Access app with a wildcard (faster)

If all apps live under the same zone:

1. Create one self-hosted application.
2. Add public hostname with subdomain `*` (or the wildcard form your dashboard offers) on `example.com`.  
   That can cover `sonarr.example.com`, `radarr.example.com`, etc.
3. Attach the same Allow policy to everyone in the house.

Wildcards are convenient; per-hostname apps let you give Jellyfin to more people than qBittorrent.

**Manager tip:** Protect `media.example.com` (or whatever subdomain you use for AIO itself) with Access as well — it can start/stop apps.

---

## 5. Allow policy examples

Access is **deny by default**. An application with no Allow policy blocks everyone.

### Household emails (recommended start)

| Field | Value |
|-------|--------|
| Policy name | `Family` |
| Action | **Allow** |
| Include | **Emails** → your addresses, or **Emails ending in** → `@yourfamily.com` |

### You only (admin apps)

Use a tighter policy on Sonarr / Radarr / Prowlarr / qBittorrent / SABnzbd:

| Include | Emails → `you@example.com` only |

Attach the broader “Family” policy to Jellyfin / Seerr / the AIO manager if others need them.

### Optional: block everyone else

You do not need an explicit Block rule for the public internet — no match ⇒ deny. Add Block rules only for special cases (e.g. block a country).

---

## 6. Recommended mapping for AIO

| Hostname (example) | Who | Why |
|--------------------|-----|-----|
| `media.example.com` (AIO) | Admins | Can control the stack |
| `sonarr` / `radarr` / `lidarr` / `prowlarr` / `bazarr` | Admins | Automation UIs |
| `qbittorrent` / `sabnzbd` / `nzbget` | Admins | Download clients |
| `jellyfin` / `plex` / `seerr` | Family (or admins) | Day-to-day media |
| `grimmory` / `shelfmark` / others | As needed | Same pattern |

Adjust subdomains to whatever you set under **Public subdomains**.

---

## 7. Test

1. Open a private/incognito window.
2. Visit `https://sonarr.example.com` (or your subdomain).
3. You should see the **Cloudflare Access** login (email code or IdP), not Sonarr yet.
4. After success, Sonarr loads. Sign out of Access (or wait for session expiry) to re-test.

LAN URLs (`http://nas-ip:8989`) bypass Access — that is expected. Use them only on your home network.

---

## 8. Optional hardening

- **Shorter sessions** on download/admin apps (e.g. 1–8 hours).
- **IdP + MFA** (Google/Microsoft) instead of email OTP for stronger accounts.
- **App Launcher** (Zero Trust) to bookmark approved apps in one place.
- Turn on **Protect with Access** on the tunnel route in the Cloudflare dashboard when available, so `cloudflared` rejects requests that skipped Access.
- Keep AIO **Support share** off unless you are debugging.

---

## 9. When you add or rename a subdomain

1. Publish the new hostname from AIO (**Public subdomains** → Publish).
2. Either:
   - Add that hostname to an existing Access application, or
   - Rely on a `*.example.com` wildcard Access app, or
   - Create a new Access application for it.

Access does not auto-discover new AIO publishes.

---

## 10. Troubleshooting

| Symptom | Check |
|---------|--------|
| No Access login — app opens directly | Hostname not added to any Access application; or wrong hostname spelling |
| Infinite redirect / login loop | Cookie / multiple Access apps overlapping; try one app; check IdP |
| 403 after login | Policy Include rules do not match your email/IdP group |
| Works on phone data, fails on home Wi‑Fi | Unrelated to Access; check split DNS / local overrides |
| Arr API from another app breaks | Browser Access does not affect container-to-container `127.0.0.1` calls inside AIO |

---

## Quick checklist

1. Tunnel up + hostnames published ([CLOUDFLARE.md](CLOUDFLARE.md)).
2. Enable **One-time PIN** (or an IdP) under Zero Trust authentication.
3. Create Access application(s) for your public hostnames.
4. Add an **Allow** policy (your emails / family domain).
5. Test in a private window on each important hostname.
6. Prefer Access on admin apps before sharing links outside the house.
