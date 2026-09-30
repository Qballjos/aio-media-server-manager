#!/usr/bin/env bash
# Run this checkout as the Linux appliance (catalog installs, wizard, Open UI).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -p amm-test -f docker-compose.yml -f compose.test.yml)

usage() {
  echo "Usage: $0 up | down | logs | ps" >&2
  exit 1
}

cmd="${1:-}"
case "$cmd" in
  up)
    mkdir -p .docker-test/config .docker-test/data/downloads .docker-test/data/media .docker-test/backups
    echo "Building and starting the test appliance (Linux image, data in .docker-test/)…"
    "${COMPOSE[@]}" up -d --build
    echo "Manager UI: http://127.0.0.1:8080"
    echo "Optional live dashboard: cd frontend && npm run dev  (proxies /api to :8080)"
    ;;
  down)
    "${COMPOSE[@]}" down
    ;;
  logs)
    "${COMPOSE[@]}" logs -f
    ;;
  ps)
    "${COMPOSE[@]}" ps
    ;;
  *)
    usage
    ;;
esac
