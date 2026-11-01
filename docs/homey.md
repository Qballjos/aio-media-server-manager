# Homey dashboard integration

## Setup

This feature requires the companion AIO Homey app. While signed in as AIO administrator, open Settings → Homey connections and create a code. Enter the AIO origin and code when adding AIO Media Server Manager in Homey. Codes expire after five minutes and are one-use; making a new code invalidates the previous invitation. Add the desired dashboard widgets in Homey. Use Homey's Repair with a fresh code after revocation or address changes. Revoke old connections in AIO, including after removing an app/device from Homey.

Use HTTPS with a valid certificate. Private LAN HTTP is supported by the companion app but does not encrypt codes or credentials. This feature does not configure HTTPS, expose AIO to the internet, install a Homey app or change any playback settings.

## Protocol and permissions

Administrator-only POST `/api/homey/pairings`, GET `/api/homey/devices` and DELETE `/api/homey/devices/{id}` create invitations and manage connections. POST `/api/homey/pairings/claim` takes `{code,deviceName}` and exchanges a one-use invitation for `{version:1,accessToken,deviceId,deviceName}`. Claims are rate-limited and unavailable before admin setup.

A dedicated `homey_` bearer is accepted only for GET `/api/homey/dashboard` and POST `/api/homey/disconnect` (self-revocation). It cannot use TV, settings, playback or general homepage endpoints. Tokens/invitations are stored as SHA-256 hashes in `.homey-connections.json` (0600, atomic replacement). Management lists contain no secrets. Revocation is checked before serving cached data. No-store headers protect invitation, claim and dashboard responses.

Dashboard schema 1: `{schemaVersion:1,version,updatedAt,playing:{state,items},recent:{state,items}}`. Playing items contain only title/detail/source/progress/paused. Recent items contain title/detail/source/addedAt; additions are combined from Jellyfin/Plex and sorted by library addition time descending, maximum 12. No user/device names, artwork URLs, service URLs, API keys, server metrics or controls are included. Failed providers are reported as unavailable, not empty. One locked 30-second cache serves concurrent Homey widgets/connections. Upstream service reads may time out; Homey retries with bounded backoff.

## Release information

Added mandatory authenticated Homey pairing, credential management UI, a dedicated read-only dashboard API and private metadata projection. Existing TV credentials/scopes and public health checks remain separate. Automated security/lifecycle/projection tests are included. Real Homey Pro mini acceptance testing is still required before distribution.
