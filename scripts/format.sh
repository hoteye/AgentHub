#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="fix"
if [[ "${1:-}" == "--check" ]]; then
  MODE="check"
  shift
fi

TARGETS=("$@")
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  TARGETS=("cli")
fi

if [[ "$MODE" == "check" ]]; then
  ruff check "${TARGETS[@]}"
  black --check "${TARGETS[@]}"
  exit 0
fi

ruff check --fix "${TARGETS[@]}"
black "${TARGETS[@]}"
