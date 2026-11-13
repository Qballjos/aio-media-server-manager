# Authentication and backup recovery

## Administrator sessions and HTTPS

Manager sessions are recorded locally and survive restarts. Logging out revokes
that session, including copies of its bearer token. Password changes invalidate
all earlier administrator sessions; changing the administrator username also
invalidates earlier tokens. Existing sessions from versions without session
records require a new login after upgrading. TV and Homey credentials keep their
own independent revocation controls. Session records are excluded from backups.

Set `AMM_SECURE_COOKIES=true` in the server environment when serving the manager
through HTTPS, including behind a reverse proxy or Cloudflare Tunnel. Both session
and CSRF cookies then require HTTPS. The default remains `false` for explicit LAN
HTTP installations. Configure `AMM_TRUSTED_PROXIES` with only the actual proxy
addresses and enforce HTTPS at the proxy. Forwarded headers do not automatically
change cookie security. Restart the manager after changing these environment settings.

## VPN profile storage

Uploaded and pasted VPN profiles may only be written inside `AMM_CONFIG_DIR/vpn`.
Absolute paths outside that directory, parent traversal and symlink escapes are
rejected before filesystem changes. Profiles are replaced atomically using private
files with mode `0600`. Existing external profiles can still be selected using
`AMM_VPN_CONFIG` or the Settings path field, but uploads cannot overwrite them.

## Backup recovery before login

Backup endpoints require administrator authentication, including on a new server.
For a fresh server, create the administrator before using the normal backup UI.
An unreadable account file, or a missing account file with an existing session
secret, cannot be replaced through public administrator setup.

For emergency recovery without a working account, the server operator can set
`AMM_BACKUP_RECOVERY_TOKEN` to a random secret of at least 32 characters, restart
the manager, and send it as the `X-AIO-Recovery-Token` HTTP header. This works only
while administrator setup is required and permits backup listing/details, job
status, upload, verification and restore. Creation, deletion and downloading are
not permitted with this token. This is an API recovery path; the normal UI does
not send the recovery header. Use HTTPS or a local connection, remove the
variable after recovery and restart. Once an account is restored the recovery
token no longer grants access. Never place the token in URLs or logs.

Restore validates selected archive paths before deleting SQLite sidecars or
writing files, rejecting traversal, absolute paths and symlink escapes. Failed
updates report binary, configuration and process recovery separately. A retained
`.APP.pre-update` installation must be inspected and resolved by the operator
before another update can replace it; its path and the configuration snapshot
are included in the failed update result. Archive activation failures also keep
`.APP.previous-*` copies when recovery fails.
