#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${CLI_ROOT}/.." && pwd)"

HOST="127.0.0.1"
PORT="8787"
PYTHON_EXE="${AGENTHUB_PYTHON:-}"
SHOW_BANNER=0

usage() {
    cat <<'EOF'
Usage: scripts/start_github_gateway.sh [--host HOST] [--port PORT] [--python PATH] [--banner]

Environment:
  GITHUB_WEBHOOK_SECRET   Optional but recommended. If set, webhook signatures are verified.

Examples:
  scripts/start_github_gateway.sh --banner
  scripts/start_github_gateway.sh --host 0.0.0.0 --port 8787
EOF
}

while (($# > 0)); do
    case "$1" in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --python)
            PYTHON_EXE="$2"
            shift 2
            ;;
        --banner)
            SHOW_BANNER=1
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
    exit 1
fi

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if ((SHOW_BANNER)); then
    echo "Starting GitHub Phase 1 gateway server"
    echo "  repo root: ${PROJECT_ROOT}"
    echo "  python: ${PYTHON_EXE}"
    echo "  listen: ${HOST}:${PORT}"
    echo "  webhook path: /webhooks/github"
    if [[ -n "${GITHUB_WEBHOOK_SECRET:-}" ]]; then
        echo "  signature verification: enabled"
    else
        echo "  signature verification: disabled"
    fi
fi

cd "${PROJECT_ROOT}"
exec "${PYTHON_EXE}" -m cli.agent_cli.gateway_api.github_http_server --host "${HOST}" --port "${PORT}"
