# Installation checks, recovery and external backups

## Check connections

Settings → App connections → **Check my installation** reads actual application
configuration. It checks expected library folders, enabled download clients and
their address/port/category, Prowlarr application synchronization and enabled
indexers, and Seerr's default Sonarr/Radarr targets. It does not download media
or change settings. A custom configuration can differ intentionally.

Use **Auto-Wire** to reapply the existing automatic configuration, then check
again after setup completes. Stopped apps and unreadable API keys produce
explicit failures, not a successful check.

Public torrent indexers default to **off** in the wizard and App connections.
Opting in saves permission to add the displayed starter set on Auto-Wire; opting
out never deletes existing indexers. You can always manage your own sources in
Prowlarr. Removed starter indexers are still remembered and not re-added.

## Before installation or updates

Catalog installation and manual updates show prerequisites before proceeding.
The server repeats the checks before changing an app. Configuration, application,
temporary, backup, download and media storage must be writable and have at least
512 MiB available. Set `AMM_PREFLIGHT_MIN_FREE_MB` in the server environment to
change this minimum. It is a minimum, not an estimate of a large app's final size.
GitHub connectivity and API quota are checked with bounded timeouts; unavailable
checks are warnings because cached downloads or other upstreams may still work.
An exhausted quota, conflicting maintenance or a required restart blocks action.

Catalog → **Installation activity** shows stages and timestamps and can be
closed and reopened. **View logs** opens the existing live log viewer. Failed
installs can be retried; an installed app with failed setup retries startup and
connections rather than reinstalling. Failed rollback requires recovery first.
The latest 100 stage changes per app are kept until the manager restarts.

## Hand-edited Recyclarr YAML

Catalog → Recyclarr → Settings has **Manual configuration**. Saving edited YAML
also enables this mode. The YAML is then preserved exactly, including URLs and
API keys, across Auto-Wire, sync and restarts. Profile regeneration and reset
require disabling manual mode explicitly. In manual mode, update endpoints and
keys yourself when they change. Existing saved hand edits migrate to manual mode.

## External HTTPS/WebDAV backups

In Settings → Backups → **Encrypted external backups**:

1. Create a WebDAV folder on an external server, for example Nextcloud or a NAS.
2. Enter its HTTPS folder URL and account credentials. URLs cannot contain login
   details, query strings or fragments. TLS verification is always enabled;
   redirects are rejected. The account needs PUT and GET access to the folder.
3. Choose an encryption password of at least 16 characters. **Keep an offline
   copy outside the appliance.** A replacement server needs this same password.
   Changing it affects new exports; older exports still require the old password.
4. Enable automatic export and save. New manual and scheduled backups are copied
   after creation. Existing local backups can be exported by entering their
   filename and choosing **Export encrypted copy**.

Files are encrypted before transfer with streaming AES-256-GCM and a separate
PBKDF2-HMAC-SHA256 key per archive (600,000 iterations, random salt and nonce).
The encrypted filename ends in `.tar.gz.aioenc`. After PUT the manager downloads
and hashes the ciphertext to check the stored copy. Transfers have bounded
connection/read timeouts and a 20 GiB file limit. WebDAV credentials and the
encryption password are kept in the encrypted secret store and are never returned
by the settings API. No unencrypted configuration is sent to WebDAV.

Local retention remains unchanged. External files are **not automatically
pruned**; configure retention on the WebDAV server. Keep the returned encrypted
filenames in your recovery notes. The manager does not browse remote directories.
A failed transfer leaves the local backup available and reports an error, the
last external result and an incident. It does not report external success merely
because a local backup succeeded.

### Recovery exercise

1. Configure the destination and the original encryption password on the manager
   that will recover the backup. The destination can remain disabled for imports.
2. Enter the exact `.tar.gz.aioenc` filename and select **Import external copy**.
3. The manager downloads, authenticates/decrypts and verifies it, then imports it
   with a new local name. It never overwrites an existing backup.
4. Enter that imported `.tar.gz` name and choose **Test restore safely**. This
   extracts into a disposable directory and checks restored files against their
   manifest. It does not stop apps or replace active settings.
5. For real recovery, refresh the normal backup list and select the imported
   backup there. The existing verified restore workflow remains a separate action.

A successful drill checks archive recovery, not whether every third-party app can
start on a replacement host. Confirm permissions, mounts and app versions there.
No external destination is contacted until you configure it and request export,
import, or enable automated exports.

## Notifications and incident history

Settings → Notifications includes configurable disk warning and recovery
thresholds. Recovery must be below the warning threshold to avoid repeated alerts
around one boundary. Back-up/transfer/restore-test failures and failed updates have
separate event switches for the existing Discord and e-mail channels.

**Recent incidents** keeps the last 100 events across manager restarts, including
when channels are disabled. Delivery switches control outbound notifications;
they do not erase this local history. Refresh the history to see new events.
