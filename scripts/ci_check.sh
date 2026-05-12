#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${AGENTHUB_CI_ROOT:-"$SCRIPT_DIR/.."}" && pwd)"
PYTHON="${PYTHON:-python}"
PYTHON_BIN="$(command -v "$PYTHON" || true)"

export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

log() {
  printf '\n==> %s\n' "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$1" >&2
    exit 127
  fi
}

run_public_tree_scan() {
  log "Scanning public tree for forbidden runtime secrets"
  local findings
  findings="$(
    cd "$ROOT"
    find . \
      -path './.git' -prune -o \
      -path './.venv' -prune -o \
      -path './venv' -prune -o \
      -path './__pycache__' -prune -o \
      -path './.pytest_cache' -prune -o \
      -path './.ruff_cache' -prune -o \
      \( \
        -name '.env' -o \
        -name '.config' -o \
        -name '.agent_cli' -o \
        -name '.agent_cli_legacy' -o \
        -name 'auth.json' -o \
        -name '*.pem' -o \
        -name '*.key' -o \
        -name '*.p12' -o \
        -name '*.pfx' \
      \) -print
  )"
  if [[ -n "$findings" ]]; then
    printf 'public tree contains forbidden secret/config paths:\n%s\n' "$findings" >&2
    exit 1
  fi

  if command -v rg >/dev/null 2>&1; then
    local rg_output
    rg_output="$(
      cd "$ROOT"
      rg -n --hidden --glob '!.git/**' --glob '!**/__pycache__/**' \
        'sk-(proj|svcacct)-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|Authorization:\s*Bearer\s+[A-Za-z0-9._-]{24,}' . || true
    )"
    if [[ -n "$rg_output" ]]; then
      printf 'public tree contains possible embedded secret text:\n%s\n' "$rg_output" >&2
      exit 1
    fi
  fi
}

cleanup_public_tree_runtime_artifacts() {
  log "Cleaning runtime artifacts generated during public tree CI"
  rm -rf \
    "$ROOT/.agent_cli" \
    "$ROOT/.agent_cli_legacy" \
    "$ROOT/.config" \
    "$ROOT/cli/.config"
}

[[ -n "$PYTHON_BIN" ]] || {
  printf 'missing required command: %s\n' "$PYTHON" >&2
  exit 127
}

cd "$ROOT"

if [[ "${AGENTHUB_PUBLIC_TREE_SCAN:-0}" == "1" ]]; then
  run_public_tree_scan
fi

log "CLI import/help smoke"
"$PYTHON_BIN" -m cli.agent_cli --help >/tmp/agenthub_ci_help.txt

log "CLI release and runtime regression tests"
"$PYTHON_BIN" -m pytest -q \
  cli/tests/test_build_release.py \
  cli/tests/test_release_artifact_smoke.py \
  cli/tests/test_paste_pipeline.py \
  cli/tests/test_reference_input_focus_baseline.py \
  cli/tests/test_host_platform.py \
  cli/tests/test_platform_regressions.py \
  cli/tests/test_provider_tool_specs_shared.py \
  cli/tests/test_tool_call_payloads.py \
  cli/tests/test_provider_config_boundary_guard.py \
  cli/tests/test_permission_mode_mapping.py \
  cli/tests/test_provider_catalog_paths_runtime.py \
  cli/tests/test_runtime_paths.py \
  cli/tests/test_provider_paths.py::ProviderPathsTest::test_explicit_provider_home_wins_over_agent_cli_home \
  cli/tests/test_provider_paths.py::ProviderPathsTest::test_explicit_provider_home_avoids_cwd_project_overlay_by_default \
  cli/tests/test_release_version_check.py

if [[ "${AGENTHUB_PUBLIC_TREE_SCAN:-0}" == "1" ]]; then
  cleanup_public_tree_runtime_artifacts
  run_public_tree_scan
else
  log "Public tree secret scan skipped; set AGENTHUB_PUBLIC_TREE_SCAN=1 for publish exports"
fi

log "CI check ok"
