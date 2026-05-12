#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUI_DIR="${ROOT_DIR}/gui"
DIST_DIR="${GUI_DIR}/dist"

DEPLOY_HOST="${DEPLOY_HOST:-}"
DEPLOY_USER="${DEPLOY_USER:-}"
DEPLOY_DIR="${DEPLOY_DIR:-}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
RELOAD_CMD="${RELOAD_CMD:-}"
SKIP_BUILD="${SKIP_BUILD:-0}"
USE_SCP_ONLY="${USE_SCP_ONLY:-0}"

if [[ -z "${DEPLOY_HOST}" || -z "${DEPLOY_USER}" || -z "${DEPLOY_DIR}" ]]; then
  cat <<'USAGE' >&2
Usage:
  DEPLOY_HOST=example.com \
  DEPLOY_USER=root \
  DEPLOY_DIR=/usr/share/nginx/html/agenthub \
  ./scripts/deploy_gui_static.sh

Optional env:
  DEPLOY_PORT=22
  RELOAD_CMD='sudo systemctl reload nginx'
  SKIP_BUILD=1
  USE_SCP_ONLY=1
USAGE
  exit 1
fi

if [[ "${SKIP_BUILD}" != "1" ]]; then
  (
    cd "${GUI_DIR}"
    pnpm build
  )
fi

if [[ ! -d "${DIST_DIR}" ]]; then
  echo "dist directory not found: ${DIST_DIR}" >&2
  exit 1
fi

SSH_TARGET="${DEPLOY_USER}@${DEPLOY_HOST}"
SSH_ARGS=(-p "${DEPLOY_PORT}" -o StrictHostKeyChecking=accept-new)

ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" "mkdir -p '${DEPLOY_DIR}'"

if command -v rsync >/dev/null 2>&1 && [[ "${USE_SCP_ONLY}" != "1" ]]; then
  rsync -avz --delete -e "ssh -p ${DEPLOY_PORT} -o StrictHostKeyChecking=accept-new" "${DIST_DIR}/" "${SSH_TARGET}:${DEPLOY_DIR}/"
else
  TMP_ARCHIVE="/tmp/agenthub-gui-dist.tar.gz"
  tar -C "${DIST_DIR}" -czf "${TMP_ARCHIVE}" .
  scp "${SSH_ARGS[@]}" "${TMP_ARCHIVE}" "${SSH_TARGET}:${TMP_ARCHIVE}"
  ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" "mkdir -p '${DEPLOY_DIR}' && tar -xzf '${TMP_ARCHIVE}' -C '${DEPLOY_DIR}' && rm -f '${TMP_ARCHIVE}'"
  rm -f "${TMP_ARCHIVE}"
fi

if [[ -n "${RELOAD_CMD}" ]]; then
  ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" "${RELOAD_CMD}"
fi

echo "Deploy completed: ${SSH_TARGET}:${DEPLOY_DIR}"
