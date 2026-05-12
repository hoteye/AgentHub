#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_REPORT_DIR="${REPO_ROOT}/artifacts/gui-acceptance"
REPORT_DIR=""
INCLUDE_DEMOQA=0
SMOKE_ONLY=0

usage() {
  cat <<'EOF'
Usage: scripts/run_gui_acceptance_suite.sh [--report-dir PATH] [--include-demoqa] [--smoke-only]

Runs the GUI acceptance suite and writes a suite-level summary JSON.

Examples:
  scripts/run_gui_acceptance_suite.sh
  scripts/run_gui_acceptance_suite.sh --include-demoqa
  scripts/run_gui_acceptance_suite.sh --smoke-only
  scripts/run_gui_acceptance_suite.sh --report-dir artifacts/gui-acceptance/manual
EOF
}

while (($# > 0)); do
  case "$1" in
    --report-dir)
      REPORT_DIR="$2"
      shift 2
      ;;
    --include-demoqa)
      INCLUDE_DEMOQA=1
      shift
      ;;
    --smoke-only)
      SMOKE_ONLY=1
      shift
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

if [[ -z "${REPORT_DIR}" ]]; then
  REPORT_DIR="${DEFAULT_REPORT_DIR}/run-$(date +%Y%m%d-%H%M%S)"
fi

if [[ "${REPORT_DIR}" != /* ]]; then
  REPORT_DIR="${REPO_ROOT}/${REPORT_DIR}"
fi

mkdir -p "${REPORT_DIR}"

run_and_record() {
  local scenario="$1"
  local report_path="$2"
  shift 2
  local started_at ended_at passed failure_detail passed_python
  started_at="$(date -Iseconds)"
  passed=true
  passed_python="True"
  failure_detail=""
  if ! "$@"; then
    passed=false
    passed_python="False"
    failure_detail="command failed: $*"
  fi
  ended_at="$(date -Iseconds)"
  python3 - <<PY
import json
from pathlib import Path

payload = {
    "scenario": ${scenario@Q},
    "executed_at": ${ended_at@Q},
    "started_at": ${started_at@Q},
    "pass": ${passed_python},
    "failure_category": None if ${passed_python} else "command_failed",
    "failure_detail": None if ${passed_python} else ${failure_detail@Q},
}
path = Path(${report_path@Q})
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
PY
  [[ "${passed}" == true ]]
}

echo "Running GUI acceptance suite"
echo "  report dir: ${REPORT_DIR}"

SUITE_FAILED=0

cd "${REPO_ROOT}/gui"
if ! run_and_record "gui-http-smoke" "${REPORT_DIR}/gui-http-smoke.json" pnpm test:smoke:http; then
  SUITE_FAILED=1
fi

if ((SMOKE_ONLY == 0)); then
  cd "${REPO_ROOT}"
  if ! ./scripts/run_gui_browser_live_exam.sh --report "${REPORT_DIR}/gui-browser-live-saucedemo.json"; then
    SUITE_FAILED=1
  fi
  if ((INCLUDE_DEMOQA == 1)); then
    if ! ./scripts/run_gui_browser_demoqa_exam.sh --report "${REPORT_DIR}/gui-browser-live-demoqa.json"; then
      SUITE_FAILED=1
    fi
  fi
fi

SUITE_REPORT="${REPORT_DIR}/gui-acceptance-suite.json"
python3 "${REPO_ROOT}/scripts/collect_gui_acceptance_reports.py" --report-dir "${REPORT_DIR}" --output "${SUITE_REPORT}" >/dev/null

echo "GUI acceptance suite summary written to:"
echo "  ${SUITE_REPORT}"

if ((SUITE_FAILED != 0)); then
  exit 1
fi
