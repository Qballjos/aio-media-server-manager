# Cleanuparr integration

Add Cleanuparr as an optional maintenance application using the existing managed-process architecture. User requested full automatic integration after the initial research; a catalog-only installation does not satisfy this scope.

Use upstream self-contained Linux amd64/arm64 releases (current stable v2.11.0), executable `Cleanuparr`, port 11011 and `/health/ready`. Store all persistent data in the app's config directory. Override the child container flag so upstream respects `CLEANUPARR_CONFIG_PATH`; keep its working directory beside `wwwroot`.

Use the upstream HTTP API to create the shared administrator on a fresh installation, complete setup, discover its API key into encrypted SecretStore, and configure installed Sonarr/Radarr/Lidarr and qBittorrent/SABnzbd. NZBGet is unsupported upstream. Existing external connections and cleanup/search rules are preserved. Seed dry-run before adding any connections and never reset the user's later choice. Following the user's request for researched defaults, enable conservative Queue Cleaner and Malware Blocker checks in dry-run, keep completed-download/orphan deletion and proactive searches off, and keep reactive replacements on. Read back writes; failed setup must be reported honestly.

Support Open UI with the shared account, using upstream authentication without disabling auth or bypassing 2FA. Keep keys and passwords server-side. Include catalog/wizard discovery, settings, public hostnames, deployment ports, backups, updates and uninstall through existing facilities.

Approaches: use upstream releases and APIs (chosen: fits existing architecture and avoids schema coupling); modify upstream databases (rejected: bypasses validation and migrations); add another Docker service (rejected by project architecture).

Verification: focused tests first, full Python suite, lint, frontend tests/build and bounded desktop/mobile checks. Real child-app/NAS acceptance is separate and must not be claimed without running it.
