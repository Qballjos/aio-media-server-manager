# Verification and browser journeys

## Local checks

From the repository root:

```sh
poetry run pytest -q
poetry run ruff check core api applications tests scripts/e2e_server.py
npm --prefix frontend test
npm --prefix frontend run build
```

The Node tests include direct calendar behavior tests: responsive view selection,
manual view preservation, grouped episode availability, year boundaries and
calendar link targets. Existing Home loading and failed-job tests exercise the
same extracted calendar module used by the actual page.

## Seerr native dependency validation

`tests/test_seerr_install_progress.py` covers both supported Next.js configuration
filenames and Seerr's SQLite runtime check. The installer executes an in-memory
SQLite query after dependency installation. If a downloaded native binary cannot
load (for example, because its glibc requirement exceeds the appliance runtime),
it rebuilds only SQLite from source and repeats the query. A failed rebuild or
query aborts installation before the runner is published; the updater retains
its snapshot, rollback and post-start health checks.

When accepting a new native dependency version, verify the actual query on the
Linux appliance as well as the mocked installer tests. A successful package
installation alone does not establish native binary compatibility.

## Home poster loading in WebKit

After `npm ci` in `frontend`, install WebKit with `npx --no-install playwright install webkit`,
then run `npm run test:posters`. This builds the production frontend and tests a
350-request rail on mobile and desktop WebKit with synthetic API responses and
local images. It covers cold loading, reload, scrolling to the final poster and
unloading offscreen image sources, without requiring the Python fixture. Requests
are rendered in pages of 20 so a large history cannot create an unbounded mobile
scrolling surface; the test visits the final page and bounds the rail width.
WebKit device emulation does not reproduce physical iPhone memory limits.

`npm run test:webkit` also checks Home's title/filter layout and phone Day default,
Catalog's collapsible category filters, and the Settings section picker at mobile,
small-mobile and desktop sizes. These UI checks use Dutch labels and synthetic
API responses; they do not exercise real media services.

## Repeatable desktop and mobile journeys

Install Python dependencies as documented in Contributing, then:

```sh
cd frontend
npm ci
npm run build
npx --no-install playwright install chromium
npm run test:e2e
```

Run these browser journeys locally before pushing to beta. GitHub Actions runs
the Python tests and frontend unit/build checks, but does not run Playwright.

The default Python executable is the repository's `.venv/bin/python`. If Poetry
uses a different environment, set `E2E_PYTHON` to the absolute path returned by
`poetry env info --executable`. `AIO_E2E_PORT` can select a free port (default
8765). Playwright starts and stops the fixture automatically and refuses to reuse
an existing server. The fixture binds only to 127.0.0.1.

`PLAYWRIGHT_BROWSERS_PATH` optionally selects a browser cache directory. On Linux,
install browser system libraries with `npx --no-install playwright install
--with-deps chromium` before running the local journeys.

### What is real, what is simulated

The tests run the **built Vue application in Chromium** against actual manager
routers, authentication/session storage, wizard persistence, catalog job state,
preflight, read-back verification, file backups, selective restore and updater
rollback. Browser requests are not replaced with canned API routes.

Media applications and their upstream/provider boundaries are synthetic adapters:
no real app binary runs, no indexer is contacted and no actual media is downloaded.
The download/import step moves a synthetic text file inside a disposable folder.
The fake provider supplies configuration for the real read-back verifier. The
settings overview substitutes host/service telemetry so tests cannot accidentally
control a host network or external account.

The fixture is `scripts/e2e_server.py`. It creates its own `TemporaryDirectory`,
never reads a production config, disables external provider requests and is not
imported by the production entry point. Its `/_test/*` routes exist only in that
fixture. Do not deploy it as the manager.

### Covered journeys

Each runs once in desktop Chromium and once with the Pixel 7 mobile viewport:

1. Create administrator → finish setup wizard → install synthetic apps → verify
   real configuration read-back → request a title → show queue → import a synthetic
   file → display it under Recently added.
2. Create a real filesystem backup → change an app preference → selectively
   restore that app through the UI → verify original settings are back.
3. Start an update through Catalog and its prerequisite dialog → inject an install
   failure → verify binary/config/process recovery → show the rollback job and an
   error toast, without a success toast.
4. Edit notification thresholds → save → navigate away and back → confirm the
   extracted notification form reloads persisted values.
5. Choose the calendar month view → change the viewport → confirm the manual
   view and event rendering remain intact.

Pages are checked for horizontal overflow. Playwright retains failure screenshots
and traces under `frontend/test-results` and an HTML report under
`frontend/playwright-report`. These folders are ignored by Git. After a failure,
use `npx --no-install playwright show-report` or `playwright show-trace` to inspect
artifacts. Avoid storing real credentials in these test fixtures or reports.

### Header and typography checks

A separate desktop/mobile scenario checks Home, Catalog and Settings at widths
1440, 1100, 960, 768, 390 and 320 px. It compares the page-link center with the
entire header center, checks that the header scrolls out of view, and compares
visible control/code font families with the body font. The layout button is
absent before login and setup. These are computed-style and geometry checks;
they do not verify delivery of the Google-hosted Figtree font.

## Architecture and target acceptance

Playwright browser journeys are no longer configured in CI. Previous native Linux
amd64 and arm64 runs are historical evidence only. A local macOS arm64 run proves
the browser journeys and manager logic there, not real Linux catalog installs or
NAS compatibility.

Continue real-app acceptance using the matrix in
[release readiness](release-readiness.md). Desktop/mobile emulation does not
certify a physical phone, Safari, Android TV or a real WebDAV destination.
