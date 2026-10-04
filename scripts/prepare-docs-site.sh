#!/usr/bin/env bash
# Assemble MkDocs input from docs/ + deploy/*.md without duplicating sources in git.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/.docs-site"
export DOCS_SITE_OUT="${OUT}"
REPO_BLOB="https://github.com/Qballjos/aio-media-server-manager/blob/main/deploy"
export DOCS_REPO_BLOB="${REPO_BLOB}"

rm -rf "${OUT}"
mkdir -p "${OUT}/deploy" "${OUT}/screenshots" "${OUT}/assets"

cp "${ROOT}/docs/index.md" "${OUT}/index.md"
cp "${ROOT}/docs/INSTALL.md" "${OUT}/INSTALL.md"
cp "${ROOT}/docs/USAGE.md" "${OUT}/USAGE.md"

if [[ -d "${ROOT}/docs/screenshots" ]]; then
  cp -R "${ROOT}/docs/screenshots/." "${OUT}/screenshots/"
fi
if [[ -f "${ROOT}/logo-aio-media-manager.png" ]]; then
  cp "${ROOT}/logo-aio-media-manager.png" "${OUT}/assets/logo-aio-media-manager.png"
fi

for name in README DOCKER LINUX UNRAID SYNOLOGY TRUENAS CLOUDFLARE CLOUDFLARE_ACCESS; do
  src="${ROOT}/deploy/${name}.md"
  if [[ -f "${src}" ]]; then
    cp "${src}" "${OUT}/deploy/${name}.md"
  fi
done

python3 <<'PY'
from pathlib import Path
import os
import re

out = Path(os.environ["DOCS_SITE_OUT"])
repo_blob = os.environ["DOCS_REPO_BLOB"]
repo_root = "https://github.com/Qballjos/aio-media-server-manager/blob/main"


def rewrite(text: str, *, kind: str) -> str:
    if kind in {"install", "usage"}:
        text = text.replace("](../deploy/", "](deploy/")
        text = text.replace("](deploy/unraid/)", f"]({repo_blob}/unraid/)")
        text = text.replace("](../.env.example)", f"]({repo_root}/.env.example)")
        text = text.replace("](../CONTRIBUTING.md)", f"]({repo_root}/CONTRIBUTING.md)")
    if kind == "deploy":
        text = text.replace("](../docs/USAGE.md", "](../USAGE.md")
        text = text.replace("](../docs/INSTALL.md", "](../INSTALL.md")
        text = text.replace("](../CONTRIBUTING.md)", f"]({repo_root}/CONTRIBUTING.md)")
        text = text.replace("](unraid/)", f"]({repo_blob}/unraid/)")
        text = text.replace("](synology/)", f"]({repo_blob}/synology/)")
        text = re.sub(r"\]\((unraid/[^)]+)\)", rf"]({repo_blob}/\1)", text)
        text = re.sub(r"\]\((synology/[^)]+)\)", rf"]({repo_blob}/\1)", text)
        text = re.sub(r"\]\((aio-media-manager\.service)\)", rf"]({repo_blob}/\1)", text)
        text = re.sub(r"\]\((unraid\.xml)\)", rf"]({repo_blob}/\1)", text)
    return text


(out / "INSTALL.md").write_text(
    rewrite((out / "INSTALL.md").read_text(encoding="utf-8"), kind="install"),
    encoding="utf-8",
)
(out / "USAGE.md").write_text(
    rewrite((out / "USAGE.md").read_text(encoding="utf-8"), kind="usage"),
    encoding="utf-8",
)
for path in sorted((out / "deploy").glob("*.md")):
    path.write_text(rewrite(path.read_text(encoding="utf-8"), kind="deploy"), encoding="utf-8")

print(f"Prepared docs site at {out.resolve()}")
PY
