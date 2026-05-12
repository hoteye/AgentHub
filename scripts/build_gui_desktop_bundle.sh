#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_EXE="${AGENTHUB_PYTHON:-}"
if [[ -z "${PYTHON_EXE}" ]]; then
  for candidate in \
    "${REPO_ROOT}/.venv/bin/python" \
    "${REPO_ROOT}/cli/.venv/bin/python" \
    "$(command -v python3 || true)" \
    "$(command -v python || true)"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      PYTHON_EXE="${candidate}"
      break
    fi
  done
fi

if [[ -z "${PYTHON_EXE}" || ! -x "${PYTHON_EXE}" ]]; then
  echo "No usable Python executable found." >&2
  exit 1
fi

cd "${REPO_ROOT}"
exec "${PYTHON_EXE}" scripts/build_gui_desktop_bundle.py "$@"
