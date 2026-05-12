#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_REPORT_DIR="${REPO_ROOT}/artifacts/gui-live-exams"
REPORT_PATH=""

usage() {
  cat <<'EOF'
Usage: scripts/run_gui_browser_demoqa_exam.sh [--report PATH]

Runs the GUI browser DemoQA register live exam and writes a JSON report.
EOF
}

while (($# > 0)); do
  case "$1" in
    --report)
      REPORT_PATH="$2"
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

if [[ -z "${REPORT_PATH}" ]]; then
  mkdir -p "${DEFAULT_REPORT_DIR}"
  REPORT_PATH="${DEFAULT_REPORT_DIR}/gui-browser-demoqa-register-exam-$(date +%Y%m%d-%H%M%S).json"
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is required" >&2
  exit 1
fi

if ! command -v google-chrome >/dev/null 2>&1; then
  echo "google-chrome is required for the GUI browser live exam" >&2
  exit 1
fi

echo "Running GUI browser DemoQA register live exam"
echo "  report: ${REPORT_PATH}"

cd "${REPO_ROOT}/gui"
AGENTHUB_GUI_LIVE_EXAM_REPORT="${REPORT_PATH}" pnpm test:smoke:browser-live:demoqa

echo "Live exam report written to:"
echo "  ${REPORT_PATH}"
