# Cleanuparr Implementation Plan

**Goal:** Fully integrate Cleanuparr as an optional managed application.
**Architecture:** Reuse SimpleApplication and transactional installer. Keep Cleanuparr API behavior in its dedicated integration adapter; connect it through the existing engine and verifier.
**Tech Stack:** Python, requests, Vue 3; no new dependencies.
**Spec:** ../specs/2026-11-09-cleanuparr-design.md

## Constraints and review focus

Preserve config/media during updates and uninstall. Never return keys/passwords in status/settings. Preserve custom connections and cleanup rules. No auth bypass, 2FA bypass, app containers or runtime upgrades. Check config-path isolation, partially completed bootstrap, repeated wiring, rotated endpoints/credentials, masked read-back values, HTTP failures and VPN reachability.

## Tasks

- [x] Write failing tests for catalog discovery, native launch/config isolation and Cleanuparr API bootstrap/safe/idempotent wiring.
- [x] Implement the app adapter, API client, shared login, engine registration and configuration verification. Run focused tests.
- [x] Connect existing settings/Open UI, icon/localization, deployment ports and docs. Verify backups/update/uninstall use the existing paths.
- [x] Run full backend tests/lint, frontend tests/build and bounded desktop/mobile checks. Obtain a fresh code review and address material findings.

Execution uses the existing checkout; no publication or stable release is requested. Docker became available during execution. Native Linux arm64 installation/API behavior was checked in a disposable container. Linux amd64, real downstream authentication/cleanup and NAS hardware remain separate acceptance work.

## Decisions

Use upstream's browser session tokens only for the authenticated same-host Open UI handoff; API keys/passwords remain server-side. Preserve 2FA and public-subdomain sign-in. No LAN authentication bypass.

Configuration read-back checks saved endpoints/enabled state. It does not claim a live downstream authentication or cleanup test. The independent review found no confirmed material issue and explicitly retained this acceptance boundary.
