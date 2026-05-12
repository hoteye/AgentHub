#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REFERENCE_REF_ROOT="${REFERENCE_REF_ROOT:-/home/lyc/project/AgentHubRef/reference_baseline}"
REFERENCE_RS_DIR="${REFERENCE_RS_DIR:-${REFERENCE_REF_ROOT}/reference-rs}"
REFERENCE_BIN="${REFERENCE_BIN:-${REFERENCE_RS_DIR}/target/debug/reference}"
WORKDIR="${WORKDIR:-${CLI_ROOT}}"
PROMPT="北京天气怎么样"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
OUT_DIR=""
SKIP_BUILD=0
RUST_LOG_LEVEL="${RUST_LOG_LEVEL:-info}"
APPROVAL_POLICY="${APPROVAL_POLICY:-never}"
SANDBOX_MODE="${SANDBOX_MODE:-danger-full-access}"

usage() {
    cat <<'EOF'
Usage: scripts/run_reference_baseline_exec.sh [options]

Compile reference_baseline from source and run one non-interactive exec experiment with
JSONL/stdout, stderr logs, and wall time persisted to disk.

Options:
  --prompt TEXT         Prompt to run. Default: 北京天气怎么样
  --out-dir PATH        Output directory. Default: /tmp/reference_baseline_run_<timestamp>
  --workdir PATH        Working directory passed to reference -C. Default: current CLI root
  --skip-build          Reuse existing binary and skip cargo build
  --rust-log LEVEL      RUST_LOG level. Default: info
  --approval POLICY     Approval policy. Default: never
  --sandbox MODE        Sandbox mode. Default: danger-full-access
  --help, -h            Show this help

Environment overrides:
  REFERENCE_REF_ROOT        Default: /home/lyc/project/AgentHubRef/reference_baseline
  REFERENCE_RS_DIR          Default: $REFERENCE_REF_ROOT/reference-rs
  REFERENCE_BIN             Default: $REFERENCE_RS_DIR/target/debug/reference

Outputs in out-dir:
  stdout.jsonl          JSONL event stream
  stderr.log            Rust/runtime logs
  time.txt              /usr/bin/time wall clock output
  meta.txt              Repro metadata and command summary

Examples:
  scripts/run_reference_baseline_exec.sh
  scripts/run_reference_baseline_exec.sh --prompt 'rg怎么用？请示范一下'
  scripts/run_reference_baseline_exec.sh --out-dir /tmp/reference_baseline_weather --prompt '北京天气怎么样'
  scripts/run_reference_baseline_exec.sh --skip-build --prompt '今天几号？'
EOF
}

while (($# > 0)); do
    case "$1" in
        --prompt)
            if (($# < 2)); then
                echo "Missing value for --prompt" >&2
                exit 2
            fi
            PROMPT="$2"
            shift 2
            ;;
        --out-dir)
            if (($# < 2)); then
                echo "Missing value for --out-dir" >&2
                exit 2
            fi
            OUT_DIR="$2"
            shift 2
            ;;
        --workdir)
            if (($# < 2)); then
                echo "Missing value for --workdir" >&2
                exit 2
            fi
            WORKDIR="$2"
            shift 2
            ;;
        --skip-build)
            SKIP_BUILD=1
            shift
            ;;
        --rust-log)
            if (($# < 2)); then
                echo "Missing value for --rust-log" >&2
                exit 2
            fi
            RUST_LOG_LEVEL="$2"
            shift 2
            ;;
        --approval)
            if (($# < 2)); then
                echo "Missing value for --approval" >&2
                exit 2
            fi
            APPROVAL_POLICY="$2"
            shift 2
            ;;
        --sandbox)
            if (($# < 2)); then
                echo "Missing value for --sandbox" >&2
                exit 2
            fi
            SANDBOX_MODE="$2"
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

if [[ -z "${OUT_DIR}" ]]; then
    OUT_DIR="/tmp/reference_baseline_run_${RUN_ID}"
fi

if [[ ! -d "${REFERENCE_RS_DIR}" ]]; then
    echo "reference-rs directory not found: ${REFERENCE_RS_DIR}" >&2
    exit 1
fi

if [[ ! -d "${WORKDIR}" ]]; then
    echo "Workdir not found: ${WORKDIR}" >&2
    exit 1
fi

mkdir -p "${OUT_DIR}"

if ((SKIP_BUILD == 0)); then
    (
        cd "${REFERENCE_RS_DIR}"
        env RULES_RUST_RUNFILES_WORKSPACE_NAME=reference cargo build -p reference-cli --bin reference
    )
fi

if [[ ! -x "${REFERENCE_BIN}" ]]; then
    echo "reference binary not found or not executable: ${REFERENCE_BIN}" >&2
    exit 1
fi

cat > "${OUT_DIR}/meta.txt" <<EOF
run_id=${RUN_ID}
reference_baseline_root=${REFERENCE_REF_ROOT}
reference_rs_dir=${REFERENCE_RS_DIR}
reference_bin=${REFERENCE_BIN}
workdir=${WORKDIR}
prompt=${PROMPT}
approval_policy=${APPROVAL_POLICY}
sandbox_mode=${SANDBOX_MODE}
rust_log=${RUST_LOG_LEVEL}
skip_build=${SKIP_BUILD}
timestamp=$(date '+%Y-%m-%dT%H:%M:%S%z')
EOF

/usr/bin/time -f 'wall_seconds=%e' -o "${OUT_DIR}/time.txt" \
    env RULES_RUST_RUNFILES_WORKSPACE_NAME=reference RUST_LOG="${RUST_LOG_LEVEL}" \
    "${REFERENCE_BIN}" \
    -a "${APPROVAL_POLICY}" \
    -s "${SANDBOX_MODE}" \
    exec --json \
    -C "${WORKDIR}" \
    "${PROMPT}" \
    > "${OUT_DIR}/stdout.jsonl" \
    2> "${OUT_DIR}/stderr.log"

printf 'reference_baseline run complete\n'
printf '  out_dir: %s\n' "${OUT_DIR}"
printf '  time: %s\n' "${OUT_DIR}/time.txt"
printf '  stdout: %s\n' "${OUT_DIR}/stdout.jsonl"
printf '  stderr: %s\n' "${OUT_DIR}/stderr.log"
printf '  meta: %s\n' "${OUT_DIR}/meta.txt"
