from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import textwrap
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = CLI_ROOT / "scripts" / "start_agent_cli.sh"
WINDOWS_LAUNCHER = CLI_ROOT / "scripts" / "start_agent_cli.ps1"


def _run_launcher(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTHUB_PYTHON"] = "/bin/echo"
    env["AGENTHUB_START_DEBUG_LOG"] = str(CLI_ROOT / ".tmp" / "start_agent_cli_test.log")
    env.pop("AGENTHUB_DEFAULT_SANDBOX_MODE", None)
    return subprocess.run(
        ["bash", str(LAUNCHER), *args],
        cwd=CLI_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_launcher_with_pty(
    command: list[str], *, env: dict[str, str], cwd: Path = CLI_ROOT
) -> subprocess.CompletedProcess[str]:
    master_fd, slave_fd = os.openpty()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        os.close(slave_fd)
        slave_fd = -1
        chunks: list[bytes] = []
        while True:
            try:
                chunk = os.read(master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        result.stdout = b"".join(chunks).decode("utf-8", errors="replace")
        return result
    finally:
        if slave_fd >= 0:
            os.close(slave_fd)
        os.close(master_fd)


def _fake_command_path(tmp_path: Path, *command_names: str) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command_name in command_names:
        real_command = shutil.which(command_name)
        if real_command is None:
            raise AssertionError(f"missing required command for test: {command_name}")
        (fake_bin / command_name).symlink_to(real_command)
    return fake_bin


def test_launcher_does_not_use_tmux_layout_without_tty() -> None:
    result = _run_launcher()

    assert result.returncode == 0
    assert "AGENTHUB_TMUX_LAYOUT_CHILD" not in result.stdout
    assert "AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW" not in result.stdout
    assert (
        "-m cli.agent_cli --sandbox-mode workspace-write --approval-policy on-request"
        in result.stdout
    )


def test_launcher_allows_tmux_layout_to_be_disabled() -> None:
    env = os.environ.copy()
    env["AGENTHUB_PYTHON"] = "/bin/echo"
    env["AGENTHUB_DISABLE_TMUX_LAYOUT"] = "1"
    env["AGENTHUB_START_DEBUG_LOG"] = str(CLI_ROOT / ".tmp" / "start_agent_cli_test.log")
    result = subprocess.run(
        ["bash", str(LAUNCHER)],
        cwd=CLI_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "AGENTHUB_TMUX_LAYOUT_CHILD" not in result.stdout
    assert "AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW" not in result.stdout
    assert (
        "-m cli.agent_cli --sandbox-mode workspace-write --approval-policy on-request"
        in result.stdout
    )


def test_launcher_defaults_to_on_request_for_interactive_tui() -> None:
    result = _run_launcher("--banner")

    assert result.returncode == 0
    assert "approval_policy=on-request" in result.stdout
    assert (
        "-m cli.agent_cli --sandbox-mode workspace-write --approval-policy on-request"
        in result.stdout
    )


def test_launcher_allows_interactive_policy_override_args() -> None:
    result = _run_launcher("--approval-policy", "never", "--sandbox-mode", "workspace-write")

    assert result.returncode == 0
    assert "Refusing to start the interactive TUI with policy-only arguments." not in result.stderr
    assert "--approval-policy on-request --approval-policy never" in result.stdout
    assert (
        "--sandbox-mode workspace-write --approval-policy on-request --approval-policy never --sandbox-mode workspace-write"
        in result.stdout
    )


def test_launcher_permission_mode_is_not_overridden_by_injected_defaults() -> None:
    result = _run_launcher("--permission-mode", "bypassPermissions")

    assert result.returncode == 0
    assert "-m cli.agent_cli --permission-mode bypassPermissions" in result.stdout
    assert "--approval-policy on-request" not in result.stdout
    assert "--sandbox-mode workspace-write" not in result.stdout


def test_launcher_requires_git_before_starting(tmp_path: Path) -> None:
    fake_bin = _fake_command_path(tmp_path, "bash", "dirname", "mkdir", "ps", "date", "tr")
    env = os.environ.copy()
    env["AGENTHUB_PYTHON"] = "/bin/echo"
    env["AGENTHUB_START_DEBUG_LOG"] = str(tmp_path / "start.log")
    env["PATH"] = str(fake_bin)

    result = subprocess.run(
        ["bash", str(LAUNCHER)],
        cwd=CLI_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "AgentHub requires git" in result.stderr
    assert "sudo apt install git" in result.stderr


def test_launcher_warns_when_interactive_preview_tmux_is_missing(tmp_path: Path) -> None:
    fake_bin = _fake_command_path(tmp_path, "git", "bash", "dirname", "mkdir", "ps", "date", "tr")
    script = textwrap.dedent(
        f"""
        set -euo pipefail
        export PATH={shlex.quote(str(fake_bin))}
        export AGENTHUB_PYTHON=/bin/echo
        export AGENTHUB_START_DEBUG_LOG={shlex.quote(str(tmp_path / "start.log"))}
        source {shlex.quote(str(LAUNCHER))}
        """
    )

    result = _run_launcher_with_pty(["bash", "-c", script], cwd=CLI_ROOT, env=os.environ.copy())

    assert result.returncode == 0
    assert "AgentHub file/URL preview panes need tmux" in result.stderr
    assert "Continuing without the preview pane" in result.stderr
    assert (
        "-m cli.agent_cli --sandbox-mode workspace-write --approval-policy on-request"
        in result.stdout
    )


def test_launcher_does_not_warn_about_tmux_for_headless_args(tmp_path: Path) -> None:
    fake_bin = _fake_command_path(tmp_path, "git", "bash", "dirname", "mkdir", "ps", "date", "tr")
    script = textwrap.dedent(
        f"""
        set -euo pipefail
        export PATH={shlex.quote(str(fake_bin))}
        export AGENTHUB_PYTHON=/bin/echo
        export AGENTHUB_START_DEBUG_LOG={shlex.quote(str(tmp_path / "start.log"))}
        source {shlex.quote(str(LAUNCHER))} --provider-status
        """
    )

    result = _run_launcher_with_pty(["bash", "-c", script], cwd=CLI_ROOT, env=os.environ.copy())

    assert result.returncode == 0
    assert "preview panes need tmux" not in result.stderr
    assert "--provider-status" in result.stdout


def test_launcher_treats_version_as_direct_cli_mode(tmp_path: Path) -> None:
    fake_bin = _fake_command_path(tmp_path, "git", "bash", "dirname", "mkdir", "ps", "date", "tr")
    script = textwrap.dedent(
        f"""
        set -euo pipefail
        export PATH={shlex.quote(str(fake_bin))}
        export AGENTHUB_PYTHON=/bin/echo
        export AGENTHUB_START_DEBUG_LOG={shlex.quote(str(tmp_path / "start.log"))}
        source {shlex.quote(str(LAUNCHER))} --version
        """
    )

    result = _run_launcher_with_pty(["bash", "-c", script], cwd=CLI_ROOT, env=os.environ.copy())

    assert result.returncode == 0
    assert "preview panes need tmux" not in result.stderr
    assert "--version" in result.stdout


def test_launcher_can_wrap_packaged_cli_executable_without_python(tmp_path: Path) -> None:
    fake_bin = _fake_command_path(tmp_path, "git", "bash", "dirname", "mkdir", "ps", "date", "tr")
    fake_cli = tmp_path / "agenthub-cli"
    fake_cli.write_text("#!/bin/sh\nprintf 'packaged:%s\\n' \"$*\"\n", encoding="utf-8")
    fake_cli.chmod(0o755)
    env = os.environ.copy()
    env.pop("AGENTHUB_PYTHON", None)
    env["AGENTHUB_CLI_EXECUTABLE"] = str(fake_cli)
    env["AGENTHUB_START_DEBUG_LOG"] = str(tmp_path / "start.log")
    env["PATH"] = str(fake_bin)

    result = subprocess.run(
        ["bash", str(LAUNCHER), "--provider-status"],
        cwd=CLI_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert (
        "packaged:--sandbox-mode workspace-write --approval-policy on-request --provider-status"
        in result.stdout
    )
    assert "-m cli.agent_cli" not in result.stdout


def test_windows_launcher_preserves_startup_cwd_before_project_chdir() -> None:
    script = WINDOWS_LAUNCHER.read_text(encoding="utf-8")

    capture_index = script.index("$StartupCwd = (Get-Location).ProviderPath")
    env_index = script.index("$env:AGENTHUB_STARTUP_CWD = $StartupCwd")
    active_index = script.index('$env:AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE = "1"')
    source_index = script.index('$env:AGENTHUB_STARTUP_CWD_SOURCE = "launcher"')
    chdir_index = script.index("Set-Location $ProjectRoot")

    assert capture_index < env_index < active_index < source_index < chdir_index
    assert "$env:AGENTHUB_PREVIEW_WORKSPACE = $env:AGENTHUB_STARTUP_CWD" in script


def test_launcher_ignores_job_control_stop_signals_across_exec() -> None:
    result = _run_launcher()

    assert result.returncode == 0
    log_text = (CLI_ROOT / ".tmp" / "start_agent_cli_test.log").read_text(encoding="utf-8")
    assert "signals.stop.ignored_for_exec" in log_text
    assert "trap -- '' SIGTSTP" in log_text
    assert "trap -- '' SIGTTIN" in log_text
    assert "trap -- '' SIGTTOU" in log_text


def test_launcher_creates_debug_log_parent_directory(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "start_agent_cli_test.log"
    env = os.environ.copy()
    env["AGENTHUB_PYTHON"] = "/bin/echo"
    env["AGENTHUB_START_DEBUG_LOG"] = str(log_path)

    result = subprocess.run(
        ["bash", str(LAUNCHER), "--provider-status"],
        cwd=CLI_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert log_path.exists()
    assert "script.enter" in log_path.read_text(encoding="utf-8")


def test_launcher_configures_preview_drag_copy_to_clipboard(tmp_path) -> None:
    log_path = tmp_path / "tmux_calls.log"
    script = textwrap.dedent(
        f"""
        set -euo pipefail
        LOG_FILE={shlex.quote(str(log_path))}
        source <(sed '/^debug_log "script.enter argv=/,$d' {shlex.quote(str(LAUNCHER))})
        tmux() {{
            printf '%s\\n' "$*" >> "$LOG_FILE"
            if [[ "${{1:-}}" == "list-keys" ]]; then
                local table="${{3:-}}"
                local key="${{@: -1}}"
                printf 'bind-key -T %s %s send-keys -M\\n' "$table" "$key"
                return 0
            fi
            return 0
        }}
        configure_tmux_preview_mouse_bindings "agenthub-test-$$" "%42"
        printf 'restore=%s\\n' "${{AGENTHUB_TMUX_MOUSE_RESTORE_FILE:-}}" >> "$LOG_FILE"
        cat "${{AGENTHUB_TMUX_MOUSE_RESTORE_FILE}}" >> "$LOG_FILE"
        rm -f "${{AGENTHUB_TMUX_MOUSE_RESTORE_FILE}}"
        """
    )

    result = subprocess.run(
        ["bash", "-c", script],
        cwd=CLI_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    log_text = log_path.read_text(encoding="utf-8")
    assert "set-option -t agenthub-test-" in log_text
    assert "@agenthub_preview_pane %42" in log_text
    assert "bind-key -T root MouseDrag1Pane if-shell -F -t =" in log_text
    assert "#{@agenthub_preview_pane}" in log_text
    assert "copy-mode -t = -M" in log_text
    assert (
        "bind-key -T copy-mode MouseDragEnd1Pane send-keys -X "
        "copy-pipe-and-cancel tmux load-buffer -w -"
    ) in log_text
    assert (
        "bind-key -T copy-mode-vi MouseDragEnd1Pane send-keys -X "
        "copy-pipe-and-cancel tmux load-buffer -w -"
    ) in log_text
    assert "set-hook -t agenthub-test-" in log_text
    assert "session-closed" in log_text
    assert "restore=/tmp/agenthub-tmux-agenthub-test-" in log_text


def test_launcher_help_lists_common_resume_permission_and_quit_usage() -> None:
    result = _run_launcher("--help")

    assert result.returncode == 0
    assert "resume <thread_id>" in result.stdout
    assert "resume --last" in result.stdout
    assert "resume --path <rollout_path>" in result.stdout
    assert "--permission-mode default|plan|acceptEdits|dontAsk|bypassPermissions" in result.stdout
    assert "accept-edits, dont-ask, bypass-permissions" in result.stdout
    assert "--approval-policy never|on-request|on-failure|untrusted" in result.stdout
    assert "--sandbox-mode read-only|workspace-write|danger-full-access" in result.stdout
    assert "--web-search-mode disabled|cached|live" in result.stdout
    assert "--network-access enabled|disabled" in result.stdout
    assert "/quit or /exit" in result.stdout
    assert "/resume_last" in result.stdout
    assert "defaults are skipped when --permission-mode is supplied" in result.stdout
