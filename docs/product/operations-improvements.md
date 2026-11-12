# Operations capabilities (points 8–14)

Administrators can inspect actual integration configuration, review installation
prerequisites, reopen progress, protect hand-edited profiles, configure incident
alerts and store encrypted configuration backups on HTTPS/WebDAV.

- Existing changes from points 1–7 and Seerr artwork must remain intact.
- Inspection is read-only; repairs use the existing explicit Auto-Wire action.
- Failed prerequisites block install/update before stopping or changing an app.
- WebDAV credentials and encryption passwords are secret-store values, never API output.
- External transfers require HTTPS, verify TLS, forbid redirects and use bounded timeouts.
- Scheduled backups export only when explicitly enabled; failures remain visible.
- Restoring an external copy imports it first; the existing verified restore remains explicit.
- Restore drills use a temporary directory and cannot start or stop managed services.
- Manual Recyclarr mode protects exact file contents, including endpoint edits.
- Public starter indexers default off. Existing indexers are never deleted by opting out.
- Long operations run in background jobs or worker threads with visible failures.
- External acceptance requires an operator-configured WebDAV destination; local tests mock transport.

Implementation surfaces: Settings / App connections (verification and indexers),
Catalog (preflight and progress), Backups (WebDAV and drills), Notifications
(thresholds and history), Recyclarr app settings (manual mode), setup wizard (indexer opt-in).
