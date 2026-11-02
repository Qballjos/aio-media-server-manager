#!/bin/sh
# Prepare SSD download staging and install the Unraid user template.
# curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/install.sh | sh
set -eu

CACHE_ROOT="${CACHE_ROOT:-/mnt/cache}"
DATA="${DATA:-/mnt/user/aio-media-manager}"
CONFIG="${CONFIG:-/mnt/user/appdata/aio-media-manager}"
BACKUPS="${BACKUPS:-/mnt/user/backups/aio-media-manager}"
TEMPLATE_DIR="${TEMPLATE_DIR:-/boot/config/plugins/dockerMan/templates-user}"
SHARE_CONFIG_DIR="${SHARE_CONFIG_DIR:-/boot/config/shares}"
TEMPLATE_URL="${TEMPLATE_URL:-https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/templates/aio-media-manager.xml}"
PUID="${PUID:-99}"
PGID="${PGID:-100}"

if [ "$(id -u)" != 0 ]; then
  echo "Run this installer as root on Unraid." >&2
  exit 1
fi
case "${PUID}:${PGID}" in
  *[!0-9:]*|:*|*:) echo "PUID and PGID must be numeric user/group IDs." >&2; exit 1 ;;
esac
for path in "${CACHE_ROOT}" "${DATA}" "${CONFIG}" "${BACKUPS}" "${TEMPLATE_DIR}" "${SHARE_CONFIG_DIR}"; do
  case "${path}" in
    /*) ;;
    *) echo "Storage and template paths must be absolute." >&2; exit 1 ;;
  esac
  case "${path}" in
    *[!a-zA-Z0-9_./-]*) echo "Use paths containing only letters, numbers, /, _, . and -." >&2; exit 1 ;;
  esac
done
case "${CACHE_ROOT}" in
  /mnt/user|/mnt/user/*|/mnt/disk*) echo "CACHE_ROOT must name a mounted SSD/NVMe pool, not the array or a user share." >&2; exit 1 ;;
esac
if ! mountpoint -q "${CACHE_ROOT}"; then
  echo "Cache pool ${CACHE_ROOT} is not mounted. Start the array and select an SSD/NVMe pool with CACHE_ROOT=/mnt/<pool>. No folders were created." >&2
  exit 1
fi

existing_template="${TEMPLATE_DIR}/my-aio-media-manager.xml"
if [ -f "${existing_template}" ] && grep -q 'Target="/data/downloads/incomplete"' "${existing_template}"; then
  if ! grep -Fq ">${CACHE_ROOT}/aio-download-cache/incomplete</Config>" "${existing_template}" ||
     ! grep -Fq ">${CACHE_ROOT}/aio-download-cache/complete</Config>" "${existing_template}"; then
    echo "The existing template uses different download storage. Stop AIO and migrate those files before changing the template; it was not overwritten." >&2
    exit 1
  fi
fi

pool_name="$(basename "${CACHE_ROOT}")"
share_config="${SHARE_CONFIG_DIR}/aio-download-cache.cfg"
if [ -e "${share_config}" ]; then
  if ! tr -d '\r' < "${share_config}" | grep -qx 'shareUseCache="only"' ||
     ! tr -d '\r' < "${share_config}" | grep -qx "shareCachePool=\"${pool_name}\""; then
    echo "Existing aio-download-cache share must be pool-only on ${pool_name}. Review it in Shares first; its settings were not changed." >&2
    exit 1
  fi
fi

for name in incomplete complete; do
  src="${DATA}/downloads/${name}"
  if [ -L "${src}" ] || { [ -d "${src}" ] && [ -n "$(find "${src}" -mindepth 1 -print -quit)" ]; }; then
    echo "Existing downloads at ${src}. Stop AIO and migrate them to ${CACHE_ROOT}/aio-download-cache/${name} before applying SSD mounts." >&2
    exit 1
  fi
done

# Fetch before changing the installation; do not overwrite a template on failure.
template_tmp="$(mktemp)"
trap 'rm -f "${template_tmp}"' EXIT HUP INT TERM
curl -fsSL "${TEMPLATE_URL}" > "${template_tmp}"
if ! grep -q 'Target="/data/downloads/incomplete"' "${template_tmp}" ||
   ! grep -q 'Target="/data/downloads/complete"' "${template_tmp}"; then
  echo "The downloaded template does not contain SSD download mounts; nothing was installed." >&2
  exit 1
fi

mkdir -p "${SHARE_CONFIG_DIR}"
if [ ! -e "${share_config}" ]; then
  cat > "${share_config}" <<EOF
shareComment="AIO download staging; keep on SSD pool, never move to array"
shareUseCache="only"
shareCachePool="${pool_name}"
shareCachePool2=""
shareFloor="20971520"
shareExport="-"
EOF
fi

mkdir -p "${CONFIG}/vpn" "${BACKUPS}" "${DATA}/downloads/torrents" "${DATA}/media" \
  "${CACHE_ROOT}/aio-download-cache/incomplete" \
  "${CACHE_ROOT}/aio-download-cache/complete" "${TEMPLATE_DIR}"
chown "${PUID}:${PGID}" "${CONFIG}" "${CONFIG}/vpn" "${BACKUPS}" "${DATA}" \
  "${DATA}/downloads" "${DATA}/downloads/torrents" "${DATA}/media" \
  "${CACHE_ROOT}/aio-download-cache" \
  "${CACHE_ROOT}/aio-download-cache/incomplete" "${CACHE_ROOT}/aio-download-cache/complete"
sed -e "s|/mnt/cache/aio-download-cache|${CACHE_ROOT}/aio-download-cache|g" \
  -e "s|/mnt/user/appdata/aio-media-manager|${CONFIG}|g" \
  -e "s|/mnt/user/backups/aio-media-manager|${BACKUPS}|g" \
  -e "s|/mnt/user/aio-media-manager|${DATA}|g" \
  -e "/Target=\"PUID\"/s|Default=\"99\"|Default=\"${PUID}\"|; /Target=\"PUID\"/s|>99</Config>|>${PUID}</Config>|" \
  -e "/Target=\"PGID\"/s|Default=\"100\"|Default=\"${PGID}\"|; /Target=\"PGID\"/s|>100</Config>|>${PGID}</Config>|" \
  "${template_tmp}" > "${TEMPLATE_DIR}/my-aio-media-manager.xml"
chmod 644 "${TEMPLATE_DIR}/my-aio-media-manager.xml"

echo "Unraid template ready: ${TEMPLATE_DIR}/my-aio-media-manager.xml"
echo "Download staging + Usenet unpacking: ${CACHE_ROOT}/aio-download-cache"
echo "Finished torrents + media library: ${DATA}"
echo "Keep free space on the SSD pool; imports to the array copy files."
echo "In Shares, verify aio-download-cache uses ${pool_name} only (no secondary storage / no mover to array)."
echo "Docker → Add Container → select my-aio-media-manager, review paths and timezone, then Apply."
