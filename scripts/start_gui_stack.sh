#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GUI_HOST="127.0.0.1"
GUI_PORT="4173"
BRIDGE_HOST="127.0.0.1"
BRIDGE_PORT="8787"
BASE_PATH="/gui"
GUI_PID=""
BRIDGE_PID=""

usage() {
  cat <<'EOF'
Usage: scripts/start_gui_stack.sh [--gui-host HOST] [--gui-port PORT] [--bridge-host HOST] [--bridge-port PORT] [--base-path PATH]

Starts the local GUI dev server and the CLI GUI bridge together.

Examples:
  scripts/start_gui_stack.sh
  scripts/start_gui_stack.sh --gui-port 4174 --bridge-port 8788
EOF
}

while (($# > 0)); do
  case "$1" in
    --gui-host)
      GUI_HOST="$2"
      shift 2
      ;;
    --gui-port)
      GUI_PORT="$2"
      shift 2
      ;;
    --bridge-host)
      BRIDGE_HOST="$2"
      shift 2
      ;;
    --bridge-port)
      BRIDGE_PORT="$2"
      shift 2
      ;;
    --base-path)
      BASE_PATH="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cleanup() {
  if [[ -n "${GUI_PID}" ]] && kill -0 "${GUI_PID}" >/dev/null 2>&1; then
    kill "${GUI_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${BRIDGE_PID}" ]] && kill -0 "${BRIDGE_PID}" >/dev/null 2>&1; then
    kill "${BRIDGE_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is required" >&2
  exit 1
fi

cd "${REPO_ROOT}"

./cli/scripts/start_gui_bridge.sh --host "${BRIDGE_HOST}" --port "${BRIDGE_PORT}" --base-path "${BASE_PATH}" &
BRIDGE_PID=$!

cd "${REPO_ROOT}/gui"
pnpm dev --host "${GUI_HOST}" --port "${GUI_PORT}" &
GUI_PID=$!

echo "EasyClaw GUI stack started"
echo "  bridge: http://${BRIDGE_HOST}:${BRIDGE_PORT}${BASE_PATH}"
echo "  gui:    http://${GUI_HOST}:${GUI_PORT}/?bridge=http&baseUrl=http://${BRIDGE_HOST}:${BRIDGE_PORT}${BASE_PATH}"
echo "Press Ctrl+C to stop both processes."

wait "${GUI_PID}"
