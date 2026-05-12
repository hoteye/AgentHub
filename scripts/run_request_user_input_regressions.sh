#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODE="core"
BATCH_TIMEOUT_SEC="${REQUEST_USER_INPUT_BATCH_TIMEOUT_SEC:-90}"
SLOW_BATCH_TIMEOUT_SEC="${REQUEST_USER_INPUT_SLOW_BATCH_TIMEOUT_SEC:-180}"
INCLUDE_APP_INTEGRATION=0

usage() {
  cat <<'EOF'
Usage: scripts/run_request_user_input_regressions.sh [--core|--all] [--include-app-integration] [-- <extra pytest args>]

Runs request_user_input focused regressions without running the full repository test suite.

Modes:
  --core   Run the focused core bundle (default)
  --all    Run all stable request_user_input-related tests under cli/tests plus TUI smoke
  --include-app-integration
           Include test_request_user_input_app_integration.py (excluded by default due runtime instability)
           Note: test_request_user_input_fallback_notice.py is always excluded due hang risk.

Env:
  REQUEST_USER_INPUT_BATCH_TIMEOUT_SEC
           Per-batch timeout in seconds (default: 90). Set 0 to disable batch timeout.
  REQUEST_USER_INPUT_SLOW_BATCH_TIMEOUT_SEC
           Per-batch timeout for known slow/flaky batches (default: 180).

Examples:
  scripts/run_request_user_input_regressions.sh
  scripts/run_request_user_input_regressions.sh --all
  scripts/run_request_user_input_regressions.sh --all -- -k "not slow"
EOF
}

PYTEST_ARGS=()
while (($# > 0)); do
  case "$1" in
    --core)
      MODE="core"
      shift
      ;;
    --all)
      MODE="all"
      shift
      ;;
    --include-app-integration)
      INCLUDE_APP_INTEGRATION=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --)
      shift
      PYTEST_ARGS=("$@")
      break
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

CORE_FAST_TESTS=(
  "cli/tests/test_request_user_input_replay_projection.py"
  "cli/tests/test_request_user_input_transcript_projection.py"
  "cli/tests/test_request_user_input_tool_event_rendering.py"
  "cli/tests/test_request_user_input_command_level.py"
  "cli/tests/test_request_user_input_presenter_contract.py"
  "cli/tests/test_request_user_input_contract_runtime.py"
  "cli/tests/test_request_user_input_bridge.py"
  "cli/tests/test_request_user_input_state_runtime.py"
  "cli/tests/test_request_user_input_modal.py"
  "cli/tests/test_request_user_input_presenter_precedence.py"
  "cli/tests/test_request_user_input_module_presenter_path.py"
)

CORE_SMOKE_TESTS=(
  "cli/tests/test_request_user_input_ui_smoke.py"
  "cli/tests/test_request_user_input_multi_question_ui_smoke.py"
)

KNOWN_SLOW_OR_FLAKY_TEST_TARGETS=(
  "cli/tests/test_request_user_input_request_notice.py"
)

cd "${REPO_ROOT}"

run_pytest_batch() {
  local label="$1"
  shift
  local targets=("$@")
  if ((${#targets[@]} == 0)); then
    return 0
  fi
  local primary_target="${targets[0]}"
  local is_known_slow=0
  for known in "${KNOWN_SLOW_OR_FLAKY_TEST_TARGETS[@]}"; do
    if [[ "${primary_target}" == "${known}" ]]; then
      is_known_slow=1
      break
    fi
  done

  local timeout_sec="${BATCH_TIMEOUT_SEC}"
  if ((is_known_slow == 1)) && ((timeout_sec > 0)) && ((SLOW_BATCH_TIMEOUT_SEC > timeout_sec)); then
    timeout_sec="${SLOW_BATCH_TIMEOUT_SEC}"
  fi

  echo "Running request_user_input regressions (${MODE}) batch: ${label}"
  local ec=0
  set +e
  if ((timeout_sec > 0)) && command -v timeout >/dev/null 2>&1; then
    timeout "${timeout_sec}" pytest -q -o addopts='' "${targets[@]}" "${PYTEST_ARGS[@]}"
  else
    pytest -q -o addopts='' "${targets[@]}" "${PYTEST_ARGS[@]}"
  fi
  ec=$?
  set -e
  if [[ "${ec}" == "5" ]] && ((${#PYTEST_ARGS[@]} > 0)); then
    echo "Batch ${label}: no tests selected by extra pytest args; skipping."
    return 0
  fi
  if [[ "${ec}" == "124" ]] && ((is_known_slow == 1)); then
    echo "Batch ${label}: timed out after ${timeout_sec}s; retrying once for known slow/flaky target."
    set +e
    if ((timeout_sec > 0)) && command -v timeout >/dev/null 2>&1; then
      timeout "${timeout_sec}" pytest -q -o addopts='' "${targets[@]}" "${PYTEST_ARGS[@]}"
    else
      pytest -q -o addopts='' "${targets[@]}" "${PYTEST_ARGS[@]}"
    fi
    ec=$?
    set -e
    if [[ "${ec}" == "5" ]] && ((${#PYTEST_ARGS[@]} > 0)); then
      echo "Batch ${label}: no tests selected by extra pytest args on retry; skipping."
      return 0
    fi
  fi
  if [[ "${ec}" == "124" ]]; then
    echo "Batch ${label}: timed out after ${timeout_sec}s." >&2
  fi
  return "${ec}"
}

if [[ "${MODE}" == "core" ]]; then
  for target in "${CORE_FAST_TESTS[@]}"; do
    run_pytest_batch "core-fast:${target}" "${target}"
  done
  for target in "${CORE_SMOKE_TESTS[@]}"; do
    run_pytest_batch "core-smoke:${target}" "${target}"
  done
  exit 0
fi

mapfile -t TEST_TARGETS < <(find cli/tests -maxdepth 1 -type f -name 'test_request_user_input*.py' | sort)
if ((INCLUDE_APP_INTEGRATION == 0)); then
  FILTERED_TARGETS=()
  for target in "${TEST_TARGETS[@]}"; do
    if [[ "${target}" == "cli/tests/test_request_user_input_app_integration.py" ]]; then
      continue
    fi
    if [[ "${target}" == "cli/tests/test_request_user_input_fallback_notice.py" ]]; then
      continue
    fi
    FILTERED_TARGETS+=("${target}")
  done
  TEST_TARGETS=("${FILTERED_TARGETS[@]}")
else
  FILTERED_TARGETS=()
  for target in "${TEST_TARGETS[@]}"; do
    if [[ "${target}" == "cli/tests/test_request_user_input_fallback_notice.py" ]]; then
      continue
    fi
    FILTERED_TARGETS+=("${target}")
  done
  TEST_TARGETS=("${FILTERED_TARGETS[@]}")
fi
if [[ -f "cli/tests/test_tui_request_user_input.py" ]]; then
  TEST_TARGETS+=("cli/tests/test_tui_request_user_input.py")
fi
if ((${#TEST_TARGETS[@]} == 0)); then
  echo "No request_user_input test targets found." >&2
  exit 1
fi

for target in "${TEST_TARGETS[@]}"; do
  run_pytest_batch "all:${target}" "${target}"
done
