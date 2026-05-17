#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${AGENTHUB_RELEASE_ROOT:-"$SCRIPT_DIR/.."}" && pwd)"
PYTHON="${PYTHON:-python}"
PYTHON_BIN="$(command -v "$PYTHON" || true)"
MODE="${AGENTHUB_RELEASE_MODE:-onedir}"
ARTIFACT_DIR="$(cd /tmp && pwd)/agenthub-release"
ARTIFACT_DIR="${AGENTHUB_RELEASE_ARTIFACT_DIR:-$ARTIFACT_DIR}"
TIMEOUT_SECONDS="${AGENTHUB_RELEASE_TIMEOUT_SECONDS:-120}"
KEEP_TMP="${AGENTHUB_RELEASE_KEEP_TMP:-0}"
SKIP_LIVE="${AGENTHUB_RELEASE_SKIP_LIVE:-0}"
REQUIRE_LIVE="${AGENTHUB_RELEASE_REQUIRE_LIVE:-0}"
PROVIDER_HOME="${AGENTHUB_RELEASE_PROVIDER_HOME:-}"
CODEX_SIDECAR_BIN="${AGENTHUB_RELEASE_CODEX_SIDECAR_BIN:-}"
CODEX_SIDECAR_RUNTIME_ROOT="${AGENTHUB_RELEASE_CODEX_SIDECAR_RUNTIME_ROOT:-}"
CODEX_SIDECAR_RUNTIME_BUNDLE="${AGENTHUB_RELEASE_CODEX_SIDECAR_RUNTIME_BUNDLE:-}"
CODEX_SIDECAR_VERSION="${AGENTHUB_RELEASE_CODEX_SIDECAR_VERSION:-}"
CODEX_SIDECAR_SOURCE_REVISION="${AGENTHUB_RELEASE_CODEX_SIDECAR_SOURCE_REVISION:-}"

export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

log() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf 'release verify failed: %s\n' "$*" >&2
  exit 1
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing required command: $1"
  fi
}

sha256_file() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file"
  else
    fail "missing sha256sum or shasum"
  fi
}

run_tui_probe() {
  local exe="$1"
  local work="$2"
  local home="$3"
  local state="$4"
  local provider="$5"
  local expect_welcome="$6"
  local output="$7"

  AGENTHUB_RELEASE_EXE="$exe" \
  AGENTHUB_RELEASE_WORK="$work" \
  AGENTHUB_RELEASE_HOME="$home" \
  AGENTHUB_RELEASE_STATE="$state" \
  AGENTHUB_RELEASE_PROVIDER="$provider" \
  AGENTHUB_RELEASE_EXPECT_WELCOME="$expect_welcome" \
  AGENTHUB_RELEASE_TUI_OUTPUT="$output" \
  "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import pty
import select
import signal
import struct
import termios
import time

exe = os.environ["AGENTHUB_RELEASE_EXE"]
work = Path(os.environ["AGENTHUB_RELEASE_WORK"])
home = Path(os.environ["AGENTHUB_RELEASE_HOME"])
state = Path(os.environ["AGENTHUB_RELEASE_STATE"])
provider = os.environ.get("AGENTHUB_RELEASE_PROVIDER", "")
expect_welcome = os.environ["AGENTHUB_RELEASE_EXPECT_WELCOME"] == "1"
output = Path(os.environ["AGENTHUB_RELEASE_TUI_OUTPUT"])

for path in (work, home, state):
    path.mkdir(parents=True, exist_ok=True)

env = {
    "PATH": "/usr/bin:/bin",
    "HOME": str(home),
    "AGENT_CLI_HOME": str(state),
    "TERM": "xterm-256color",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONUTF8": "1",
    "COLUMNS": "120",
    "LINES": "40",
}
if provider:
    env["AGENTHUB_PROVIDER_HOME"] = provider

pid, fd = pty.fork()
if pid == 0:
    os.chdir(work)
    os.execve(exe, [exe], env)

fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
os.set_blocking(fd, False)
chunks: list[bytes] = []
end = time.time() + 7
try:
    while time.time() < end:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if fd not in ready:
            continue
        try:
            data = os.read(fd, 65536)
        except (BlockingIOError, OSError):
            break
        if not data:
            break
        chunks.append(data)
finally:
    try:
        os.kill(pid, signal.SIGINT)
    except ProcessLookupError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass

raw = b"".join(chunks)
output.write_bytes(raw)

if expect_welcome:
    required = (b"Welcome to AgentHub", b"No provider configured", b"API key", b"openai")
    missing = [item.decode("utf-8", errors="ignore") for item in required if raw.find(item) < 0]
    if missing:
        raise SystemExit(f"welcome probe missing tokens: {missing}; raw={output}")
else:
    if raw.find(b"Welcome to AgentHub") >= 0:
        raise SystemExit(f"configured TUI unexpectedly showed welcome; raw={output}")
    required = (b"openai", b"gpt-5.5", b"xhigh")
    missing = [item.decode("utf-8", errors="ignore") for item in required if raw.find(item) < 0]
    if missing:
        raise SystemExit(f"configured TUI missing provider tokens: {missing}; raw={output}")
PY
}

assert_json_response_ok() {
  local json_path="$1"
  local expected_provider="$2"
  local expected_base_url="$3"
  "$PYTHON_BIN" - "$json_path" "$expected_provider" "$expected_base_url" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_provider = sys.argv[2]
expected_base_url = sys.argv[3]
payload = json.loads(path.read_text(encoding="utf-8"))
assistant_text = str(payload.get("assistant_text") or "").strip()
status = payload.get("status") or {}
provider = str(status.get("provider_name") or "")
base_url = str(status.get("provider_base_url") or "")
ready = str(status.get("provider_ready") or "").lower()

if assistant_text != "OK":
    raise SystemExit(f"unexpected assistant_text={assistant_text!r} in {path}")
if provider != expected_provider:
    raise SystemExit(f"unexpected provider={provider!r}, expected={expected_provider!r}")
if base_url != expected_base_url:
    raise SystemExit(f"unexpected base_url={base_url!r}, expected={expected_base_url!r}")
if ready != "true":
    raise SystemExit(f"provider_ready is not true: {ready!r}")
PY
}

[[ -n "$PYTHON_BIN" ]] || fail "missing required command: $PYTHON"
require_command tar

cd "$ROOT"

if [[ -z "$PROVIDER_HOME" && -f "$ROOT/cli/.config/config.toml" && -f "$ROOT/cli/.config/auth.json" ]]; then
  PROVIDER_HOME="$ROOT/cli/.config"
fi

VERIFY_ROOT="$(mktemp -d /tmp/agenthub-release-verify.XXXXXX)"
cleanup() {
  local status=$?
  if [[ "$status" -eq 0 && "$KEEP_TMP" != "1" ]]; then
    rm -rf "$VERIFY_ROOT"
  else
    printf 'release verify workspace kept: %s\n' "$VERIFY_ROOT" >&2
  fi
}
trap cleanup EXIT

mkdir -p "$ARTIFACT_DIR"

log "Build release artifact"
build_args=(cli/scripts/build_release.py --clean --mode "$MODE" --artifact-dir "$ARTIFACT_DIR")
if [[ -n "$CODEX_SIDECAR_BIN" ]]; then
  build_args+=(--codex-sidecar-bin "$CODEX_SIDECAR_BIN")
fi
if [[ -n "$CODEX_SIDECAR_RUNTIME_ROOT" ]]; then
  build_args+=(--codex-sidecar-runtime-root "$CODEX_SIDECAR_RUNTIME_ROOT")
fi
if [[ -n "$CODEX_SIDECAR_RUNTIME_BUNDLE" ]]; then
  build_args+=(--codex-sidecar-runtime-bundle "$CODEX_SIDECAR_RUNTIME_BUNDLE")
fi
if [[ -n "$CODEX_SIDECAR_VERSION" ]]; then
  build_args+=(--codex-sidecar-version "$CODEX_SIDECAR_VERSION")
fi
if [[ -n "$CODEX_SIDECAR_SOURCE_REVISION" ]]; then
  build_args+=(--codex-sidecar-source-revision "$CODEX_SIDECAR_SOURCE_REVISION")
fi
build_output="$("$PYTHON_BIN" "${build_args[@]}")"
printf '%s\n' "$build_output"
ARCHIVE="$(printf '%s\n' "$build_output" | tail -n 1)"
[[ -f "$ARCHIVE" ]] || fail "build did not produce archive: $ARCHIVE"

log "Archive checksum"
sha256_file "$ARCHIVE"

log "Extract release artifact"
INSTALL_DIR="$VERIFY_ROOT/install"
mkdir -p "$INSTALL_DIR"
case "$ARCHIVE" in
  *.tar.gz) tar -xzf "$ARCHIVE" -C "$INSTALL_DIR" ;;
  *.zip)
    require_command unzip
    unzip -q "$ARCHIVE" -d "$INSTALL_DIR"
    ;;
  *) fail "unsupported archive type: $ARCHIVE" ;;
esac

EXE="$(find "$INSTALL_DIR" -maxdepth 3 \( -name agenthub-cli -o -name agenthub-cli.exe \) -type f | head -n 1)"
[[ -n "$EXE" ]] || fail "release executable not found under $INSTALL_DIR"
BUNDLE_ROOT="$(dirname "$EXE")"

log "Check bundled runtime assets"
find "$BUNDLE_ROOT" -path '*/interaction_profiles/schema/interaction_profile.schema.json' -type f | grep -q . \
  || fail "missing bundled interaction profile schema"
find "$BUNDLE_ROOT" -path '*/config/provider_catalog.toml' -type f | grep -q . \
  || fail "missing bundled provider catalog"
[[ -f "$BUNDLE_ROOT/_internal/LICENSE" || -f "$BUNDLE_ROOT/LICENSE" ]] || fail "missing bundled Apache-2.0 LICENSE"

log "Check public release boundary"
if find "$BUNDLE_ROOT" -path '*/plugins/psbc_policy*' -print -quit | grep -q .; then
  fail "release bundle contains commercial psbc_policy plugin"
fi
if find "$BUNDLE_ROOT" -path '*/.config*' -print -quit | grep -q .; then
  fail "release bundle contains private .config data"
fi

log "Release help smoke"
"$EXE" --help >/tmp/agenthub_release_help.txt
grep -q "Reference-like CLI" /tmp/agenthub_release_help.txt || fail "help smoke missing expected text"

log "Release version smoke"
"$EXE" --version >/tmp/agenthub_release_version.txt
grep -q "^agenthub-cli " /tmp/agenthub_release_version.txt || fail "version smoke missing expected text"

log "Clean provider catalog smoke"
env -i \
  PATH="/usr/bin:/bin" \
  HOME="$VERIFY_ROOT/catalog-home" \
  AGENT_CLI_HOME="$VERIFY_ROOT/catalog-state" \
  TERM="xterm-256color" \
  LANG="C.UTF-8" \
  LC_ALL="C.UTF-8" \
  PYTHONUTF8="1" \
  "$EXE" --provider-status >"$VERIFY_ROOT/clean-provider-status.txt"
grep -q "provider_name=openai" "$VERIFY_ROOT/clean-provider-status.txt" || fail "clean provider status missing bundled openai provider"
grep -q "provider_model=gpt-5.5" "$VERIFY_ROOT/clean-provider-status.txt" || fail "clean provider status missing bundled gpt-5.5 model"
grep -q "model_key=gpt_55" "$VERIFY_ROOT/clean-provider-status.txt" || fail "clean provider status missing bundled gpt_55 alias"
grep -q "provider_base_url=https://codexcs.ysaikeji.cn/v1" "$VERIFY_ROOT/clean-provider-status.txt" || fail "clean provider status missing bundled codexcs base_url"

log "Empty install TUI should show Welcome"
run_tui_probe \
  "$EXE" \
  "$VERIFY_ROOT/empty-workspace" \
  "$VERIFY_ROOT/empty-home" \
  "$VERIFY_ROOT/empty-state" \
  "" \
  "1" \
  "$VERIFY_ROOT/empty-tui.raw"
[[ ! -e "$BUNDLE_ROOT/.config" ]] || fail "release bundle wrote .config into install directory"

if [[ "$REQUIRE_LIVE" != "1" ]]; then
  log "Live provider checks skipped by AGENTHUB_RELEASE_REQUIRE_LIVE=$REQUIRE_LIVE"
  log "Release verify ok"
  printf 'artifact=%s\n' "$ARCHIVE"
  exit 0
fi

if [[ -z "$PROVIDER_HOME" || ! -f "$PROVIDER_HOME/config.toml" || ! -f "$PROVIDER_HOME/auth.json" ]]; then
  fail "live provider checks required but AGENTHUB_RELEASE_PROVIDER_HOME is missing config.toml/auth.json"
fi

if [[ "$SKIP_LIVE" == "1" ]]; then
  log "Live provider checks skipped by AGENTHUB_RELEASE_SKIP_LIVE=1"
  log "Release verify ok"
  printf 'artifact=%s\n' "$ARCHIVE"
  exit 0
fi

log "Configured provider status: OpenAI/GAC"
OPENAI_STATUS="$VERIFY_ROOT/openai-provider-status.txt"
cd "$VERIFY_ROOT/empty-workspace"
env -i \
  PATH="/usr/bin:/bin" \
  HOME="$VERIFY_ROOT/configured-home" \
  AGENT_CLI_HOME="$VERIFY_ROOT/configured-state" \
  AGENTHUB_PROVIDER_HOME="$PROVIDER_HOME" \
  TERM="xterm-256color" \
  LANG="C.UTF-8" \
  LC_ALL="C.UTF-8" \
  PYTHONUTF8="1" \
  "$EXE" --provider-status >"$OPENAI_STATUS"
grep -q "provider_name=openai" "$OPENAI_STATUS" || fail "OpenAI provider status did not select openai"
grep -q "provider_ready=true" "$OPENAI_STATUS" || fail "OpenAI provider is not ready"
grep -q "provider_base_url=https://gaccode.com/codex/v1" "$OPENAI_STATUS" || fail "OpenAI base_url mismatch"

log "Configured provider status: Anthropic/GAC"
ANTHROPIC_STATUS="$VERIFY_ROOT/anthropic-provider-status.txt"
env -i \
  PATH="/usr/bin:/bin" \
  HOME="$VERIFY_ROOT/configured-home" \
  AGENT_CLI_HOME="$VERIFY_ROOT/configured-state" \
  AGENTHUB_PROVIDER_HOME="$PROVIDER_HOME" \
  AGENT_CLI_PROVIDER="anthropic" \
  TERM="xterm-256color" \
  LANG="C.UTF-8" \
  LC_ALL="C.UTF-8" \
  PYTHONUTF8="1" \
  "$EXE" --provider-status >"$ANTHROPIC_STATUS"
grep -q "provider_name=anthropic" "$ANTHROPIC_STATUS" || fail "Anthropic provider status did not select anthropic"
grep -q "provider_ready=true" "$ANTHROPIC_STATUS" || fail "Anthropic provider is not ready"
grep -q "provider_base_url=https://gaccode.com/claudecode" "$ANTHROPIC_STATUS" || fail "Anthropic base_url mismatch"

log "Configured TUI should not show Welcome"
run_tui_probe \
  "$EXE" \
  "$VERIFY_ROOT/configured-workspace" \
  "$VERIFY_ROOT/configured-home-tui" \
  "$VERIFY_ROOT/configured-state-tui" \
  "$PROVIDER_HOME" \
  "0" \
  "$VERIFY_ROOT/configured-tui.raw"
[[ ! -e "$BUNDLE_ROOT/.config" ]] || fail "configured TUI wrote .config into install directory"

log "Live headless: OpenAI/GAC"
OPENAI_JSON="$VERIFY_ROOT/openai-headless.json"
env -i \
  PATH="/usr/bin:/bin" \
  HOME="$VERIFY_ROOT/configured-home" \
  AGENT_CLI_HOME="$VERIFY_ROOT/configured-state" \
  AGENTHUB_PROVIDER_HOME="$PROVIDER_HOME" \
  TERM="xterm-256color" \
  LANG="C.UTF-8" \
  LC_ALL="C.UTF-8" \
  PYTHONUTF8="1" \
  "$PYTHON_BIN" - "$EXE" "$TIMEOUT_SECONDS" "$OPENAI_JSON" <<'PY'
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

exe, timeout_seconds, output = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
result = subprocess.run(
    [exe, "--headless", "--output-format", "json", "--prompt", "只回复 OK"],
    check=False,
    capture_output=True,
    text=True,
    encoding="utf-8",
    timeout=timeout_seconds,
    env=dict(os.environ),
)
output.write_text(result.stdout, encoding="utf-8")
if result.returncode != 0:
    raise SystemExit(f"OpenAI headless failed: {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}")
PY
assert_json_response_ok "$OPENAI_JSON" "openai" "https://gaccode.com/codex/v1"

log "Live headless: Anthropic/GAC"
ANTHROPIC_JSON="$VERIFY_ROOT/anthropic-headless.json"
env -i \
  PATH="/usr/bin:/bin" \
  HOME="$VERIFY_ROOT/configured-home" \
  AGENT_CLI_HOME="$VERIFY_ROOT/configured-state" \
  AGENTHUB_PROVIDER_HOME="$PROVIDER_HOME" \
  AGENT_CLI_PROVIDER="anthropic" \
  TERM="xterm-256color" \
  LANG="C.UTF-8" \
  LC_ALL="C.UTF-8" \
  PYTHONUTF8="1" \
  "$PYTHON_BIN" - "$EXE" "$TIMEOUT_SECONDS" "$ANTHROPIC_JSON" <<'PY'
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

exe, timeout_seconds, output = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
result = subprocess.run(
    [exe, "--headless", "--output-format", "json", "--prompt", "只回复 OK"],
    check=False,
    capture_output=True,
    text=True,
    encoding="utf-8",
    timeout=timeout_seconds,
    env=dict(os.environ),
)
output.write_text(result.stdout, encoding="utf-8")
if result.returncode != 0:
    raise SystemExit(f"Anthropic headless failed: {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}")
PY
assert_json_response_ok "$ANTHROPIC_JSON" "anthropic" "https://gaccode.com/claudecode"

log "Release verify ok"
printf 'artifact=%s\n' "$ARCHIVE"
