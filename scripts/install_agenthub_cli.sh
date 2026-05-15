#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${AGENTHUB_INSTALL_REPO:-hoteye/AgentHub}"
REQUESTED_VERSION="${AGENTHUB_INSTALL_VERSION:-latest}"
INSTALL_ROOT="${AGENTHUB_INSTALL_DIR:-$HOME/.local/agenthub-cli}"
BIN_DIR="${AGENTHUB_BIN_DIR:-$HOME/.local/bin}"
COMMAND_NAME="${AGENTHUB_COMMAND_NAME:-agenthub}"
INSTALL_TMP_DIR=""

cleanup() {
  if [[ -n "${INSTALL_TMP_DIR:-}" ]]; then
    rm -rf "$INSTALL_TMP_DIR"
  fi
}

trap cleanup EXIT

fail() {
  printf 'agenthub install failed: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

detect_platform_tag() {
  local system machine
  system="$(uname -s | tr '[:upper:]' '[:lower:]')"
  machine="$(uname -m | tr '[:upper:]' '[:lower:]')"
  case "$system" in
    linux*) system="linux" ;;
    darwin*) system="darwin" ;;
    mingw*|msys*|cygwin*) system="windows" ;;
    *) fail "unsupported operating system: $system" ;;
  esac
  case "$machine" in
    x86_64|amd64) machine="x86_64" ;;
    arm64|aarch64) machine="arm64" ;;
    *) fail "unsupported CPU architecture: $machine" ;;
  esac
  printf '%s-%s\n' "$system" "$machine"
}

resolve_release_tag() {
  local requested="$1"
  if [[ "$requested" != "latest" ]]; then
    if [[ "$requested" == cli-v* ]]; then
      printf '%s\n' "$requested"
    else
      printf 'cli-v%s\n' "$requested"
    fi
    return
  fi

  local latest_url effective_url tag
  latest_url="https://github.com/${REPO}/releases/latest"
  effective_url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$latest_url")"
  tag="${effective_url##*/}"
  [[ -n "$tag" && "$tag" != "latest" ]] || fail "could not resolve latest release tag"
  printf '%s\n' "$tag"
}

verify_checksum_if_available() {
  local archive="$1"
  local checksum_url="$2"
  local checksum_file expected actual
  checksum_file="${archive}.sha256"
  if ! curl -fsSL --retry 3 -o "$checksum_file" "$checksum_url"; then
    printf 'checksum unavailable; continuing without sha256 verification\n' >&2
    return
  fi
  if ! command -v sha256sum >/dev/null 2>&1; then
    printf 'sha256sum unavailable; skipping checksum verification\n' >&2
    return
  fi
  expected="$(awk 'NF {print $1; exit}' "$checksum_file")"
  [[ -n "$expected" ]] || fail "empty checksum file: $checksum_url"
  actual="$(sha256sum "$archive" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || fail "sha256 mismatch for $(basename "$archive")"
}

write_agenthub_wrapper() {
  local wrapper="$1"
  local executable="$2"
  {
    printf '#!/usr/bin/env bash\n'
    printf 'set -euo pipefail\n\n'
    printf 'AGENTHUB_CLI_EXECUTABLE=%q\n' "$executable"
    cat <<'WRAPPER'

STARTUP_CWD="$(pwd -P 2>/dev/null || pwd)"
ORIGINAL_ARGS=("$@")

truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

has_explicit_run_mode() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      -h|--help|--headless|--serve|--provider-status|--stdin|--prompt|--prompt=*|--json|--jsonl|--output-format|--output-format=*|--resume|--resume=*|--resume-last|--resume-path|--resume-path=*|resume)
        return 0
        ;;
    esac
  done
  return 1
}

tmux_supported_platform() {
  case "$(uname -s 2>/dev/null || true)" in
    MINGW*|MSYS*|CYGWIN*)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

should_use_tmux_preview_layout() {
  if [[ -n "${AGENTHUB_TMUX_LAYOUT_CHILD:-}" ]]; then
    return 1
  fi
  if truthy "${AGENTHUB_DISABLE_TMUX_LAYOUT:-}"; then
    return 1
  fi
  if has_explicit_run_mode "$@"; then
    return 1
  fi
  if [[ -z "${TMUX:-}" && (! -t 0 || ! -t 1) ]]; then
    return 1
  fi
  if ! tmux_supported_platform; then
    return 1
  fi
  if ! command -v tmux >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

shell_join() {
  local joined=""
  local arg
  for arg in "$@"; do
    if [[ -n "$joined" ]]; then
      joined+=" "
    fi
    joined+="$(printf '%q' "$arg")"
  done
  printf '%s' "$joined"
}

tmux_child_command() {
  local tui_pane="$1"
  local command
  command="cd $(printf '%q' "$STARTUP_CWD") && env"
  command+=" AGENTHUB_TMUX_LAYOUT_CHILD=1"
  command+=" AGENTHUB_TUI_PANE=$(printf '%q' "$tui_pane")"
  command+=" AGENTHUB_PREVIEW_WORKSPACE=$(printf '%q' "${AGENTHUB_PREVIEW_WORKSPACE:-$STARTUP_CWD}")"
  command+=" AGENTHUB_PREVIEW_DISABLED=1"
  command+=" AGENTHUB_STARTUP_CWD=$(printf '%q' "$STARTUP_CWD")"
  command+=" AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE=1"
  command+=" AGENTHUB_STARTUP_CWD_SOURCE=installer_wrapper"
  command+=" AGENTHUB_CLI_EXECUTABLE=$(printf '%q' "$AGENTHUB_CLI_EXECUTABLE")"
  command+=" $(printf '%q' "$AGENTHUB_CLI_EXECUTABLE")"
  if ((${#ORIGINAL_ARGS[@]} > 0)); then
    command+=" $(shell_join "${ORIGINAL_ARGS[@]}")"
  fi
  printf '%s' "$command"
}

start_tmux_preview_layout_in_current_session() {
  local tui_pane
  tui_pane="$(tmux display-message -p "#{pane_id}" 2>/dev/null || printf '%s' "${TMUX_PANE:-}")"
  export AGENTHUB_TMUX_LAYOUT_CHILD=1
  export AGENTHUB_TUI_PANE="$tui_pane"
  export AGENTHUB_PREVIEW_WORKSPACE="${AGENTHUB_PREVIEW_WORKSPACE:-$STARTUP_CWD}"
  export AGENTHUB_PREVIEW_DISABLED=1
  export AGENTHUB_STARTUP_CWD="$STARTUP_CWD"
  export AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE=1
  export AGENTHUB_STARTUP_CWD_SOURCE=installer_wrapper
}

start_tmux_preview_layout_new_session() {
  local session_name="agenthub-$PPID-$$-$(date +%s)"
  local tui_pane
  local child_command
  if ! tmux new-session -d -s "$session_name" -c "$STARTUP_CWD"; then
    return 125
  fi
  tmux set-option -t "$session_name" status off >/dev/null 2>&1 || true
  tmux set-option -t "$session_name" mouse on >/dev/null 2>&1 || true
  tui_pane="$(tmux display-message -p -t "${session_name}:0.0" "#{pane_id}" 2>/dev/null || true)"
  child_command="$(tmux_child_command "$tui_pane")"
  if ! tmux respawn-pane -k -t "${session_name}:0.0" -c "$STARTUP_CWD" -- "$child_command"; then
    tmux kill-session -t "$session_name" >/dev/null 2>&1 || true
    return 125
  fi
  tmux select-pane -t "${session_name}:0.0" >/dev/null 2>&1 || true
  tmux attach-session -t "$session_name"
}

if should_use_tmux_preview_layout "${ORIGINAL_ARGS[@]}"; then
  if [[ -n "${TMUX:-}" ]]; then
    start_tmux_preview_layout_in_current_session
  else
    if start_tmux_preview_layout_new_session; then
      exit 0
    else
      tmux_status=$?
      if ((tmux_status != 125)); then
        exit "$tmux_status"
      fi
    fi
  fi
fi

exec "$AGENTHUB_CLI_EXECUTABLE" "$@"
WRAPPER
  } > "$wrapper"
}

install_bundle() {
  local extract_dir target_dir executable executable_name wrapper
  extract_dir="$1"
  target_dir="$2"

  executable="$(
    find "$extract_dir" -maxdepth 3 \( -name agenthub-cli -o -name agenthub-cli.exe \) -type f \
      | sort \
      | head -n 1
  )"
  [[ -n "$executable" ]] || fail "agenthub-cli executable not found in downloaded archive"
  executable_name="$(basename "$executable")"

  rm -rf "$target_dir"
  mkdir -p "$(dirname "$target_dir")"
  mv "$(dirname "$executable")" "$target_dir"
  chmod +x "$target_dir/$executable_name" 2>/dev/null || true

  mkdir -p "$BIN_DIR"
  wrapper="$BIN_DIR/$COMMAND_NAME"
  write_agenthub_wrapper "$wrapper" "$target_dir/$executable_name"
  chmod +x "$wrapper"
}

main() {
  require_command curl
  require_command awk
  require_command find
  require_command sort
  require_command head

  local platform_tag tag version archive_ext archive_name download_url tmp archive extract_dir target_dir
  platform_tag="$(detect_platform_tag)"
  tag="$(resolve_release_tag "$REQUESTED_VERSION")"
  version="${tag#cli-v}"

  if [[ "$platform_tag" == windows-* ]]; then
    archive_ext="zip"
    require_command unzip
  else
    archive_ext="tar.gz"
    require_command tar
  fi

  archive_name="agenthub-cli-${version}-${platform_tag}.${archive_ext}"
  download_url="https://github.com/${REPO}/releases/download/${tag}/${archive_name}"

  tmp="$(mktemp -d)"
  INSTALL_TMP_DIR="$tmp"
  archive="$tmp/$archive_name"
  extract_dir="$tmp/extract"
  mkdir -p "$extract_dir"

  printf 'Downloading AgentHub %s for %s...\n' "$tag" "$platform_tag"
  curl -fL --retry 3 -o "$archive" "$download_url"
  verify_checksum_if_available "$archive" "${download_url}.sha256"

  if [[ "$archive_ext" == "zip" ]]; then
    unzip -q "$archive" -d "$extract_dir"
  else
    tar -xzf "$archive" -C "$extract_dir"
  fi

  target_dir="${INSTALL_ROOT}/${archive_name%.$archive_ext}"
  if [[ "$archive_ext" == "tar.gz" ]]; then
    target_dir="${INSTALL_ROOT}/${archive_name%.tar.gz}"
  fi
  install_bundle "$extract_dir" "$target_dir"

  printf '\nInstalled AgentHub CLI:\n'
  printf '  %s/%s\n' "$BIN_DIR" "$COMMAND_NAME"
  printf '\nRun:\n'
  printf '  %s\n' "$COMMAND_NAME"
  if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    printf '\nAdd this to your shell profile if needed:\n'
    printf '  export PATH=%q:"$PATH"\n' "$BIN_DIR"
  fi
  printf '\nUninstall:\n'
  printf '  rm -rf %q %q\n' "$INSTALL_ROOT" "$BIN_DIR/$COMMAND_NAME"
}

main "$@"
