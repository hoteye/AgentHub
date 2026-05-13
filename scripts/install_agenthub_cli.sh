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
  {
    printf '#!/usr/bin/env bash\n'
    printf 'exec %q "$@"\n' "$target_dir/$executable_name"
  } > "$wrapper"
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
