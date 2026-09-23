# Security Policy

## Supported versions

This project is pre-1.0. Security fixes land on `main` only.

| Version | Supported |
|---------|-----------|
| `main`  | Yes       |
| older tags | No    |

## Reporting a vulnerability

Do **not** open a public issue for security problems.

1. Use [GitHub Private Vulnerability Reporting](https://github.com/Qballjos/aio-media-server-manager/security/advisories/new) if it is available on this repository.
2. Otherwise email the maintainer through GitHub (`@Qballjos`) with:
   - a description of the issue
   - steps to reproduce
   - impact (credential leak, unauthenticated API, path traversal, etc.)
   - any suggested fix

Please allow a reasonable time for a response before disclosing publicly.

## Handling secrets

- Never commit `.env`, API keys, VPN configs, or `secret.key` / `secrets.enc`.
- Application credentials must stay in the encrypted secret store, not in logs or API responses.
- Use `GITHUB_TOKEN` only as a local/CI secret for GitHub API rate limits.
