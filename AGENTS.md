# Project agent defaults

These defaults apply to aio-media-server-manager. Explicit user instructions override them.
Use Caveman Lite for communication, Ponytail Full for development, and Impeccable for frontend/UI work in every session for this project, unless the user changes or disables them. Apply the technical skills below when their scope matches the task.
These are project instructions; they do not require a gateway or change global plugin settings.
Caveman Lite and Ponytail Full are defined in this file and apply directly; they do not depend on separately installed skills. Read this file at the start of every chat working in this project and follow the applicable skill instructions before doing the work.

## Project context

AIO Media Server Manager is a self-hosted media appliance: one Docker container or native Linux service installs, supervises and connects selected media applications, download clients and library folders through a single dashboard. Target deployments include Linux amd64/arm64 and NAS platforms such as Unraid. macOS and Windows are development/Docker hosts, not native appliance targets.

- Read `CONTRIBUTING.md` before implementation; it owns architecture rules, runtime pins, deployment compatibility and release policy. Read `docs/testing.md` when choosing verification, and `docs/release-readiness.md` when assessing platform readiness. Read only the additional documentation relevant to the task.
- Backend: Python/FastAPI, routes in `api/routers/`, shared lifecycle/install/storage logic in `core/`, application-specific adapters in `applications/`. Keep app-specific behavior in its adapter.
- Frontend: Vue 3, Vite, Vue Router and vue-i18n in `frontend/`. Read `DESIGN.md` before UI work. Reuse shared controls in `frontend/src/style.css`; preserve existing themes, responsive behavior and translation conventions.
- Preserve the single-appliance architecture: managed applications are processes, not per-app Docker containers. No Debrid functionality or cloud remotes.
- Never remove media libraries during uninstall, backup or restore. Never expose credentials through logs, API responses, screenshots or documentation examples.
- For environment variables, ports or Settings changes, check `.env.example`, Compose files, NAS templates and relevant documentation together, following `CONTRIBUTING.md`.
- Do not upgrade intentional runtime pins just because newer majors exist. Consult the current pins and their reasons in `CONTRIBUTING.md` and the actual manifests.
- A push to `main` triggers a stable release, including documentation-only pushes. Use `beta` for requested nightly work; promote to `main` only when the user explicitly requests a stable release. Do not infer publication authorization from a local edit request.

## Verification commands

Run checks relevant to the change; these commands assume dependencies are installed:

- Backend: `poetry run pytest -q` (target the affected tests first).
- Python lint: `poetry run ruff check core api applications tests scripts/e2e_server.py`.
- Frontend unit tests: `npm --prefix frontend test`.
- Frontend build: `npm --prefix frontend run build`.
- Browser journeys: run locally before pushing beta with `npm --prefix frontend run test:e2e`; see `docs/testing.md` for browser installation and Python environment setup. GitHub Actions does not run them.
- Real appliance testing: `./scripts/test-env.sh up`, with logs/down subcommands; see `CONTRIBUTING.md`. Do not run native catalog installs on macOS/Windows.
- Report what actually ran and distinguish synthetic browser adapters from real child-app/NAS acceptance. Never present an unexecuted CI job or an emulated device as verified hardware.

## Durable project knowledge

- Keep stable project facts and workflow defaults here; keep detailed architecture, runtime pins and test procedures in their existing authoritative documents instead of duplicating them.
- Check current code/manifests before trusting old chat context. Record lasting decisions with their reason in the relevant project document when the task changes them.
- Do not store credentials, personal information, transient debugging output or claims of passing tests as permanent project memory.

## MCP tools

- Use the connected Context7 plugin for library/framework API syntax, configuration, upgrades and dependency-specific debugging. Resolve the library ID first, then query the relevant documentation; match installed versions where supported and state version gaps.
- Keep documentation queries focused and exclude secrets, personal data and proprietary source code. If Context7 is unavailable or lacks the needed documentation, use official sources and state the limitation.
- Reuse the connected GitHub and Chrome DevTools tools for repository and browser work. Do not add duplicate MCP servers for capabilities already provided by these connections.

## Skill installation and planning

- Use the installed `skill-installer` skill when the user requests listing or installing skills. Load its instructions first; do not install unrelated skills automatically.
- For implementation plans, use `create-plan` if installed; otherwise use the available `writing-plans` skill or provide a concise plan directly, stating the fallback. Never claim an unavailable skill ran.
- Skills and Codex Plan Mode are separate. Follow the active host mode; do not claim that a planning request switches modes or automatically writes `PLAN.md`.
- Keep planning proportional to the task. Routine edits do not need a separate plan. A request for a plan alone does not authorize implementing it.

## Caveman Lite

- Keep complete sentences and natural grammar. Be professional, brief and direct.
- Remove filler, repetitive explanations and unnecessary hedging; preserve technical accuracy and meaningful uncertainty.
- Keep code, commands, error messages, commits and pull requests in their normal form.
- Give enough detail for clear instructions, security concerns and irreversible actions.
- Respond in the user's language.

## Impeccable

- Load the installed Impeccable skill before designing, implementing, reviewing or refining frontend interfaces, and follow its relevant workflow and references. Resolve its location from the current skill catalog; do not assume a version-specific path.
- Preserve the existing product identity, design conventions and behavior for refinements. Use the Operate mode for the manager's application UI.
- Cover accessibility, responsive layouts, clear UX copy, and loading, empty and error states as relevant to the requested change.
- Keep work within the requested scope alongside Ponytail Full. Verify UI changes in bounded desktop and mobile passes as directed by Impeccable.
- Backend-only tasks do not require Impeccable. If the skill is unavailable, report that limitation instead of claiming it ran.

## Technical skills

- Resolve installed skills from the current catalog or installed skill directories and read their instructions before use. Report unavailable skills rather than claiming they ran.
- Use `vue-patterns` when building or reviewing Vue components, composables, reactivity or routing. Follow the existing Vue 3/Vite architecture; do not introduce Pinia, Nuxt or other dependencies solely because a skill mentions them.
- Use `security-review` for changes involving authentication, authorization, secrets, untrusted input, API endpoints, file access or process execution. Focus the review on the changed behavior and its trust boundaries.
- Use `docker-patterns` when changing Dockerfiles, Compose services, container networking, volumes or installation behavior. Preserve existing deployment and Unraid compatibility.
- Use `python-testing` when adding or updating meaningful backend tests, especially for changed non-trivial logic and regressions. Reuse the existing pytest and pytest-asyncio setup.
- Use `e2e-testing` when adding or updating Playwright coverage for important user flows or investigating browser regressions. Reuse the existing setup; keep checks proportional to the change.
- Do not load every skill for every task or add tests for trivial documentation/configuration edits solely to satisfy a skill checklist.

## Unslop compatibility

Unslop is not an active project default: the installed version requires React + Tailwind, while this frontend uses Vue. Use Impeccable for UI work. Reassess Unslop only if a compatible version becomes available or the user explicitly requests it; verify prerequisites before running it.

## Ponytail Full

- Solve the whole task with the smallest clear change. Read affected callers, tests and configuration before editing; fix shared root causes once.
- Reuse project patterns, then platform/standard-library features, then installed dependencies. Do not add speculative options, abstractions or dependencies.
- Preserve validation, error handling, security, accessibility and deployment compatibility. Complete affected callers, fixtures and documentation.
- Verify non-trivial behavior with focused tests; trivial edits need no new tests. Mark intentional shortcuts with their limit and when to revisit them.
- Keep verification proportional. Do not add tests for every edit, mirror the implementation with assertions, or add tests merely to satisfy a workflow. For reversible wording, styling and simple layout changes, use a focused inspection or existing checks when sufficient. Add a targeted regression when it meaningfully protects a bug fix or non-trivial behavior.
- Once relevant checks pass, stop expanding or repeating them unless a new change, failure or unresolved concern justifies it. Distinguish a passing automated check from confirmation that the reported problem is resolved on the user's actual device.
- End with the outcome, checks actually performed and material limitations. Keep communication concise, in complete sentences (Caveman Lite).
