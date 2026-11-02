# Documentation showcase and beginner guides

Requested direction: TV Thuis-inspired homepage and cohesive guide styling, with a framed AIO preview, light/dark views, and a visual demonstration of Home widget editing. Retain MkDocs, search, four languages, and GitHub Pages.

- Build a responsive landing page with gradient headings, glass navigation, a populated sample-data dashboard, real Catalog/Settings screenshots, and clear platform entry points.
- Make widget editing demonstrable: editing toggle, add/remove, drag/reorder with keyboard/button alternatives, and size changes. Explicitly distinguish the simplified website demo from the real app; never connect to the live server.
- Explain the real layout icon and editing actions with visible controls and concise numbered guidance, reflecting frontend/src/HomeGrid.vue, HomeEditBar.vue, HomeGridSheet.vue, and homeLayout.js.
- Rewrite beginner onboarding around platform choice, prerequisite checks, first login, expected outcomes, and troubleshooting. Preserve technical reference tables and guides.
- Localize homepage and onboarding explanations in English, Dutch, German, and French. Update storage advice for SSD staging.
- Validate build, JavaScript, links, desktop/mobile behavior, preview tabs, theme changes, widget actions, and reduced-motion behavior. Do not publish or alter the live app.

Implemented and verified: four localized homepages, sample dashboard with editable widgets, three original SVG example posters, local library search, episode/film release agenda, light/dark previews, real Catalog/Settings screenshots, visual layout instructions, rewritten beginner install/Docker guides, and AIO blue/glass colours taken from frontend/src/style.css. Strict four-locale MkDocs build passed. Audited 2,063 local references across 24 key pages with no missing files or anchors. JavaScript syntax, Python hook lint and diff whitespace checks passed; 22 focused NAS/layout tests passed. Browser checks covered tabs, preview theme, add/remove/reorder/resize/reset, keyboard focus, phone-width grip dragging, search and empty results. Independent review findings (focus retention, touch target sizes, pointer grip support) were addressed. No live API is called by the demo, and nothing was deployed to GitHub Pages.
