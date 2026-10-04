# Cloudflare Access (login gate)

Once a tunnel hostname is public (`https://sonarr.example.com`), anyone who finds the URL can reach that app’s login page. **Cloudflare Access** puts a second door in front: Cloudflare asks for email (or SSO) **before** Sonarr, Jellyfin, or qBittorrent even loads.

Think of it as a bouncer for your household links.

### Before you start

1. Tunnel working — [Cloudflare Tunnel](CLOUDFLARE.md)
2. Hostnames published (AIO **Public subdomains** → Publish, or manual tunnel routes)

Official Cloudflare docs: [Self-hosted apps](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/) · [Policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/).

---

## What Access does (and does not)

| It does | It does not |
|---------|-------------|
| Show a Cloudflare login first | Replace Sonarr/Jellyfin’s own passwords |
| Allow only emails / groups you choose | Protect LAN links like `http://192.168.x.x:8989` |
| Cover hostnames you attach to an Access app | Auto-add brand-new subdomains until you include them |

Keep strong passwords inside each app too. Access is the outer door.

---

## Suggested order

1. Publish hostnames.
2. **Turn on Access + Allow policies** (this page).
3. Share HTTPS links with family.

If you publish without Access first, a guessed hostname can hit Sonarr or qBittorrent until you finish this guide.

---

## 1. Turn on a simple login method

Easiest for a household — **email one-time PIN** (no Google/Microsoft required):

1. Open [Cloudflare Zero Trust](https://one.dash.cloudflare.com/).
2. **Settings → Authentication**
3. Under **Login methods**, enable **One-time PIN**.  
   People get a code by email when they sign in.

You can add Google, Microsoft, etc. later if you prefer.

---

## 2. Create an Access application

### Option A — one app per hostname (clearest)

Repeat for each URL you care about (`media`, `sonarr`, `jellyfin`, `qbittorrent`, …):

1. **Access controls → Applications → Create**
2. Choose **Self-hosted**
3. **Add public hostname** — subdomain + your domain  
   (for `example.co.uk`, use the full zone)
4. Attach an Allow policy (next section)
5. Enable **One-time PIN** (and/or SSO)
6. Session length: e.g. 24 hours at home; shorter for admin tools
7. **Create**

### Option B — one wildcard (faster)

One self-hosted application with subdomain `*` on `example.com` can cover `sonarr.example.com`, `radarr.example.com`, and the rest.  
Handy for a small household; separate apps let you share Jellyfin with more people than qBittorrent.

Protect the AIO manager hostname too — it can start and stop the stack.

---

## 3. Who is allowed in

Access **denies everyone** until you add an Allow policy.

### Whole household (good start)

| Field | Value |
|-------|--------|
| Policy name | `Family` |
| Action | **Allow** |
| Include | **Emails** → your addresses, or **Emails ending in** → `@yourfamily.com` |

### Admins only (Sonarr, Radarr, download clients)

| Include | Emails → `you@example.com` only |

Attach the broader “Family” policy to Jellyfin / Seerr / the manager if others need them.  
You usually do **not** need an explicit Block rule for the open internet — no match means deny.

---

## 4. Recommended who-gets-what

| Hostname (example) | Who | Why |
|--------------------|-----|-----|
| `media.example.com` (AIO) | Admins | Controls the stack |
| `sonarr` / `radarr` / `lidarr` / `prowlarr` / `bazarr` | Admins | Automation UIs |
| `qbittorrent` / `sabnzbd` | Admins | Downloads |
| `jellyfin` / `plex` / `seerr` | Family (or admins) | Day-to-day watching |
| Other apps | As needed | Same idea |

Use whatever subdomains you set under **Public subdomains**.

---

## 5. Test it

1. Open a private/incognito window.
2. Visit `https://sonarr.example.com` (or your URL).
3. You should see **Cloudflare Access** first — not Sonarr.
4. After login, the app loads. Sign out of Access (or wait for expiry) to re-test.

LAN URLs (`http://nas-ip:8989`) **skip** Access — that is normal. Use those only at home.

---

## Optional hardening

- Shorter sessions on download/admin apps (1–8 hours)
- SSO + MFA instead of email codes
- Zero Trust **App Launcher** to bookmark approved apps
- “Protect with Access” on the tunnel route in Cloudflare when available
- Keep AIO **Support share** off unless you are debugging

---

## When you add or rename a subdomain

1. Publish it from AIO (**Public subdomains** → Publish).
2. Add it to an Access application, use a `*.example.com` wildcard, or create a new Access app.

Access does not notice new publishes by itself.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| No Access login — app opens straight away | Hostname missing from Access, or typo |
| Login loop | Overlapping Access apps / cookies; try one app; check IdP |
| 403 after login | Allow policy does not match your email/group |
| Works on mobile data, fails on home Wi‑Fi | Usually DNS / local overrides — not Access |
| *Arr API between apps breaks | No — browser Access does not affect calls inside AIO on `127.0.0.1` |

---

## Quick checklist

1. Tunnel up + hostnames published ([Tunnel guide](CLOUDFLARE.md)).
2. Enable **One-time PIN** (or an IdP).
3. Create Access application(s) for your public hostnames.
4. Add an **Allow** policy (your emails / family domain).
5. Test in a private window.
6. Protect admin apps before sharing links outside the house.
