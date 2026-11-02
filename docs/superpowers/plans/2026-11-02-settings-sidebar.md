# Settings Sidebar Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Apply approved sidebar settings design and reorganize existing options.
**Architecture:** A pure settingsNavigation.js module owns grouped navigation, search and legacy resolution. SettingsPanel retains existing forms and actions while using a responsive SettingsSidebar component.
**Tech Stack:** Vue 3, Vue Router, vue-i18n, Node test runner, Vite.
**Spec:** docs/superpowers/specs/2026-11-02-settings-sidebar-design.md

## Global Constraints
Preserve existing features and stored values. Reuse current checkout and leave unrelated changes intact. Support four languages, both color modes and mobile. Preserve independent form saving.

## Review Focus
Legacy links resolve correctly; translated search finds relevant pages; empty search results are explained; moved forms still load their data; mobile navigation stays reachable.

### Task 1: Navigation model
Files: frontend/src/settingsNavigation.js, frontend/src/router.js, frontend/tests/settings-navigation.test.mjs.
- [x] Test canonical and legacy sections plus translated and keyword search, whitespace and empty matches; run and observe failure.
- [x] Implement SETTINGS_GROUPS, SETTINGS_NAV, resolveSettingsSection and filterSettingsGroups; connect router and preserve old aliases.
- [x] Run navigation tests.

### Task 2: Sidebar and content
Files: frontend/src/SettingsSidebar.vue, frontend/src/SettingsPanel.vue, frontend/src/i18n/locales/table.js.
- [x] Build accessible sidebar with search, active page and collapsible mobile navigation.
- [x] Split network into VPN and external access, move API keys and TV connections to integrations, move install/donation to about.
- [x] Add page titles/descriptions, translated copy and calmer theme-aware styles; update section loading.
- [x] Verify complete form/action preservation and translations.

### Task 3: Verification
- [x] Run npm test and npm run build in frontend.
- [x] Inspect desktop/mobile rendering where available; review full task diff and correct regressions.

## Execution decisions
User approved design and requested application; proceed inline without another approval. No commits or branch changes in this mixed working checkout. Test new routing/search behavior; visual changes verified through build and UI inspection.

## Verification results
48 frontend tests passed. Production build passed (bundle-size advisory). All 13 pages inspected in browser using mocked API responses; no console errors. Desktop dark and mobile light/dark checked. Mobile selection restores focus to the navigation toggle, with no horizontal overflow at 390px. Independent review found no remaining important issues after this focus fix. Actual backend writes were not exercised; existing handlers are preserved.
