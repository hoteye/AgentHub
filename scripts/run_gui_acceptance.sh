#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[compat] scripts/run_gui_acceptance.sh is kept as a wrapper."
echo "[compat] Prefer scripts/run_gui_acceptance_suite.sh for new runs."

exec "${SCRIPT_DIR}/run_gui_acceptance_suite.sh" "$@"
