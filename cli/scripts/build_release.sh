#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${CLI_ROOT}"

python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
python scripts/build_release.py --clean "$@"
