# Roadmap and release readiness

Reviewed against **beta commit `542518a`**, pushed on **2 November 2026**. A push
to beta is not proof of a successful image build or a published stable release. This document distinguishes implementation,
repeatable tests and acceptance on a real appliance.

## Implemented on beta

- Protected backup access and explicit operator recovery; safe restore paths.
- Honest rollback results, retained recovery copies, session revocation and
  configurable HTTPS cookies; non-blocking update checks.
- Read-back verification of integration configuration and action prerequisites.
- Reopenable installation activity, live logs and separate setup retries.
- Encrypted HTTPS/WebDAV backup export/import and isolated restore drills.
- Exact preservation of Recyclarr YAML in explicit manual mode.
- Configurable disk thresholds, failed-operation alerts and incident history.
- Explicit opt-in for public starter indexers in the wizard and App connections.
- Settings backup/notification sections and their state are separated; Home
  calendar behavior has a dedicated module. Stylesheets are kept separately.
- The page links stay centered over the full, non-sticky header. All app text
  uses Figtree, including forms and labels; the layout button sits beside the account.
- Browser journeys use the real manager routes, filesystem backups and rollback,
  with synthetic media app/provider boundaries. Desktop and mobile are covered.

See [operations](operations.md) and [security operations](security-operations.md).

## Latest local verification

On macOS arm64, 2 November 2026:

- Python regression suite: **654 passed** (including three portable unsafe-path regressions).
- Frontend behavior tests: **65 passed**.
- Chromium browser journeys: **12 passed**, six each on desktop and mobile,
  including focused header checks covering centering at 320–1440 px,
  scroll behavior and consistent font families.
- Ruff, frontend production build and strict documentation build: **passed**.
- Changed CI workflows parsed successfully. Native Linux amd64/arm64 CI is
  configured. In [beta run 41536074848](https://github.com/Qballjos/aio-media-server-manager/actions/runs/41536074848), both native browser jobs and the frontend build passed. Python 3.11/3.12/3.14 exposed an unsafe-path validation ordering bug on Linux; this checkout validates archive paths before exclusion filters. The corrected Python 3.11/3.12/3.14 jobs passed in [run 41537035155](https://github.com/Qballjos/aio-media-server-manager/actions/runs/41537035155). That run also exposed a mobile setup-test locator whose indices changed while unchecking options; the test now selects a stable list. The complete corrected workflow [41537663957](https://github.com/Qballjos/aio-media-server-manager/actions/runs/41537663957) passed on beta commit `22be3d7`, including both browser architectures, all three Python versions, both Docker builds and nightly publication.

Coverage percentage was not measured. Browser service adapters are synthetic;
real media-app installation and external WebDAV acceptance remain open below.

## Release automation: implemented versus still open

| Capability | Evidence in this checkout | Remaining work |
| --- | --- | --- |
| Versioned release per `main` push | `scripts/release_version.py`, `docker.yml` release job | Verify the actual published release; no release is created by this review |
| Docker `latest`, exact version and SHA tags | `docker.yml` | Pin deployment guidance consistently; major-only tags are not configured |
| SemVer full and minor patterns on tag builds | Docker metadata configuration | Add a major-only pattern if that is the release policy |
| Stable and nightly image channels | `appliance_update.py`, `docker.yml`, `nightly.yml` | Update checks still compare workflow SHAs, not latest release versions |
| Changelog | No maintained root `CHANGELOG.md` in this checkout | Add release notes history; generated GitHub notes are already configured |
| v1.0 readiness | Local reliability features implemented | Real application/platform acceptance, external tester and explicit v1.0 release remain open |

## Supported architecture is not the same as tested installation

Published appliance build targets are **Linux amd64 and arm64**. ARMv7 is
recognized by the installer and declared by some plugins, but there is no ARMv7
appliance image job. Do not present ARMv7 as a supported Docker image.

| Environment | Automated coverage configured | Acceptance status |
| --- | --- | --- |
| Python logic on Linux amd64 | Existing Python CI (3.11, 3.12, 3.14) | Python 3.11/3.12/3.14 passed in run 41537663957 |
| Browser journeys on Linux amd64 | Native amd64 job, desktop and mobile Chromium | Passed in beta run 41537663957 |
| Browser journeys on Linux arm64 | Native `ubuntu-24.04-arm` job, desktop and mobile Chromium | Passed in beta run 41537663957 |
| macOS arm64 | Local Python, Node and Chromium tests | Local evidence only; not a Linux appliance installation |
| Docker amd64 / arm64 real catalog apps | Architecture-specific image builds exist | Full install/start/auto-wire acceptance still needed |
| Native Linux / LXC | Installation scripts and tests exist | Full catalog acceptance still needed |
| Unraid / Synology / TrueNAS | Deployment guides/templates exist | Full catalog acceptance still needed |
| External WebDAV destination | Transport contract tests use a fake server | Real destination acceptance still needed |

Mobile browser emulation verifies layout and interaction in Chromium. It is not
an Android TV, iOS Safari or physical-phone certification.

## Real-app acceptance matrix

`Declared` below means the plugin lists the architecture. Every real-app
installation check remains **unverified** in this review; synthetic browser
fixtures do not make these cells green.

| App | amd64 declared | arm64 declared | ARMv7 declared | Real install/start/auto-wire |
| --- | --- | --- | --- | --- |
| Prowlarr | Yes | Yes | Yes | Unverified |
| Sonarr | Yes | Yes | Yes | Unverified |
| Radarr | Yes | Yes | Yes | Unverified |
| SABnzbd | Yes | Yes | Yes | Unverified |
| NZBGet | Yes | Yes | Yes | Unverified |
| qBittorrent | Yes | Yes | Yes | Unverified |
| Jellyfin | Yes | Yes | No | Unverified |
| Plex | Yes | Yes | No | Unverified |
| Seerr | Yes | Yes | No | Unverified |
| Bazarr | Yes | Yes | No | Unverified |
| Recyclarr | Yes | Yes | No | Unverified |
| NeutArr | Yes | Yes | No | Unverified |
| Lidarr | Yes | Yes | Yes | Unverified |
| Flaresolverr | Yes | No | No | Unverified |
| Grimmory | Yes | Yes | No | Unverified |
| Shelfmark | Yes | Yes | No | Unverified |

Record acceptance per app and environment with image version/SHA, host CPU,
platform/version, install/start/wiring outcomes, backup/rollback outcome and
reproducible logs. Known upstream gaps must stay explicit.

## Next priorities

1. Retain the successful beta workflow [41537663957](https://github.com/Qballjos/aio-media-server-manager/actions/runs/41537663957) as the automated baseline for real-appliance acceptance.
2. Validate every supported catalog app on actual Docker amd64/arm64 appliances,
   then the advertised NAS/native platforms.
3. Test a real WebDAV destination and recovery on a replacement host.
4. Complete version/tag policy, changelog and release-based update comparison.
5. Obtain an external beginner installation test before claiming release readiness.
6. Continue splitting remaining Home search/requests and Settings network/visuals
   responsibilities in small steps, retaining behavior tests.
