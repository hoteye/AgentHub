#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${CLI_ROOT}/.." && pwd)"
STARTUP_CWD="$(pwd -P 2>/dev/null || pwd)"
ORIGINAL_ARGS=("$@")

SHOW_BANNER=0
PYTHON_EXE="${AGENTHUB_PYTHON:-}"
CLI_EXECUTABLE="${AGENTHUB_CLI_EXECUTABLE:-}"
DEFAULT_SANDBOX_MODE="${AGENTHUB_DEFAULT_SANDBOX_MODE:-workspace-write}"
DEFAULT_APPROVAL_POLICY="${AGENTHUB_DEFAULT_APPROVAL_POLICY:-on-request}"
DEFAULT_DEBUG_LOG_DIR="${AGENTHUB_DEFAULT_DEBUG_LOG_DIR:-${CLI_ROOT}/logs/live_debug}"
START_DEBUG_LOG="${AGENTHUB_START_DEBUG_LOG:-/tmp/agenthub-start-debug.log}"

has_explicit_run_mode() {
    local args=("$@")
    local i=0
    while ((i < ${#args[@]})); do
        case "${args[$i]}" in
            --headless|--serve|--resume|--resume-last|--resume-path|--provider-status|--stdin|--prompt|--json|--jsonl|--output-format|resume)
                return 0
                ;;
        esac
        ((i += 1))
    done
    return 1
}

has_permission_mode_arg() {
    local args=("$@")
    local i=0
    while ((i < ${#args[@]})); do
        case "${args[$i]}" in
            --permission-mode|--permission-mode=*)
                return 0
                ;;
        esac
        ((i += 1))
    done
    return 1
}

_process_field() {
    local field="${1:-}"
    ps -o "${field}=" -p "$$" 2>/dev/null | tr -d '[:space:]'
}

debug_log() {
    local message="${1:-}"
    {
        printf '[%s] pid=%s ppid=%s pgid=%s sid=%s tpgid=%s tty=%s shell_flags=%s %s\n' \
            "$(date '+%Y-%m-%dT%H:%M:%S%z')" \
            "$$" \
            "${PPID:-}" \
            "$(_process_field pgid)" \
            "$(_process_field sid)" \
            "$(_process_field tpgid)" \
            "$(tty 2>/dev/null || printf 'not-a-tty')" \
            "$-" \
            "${message}"
    } >> "${START_DEBUG_LOG}" 2>/dev/null || true
}

debug_snapshot() {
    {
        printf '[%s] snapshot startup_cwd=%s cli_root=%s python=%s textual_allow_signals=%s args=%s\n' \
            "$(date '+%Y-%m-%dT%H:%M:%S%z')" \
            "${STARTUP_CWD}" \
            "${CLI_ROOT}" \
            "${PYTHON_EXE:-}" \
            "${TEXTUAL_ALLOW_SIGNALS-}" \
            "$*"
        echo "--- trap -p ---"
        trap -p EXIT INT TERM HUP TSTP TTIN TTOU 2>/dev/null || true
        echo "--- ps ---"
        ps -o pid=,ppid=,pgid=,sid=,tpgid=,stat=,tty=,cmd= -p "$$" 2>/dev/null || true
        if [[ -t 0 ]] && command -v stty >/dev/null 2>&1; then
            echo "--- stty -a ---"
            stty -a 2>/dev/null || true
        fi
    } >> "${START_DEBUG_LOG}" 2>/dev/null || true
}

tmux_layout_disabled() {
    case "${AGENTHUB_DISABLE_TMUX_LAYOUT:-}" in
        1|true|TRUE|yes|YES|on|ON)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

git_install_hint() {
    printf '%s\n' \
        "AgentHub requires git, but git was not found in PATH." \
        "Install git and run AgentHub again." \
        "" \
        "Ubuntu/Debian: sudo apt install git" \
        "Fedora: sudo dnf install git" \
        "Arch: sudo pacman -S git" \
        "macOS: brew install git"
}

tmux_install_hint() {
    printf '%s\n' \
        "AgentHub file/URL preview panes need tmux, but tmux was not found in PATH." \
        "Install tmux to enable the preview pane. Continuing without the preview pane." \
        "" \
        "Ubuntu/Debian: sudo apt install tmux" \
        "Fedora: sudo dnf install tmux" \
        "Arch: sudo pacman -S tmux" \
        "macOS: brew install tmux"
}

require_git_dependency() {
    if command -v git >/dev/null 2>&1; then
        return 0
    fi
    git_install_hint >&2
    exit 1
}

should_warn_missing_tmux_preview_dependency() {
    if [[ -n "${AGENTHUB_TMUX_LAYOUT_CHILD:-}" ]]; then
        return 1
    fi
    if tmux_layout_disabled; then
        return 1
    fi
    if [[ -z "${TMUX:-}" && (! -t 0 || ! -t 1) ]]; then
        return 1
    fi
    if has_explicit_run_mode "$@"; then
        return 1
    fi
    if command -v tmux >/dev/null 2>&1; then
        return 1
    fi
    return 0
}

warn_missing_tmux_preview_dependency() {
    if should_warn_missing_tmux_preview_dependency "$@"; then
        export AGENTHUB_TMUX_DEPENDENCY_CHECKED=1
        tmux_install_hint >&2
    fi
}

should_use_tmux_preview_layout() {
    if [[ -n "${AGENTHUB_TMUX_LAYOUT_CHILD:-}" ]]; then
        return 1
    fi
    if tmux_layout_disabled; then
        return 1
    fi
    if [[ -z "${TMUX:-}" && (! -t 0 || ! -t 1) ]]; then
        return 1
    fi
    if has_explicit_run_mode "$@"; then
        return 1
    fi
    if ! command -v tmux >/dev/null 2>&1; then
        return 1
    fi
    return 0
}

tmux_preview_ready_command() {
    local shell_bin="${SHELL:-/bin/bash}"
    printf "printf 'AgentHub Preview ready\\nClick a file path or URL in the left Transcript to open it here.\\n'; exec %q" "${shell_bin}"
}

shell_join() {
    local joined=""
    local arg
    for arg in "$@"; do
        if [[ -n "${joined}" ]]; then
            joined+=" "
        fi
        joined+="$(printf '%q' "${arg}")"
    done
    printf '%s' "${joined}"
}

tmux_child_command() {
    local preview_pane="$1"
    local tui_pane="${2:-}"
    local script_path="${SCRIPT_DIR}/start_agent_cli.sh"
    local command
    command="cd $(printf '%q' "${STARTUP_CWD}") && env"
    command+=" AGENTHUB_TMUX_LAYOUT_CHILD=1"
    command+=" AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW=1"
    command+=" AGENTHUB_PREVIEW_PANE=$(printf '%q' "${preview_pane}")"
    command+=" AGENTHUB_PREVIEW_DISABLED=1"
    if [[ -n "${tui_pane}" ]]; then
        command+=" AGENTHUB_TUI_PANE=$(printf '%q' "${tui_pane}")"
    fi
    command+=" AGENTHUB_PREVIEW_WORKSPACE=$(printf '%q' "${STARTUP_CWD}")"
    command+=" AGENTHUB_STARTUP_CWD=$(printf '%q' "${STARTUP_CWD}")"
    command+=" AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE=1"
    command+=" AGENTHUB_STARTUP_CWD_SOURCE=launcher"
    if [[ -n "${CLI_EXECUTABLE}" ]]; then
        command+=" AGENTHUB_CLI_EXECUTABLE=$(printf '%q' "${CLI_EXECUTABLE}")"
    else
        command+=" AGENTHUB_PYTHON=$(printf '%q' "${PYTHON_EXE}")"
    fi
    if [[ -n "${AGENTHUB_TMUX_MOUSE_RESTORE_FILE:-}" ]]; then
        command+=" AGENTHUB_TMUX_MOUSE_RESTORE_FILE=$(printf '%q' "${AGENTHUB_TMUX_MOUSE_RESTORE_FILE}")"
    fi
    command+=" $(printf '%q' "${script_path}")"
    if ((${#ORIGINAL_ARGS[@]} > 0)); then
        command+=" $(shell_join "${ORIGINAL_ARGS[@]}")"
    fi
    printf '%s' "${command}"
}

save_tmux_key_binding() {
    local table="$1"
    local key="$2"
    if ! tmux list-keys -T "${table}" "${key}" 2>/dev/null; then
        printf 'unbind-key -T %s %s\n' "${table}" "${key}"
    fi
}

configure_tmux_preview_mouse_bindings() {
    local session_name="$1"
    local preview_pane="${2:-}"
    local copy_command="tmux load-buffer -w -"
    local safe_session_name
    local restore_file
    if [[ -z "${session_name}" ]]; then
        return 0
    fi
    safe_session_name="$(printf '%s' "${session_name}" | tr -c '[:alnum:]_.-' '_')"
    restore_file="/tmp/agenthub-tmux-${safe_session_name}-mouse-restore.conf"
    {
        save_tmux_key_binding root MouseDown3Pane
        save_tmux_key_binding root M-MouseDown3Pane
        save_tmux_key_binding root MouseDrag1Pane
        save_tmux_key_binding copy-mode MouseDragEnd1Pane
        save_tmux_key_binding copy-mode-vi MouseDragEnd1Pane
    } > "${restore_file}" 2>/dev/null || true
    export AGENTHUB_TMUX_MOUSE_RESTORE_FILE="${restore_file}"
    if [[ -n "${preview_pane}" ]]; then
        tmux set-option -t "${session_name}" -q @agenthub_preview_pane "${preview_pane}" >/dev/null 2>&1 || true
    fi
    tmux bind-key -T root MouseDown3Pane select-pane -t = '\;' send-keys -M >/dev/null 2>&1 || true
    tmux bind-key -T root M-MouseDown3Pane select-pane -t = '\;' send-keys -M >/dev/null 2>&1 || true
    tmux bind-key -T root MouseDrag1Pane if-shell -F -t = \
        '#{&&:#{@agenthub_preview_pane},#{==:#{pane_id},#{@agenthub_preview_pane}}}' \
        'copy-mode -t = -M' \
        'if-shell -F -t = "#{||:#{pane_in_mode},#{mouse_any_flag}}" "send-keys -M" "copy-mode -t = -M"' \
        >/dev/null 2>&1 || true
    tmux bind-key -T copy-mode MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "${copy_command}" \
        >/dev/null 2>&1 || true
    tmux bind-key -T copy-mode-vi MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "${copy_command}" \
        >/dev/null 2>&1 || true
    tmux set-hook -t "${session_name}" session-closed \
        "run-shell 'tmux source-file ${restore_file} >/dev/null 2>&1 || true; rm -f ${restore_file}'" \
        >/dev/null 2>&1 || true
}

restore_tmux_preview_mouse_bindings() {
    local restore_file="${AGENTHUB_TMUX_MOUSE_RESTORE_FILE:-}"
    if [[ -z "${restore_file}" ]]; then
        return 0
    fi
    if command -v tmux >/dev/null 2>&1; then
        tmux source-file "${restore_file}" >/dev/null 2>&1 || true
    fi
    rm -f "${restore_file}" >/dev/null 2>&1 || true
}

start_tmux_preview_layout_in_current_session() {
    local tui_pane
    tui_pane="$(tmux display-message -p "#{pane_id}" 2>/dev/null || printf '%s' "${TMUX_PANE:-}")"
    export AGENTHUB_TMUX_LAYOUT_CHILD=1
    export AGENTHUB_TUI_PANE="${tui_pane}"
    export AGENTHUB_PREVIEW_WORKSPACE="${AGENTHUB_PREVIEW_WORKSPACE:-${STARTUP_CWD}}"
    export AGENTHUB_PREVIEW_DISABLED=1
    debug_log "tmux.layout.current no_preview tui_pane=${tui_pane}"
    return 0
}

start_tmux_preview_layout_new_session() {
    local session_name="agenthub-$PPID-$$-$(date +%s)"
    local tui_pane
    local child_command
    if ! tmux new-session -d -s "${session_name}" -c "${STARTUP_CWD}"; then
        debug_log "tmux.layout.new_session.failed session=${session_name}"
        return 125
    fi
    tmux set-option -t "${session_name}" status off >/dev/null 2>&1 || true
    tmux set-option -t "${session_name}" mouse on >/dev/null 2>&1 || true
    tui_pane="$(tmux display-message -p -t "${session_name}:0.0" "#{pane_id}" 2>/dev/null || true)"
    child_command="$(tmux_child_command "" "${tui_pane}")"
    if ! tmux respawn-pane -k -t "${session_name}:0.0" -c "${STARTUP_CWD}" -- "${child_command}"; then
        debug_log "tmux.layout.new_session.child_respawn_failed session=${session_name}"
        tmux kill-session -t "${session_name}" >/dev/null 2>&1 || true
        return 125
    fi
    tmux select-pane -t "${session_name}:0.0"
    debug_log "tmux.layout.new_session session=${session_name} no_preview"
    tmux attach-session -t "${session_name}"
}

usage() {
    cat <<'EOF'
Usage: scripts/start_agent_cli.sh [--python PATH] [--banner] [--help] [--] [agenthub args...]

Launcher options:
  --python PATH
      Use a specific Python executable.
  --banner
      Print startup diagnostics before launching AgentHub.
  --help, -h
      Show this help.
  --
      Stop parsing launcher options and pass the rest to agenthub.

Required external tools:
  git
      Required. AgentHub refuses to start if git is not installed.
  tmux
      Optional. Install tmux to enable the right-side file/URL preview pane.

Common startup forms:
  scripts/start_agent_cli.sh
  scripts/start_agent_cli.sh resume <thread_id>
  scripts/start_agent_cli.sh resume --last
  scripts/start_agent_cli.sh resume --path <rollout_path>
  scripts/start_agent_cli.sh --banner
  scripts/start_agent_cli.sh --headless --prompt "/provider" --json
  scripts/start_agent_cli.sh --python /usr/bin/python3 --serve

Permission and runtime args:
  --permission-mode default|plan|acceptEdits|dontAsk|bypassPermissions
      High-level permission profile. Aliases: accept-edits, dont-ask, bypass-permissions.
  --approval-policy never|on-request|on-failure|untrusted
      Approval behavior for tool execution.
  --sandbox-mode read-only|workspace-write|danger-full-access
      File-system sandbox label for the session.
  --web-search-mode disabled|cached|live
      Web-search availability for the session.
  --network-access enabled|disabled
      Network availability for the session.

Headless args:
  --headless --prompt "..."
  --stdin
  --output-format text|json|stream-json
  --json | --jsonl
  --provider-status

TUI slash commands:
  /quit or /exit
      Exit the interactive TUI. Double Ctrl+C also exits.
  /resume <thread_id>
  /resume_last
  /resume_path <rollout_path>

Defaults injected by this launcher:
  --sandbox-mode ${AGENTHUB_DEFAULT_SANDBOX_MODE:-workspace-write}
  --approval-policy ${AGENTHUB_DEFAULT_APPROVAL_POLICY:-on-request}

These defaults are skipped when --permission-mode is supplied, because
permission-mode is the higher-level preset for approval and sandbox behavior.
Otherwise, user supplied agenthub args are appended after these defaults, so
explicit args such as --approval-policy never or --sandbox-mode danger-full-access
override them.
EOF
}

debug_log "script.enter argv=$*"

while (($# > 0)); do
    case "$1" in
        --python)
            if (($# < 2)); then
                echo "Missing value for --python" >&2
                exit 2
            fi
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
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done

if [[ -z "${CLI_EXECUTABLE}" && -z "${PYTHON_EXE}" ]]; then
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

if [[ -n "${CLI_EXECUTABLE}" ]]; then
    if [[ ! -x "${CLI_EXECUTABLE}" ]]; then
        echo "No usable AgentHub executable found: ${CLI_EXECUTABLE}" >&2
        exit 1
    fi
elif [[ -z "${PYTHON_EXE}" || ! -x "${PYTHON_EXE}" ]]; then
    echo "No usable Python executable found." >&2
    echo "Expected one of:" >&2
    echo "  ${PROJECT_ROOT}/.venv/bin/python" >&2
    echo "  ${CLI_ROOT}/.venv/bin/python" >&2
    echo "Or pass --python PATH." >&2
    exit 1
fi

require_git_dependency

cd "${PROJECT_ROOT}"

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export AGENTHUB_STARTUP_CWD="${STARTUP_CWD}"
export AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE=1
export AGENTHUB_STARTUP_CWD_SOURCE=launcher
unset TEXTUAL_ALLOW_SIGNALS
export AGENTHUB_DEBUG_LOG_DIR="${AGENTHUB_DEBUG_LOG_DIR:-${DEFAULT_DEBUG_LOG_DIR}}"
mkdir -p "${AGENTHUB_DEBUG_LOG_DIR}"
export AGENTHUB_DEBUG_RESPONSES_TIMELINE="${AGENTHUB_DEBUG_RESPONSES_TIMELINE:-${AGENTHUB_DEBUG_LOG_DIR}/timeline.jsonl}"

cleanup_owned_tmux_preview_pane() {
    if [[ "${AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW:-}" != "1" ]]; then
        return 0
    fi
    local preview_pane="${AGENTHUB_PREVIEW_PANE:-}"
    local tui_pane="${AGENTHUB_TUI_PANE:-${TMUX_PANE:-}}"
    if command -v tmux >/dev/null 2>&1; then
        if [[ -n "${preview_pane}" && "${preview_pane}" != "${tui_pane}" ]]; then
            tmux kill-pane -t "${preview_pane}" >/dev/null 2>&1 || true
        fi
    fi
    restore_tmux_preview_mouse_bindings
}

trap cleanup_owned_tmux_preview_pane EXIT

# Ignore shell job-control stop signals during the handoff to the Python TUI.
# This covers terminals that still manage to deliver TSTP/TTIN/TTOU before
# Textual has fully entered application mode.
# Use an ignored disposition rather than a shell handler: caught handlers are
# reset by exec, but ignored dispositions survive into Python startup.
trap '' TSTP
trap '' TTIN
trap '' TTOU
debug_log "signals.stop.ignored_for_exec"
debug_snapshot "$@"

if should_use_tmux_preview_layout "${ORIGINAL_ARGS[@]}"; then
    if [[ -n "${TMUX:-}" ]]; then
        if start_tmux_preview_layout_in_current_session; then
            :
        fi
    else
        if start_tmux_preview_layout_new_session; then
            exit 0
        else
            tmux_status=$?
            if ((tmux_status != 125)); then
                exit "${tmux_status}"
            fi
        fi
    fi
else
    warn_missing_tmux_preview_dependency "${ORIGINAL_ARGS[@]}"
fi

DEFAULT_AGENTHUB_ARGS=()
if ! has_permission_mode_arg "$@"; then
    DEFAULT_AGENTHUB_ARGS=(
        --sandbox-mode "${DEFAULT_SANDBOX_MODE}"
        --approval-policy "${DEFAULT_APPROVAL_POLICY}"
    )
fi

if ((SHOW_BANNER)); then
    echo "Starting AgentHub CLI"
    echo "  cwd: ${AGENTHUB_STARTUP_CWD}"
    echo "  cli root: ${CLI_ROOT}"
    if [[ -n "${CLI_EXECUTABLE}" ]]; then
        echo "  executable: ${CLI_EXECUTABLE}"
    else
        echo "  python: ${PYTHON_EXE}"
    fi
    if ((${#DEFAULT_AGENTHUB_ARGS[@]} > 0)); then
        echo "  runtime defaults: sandbox_mode=${DEFAULT_SANDBOX_MODE}, approval_policy=${DEFAULT_APPROVAL_POLICY}"
    else
        echo "  runtime defaults: skipped because --permission-mode was supplied"
    fi
    echo "  debug logs: ${AGENTHUB_DEBUG_LOG_DIR}"
    echo "  recommended first commands: /provider, /plugins, /tools"
fi

debug_log "python.exec default_args=${DEFAULT_AGENTHUB_ARGS[*]:-<skipped>}"
set +e
if [[ -n "${CLI_EXECUTABLE}" ]]; then
    "${CLI_EXECUTABLE}" "${DEFAULT_AGENTHUB_ARGS[@]}" "$@"
else
    "${PYTHON_EXE}" -m cli.agent_cli \
        "${DEFAULT_AGENTHUB_ARGS[@]}" \
        "$@"
fi
python_status=$?
set -e
debug_log "python.exit status=${python_status}"
exit "${python_status}"
