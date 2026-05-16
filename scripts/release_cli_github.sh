#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_ROOT="${AGENTHUB_SOURCE_ROOT:-$SOURCE_ROOT_DEFAULT}"
PUBLISH_ROOT="${AGENTHUB_PUBLISH_ROOT:-$(cd "$SOURCE_ROOT/.." && pwd)/agenthubpublish}"
PYTHON="${PYTHON:-python}"
TAG_PREFIX="${AGENTHUB_RELEASE_TAG_PREFIX:-cli-v}"
PUBLIC_REMOTE="${AGENTHUB_PUBLIC_GIT_REMOTE:-origin}"
PUBLIC_BRANCH="${AGENTHUB_PUBLIC_GIT_BRANCH:-main}"
WORKFLOW_NAME="${AGENTHUB_RELEASE_WORKFLOW:-release-executables}"
GITHUB_REPO="${AGENTHUB_GITHUB_REPO:-}"
COMMIT_MESSAGE="${AGENTHUB_PUBLIC_GIT_COMMIT_MESSAGE:-}"

PUSH=0
WATCH=1
SOURCE_TESTS=1
PUBLIC_TESTS=1
FULL_CI=0
LOCAL_VERIFY=0
USE_HEAD_SNAPSHOT=0
ALLOW_EXISTING_TAG=0

TMP_DIRS=()

usage() {
  cat <<'EOF'
Usage:
  scripts/release_cli_github.sh [options]

Default behavior validates and commits the sanitized public tree locally, but does
not push. Add --push to publish to GitHub and trigger cross-platform binaries.

Common:
  scripts/release_cli_github.sh --use-head-snapshot --push --watch

Options:
  --source ROOT             Source AgentHub repo. Default: this repo.
  --publish-root ROOT       Sanitized public repo. Default: ../agenthubpublish.
  --repo OWNER/NAME         GitHub repo for gh release checks. Default: parsed from public remote.
  --remote NAME             Public repo git remote. Default: origin.
  --branch NAME             Public repo branch. Default: main.
  --tag-prefix PREFIX       Release tag prefix. Default: cli-v.
  --workflow NAME           GitHub Actions workflow name. Default: release-executables.
  --push                    Push public branch and tag.
  --no-watch                Do not wait for GitHub Actions after pushing.
  --use-head-snapshot       Release committed HEAD via git archive, ignoring dirty source files.
  --skip-source-tests       Skip local source release tests.
  --skip-public-tests       Skip public tree release tests.
  --full-ci                 Run scripts/ci_check.sh before export.
  --local-verify            Run scripts/release_verify.sh for current platform.
  --allow-existing-tag      Do not fail when the local public tag already exists.
  -h, --help                Show this help.

Required release state:
  - cli/agent_cli/__init__.py contains the target __version__.
  - CHANGELOG.md has a matching section.
  - The release tag is ${TAG_PREFIX}<version>.
  - Cross-platform binaries are built by the release-executables workflow.
EOF
}

log() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf 'release failed: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  for dir in "${TMP_DIRS[@]:-}"; do
    [[ -n "$dir" && -d "$dir" ]] && rm -rf "$dir"
  done
  return 0
}
trap cleanup EXIT

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing required command: $1"
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --source)
        SOURCE_ROOT="$2"
        shift 2
        ;;
      --publish-root)
        PUBLISH_ROOT="$2"
        shift 2
        ;;
      --repo)
        GITHUB_REPO="$2"
        shift 2
        ;;
      --remote)
        PUBLIC_REMOTE="$2"
        shift 2
        ;;
      --branch)
        PUBLIC_BRANCH="$2"
        shift 2
        ;;
      --tag-prefix)
        TAG_PREFIX="$2"
        shift 2
        ;;
      --workflow)
        WORKFLOW_NAME="$2"
        shift 2
        ;;
      --push)
        PUSH=1
        shift
        ;;
      --watch)
        WATCH=1
        shift
        ;;
      --no-watch)
        WATCH=0
        shift
        ;;
      --use-head-snapshot)
        USE_HEAD_SNAPSHOT=1
        shift
        ;;
      --skip-source-tests)
        SOURCE_TESTS=0
        shift
        ;;
      --skip-public-tests)
        PUBLIC_TESTS=0
        shift
        ;;
      --full-ci)
        FULL_CI=1
        shift
        ;;
      --local-verify)
        LOCAL_VERIFY=1
        shift
        ;;
      --allow-existing-tag)
        ALLOW_EXISTING_TAG=1
        shift
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
}

safe_abs_path() {
  local path="$1"
  "$PYTHON_BIN" - "$path" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve())
PY
}

repo_from_remote_url() {
  local url="$1"
  case "$url" in
    https://github.com/*/*.git)
      url="${url#https://github.com/}"
      printf '%s\n' "${url%.git}"
      ;;
    https://github.com/*/*)
      url="${url#https://github.com/}"
      printf '%s\n' "${url%.git}"
      ;;
    git@github.com:*/*.git)
      url="${url#git@github.com:}"
      printf '%s\n' "${url%.git}"
      ;;
    git@github.com:*/*)
      url="${url#git@github.com:}"
      printf '%s\n' "${url%.git}"
      ;;
    *)
      printf '\n'
      ;;
  esac
}

resolve_github_repo() {
  if [[ -n "$GITHUB_REPO" ]]; then
    return
  fi
  local remote_url
  remote_url="$(git -C "$PUBLISH_ROOT" remote get-url "$PUBLIC_REMOTE" 2>/dev/null || true)"
  GITHUB_REPO="$(repo_from_remote_url "$remote_url")"
  [[ -n "$GITHUB_REPO" ]] || fail "could not infer GitHub repo; pass --repo OWNER/NAME"
}

source_is_dirty() {
  [[ -d "$SOURCE_ROOT/.git" ]] || return 1
  [[ -n "$(git -C "$SOURCE_ROOT" status --short)" ]]
}

export_head_snapshot() {
  [[ -d "$SOURCE_ROOT/.git" ]] || fail "--use-head-snapshot requires a git source repo"
  local snapshot
  snapshot="$(mktemp -d /tmp/agenthub-release-source.XXXXXX)"
  TMP_DIRS+=("$snapshot")
  git -C "$SOURCE_ROOT" archive --format=tar HEAD | tar -x -C "$snapshot"
  printf '%s\n' "$snapshot"
}

release_version() {
  local root="$1"
  "$PYTHON_BIN" "$root/cli/scripts/check_release_version.py" \
    --repo-root "$root" \
    --print-version
}

validate_release_version() {
  local root="$1"
  local tag="$2"
  local notes="$3"
  "$PYTHON_BIN" "$root/cli/scripts/check_release_version.py" \
    --repo-root "$root" \
    --ref-name "$tag" \
    --release-notes-out "$notes" \
    --print-version >/dev/null
}

run_source_tests() {
  local root="$1"
  if [[ "$SOURCE_TESTS" != "1" ]]; then
    log "Source tests skipped"
    return
  fi
  if [[ "$FULL_CI" == "1" ]]; then
    log "Run full source CI"
    AGENTHUB_CI_ROOT="$root" AGENTHUB_PUBLIC_TREE_SCAN=0 "$root/scripts/ci_check.sh"
    return
  fi
  log "Run source release tests"
  (
    cd "$root"
    "$PYTHON_BIN" -m pytest -q \
      cli/tests/test_build_release.py \
      cli/tests/test_codex_sidecar_artifact.py \
      cli/tests/test_prepare_codex_sidecar_runtime.py \
      cli/tests/test_release_version_check.py \
      tests/test_update_agenthubpublish.py \
      cli/tests/test_tab_session_manager.py
    "$PYTHON_BIN" scripts/run_governance_guards.py --mode fast
  )
}

run_public_tests() {
  local root="$1"
  local tag="$2"
  if [[ "$PUBLIC_TESTS" != "1" ]]; then
    log "Public tests skipped"
    return
  fi
  log "Run public release tests"
  (
    cd "$root"
    "$PYTHON_BIN" cli/scripts/check_release_version.py \
      --ref-name "$tag" \
      --release-notes-out /tmp/agenthub_cli_release_notes.md \
      --print-version
    "$PYTHON_BIN" -m pytest -q \
      cli/tests/test_release_version_check.py \
      tests/test_update_agenthubpublish.py \
      cli/tests/test_tab_session_manager.py \
      cli/tests/test_build_release.py \
      cli/tests/test_codex_sidecar_artifact.py
  )
}

run_local_verify() {
  local root="$1"
  if [[ "$LOCAL_VERIFY" != "1" ]]; then
    log "Local binary verify skipped; pass --local-verify to build current platform locally"
    return
  fi
  log "Run local release verify"
  AGENTHUB_RELEASE_ROOT="$root" \
  AGENTHUB_RELEASE_REQUIRE_LIVE="${AGENTHUB_RELEASE_REQUIRE_LIVE:-0}" \
    "$root/scripts/release_verify.sh"
}

next_patch_version() {
  local version="$1"
  "$PYTHON_BIN" - "$version" <<'PY'
from __future__ import annotations

import re
import sys

version = str(sys.argv[1] or "").strip()
match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
if not match:
    print("the next release version")
else:
    major, minor, patch = match.groups()
    print(f"{major}.{minor}.{int(patch) + 1}")
PY
}

source_release_commit_for_version() {
  local version="$1"
  [[ -d "$SOURCE_ROOT/.git" ]] || return 0
  git -C "$SOURCE_ROOT" log \
    --fixed-strings \
    --grep "Release AgentHub CLI $version" \
    --format='%H' \
    -n 1
}

release_tag_conflict_message() {
  local version="$1"
  local tag="$2"
  local location="$3"
  local message="$location public tag already exists: $tag"
  local release_commit count short_commit suggested_version

  release_commit="$(source_release_commit_for_version "$version" || true)"
  if [[ -n "$release_commit" ]]; then
    count="$(git -C "$SOURCE_ROOT" rev-list --count "${release_commit}..HEAD" 2>/dev/null || printf '0')"
    short_commit="${release_commit:0:9}"
    if [[ "$count" =~ ^[0-9]+$ ]] && ((count > 0)); then
      suggested_version="$(next_patch_version "$version")"
      message+="
source HEAD has $count commit(s) after source release commit $short_commit for $version.
bump cli/agent_cli/__init__.py and CHANGELOG.md to $suggested_version, then rerun."
    fi
  fi

  printf '%s\n' "$message"
}

check_tag_available() {
  local version="$1"
  local tag="$2"
  if git -C "$PUBLISH_ROOT" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    [[ "$ALLOW_EXISTING_TAG" == "1" ]] || fail "$(release_tag_conflict_message "$version" "$tag" "local")"
  fi
  if [[ "$PUSH" == "1" ]]; then
    if git -C "$PUBLISH_ROOT" ls-remote --exit-code --tags "$PUBLIC_REMOTE" "$tag" >/dev/null 2>&1; then
      fail "$(release_tag_conflict_message "$version" "$tag" "remote")"
    fi
  fi
}

commit_public_tree() {
  local version="$1"
  local tag="$2"
  local message="${COMMIT_MESSAGE:-Sync AgentHub $version public release}"

  log "Check public tree diff"
  git -C "$PUBLISH_ROOT" diff --check

  log "Commit public tree"
  git -C "$PUBLISH_ROOT" add -A
  if git -C "$PUBLISH_ROOT" diff --cached --quiet; then
    log "No public tree changes to commit"
  else
    git -C "$PUBLISH_ROOT" commit -m "$message"
  fi

  if git -C "$PUBLISH_ROOT" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    [[ "$ALLOW_EXISTING_TAG" == "1" ]] || fail "$(release_tag_conflict_message "$version" "$tag" "local")"
  else
    git -C "$PUBLISH_ROOT" tag "$tag"
  fi
}

retry_git_push() {
  local description="$1"
  shift
  local attempt
  for attempt in 1 2 3; do
    if git -C "$PUBLISH_ROOT" push "$@"; then
      return 0
    fi
    log "$description push attempt $attempt failed; retrying"
    sleep $((attempt * 3))
  done
  fail "$description push failed"
}

push_public_tree() {
  local tag="$1"
  if [[ "$PUSH" != "1" ]]; then
    log "Push skipped. To publish, run:"
    printf '  git -C %q push %q HEAD:%q\n' "$PUBLISH_ROOT" "$PUBLIC_REMOTE" "$PUBLIC_BRANCH"
    printf '  git -C %q push %q %q\n' "$PUBLISH_ROOT" "$PUBLIC_REMOTE" "$tag"
    return
  fi
  log "Push public branch"
  retry_git_push "branch" "$PUBLIC_REMOTE" "HEAD:$PUBLIC_BRANCH"
  log "Push release tag"
  retry_git_push "tag" "$PUBLIC_REMOTE" "$tag"
}

find_workflow_run() {
  local tag="$1"
  local runs_json
  runs_json="$(gh run list \
    --repo "$GITHUB_REPO" \
    --workflow "$WORKFLOW_NAME" \
    --limit 20 \
    --json databaseId,headBranch,event,status,displayTitle)"
  RUNS_JSON="$runs_json" "$PYTHON_BIN" - "$tag" <<'PY'
from __future__ import annotations

import json
import os
import sys

tag = sys.argv[1]
runs = json.loads(os.environ.get("RUNS_JSON") or "[]")
for run in runs:
    if run.get("headBranch") == tag:
        print(run.get("databaseId") or "")
        break
PY
}

wait_for_workflow_run() {
  local tag="$1"
  local run_id=""
  local attempt
  for attempt in $(seq 1 60); do
    run_id="$(find_workflow_run "$tag" || true)"
    if [[ -n "$run_id" ]]; then
      printf '%s\n' "$run_id"
      return
    fi
    sleep 5
  done
  fail "timed out waiting for workflow run for $tag"
}

verify_github_release_assets() {
  local version="$1"
  local tag="$2"
  local release_json
  release_json="$(gh release view "$tag" \
    --repo "$GITHUB_REPO" \
    --json tagName,url,assets,isDraft,isPrerelease,publishedAt)"
  RELEASE_JSON="$release_json" "$PYTHON_BIN" - "$version" <<'PY'
from __future__ import annotations

import json
import os
import sys

version = sys.argv[1]
payload = json.loads(os.environ["RELEASE_JSON"])
assets = {item.get("name"): item for item in payload.get("assets", [])}
expected = [
    f"agenthub-cli-{version}-linux-x86_64.tar.gz",
    f"agenthub-cli-{version}-linux-x86_64.tar.gz.sha256",
    f"agenthub-cli-{version}-darwin-arm64.tar.gz",
    f"agenthub-cli-{version}-darwin-arm64.tar.gz.sha256",
    f"agenthub-cli-{version}-windows-x86_64.zip",
    f"agenthub-cli-{version}-windows-x86_64.zip.sha256",
]
missing = [name for name in expected if name not in assets]
if missing:
    raise SystemExit(f"missing release assets: {missing}")
print(payload["url"])
for name in expected:
    item = assets[name]
    print(f"{name}\t{item.get('size', 0)}")
PY
}

watch_release_workflow() {
  local version="$1"
  local tag="$2"
  if [[ "$PUSH" != "1" || "$WATCH" != "1" ]]; then
    log "Workflow watch skipped"
    return
  fi
  require_command gh
  resolve_github_repo
  log "Wait for GitHub Actions workflow"
  local run_id
  run_id="$(wait_for_workflow_run "$tag")"
  gh run watch "$run_id" --repo "$GITHUB_REPO" --exit-status
  log "Verify GitHub Release assets"
  verify_github_release_assets "$version" "$tag"
}

main() {
  parse_args "$@"

  require_command git
  require_command tar
  require_command "$PYTHON"
  PYTHON_BIN="$(command -v "$PYTHON")"

  SOURCE_ROOT="$(safe_abs_path "$SOURCE_ROOT")"
  PUBLISH_ROOT="$(safe_abs_path "$PUBLISH_ROOT")"
  [[ -d "$SOURCE_ROOT/cli/agent_cli" ]] || fail "source does not look like AgentHub: $SOURCE_ROOT"
  [[ -d "$PUBLISH_ROOT/.git" ]] || fail "publish root is not a git repo: $PUBLISH_ROOT"

  local release_source="$SOURCE_ROOT"
  if source_is_dirty; then
    if [[ "$USE_HEAD_SNAPSHOT" != "1" ]]; then
      git -C "$SOURCE_ROOT" status --short >&2
      fail "source tree is dirty; commit changes or pass --use-head-snapshot"
    fi
    log "Export committed HEAD snapshot"
    release_source="$(export_head_snapshot)"
  elif [[ "$USE_HEAD_SNAPSHOT" == "1" ]]; then
    log "Export committed HEAD snapshot"
    release_source="$(export_head_snapshot)"
  fi

  local version tag notes
  version="$(release_version "$release_source")"
  tag="${TAG_PREFIX}${version}"
  notes="/tmp/agenthub_cli_${version}_release_notes.md"

  log "Validate release version"
  validate_release_version "$release_source" "$tag" "$notes"
  check_tag_available "$version" "$tag"
  printf 'version=%s\n' "$version"
  printf 'tag=%s\n' "$tag"
  printf 'release_source=%s\n' "$release_source"
  printf 'publish_root=%s\n' "$PUBLISH_ROOT"

  run_source_tests "$release_source"

  log "Sync sanitized public tree"
  "$PYTHON_BIN" "$release_source/scripts/update_agenthubpublish.py" \
    --source "$release_source" \
    --target "$PUBLISH_ROOT"

  run_public_tests "$PUBLISH_ROOT" "$tag"
  run_local_verify "$PUBLISH_ROOT"
  commit_public_tree "$version" "$tag"
  push_public_tree "$tag"
  watch_release_workflow "$version" "$tag"

  log "Release flow complete"
}

main "$@"
