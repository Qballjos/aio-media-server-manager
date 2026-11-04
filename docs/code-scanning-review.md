# Code scanning remediation review

Reviewed: 4 November 2026. Repository: `Qballjos/aio-media-server-manager`.

This review covers 30 open CodeQL alerts (20 High, 10 Medium) retrieved from
GitHub and checked against the flagged source on `main`. It is a snapshot, not
a live alert count. Priorities below reflect source review; CodeQL severity
does not by itself establish exploitability. Proposed fixes have not yet been
implemented or validated.

Alert links use the repository's [code scanning dashboard](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning).

## Priority 1: address first

### User-controlled VPN configuration destination — alert #21

- Alert: [#21](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/21).
- Location: `api/routers/settings.py`, with the write in `core/vpn.py`.
- Finding: a user-provided VPN configuration path becomes a write destination.
- Fix: restrict uploaded or pasted configurations to the managed VPN directory;
  resolve paths and enforce containment, including protection against symlink
  escapes. Keep externally mounted configuration paths separate and read-only.
  Preserve the endpoint's authentication requirements.
- Verify: reject absolute destinations outside the managed directory, `../`
  traversal, and symlinks to outside destinations; verify normal VPN uploads work.

### Email validation denial of service — alert #5

- Alert: [#5](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/5).
- Location: `core/auth.py`.
- Finding: the email regex can perform excessive work on malformed input.
- Fix: enforce a maximum input length before validation and use validation with
  predictable runtime instead of the overlapping regex.
- Verify: test valid addresses and long malformed addresses with repeated dots;
  confirm rejection occurs within a bounded execution time.

## Priority 2: fix or harden

### Bazarr configuration regex — alert #6

- Alert: [#6](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/6).
- Location: `core/integrations/credentials.py`.
- Finding: the multiline regex used to extract an API key can backtrack excessively.
- Fix: use safe YAML parsing or a single-pass parser, with a file-size limit.
- Verify: test normal Bazarr configurations and large malformed `auth` sections.

### Credentials in application configuration files — alerts #1–#3

- Alerts: [#1](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/1),
  [#2](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/2),
  [#3](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/3).
- Locations: `core/recyclarr.py`, `core/integrations/sabnzbd.py`.
- Finding: API keys or passwords are written into application configuration files.
- Fix: investigate supported secret references or environment injection for each
  consumer. Where plaintext is required, create files with mode `0600` from the
  outset, restrict directory access, and use protected atomic writes. Directly
  encrypting these files would break consumers that expect plaintext.
- Verify: inspect permissions on initial creation and replacement, exercise each
  integration, and check that logs and temporary files do not expose credentials.
- Disposition: document residual compatibility risk where the consumer requires
  plaintext; permission hardening alone does not eliminate plaintext storage.

### Internal exception messages in API responses — alerts #22–#26

- Alerts: [#22](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/22),
  [#23](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/23),
  [#24](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/24),
  [#25](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/25),
  [#26](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/26).
- Locations: `api/routers/applications.py`, `api/routers/backups.py`,
  `api/routers/cloudflare_hostnames.py`.
- Finding: raw exception text can expose internal details to API clients.
- Fix: return stable error codes and safe messages; retain technical details only
  in protected, redacted logs. Review the underlying exception sources rather
  than only the response lines flagged by CodeQL.
- Verify: simulate failures and assert that responses contain no internal paths,
  credentials, stack traces, or unfiltered upstream response bodies.

### Shared diagnostic reports — alerts #27–#28

- Alerts: [#27](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/27),
  [#28](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/28).
- Location: `api/routers/diagnostics.py`; report generation in `core/diagnostics.py`.
- Finding: debug reports intentionally share diagnostic information behind an
  expiring bearer token, including exception details.
- Fix: define a sanitized shared-report format; keep full traces behind
  authenticated administrator access. Review HTML and JSON output together.
- Verify: exercise redaction, token expiry and revocation, unauthenticated access,
  and both output formats. HTML escaping alone does not prevent disclosure.

### Jellyfin redirect and reported XSS — alerts #29–#30

- Alerts: [#29](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/29),
  [#30](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/30).
- Location: `applications/jellyfin/aio-login.js`.
- Assessment: the current code already restricts `next` to `/web/…`; exploitability
  is unconfirmed. Both alerts point to the same redirect sink.
- Fix: prefer fixed allowed destinations. If dynamic destinations are required,
  parse and normalize the URL, then require the current origin, HTTP(S), and an
  allowed pathname before redirecting.
- Verify: test script URLs, external URLs, protocol-relative URLs, backslashes,
  control characters, and traversal, alongside successful Jellyfin sign-in.

## Priority 3: compatibility and deployment review

### Bazarr MD5 password compatibility — alert #8

- Alert: [#8](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/8).
- Location: `core/integrations/local_auth.py`.
- Finding: the integration hashes passwords with MD5; its comment states that
  Bazarr expects this format.
- Fix: verify the requirement against the supported Bazarr version. Do not
  substitute bcrypt locally without consumer support. If MD5 remains required,
  document the upstream limitation and avoid reusing the manager password for
  the weaker credential; assess how this affects shared-login behavior.
- Verify: test Bazarr authentication end to end and confirm the manager's own
  password storage remains independent of this compatibility helper.

### SHA-256 helper used by tests — alert #7

- Alert: [#7](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/7).
- Location: `core/integrations/local_auth.py`.
- Assessment: the checked source uses this helper only in negative test assertions.
- Fix: remove the helper from production code and rewrite tests around required
  behavior; do not add a production password migration without evidence it is needed.
- Verify: search all callers and run the shared-auth and integration tests.

### VPN proxy network binding — alert #20

- Alert: [#20](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/20).
- Location: `core/vpn_proxy.py`.
- Assessment: listening on `0.0.0.0` appears intentional for Docker port forwarding.
- Fix: make the bind address configurable and review published host ports and
  downstream authentication. Do not blindly replace it with localhost, which can
  break published-port access.
- Verify: test Docker port forwarding, VPN isolation, intended LAN access, and
  denial of unintended external access. Document an exception if all-interface
  binding is required for the supported deployment.

## Priority 4: test cleanup and likely false positives

### Test socket network binding — alert #19

- Alert: [#19](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/19).
- Location: `tests/test_phase5.py`.
- Fix: use loopback for the port probe and configure the proxy under test to use
  loopback where possible.
- Verify: run the socket forwarding test and confirm it still tests the intended
  proxy behavior without unnecessary interface exposure.

### Hostname assertions in tests — alerts #9–#18

- Alerts: [#9](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/9),
  [#10](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/10),
  [#11](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/11),
  [#12](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/12),
  [#13](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/13),
  [#14](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/14),
  [#15](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/15),
  [#16](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/16),
  [#17](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/17),
  [#18](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/18).
- Locations: `tests/test_homepage.py`, `tests/test_jellyfin.py`,
  `tests/test_integrations.py`, `tests/test_public_hostnames.py`.
- Assessment: these findings flag assertions rather than production URL sanitizers.
  Several membership checks operate on hostname collections, not URL substrings.
- Fix: use exact parsed-hostname or structured-configuration assertions where
  appropriate. Keep meaningful collection-membership assertions; document false
  positives where a rewrite would not improve the test.
- Verify: run affected tests and confirm they reject incorrect hostnames where
  hostname validation is the behavior under test.

### Secret-name debug logging — alert #4

- Alert: [#4](https://github.com/Qballjos/aio-media-server-manager/security/code-scanning/4).
- Location: `core/crypto.py`.
- Assessment: the flagged statement logs the secret's name, not its value.
- Fix: verify that all callers supply non-sensitive identifiers; remove the
  unnecessary log or dismiss the alert with evidence after caller review.
- Verify: capture logs while saving representative secrets and assert that no
  secret values are emitted.

## Completion criteria

1. Address priority 1 findings, then priority 2 fixes and reviews.
2. Run focused regression tests for each change and the required repository checks.
3. Rerun CodeQL on the final commit and compare alerts against this snapshot.
4. Close or dismiss findings only with evidence. For accepted compatibility risks,
   record the rationale, remaining exposure, and conditions for revisiting it.

No alert statuses were changed as part of this review.

## References

- [CodeQL: path injection](https://codeql.github.com/codeql-query-help/python/py-path-injection/)
- [CodeQL: clear-text credential storage](https://codeql.github.com/codeql-query-help/python/py-clear-text-storage-sensitive-data/)
- [CodeQL: exception information exposure](https://codeql.github.com/codeql-query-help/python/py-stack-trace-exposure/)
- [CodeQL: client-side URL redirects](https://codeql.github.com/codeql-query-help/javascript/js-client-side-unvalidated-url-redirection/)
- [CodeQL: weak sensitive-data hashing](https://codeql.github.com/codeql-query-help/python/py-weak-sensitive-data-hashing/)
