#!/bin/sh
# Create a Synology Container Manager project (folders + docker-compose.yml).
# Run over SSH on the NAS:
#   curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
# Or: sudo sh install.sh
# Then open Container Manager → Project → Create and point at the project path.
#
# Downloads and media live in the DSM user home (File Station → Home), not
# /volume1/data, which mkdir creates outside any shared folder.

set -eu

VOLUME="${VOLUME:-/volume1}"
PROJECT="${PROJECT:-${VOLUME}/docker/aio-media-manager}"
BACKUPS="${BACKUPS:-${PROJECT}/backups}"
PUID="${PUID:-${SUDO_UID:-$(id -u)}}"
PGID="${PGID:-${SUDO_GID:-$(id -g)}}"
IMAGE="${IMAGE:-ghcr.io/qballjos/aio-media-server-manager:latest}"
DOWNLOAD_CACHE="${DOWNLOAD_CACHE:-}"

# Never create DSM's docker shared folder ourselves: Package Center owns it.
# These checks must precede migration, mkdir, chown, and compose generation.
SYNOPKG="$(command -v synopkg || true)"
[ -n "${SYNOPKG}" ] || SYNOPKG=/usr/syno/bin/synopkg
if ! "${SYNOPKG}" status ContainerManager >/dev/null 2>&1; then
  echo "Install and start Container Manager in DSM Package Center before running this script." >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Container Manager's Docker engine is not ready. Start Container Manager and run this script with sudo." >&2
  exit 1
fi
if [ ! -d "${VOLUME}/docker" ]; then
  echo "Container Manager's ${VOLUME}/docker shared folder is missing. Finish installing Container Manager first, or set VOLUME to its volume." >&2
  exit 1
fi
if [ -n "${DOWNLOAD_CACHE}" ]; then
  case "${DOWNLOAD_CACHE}" in
    /*) ;;
    *) echo "DOWNLOAD_CACHE must be an absolute path inside an existing SSD shared folder." >&2; exit 1 ;;
  esac
  if [ ! -d "$(dirname "${DOWNLOAD_CACHE}")" ]; then
    echo "Create the SSD shared folder in DSM first; DOWNLOAD_CACHE's parent must already exist." >&2
    exit 1
  fi
fi
if [ -f "${PROJECT}/docker-compose.yml" ] &&
   grep -q ':/data/downloads/incomplete' "${PROJECT}/docker-compose.yml"; then
  if [ -z "${DOWNLOAD_CACHE}" ] ||
     ! grep -Fxq "      - ${DOWNLOAD_CACHE}/incomplete:/data/downloads/incomplete" "${PROJECT}/docker-compose.yml" ||
     ! grep -Fxq "      - ${DOWNLOAD_CACHE}/complete:/data/downloads/complete" "${PROJECT}/docker-compose.yml"; then
    echo "This project already uses SSD download mounts. Re-run with its existing DOWNLOAD_CACHE value; migrate files separately before changing storage." >&2
    exit 1
  fi
fi

dsm_user() {
  if [ -n "${HOME_USER:-}" ] && [ "${HOME_USER}" != "root" ]; then
    echo "${HOME_USER}"
    return
  fi
  if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
    echo "${SUDO_USER}"
    return
  fi
  uname_now="$(id -un 2>/dev/null || true)"
  if [ -n "${uname_now}" ] && [ "${uname_now}" != "root" ]; then
    echo "${uname_now}"
    return
  fi
  echo "admin"
}

real_dir() {
  readlink -f "$1" 2>/dev/null || echo "$1"
}

dsm_home() {
  user="$1"
  for candidate in \
    "${VOLUME}/homes/${user}" \
    "/var/services/homes/${user}" \
    "/volume1/homes/${user}"
  do
    if [ -d "${candidate}" ]; then
      real_dir "${candidate}"
      return 0
    fi
  done
  return 1
}

migrate_tree() {
  src="$1"
  dest="$2"
  [ -d "${src}" ] || return 0
  src_real="$(real_dir "${src}")"
  dest_real="$(real_dir "${dest}")"
  [ "${src_real}" != "${dest_real}" ] || return 0
  [ -e "${src}/downloads" ] || [ -e "${src}/media" ] || return 0

  echo "Moving downloads + media from ${src_real} → ${dest_real}"
  echo "(DSM File Station shows Home, not a raw /volume*/data folder.)"
  if command -v docker >/dev/null 2>&1; then
    docker stop aio-media-manager >/dev/null 2>&1 || true
  fi
  mkdir -p "${dest}"
  for name in downloads media; do
    if [ -e "${src}/${name}" ]; then
      if [ -e "${dest}/${name}" ]; then
        echo "  skip ${name}: already at ${dest}/${name}"
      else
        mv "${src}/${name}" "${dest}/${name}"
        echo "  moved ${name}"
      fi
    fi
  done
  rmdir "${src}" 2>/dev/null || true
}

DSM_USER="$(dsm_user)"

if [ -n "${DATA:-}" ]; then
  DATA_ROOT="${DATA}"
else
  if ! DSM_HOME="$(dsm_home "${DSM_USER}")"; then
    echo "Could not find a DSM home directory for user '${DSM_USER}'." >&2
    echo "Enable Control Panel → User & Group → Advanced → Enable user home service," >&2
    echo "or re-run with HOME_USER=<dsm-username> or DATA=/volume1/<share>/aio-media-manager." >&2
    exit 1
  fi
  DATA_ROOT="${DSM_HOME}/aio-media-manager"
fi

# Adding nested mounts to populated folders would hide existing downloads.
# A migration is separate work; this installer never silently moves live data.
if [ -n "${DOWNLOAD_CACHE}" ]; then
  for name in incomplete complete; do
    for src in "${DATA_ROOT}/downloads/${name}" "${VOLUME}/data/downloads/${name}" /volume1/data/downloads/"${name}"; do
      if [ -L "${src}" ] || { [ -d "${src}" ] && [ -n "$(find "${src}" -mindepth 1 -print -quit)" ]; }; then
        echo "Existing downloads at ${src}. Stop AIO and migrate them to DOWNLOAD_CACHE before enabling SSD mounts." >&2
        exit 1
      fi
    done
  done
fi

if [ -z "${DATA:-}" ]; then
  migrate_tree "${VOLUME}/data" "${DATA_ROOT}"
  if [ "${VOLUME}" != "/volume1" ]; then
    migrate_tree "/volume1/data" "${DATA_ROOT}"
  fi
fi

mkdir -p \
  "${PROJECT}/config/vpn" \
  "${PROJECT}/config/cloudflare" \
  "${BACKUPS}" \
  "${DATA_ROOT}/downloads" \
  "${DATA_ROOT}/media/movies" \
  "${DATA_ROOT}/media/tv"

chown -R "${PUID}:${PGID}" "${PROJECT}" "${DATA_ROOT}" "${BACKUPS}"

CACHE_MOUNTS=""
if [ -n "${DOWNLOAD_CACHE}" ]; then
  mkdir -p "${DOWNLOAD_CACHE}/incomplete" "${DOWNLOAD_CACHE}/complete"
  chown -R "${PUID}:${PGID}" "${DOWNLOAD_CACHE}"
  CACHE_MOUNTS="      - ${DOWNLOAD_CACHE}/incomplete:/data/downloads/incomplete
      - ${DOWNLOAD_CACHE}/complete:/data/downloads/complete"
fi

cat > "${PROJECT}/docker-compose.yml" <<EOF
# Generated by deploy/synology/install.sh — one AIO container only.
services:
  aio-media-manager:
    image: ${IMAGE}
    container_name: aio-media-manager
    restart: unless-stopped
    ports:
      - "8080:8080"
      - "8081:8081"
      - "8084:8084"
      - "8085:8085"
      - "8096:8096"
      - "8191:8191"
      - "5055:5055"
      - "6060:6060"
      - "6767:6767"
      - "6789:6789"
      - "7878:7878"
      - "8686:8686"
      - "8989:8989"
      - "9696:9696"
      - "9705:9705"
      - "11011:11011"    # Cleanuparr
      - "32400:32400"
    volumes:
      - ${PROJECT}/config:/config
      - ${DATA_ROOT}:/data
${CACHE_MOUNTS}
      - ${BACKUPS}:/backups
      - /sys:/host/sys:ro
    environment:
      PUID: "${PUID}"
      PGID: "${PGID}"
      TZ: UTC
      AMM_DOWNLOAD_DIR: /data/downloads
      AMM_MEDIA_DIR: /data/media
      AMM_VPN_ENABLED: "false"
      AMM_VPN_ENFORCE: "false"
      AMM_CLOUDFLARE_TUNNEL_ENABLED: "false"
      AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE: /config/cloudflare/tunnel.token
      AMM_TRUSTED_PROXIES: ""
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    privileged: true
EOF

chmod 644 "${PROJECT}/docker-compose.yml"

echo
echo "Container Manager project files are ready."
echo "  Compose:    ${PROJECT}/docker-compose.yml"
echo "  Config:     ${PROJECT}/config"
echo "  Data:       ${DATA_ROOT}  (File Station → Home → aio-media-manager)"
if [ -n "${DOWNLOAD_CACHE}" ]; then
  echo "  SSD work:   ${DOWNLOAD_CACHE} (incomplete downloads + Usenet unpacking)"
  echo "  Finished torrents and imported media stay under ${DATA_ROOT}; SSD-to-HDD imports copy files."
else
  echo "  SSD option: set DOWNLOAD_CACHE to a folder inside an existing SSD-volume shared folder."
fi
echo "  Backups:    ${BACKUPS}  (config backups; set BACKUPS=/volume2/... for another volume)"
echo "  DSM user:   ${DSM_USER}"
echo "  PUID:PGID:  ${PUID}:${PGID}"
echo
echo "In DSM: Container Manager → Project → Create"
echo "  Name: aio-media-manager"
echo "  Path: ${PROJECT}"
echo "  Source: existing docker-compose.yml"
echo "Then start the project and open http://<nas-ip>:8080"
echo
echo "Optional (SSH): docker compose -f ${PROJECT}/docker-compose.yml pull"
