#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${CLI_ROOT}/.." && pwd)"

PYTHON_EXE="${AGENTHUB_PYTHON:-}"
SCENARIO="single_turn_headless"
RUNS=1
TIMEOUT=60
MAX_WORKERS=4
PROMPT="你好"
PROVIDER_HOME="${AGENTHUB_PROVIDER_HOME:-}"
JSON_OUTPUT=1
OUT_PATH=""
CASES=()
EXTRA_ARGS=()

usage() {
    cat <<'EOF'
Usage: scripts/benchmark_selected_models.sh [options] [-- extra benchmark args]

Runs the fixed cross-provider benchmark matrix used in the latest validation:
  - single_turn_headless: claude:claude-sonnet-4-6, claude:claude-haiku-4-5-20251001, deepseek:deepseek-chat, glm:glm-5, glm-claude-mode:glm-5
  - multi_llm_live_cases: openai:gpt_54
  - policy_helper_live_cases: glm:glm_5 + helper profile policy_helper_regression

For `multi_llm_live_cases` and `policy_helper_live_cases`, JSON/table output also includes
minimal cost proxy metrics:
  - request_count
  - child_turn_count
  - timeout_count
  - fallback_count
  - delegation_wall_ms
And structured summary fields:
  - success_rate
  - empty_response_count
  - failure_categories
  - human_summary

Options:
  --python PATH          Python executable to use.
  --scenario NAME        Benchmark scenario. Default: single_turn_headless
  --runs N               Runs per case. Default: 1
  --timeout SECONDS      Per-run timeout. Default: 60
  --max-workers N        Concurrent benchmark workers. Default: 4
  --prompt TEXT          Prompt for single-turn benchmark. Default: 你好
  --provider-home PATH   Optional provider home override passed via AGENTHUB_PROVIDER_HOME.
                         Default: runtime-managed provider home resolution
  --case provider:model  Override the default case matrix. Repeat to add more cases.
  --out PATH             Write full JSON report to PATH.
  --json                 Emit JSON report. Default.
  --table                Emit table summary instead of JSON.
  --help, -h             Show this help.

Examples:
  scripts/benchmark_selected_models.sh
  scripts/benchmark_selected_models.sh --table
  scripts/benchmark_selected_models.sh --prompt "请只回复ok" --out /tmp/selected_models.json
  scripts/benchmark_selected_models.sh --scenario two_turn_dates --first-prompt "今天几号？" --second-prompt "明天呢？"
  scripts/benchmark_selected_models.sh --scenario multi_llm_live_cases --case openai:gpt_54 --out /tmp/multi_llm_cases.json
  scripts/benchmark_selected_models.sh --scenario policy_helper_live_cases --case glm:glm_5 --out /tmp/policy_helper_cases.json
  scripts/benchmark_selected_models.sh --scenario policy_helper_live_cases --policy-helper-profile single --policy-helper-provider deepseek --policy-helper-model deepseek_chat --out /tmp/policy_helper_override.json
EOF
}

while (($# > 0)); do
    case "$1" in
        --python)
            if (($# < 2)); then
                echo "Missing value for --python" >&2
                exit 2
            fi
            PYTHON_EXE="$2"
            shift 2
            ;;
        --scenario)
            if (($# < 2)); then
                echo "Missing value for --scenario" >&2
                exit 2
            fi
            SCENARIO="$2"
            shift 2
            ;;
        --runs)
            if (($# < 2)); then
                echo "Missing value for --runs" >&2
                exit 2
            fi
            RUNS="$2"
            shift 2
            ;;
        --timeout)
            if (($# < 2)); then
                echo "Missing value for --timeout" >&2
                exit 2
            fi
            TIMEOUT="$2"
            shift 2
            ;;
        --max-workers)
            if (($# < 2)); then
                echo "Missing value for --max-workers" >&2
                exit 2
            fi
            MAX_WORKERS="$2"
            shift 2
            ;;
        --prompt)
            if (($# < 2)); then
                echo "Missing value for --prompt" >&2
                exit 2
            fi
            PROMPT="$2"
            shift 2
            ;;
        --provider-home)
            if (($# < 2)); then
                echo "Missing value for --provider-home" >&2
                exit 2
            fi
            PROVIDER_HOME="$2"
            shift 2
            ;;
        --case)
            if (($# < 2)); then
                echo "Missing value for --case" >&2
                exit 2
            fi
            CASES+=("$2")
            shift 2
            ;;
        --out)
            if (($# < 2)); then
                echo "Missing value for --out" >&2
                exit 2
            fi
            OUT_PATH="$2"
            shift 2
            ;;
        --json)
            JSON_OUTPUT=1
            shift
            ;;
        --table)
            JSON_OUTPUT=0
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --)
            shift
            EXTRA_ARGS+=("$@")
            break
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

if [[ -z "${PYTHON_EXE}" ]]; then
    for candidate in \
        "${PROJECT_ROOT}/.venv/bin/python" \
        "${CLI_ROOT}/.venv/bin/python" \
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
    echo "Expected one of:" >&2
    echo "  ${PROJECT_ROOT}/.venv/bin/python" >&2
    echo "  ${CLI_ROOT}/.venv/bin/python" >&2
    echo "Or pass --python PATH." >&2
    exit 1
fi

cd "${CLI_ROOT}"

CMD=(
    "${PYTHON_EXE}"
    "${SCRIPT_DIR}/benchmark_headless_models.py"
    --scenario "${SCENARIO}"
    --runs "${RUNS}"
    --timeout "${TIMEOUT}"
    --max-workers "${MAX_WORKERS}"
    --prompt "${PROMPT}"
)

if [[ -n "${PROVIDER_HOME}" ]]; then
    CMD+=(--provider-home "${PROVIDER_HOME}")
fi

if ((${#CASES[@]} > 0)); then
    for case_value in "${CASES[@]}"; do
        CMD+=(--case "${case_value}")
    done
elif [[ "${SCENARIO}" == "multi_llm_live_cases" ]]; then
    CMD+=(--case "openai:gpt_54")
elif [[ "${SCENARIO}" == "policy_helper_live_cases" ]]; then
    CMD+=(--case "glm:glm_5")
    CMD+=(--policy-helper-profile "policy_helper_regression")
else
    CMD+=(--case "claude:claude-sonnet-4-6")
    CMD+=(--case "claude:claude-haiku-4-5-20251001")
    CMD+=(--case "deepseek:deepseek-chat")
    CMD+=(--case "glm:glm-5")
    CMD+=(--case "glm-claude-mode:glm-5")
fi

if ((JSON_OUTPUT)); then
    CMD+=(--json)
fi

if [[ -n "${OUT_PATH}" ]]; then
    CMD+=(--out "${OUT_PATH}")
fi

if [[ ("${SCENARIO}" == "multi_llm_live_cases" || "${SCENARIO}" == "policy_helper_live_cases") && "${TIMEOUT}" == "60" ]]; then
    for i in "${!CMD[@]}"; do
        if [[ "${CMD[$i]}" == "--timeout" && $((i + 1)) -lt ${#CMD[@]} ]]; then
            CMD[$((i + 1))]="240"
            break
        fi
    done
fi

if ((${#EXTRA_ARGS[@]} > 0)); then
    CMD+=("${EXTRA_ARGS[@]}")
fi

exec "${CMD[@]}"
