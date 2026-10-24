#!/usr/bin/env bash
# Assemble MkDocs input from docs/ + deploy/*.md without duplicating sources in git.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/.docs-site"
export DOCS_SITE_OUT="${OUT}"
REPO_BLOB="https://github.com/Qballjos/aio-media-server-manager/blob/main/deploy"
export DOCS_REPO_BLOB="${REPO_BLOB}"

rm -rf "${OUT}"
mkdir -p "${OUT}/deploy" "${OUT}/screenshots" "${OUT}/assets/app-icons" "${OUT}/stylesheets"

copy_localized() {
  local src_dir="$1" name="$2" dest_dir="$3" suffix
  for suffix in "" .nl .de .fr; do
    if [[ -f "${src_dir}/${name}${suffix}.md" ]]; then
      cp "${src_dir}/${name}${suffix}.md" "${dest_dir}/${name}${suffix}.md"
    fi
  done
}

copy_localized "${ROOT}/docs" index "${OUT}"
copy_localized "${ROOT}/docs" INSTALL "${OUT}"
copy_localized "${ROOT}/docs" USAGE "${OUT}"

if [[ -d "${ROOT}/docs/stylesheets" ]]; then
  cp -R "${ROOT}/docs/stylesheets/." "${OUT}/stylesheets/"
fi
if [[ -d "${ROOT}/docs/screenshots" ]]; then
  cp -R "${ROOT}/docs/screenshots/." "${OUT}/screenshots/"
fi
if [[ -f "${ROOT}/logo-aio-media-manager.png" ]]; then
  cp "${ROOT}/logo-aio-media-manager.png" "${OUT}/assets/logo-aio-media-manager.png"
fi
if [[ -d "${ROOT}/frontend/public/app-icons" ]]; then
  cp -R "${ROOT}/frontend/public/app-icons/." "${OUT}/assets/app-icons/"
fi

for name in README DOCKER LINUX UNRAID SYNOLOGY TRUENAS CLOUDFLARE CLOUDFLARE_ACCESS; do
  copy_localized "${ROOT}/deploy" "${name}" "${OUT}/deploy"
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


def kind_for(path: Path) -> str | None:
    if path.parent.name == "deploy":
        return "deploy"
    base = path.name.split(".", 1)[0]
    if base == "INSTALL":
        return "install"
    if base == "USAGE":
        return "usage"
    return None


for path in sorted(out.rglob("*.md")):
    kind = kind_for(path)
    if not kind:
        continue
    path.write_text(rewrite(path.read_text(encoding="utf-8"), kind=kind), encoding="utf-8")

print(f"Prepared docs site at {out.resolve()}")
PY
