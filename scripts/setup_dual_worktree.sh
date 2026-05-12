#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TARGET_PATH="/mnt/d/project/AgentHub-win"
BRANCH_NAME="win-dev"
REF_ROOT="${HOME}/project/AgentHubRef"
ALLOW_DIRTY=0
INIT_VENV=0
SKIP_REF_LINKS=0
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage: scripts/setup_dual_worktree.sh [options]

Options:
  --target <path>         Windows-visible worktree path. Default: /mnt/d/project/AgentHub-win
  --branch <name>         Branch name for the worktree. Default: win-dev
  --ref-root <path>       External reference root. Default: ~/project/AgentHubRef
  --allow-dirty           Allow creating the worktree even when the main repo has uncommitted changes
  --skip-ref-links        Do not create reference_baseline/openclaw_ref/repo_ref links in the target worktree
  --init-venv             Create .venv in the target worktree and install requirements
  --python <bin>          Python executable for --init-venv. Default: python3
  -h, --help              Show this help text

Notes:
  - Worktree creation is WSL-managed. Do not use this script from native Windows Git.
  - Without --allow-dirty, the script refuses to create a new worktree from a dirty main repo.
  - Uncommitted changes in the main repo are never copied into the new worktree.
EOF
}

fail() {
  echo "[dual-worktree] error: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || fail "--target requires a value"
      TARGET_PATH="$2"
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || fail "--branch requires a value"
      BRANCH_NAME="$2"
      shift 2
      ;;
    --ref-root)
      [[ $# -ge 2 ]] || fail "--ref-root requires a value"
      REF_ROOT="$2"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --skip-ref-links)
      SKIP_REF_LINKS=1
      shift
      ;;
    --init-venv)
      INIT_VENV=1
      shift
      ;;
    --python)
      [[ $# -ge 2 ]] || fail "--python requires a value"
      PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

command -v git >/dev/null 2>&1 || fail "git is required"

if ! git -C "${REPO_ROOT}" rev-parse --show-toplevel >/dev/null 2>&1; then
  fail "repository root is not a Git checkout: ${REPO_ROOT}"
fi

TARGET_PATH="$(realpath -m "${TARGET_PATH}")"
REF_ROOT="$(realpath -m "${REF_ROOT}")"

if [[ "${ALLOW_DIRTY}" -ne 1 ]]; then
  if [[ -n "$(git -C "${REPO_ROOT}" status --short)" ]]; then
    fail "main repo has uncommitted changes; commit/stash first or pass --allow-dirty"
  fi
fi

if [[ -e "${TARGET_PATH}" ]] && ! git -C "${TARGET_PATH}" rev-parse --show-toplevel >/dev/null 2>&1; then
  fail "target path exists but is not a Git worktree: ${TARGET_PATH}"
fi

mkdir -p "$(dirname "${TARGET_PATH}")"

if git -C "${TARGET_PATH}" rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "[dual-worktree] reusing existing worktree: ${TARGET_PATH}"
else
  if git -C "${REPO_ROOT}" show-ref --verify --quiet "refs/heads/${BRANCH_NAME}"; then
    echo "[dual-worktree] creating worktree on existing branch: ${BRANCH_NAME}"
    git -C "${REPO_ROOT}" worktree add "${TARGET_PATH}" "${BRANCH_NAME}"
  else
    echo "[dual-worktree] creating worktree and branch: ${BRANCH_NAME}"
    git -C "${REPO_ROOT}" worktree add -b "${BRANCH_NAME}" "${TARGET_PATH}" HEAD
  fi
fi

create_ref_link() {
  local name="$1"
  local source_path="${REF_ROOT}/${name}"
  local target_link="${TARGET_PATH}/${name}"

  if [[ ! -e "${source_path}" ]]; then
    echo "[dual-worktree] warning: missing reference source: ${source_path}" >&2
    return 0
  fi
  if [[ -L "${target_link}" ]]; then
    local current_target
    current_target="$(readlink "${target_link}")"
    if [[ "${current_target}" == "${source_path}" ]]; then
      echo "[dual-worktree] ref link already exists: ${name}"
      return 0
    fi
    rm -f "${target_link}"
  elif [[ -e "${target_link}" ]]; then
    echo "[dual-worktree] warning: target exists, skip ref link: ${target_link}" >&2
    return 0
  fi

  ln -s "${source_path}" "${target_link}"
  echo "[dual-worktree] linked ${name} -> ${source_path}"
}

if [[ "${SKIP_REF_LINKS}" -ne 1 ]]; then
  create_ref_link "reference_baseline"
  create_ref_link "openclaw_ref"
  create_ref_link "repo_ref"
fi

if [[ "${INIT_VENV}" -eq 1 ]]; then
  command -v "${PYTHON_BIN}" >/dev/null 2>&1 || fail "python executable not found: ${PYTHON_BIN}"
  if [[ -x "${TARGET_PATH}/.venv/bin/python" ]]; then
    echo "[dual-worktree] reusing existing virtualenv: ${TARGET_PATH}/.venv"
  else
    echo "[dual-worktree] creating virtualenv with ${PYTHON_BIN}"
    "${PYTHON_BIN}" -m venv "${TARGET_PATH}/.venv"
  fi
  "${TARGET_PATH}/.venv/bin/pip" install -r "${TARGET_PATH}/requirements.txt" -r "${TARGET_PATH}/requirements-dev.txt"
fi

echo
echo "[dual-worktree] setup complete"
echo "[dual-worktree] repo root:   ${REPO_ROOT}"
echo "[dual-worktree] worktree:    ${TARGET_PATH}"
echo "[dual-worktree] branch:      ${BRANCH_NAME}"
echo "[dual-worktree] ref root:    ${REF_ROOT}"
echo
echo "[dual-worktree] next steps:"
echo "  cd ${TARGET_PATH}"
if [[ "${INIT_VENV}" -eq 1 ]]; then
  echo "  source .venv/bin/activate"
else
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -r requirements.txt -r requirements-dev.txt"
fi
echo "  git status"
echo
echo "[dual-worktree] reminder:"
echo "  - uncommitted changes from the main repo are not copied into the new worktree"
echo "  - keep WSL Git as the owner of this worktree"
