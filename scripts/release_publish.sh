#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${AGENTHUB_SOURCE_ROOT:-"$SCRIPT_DIR/.."}" && pwd)"
PYTHON="${PYTHON:-python}"
PYTHON_BIN="$(command -v "$PYTHON" || true)"

DEFAULT_PUBLISH_ROOT="$(cd "$SOURCE_ROOT/.." && pwd)/agenthubpublish"
if [[ -d "$DEFAULT_PUBLISH_ROOT" ]]; then
  VERIFY_ROOT_DEFAULT="$DEFAULT_PUBLISH_ROOT"
else
  VERIFY_ROOT_DEFAULT="$SOURCE_ROOT"
fi

VERIFY_ROOT="${AGENTHUB_PUBLISH_ROOT:-$VERIFY_ROOT_DEFAULT}"
ARTIFACT_DIR="${AGENTHUB_RELEASE_ARTIFACT_DIR:-/tmp/agenthubpublish-release}"
PROVIDER_HOME="${AGENTHUB_RELEASE_PROVIDER_HOME:-}"
UPLOAD_ENABLED="${AGENTHUB_RELEASE_UPLOAD:-0}"
SKIP_CI="${AGENTHUB_RELEASE_SKIP_CI:-0}"
SKIP_SYNC="${AGENTHUB_RELEASE_SKIP_SYNC:-0}"
PUBLIC_GIT_PUSH="${AGENTHUB_PUBLIC_GIT_PUSH:-0}"
PUBLIC_GIT_REMOTE="${AGENTHUB_PUBLIC_GIT_REMOTE:-origin}"
PUBLIC_GIT_BRANCH="${AGENTHUB_PUBLIC_GIT_BRANCH:-main}"
PUBLIC_GIT_COMMIT_MESSAGE="${AGENTHUB_PUBLIC_GIT_COMMIT_MESSAGE:-Sync public AgentHub export}"
PUBLIC_GIT_REQUIRE_CLEAN_SOURCE="${AGENTHUB_PUBLIC_GIT_REQUIRE_CLEAN_SOURCE:-1}"

export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

log() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf 'release publish failed: %s\n' "$*" >&2
  exit 1
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing required command: $1"
  fi
}

latest_archive() {
  "$PYTHON_BIN" - "$ARTIFACT_DIR" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

root = Path(sys.argv[1])
items = [path for pattern in ("*.tar.gz", "*.zip") for path in root.glob(pattern)]
items.sort(key=lambda path: path.stat().st_mtime, reverse=True)
print(items[0] if items else "")
PY
}

upload_archive() {
  local archive="$1"
  local token="${AGENTHUB_UPLOAD_TOKEN:-}"
  local upload_base="${AGENTHUB_UPLOAD_BASE:-https://117.133.98.240:8443/upload}"
  local download_base="${AGENTHUB_DOWNLOAD_BASE:-https://dl.pressget.cn:8443}"
  local upload_prefix="${AGENTHUB_UPLOAD_PREFIX:-agenthub}"
  local upload_path="${AGENTHUB_UPLOAD_PATH:-$upload_prefix/$(basename "$archive")}"
  local nonce

  [[ -n "$token" ]] || fail "AGENTHUB_UPLOAD_TOKEN is required when AGENTHUB_RELEASE_UPLOAD=1"
  require_command curl
  nonce="$(date +%s)-$RANDOM"

  log "Uploading archive to dl.pressget.cn path: $upload_path"
  curl -k -fsS -X PUT "${upload_base%/}/$upload_path?nonce=$nonce" \
    -H "Authorization: Bearer $token" \
    --data-binary "@$archive"
  printf '\nDownload URL: %s/%s\n' "${download_base%/}" "$upload_path"
}

push_public_git_tree() {
  if [[ "$PUBLIC_GIT_PUSH" != "1" ]]; then
    log "Public git push skipped; set AGENTHUB_PUBLIC_GIT_PUSH=1 to commit and push the publish tree"
    return
  fi

  require_command git
  [[ "$VERIFY_ROOT" != "$SOURCE_ROOT" ]] || fail "AGENTHUB_PUBLIC_GIT_PUSH requires a separate AGENTHUB_PUBLISH_ROOT"
  [[ -d "$VERIFY_ROOT/.git" ]] || fail "publish tree is not a git repository: $VERIFY_ROOT"

  if [[ "$PUBLIC_GIT_REQUIRE_CLEAN_SOURCE" == "1" && -d "$SOURCE_ROOT/.git" ]]; then
    local source_status
    source_status="$(git -C "$SOURCE_ROOT" status --short)"
    if [[ -n "$source_status" ]]; then
      printf 'source tree has uncommitted changes:\n%s\n' "$source_status" >&2
      fail "commit or stash source changes before public git push, or set AGENTHUB_PUBLIC_GIT_REQUIRE_CLEAN_SOURCE=0"
    fi
  fi

  git -C "$VERIFY_ROOT" add -A
  local publish_status
  publish_status="$(git -C "$VERIFY_ROOT" status --short)"
  if [[ -n "$publish_status" ]]; then
    log "Commit publish tree changes"
    git -C "$VERIFY_ROOT" commit -m "$PUBLIC_GIT_COMMIT_MESSAGE"
  else
    log "No publish tree changes to commit"
  fi

  git -C "$VERIFY_ROOT" remote get-url "$PUBLIC_GIT_REMOTE" >/dev/null 2>&1 \
    || fail "publish tree remote not found: $PUBLIC_GIT_REMOTE"
  log "Push publish tree to $PUBLIC_GIT_REMOTE/$PUBLIC_GIT_BRANCH"
  git -C "$VERIFY_ROOT" push "$PUBLIC_GIT_REMOTE" "HEAD:$PUBLIC_GIT_BRANCH"
}

[[ -n "$PYTHON_BIN" ]] || fail "missing required command: $PYTHON"

if [[ "$SKIP_CI" != "1" ]]; then
  log "Run source CI check"
  AGENTHUB_CI_ROOT="$SOURCE_ROOT" AGENTHUB_PUBLIC_TREE_SCAN=0 "$SOURCE_ROOT/scripts/ci_check.sh"
else
  log "Source CI check skipped by AGENTHUB_RELEASE_SKIP_CI=1"
fi

if [[ "$SKIP_SYNC" != "1" && "$VERIFY_ROOT" != "$SOURCE_ROOT" ]]; then
  if [[ -f "$SOURCE_ROOT/scripts/update_agenthubpublish.py" ]]; then
    log "Update publish tree"
    "$PYTHON_BIN" "$SOURCE_ROOT/scripts/update_agenthubpublish.py" --source "$SOURCE_ROOT" --target "$VERIFY_ROOT"
  else
    log "Publish sync hook not found; verifying existing publish tree at $VERIFY_ROOT"
  fi
fi

[[ -d "$VERIFY_ROOT" ]] || fail "verify root does not exist: $VERIFY_ROOT"

if [[ -z "$PROVIDER_HOME" && -f "$SOURCE_ROOT/cli/.config/config.toml" && -f "$SOURCE_ROOT/cli/.config/auth.json" ]]; then
  PROVIDER_HOME="$SOURCE_ROOT/cli/.config"
fi

log "Run release verification"
AGENTHUB_RELEASE_ROOT="$VERIFY_ROOT" \
AGENTHUB_RELEASE_ARTIFACT_DIR="$ARTIFACT_DIR" \
AGENTHUB_RELEASE_PROVIDER_HOME="$PROVIDER_HOME" \
AGENTHUB_RELEASE_REQUIRE_LIVE="${AGENTHUB_RELEASE_REQUIRE_LIVE:-1}" \
AGENTHUB_PUBLIC_TREE_SCAN="${AGENTHUB_PUBLIC_TREE_SCAN:-0}" \
  "$SOURCE_ROOT/scripts/release_verify.sh"

push_public_git_tree

if [[ "$UPLOAD_ENABLED" == "1" ]]; then
  archive="$(latest_archive)"
  [[ -n "$archive" && -f "$archive" ]] || fail "no release archive found in $ARTIFACT_DIR"
  upload_archive "$archive"
else
  log "Upload skipped; set AGENTHUB_RELEASE_UPLOAD=1 and AGENTHUB_UPLOAD_TOKEN to publish"
fi

log "Release publish flow ok"
