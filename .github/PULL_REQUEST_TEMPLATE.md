## Summary
<!-- What changed and why? -->

## Type of change
- [ ] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] Documentation / CI / dependencies

## Checklist
- [ ] Tests added or updated
- [ ] `poetry run pytest` passes
- [ ] No Debrid functionality or per-app Docker Compose added
- [ ] Catalog still 16 apps (VueTorrent is a qBittorrent option, not a new catalog entry)
- [ ] Secrets are not logged or returned by the API
- [ ] Docs, `.env.example`, and compose templates updated if ports, env, or Settings changed
- [ ] Wizard, catalog, or Open UI changes were checked with `./scripts/test-env.sh up` (Linux image), not a native macOS or Windows process
