# Cloudflare Access (Anmeldetor)

Nutzen Sie beide Türen. Cloudflare Access ist die zusätzliche Anmeldung vor den *Arr-Apps, den Download-Clients und Seerr. Das AIO-Dashboard, Jellyfin und Plex behalten die Anmeldung, die sie schon haben.

Access ersetzt das Passwort von Sonarr oder das Konto von Seerr nicht. Es fragt nur, wer Sie sind, **bevor** diese Seite lädt. Adressen im Heimnetz (`http://nas-ip:8989`) überspringen Access. Aufrufe innerhalb von AIO auf `127.0.0.1` ebenfalls.

Veröffentlichen Sie zuerst die Hostnamen: [Cloudflare Tunnel](CLOUDFLARE.md).

Offizielle Cloudflare-Docs: [Self-hosted apps](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/) · [Policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/) · [Identity providers](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/).

---

## Welcher Hostname welche Anmeldung bekommt

| Hostname (Beispiel) | Anmeldung | Warum |
|--------------------|-------|-----|
| `media.example.com` (AIO) | Das eigene Konto von AIO | Dieselbe Idee wie Jellyfin und Plex: eine Anmeldung, die Sie schon angelegt haben |
| `jellyfin` / `plex` | Das eigene Konto dieser App | Telefon- und TV-Apps können eine Access-Seite nicht abschließen |
| `sonarr` / `radarr` / `lidarr` / `prowlarr` / `bazarr` | Cloudflare Access, danach das App-Passwort | Verwaltungsoberflächen. Browser schaffen die Access-Seite |
| `qbittorrent` / `sabnzbd` / `nzbget` | Cloudflare Access, danach das App-Passwort | Download-Clients, wie *Arr |
| `seerr` | Cloudflare Access, danach das eigene Konto von Seerr | Anfrageoberfläche im Browser |

Shelfmark, Grimmory und NeutArr bleiben bei ihrer eigenen Anmeldung, außer Sie fügen selbst eine Access-Anwendung dafür hinzu.

Setzen Sie den AIO-Hostnamen, Jellyfin oder Plex nicht auf eine Access-Anwendung. Ein Wildcard `*.example.com` erfasst die ebenfalls. AIO legt eine Anwendung je geschütztem Hostnamen an.

---

## 1. Zero Trust öffnen

1. Melden Sie sich unter [dash.cloudflare.com](https://dash.cloudflare.com/) an.
2. Öffnen Sie **Zero Trust**. Hat dieses Konto noch keine Zero-Trust-Organisation, legen Sie eine an und wählen Sie einen Teamnamen. Der kostenlose Plan reicht für einen Haushalt. Siehe [Create a Zero Trust organization](https://developers.cloudflare.com/cloudflare-one/setup/).

Der Teamname ist der `<your-team-name>` in der Google-Redirect-URL unten. Sie finden ihn unter **Settings → Team name and domain**.

---

## 2. Die Anmeldemethode selbst hinzufügen

Wählen Sie eine. Eine weitere können Sie später ergänzen. AIO legt das nicht für Sie an.

### Cloudflare-Konto (nutzt die MFA dieses Kontos)

Neue Zero-Trust-Organisationen haben den [Cloudflare identity provider](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/cloudflare/) bereits. Menschen melden sich mit ihrem Cloudflare-Konto an. Mehrfaktor-Authentifizierung ist die 2FA, die schon auf diesem Cloudflare-Benutzer liegt, kein eigener Schalter in Access.

1. **Zero Trust → Integrations → Identity providers**.
2. Fehlt **Cloudflare**: **Add new identity provider → Cloudflare**.
3. Schalten Sie **Restrict to account members** ein und wählen Sie **Save**.

Mit diesem Schalter kann sich ein Fremder, der nur irgendein Cloudflare-Konto besitzt, nicht anmelden. Fügen Sie die Personen, die Sonarr öffnen dürfen, als Mitglieder dieses Cloudflare-Kontos hinzu, und lassen Sie sie 2FA auf ihrem Cloudflare-Benutzer einschalten.

### Google

Folgen Sie [Google](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google/). Kurz:

1. Legen Sie in Google Cloud einen OAuth-Client vom Typ **Web application** an.
2. Authorized JavaScript origin:

   ```text
   https://<your-team-name>.cloudflareaccess.com
   ```

3. Authorized redirect URI:

   ```text
   https://<your-team-name>.cloudflareaccess.com/cdn-cgi/access/callback
   ```

4. Kopieren Sie die Client-ID und das Client secret.
5. **Zero Trust → Integrations → Identity providers → Add new identity provider → Google**. Fügen Sie beide Werte ein und wählen Sie **Save**.
6. Wählen Sie **Test** neben Google.

Eine Google-Anmeldung allein lässt jedes Google-Konto durch. Die Allow-Richtlinie im nächsten Abschnitt muss die Adressen nennen, die eintreten dürfen.

Google Workspace (Gruppen einer Organisation) ist ein anderer Anbieter: [Google Workspace](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google-workspace/).

### One-time PIN

Nutzen Sie dies, wenn Menschen einen Code per E-Mail bekommen sollen und Sie kein Google- oder Cloudflare-Konto wollen. Siehe [One-time PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/).

1. **Zero Trust → Integrations → Identity providers → Add new identity provider → One-time PIN**.
2. Die Allow-Richtlinie muss diese E-Mail-Adressen nennen. Eine Richtlinie, die nur „One-time PIN“ sagt, lässt jeden einen Code anfordern, der ein Postfach lesen kann.

---

## 3. Wer hinein darf

Access lehnt alle ab, bis eine Allow-Richtlinie passt.

| Feld | Wert |
|-------|--------|
| Policy name | `Admins` |
| Action | **Allow** |
| Include | **Emails** → die Adressen, die Sonarr und die Download-Clients öffnen dürfen |

Wenn Sie den Cloudflare identity provider mit **Restrict to account members** nutzen, können Sie stattdessen **Login methods → Cloudflare** aufnehmen.

Eine eigene Block-Regel brauchen Sie nicht. Kein Treffer bedeutet Ablehnen.

---

## 4. Access aus AIO hinzufügen

Sobald die Anmeldemethode existiert, legt AIO die Access-Anwendungen an. Die Anmeldemethode selbst legt AIO nicht an.

1. **Einstellungen → Netzwerk → Öffentliche Subdomains**.
2. Schalten Sie **Freigeben** für die *Arr-Apps, Download-Clients und Seerr ein, die ins Internet sollen. Lassen Sie Jellyfin, Plex und AIO ohne Access (sie sind mit **Eigene Anmeldung** markiert).
3. Zuerst **Bei Cloudflare veröffentlichen**, damit die Hostnamen existieren.
4. Unter **E-Mail-Adressen für Cloudflare Access** die Adressen, die eintreten dürfen. Lassen Sie die Liste leer, nur wenn die einzige Anmeldemethode Cloudflare mit **Restrict to account members** ist.
5. **Cloudflare Access hinzufügen**.

Das API-Token braucht zwei weitere Rechte, zusätzlich zu Zone DNS Edit und Cloudflare Tunnel Edit:

- **Access: Apps and Policies → Write**
- **Access: Organizations, Identity Providers, and Groups → Read**

AIO schreibt eine Allow-Richtlinie namens `AIO Access` und eine Self-hosted-Anwendung je freigegebenem geschütztem Hostnamen. Die Sitzung dauert 8 Stunden für *Arr und Download-Clients und 24 Stunden für Seerr. Die Schaltfläche erneut ausführen aktualisiert diese Anwendungen. **Freigeben** aus und erneut ausführen löscht nur die Access-Anwendungen, die AIO angelegt hat.

Von Hand: **Access controls → Applications → Create → Self-hosted**, ein Hostname nach dem anderen, die Allow-Richtlinie anhängen, und `media`, `jellyfin` und `plex` überspringen.

---

## 5. Testen

1. Öffnen Sie ein privates Fenster.
2. Besuchen Sie `https://sonarr.example.com`. Sie sollten zuerst **Cloudflare Access** sehen, danach die eigene Anmeldung von Sonarr.
3. Besuchen Sie `https://seerr.example.com`. Sie sollten zuerst **Cloudflare Access** sehen, danach Seerr.
4. Besuchen Sie `https://jellyfin.example.com` und `https://media.example.com`. Sie sollten die Anmeldung von Jellyfin und die von AIO sehen, ohne Access-Seite davor.
5. Im Heim-WLAN öffnet `http://nas-ip:8989` Sonarr weiter ohne Access. Nutzen Sie das nur zu Hause.

---

## Fehlersuche

| Symptom | Prüfen |
|---------|--------|
| Keine Access-Anmeldung bei Sonarr | Dieser Hostname fehlt in Access, oder ein Tippfehler |
| Access-Anmeldung bei Jellyfin, Plex oder AIO | Entfernen Sie diesen Hostnamen aus der Access-Anwendung. Ein Wildcard `*` verursacht das |
| Anmeldeschleife | Überlappende Access-Apps, oder Google Workspace schützt eine Google-Seite. Eine App versuchen |
| 403 nach der Anmeldung | Die Allow-Richtlinie passt nicht zu dieser E-Mail oder diesem Cloudflare-Konto |
| Jedes Google-Konto kann eintreten | Die Richtlinie nimmt die Google-Anmeldemethode auf und nennt keine E-Mail-Adressen |
| *Arr innerhalb von AIO spricht nicht mehr miteinander | Das sollte nicht passieren. Browser-Access betrifft Aufrufe auf `127.0.0.1` nicht |

---

## Kurze Checkliste

1. Tunnel an und Hostnamen veröffentlicht ([Tunnel-Anleitung](CLOUDFLARE.md)).
2. Eine Anmeldemethode hinzufügen: Cloudflare-Konto, Google oder One-time PIN.
3. Allow-Richtlinie begrenzt auf Ihre Admin-Adressen oder auf Mitglieder dieses Cloudflare-Kontos.
4. **Cloudflare Access hinzufügen** in AIO für jede freigegebene *Arr-App, jeden Download-Client und Seerr.
5. AIO, Jellyfin und Plex bei ihrer eigenen Anmeldung lassen.
6. Sonarr und Seerr in einem privaten Fenster testen, danach Jellyfin und das AIO-Dashboard.
