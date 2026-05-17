#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE="${AGENTHUB_CLEAN_INSTALL_IMAGE:-ubuntu:24.04}"
REPO="${AGENTHUB_INSTALL_REPO:-hoteye/AgentHub}"
VERSION="${AGENTHUB_INSTALL_VERSION:-latest}"
INSTALL_SCRIPT_URL="${AGENTHUB_INSTALL_SCRIPT_URL:-https://raw.githubusercontent.com/${REPO}/main/scripts/install_agenthub_cli.sh}"
COMMAND_NAME="${AGENTHUB_COMMAND_NAME:-agenthub}"
DOCKER="${DOCKER:-docker}"
DOCKER_NETWORK="${AGENTHUB_CLEAN_INSTALL_DOCKER_NETWORK:-}"
INSTALL_TIMEOUT_SECONDS="${AGENTHUB_CLEAN_INSTALL_TIMEOUT_SECONDS:-600}"

usage() {
  cat <<'EOF'
Usage:
  scripts/clean_install_smoke_linux.sh [options]

Runs a fresh Linux install smoke in a clean Docker container. The container uses
the public install script, downloads the requested GitHub Release asset, verifies
the installed command, runs basic no-key smoke checks, and verifies cleanup.

Options:
  --image IMAGE            Docker image. Default: ubuntu:24.04.
  --repo OWNER/NAME        GitHub repo used by install script. Default: hoteye/AgentHub.
  --version TAG_OR_VERSION Release tag/version. Default: latest.
  --install-script URL     Install script URL. Default: repo main branch install script.
  --docker-network NAME    Optional docker --network value, for example host.
  --timeout SECONDS        Container smoke timeout. Default: 600.
  -h, --help               Show this help.

Environment:
  AGENTHUB_CLEAN_INSTALL_IMAGE, AGENTHUB_INSTALL_REPO,
  AGENTHUB_INSTALL_VERSION, AGENTHUB_INSTALL_SCRIPT_URL,
  AGENTHUB_COMMAND_NAME, AGENTHUB_CLEAN_INSTALL_DOCKER_NETWORK,
  AGENTHUB_CLEAN_INSTALL_TIMEOUT_SECONDS, DOCKER
EOF
}

fail() {
  printf 'clean install smoke failed: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --image)
        IMAGE="$2"
        shift 2
        ;;
      --repo)
        REPO="$2"
        shift 2
        ;;
      --version)
        VERSION="$2"
        shift 2
        ;;
      --install-script)
        INSTALL_SCRIPT_URL="$2"
        shift 2
        ;;
      --docker-network)
        DOCKER_NETWORK="$2"
        shift 2
        ;;
      --timeout)
        INSTALL_TIMEOUT_SECONDS="$2"
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
}

main() {
  parse_args "$@"
  require_command "$DOCKER"

  printf 'Running AgentHub clean install smoke\n'
  printf '  image=%s\n' "$IMAGE"
  printf '  repo=%s\n' "$REPO"
  printf '  version=%s\n' "$VERSION"
  printf '  install_script=%s\n' "$INSTALL_SCRIPT_URL"
  printf '  timeout_seconds=%s\n' "$INSTALL_TIMEOUT_SECONDS"

  local docker_args=()
  if [[ -n "$DOCKER_NETWORK" ]]; then
    docker_args+=(--network "$DOCKER_NETWORK")
    printf '  docker_network=%s\n' "$DOCKER_NETWORK"
  fi

  timeout "$INSTALL_TIMEOUT_SECONDS" "$DOCKER" run --rm -i \
    "${docker_args[@]}" \
    --entrypoint bash \
    -e "AGENTHUB_INSTALL_REPO=$REPO" \
    -e "AGENTHUB_INSTALL_VERSION=$VERSION" \
    -e "AGENTHUB_INSTALL_SCRIPT_URL=$INSTALL_SCRIPT_URL" \
    -e "AGENTHUB_COMMAND_NAME=$COMMAND_NAME" \
    "$IMAGE" \
    -s <<'CONTAINER_SMOKE'
set -Eeuo pipefail

fail() {
  printf 'container smoke failed: %s\n' "$*" >&2
  exit 1
}

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git tar gzip

curl -fsSL "$AGENTHUB_INSTALL_SCRIPT_URL" | bash
export PATH="$HOME/.local/bin:$PATH"

command -v "$AGENTHUB_COMMAND_NAME" >/dev/null 2>&1 || fail "installed command is not on PATH"

"$AGENTHUB_COMMAND_NAME" --help >/tmp/agenthub-help.txt
grep -qi "agenthub" /tmp/agenthub-help.txt || fail "help output did not mention AgentHub"

"$AGENTHUB_COMMAND_NAME" --provider-status >/tmp/agenthub-provider-status.txt
grep -q "provider_name=openai" /tmp/agenthub-provider-status.txt || fail "provider status missing bundled openai provider"
grep -q "provider_model=gpt-5.5" /tmp/agenthub-provider-status.txt || fail "provider status missing bundled gpt-5.5 model"
grep -q "model_key=gpt_55" /tmp/agenthub-provider-status.txt || fail "provider status missing bundled gpt_55 alias"
grep -q "provider_base_url=https://codexcs.ysaikeji.cn/v1" /tmp/agenthub-provider-status.txt || fail "provider status missing bundled codexcs base_url"
grep -q "provider_ready=" /tmp/agenthub-provider-status.txt || fail "provider status missing provider_ready"

"$AGENTHUB_COMMAND_NAME" --headless --prompt "/provider verbose" --json >/tmp/agenthub-provider.json
grep -q "provider status" /tmp/agenthub-provider.json || fail "headless provider output missing provider status"
grep -q "provider_model=gpt-5.5" /tmp/agenthub-provider.json || fail "headless provider output missing bundled model"
grep -q "model_key=gpt_55" /tmp/agenthub-provider.json || fail "headless provider output missing bundled alias"

rm -rf "$HOME/.local/agenthub-cli" "$HOME/.local/bin/$AGENTHUB_COMMAND_NAME"
hash -r
if command -v "$AGENTHUB_COMMAND_NAME" >/dev/null 2>&1; then
  fail "command still exists after uninstall cleanup"
fi

printf 'clean install smoke ok\n'
CONTAINER_SMOKE
}

main "$@"
