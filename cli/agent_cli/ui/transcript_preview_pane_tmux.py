from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from cli.agent_cli.ui.transcript_preview_target import PreviewTarget


@dataclass(frozen=True)
class PreviewOpenResult:
    opened: bool
    reason: str
    target: PreviewTarget | None = None
    command: tuple[str, ...] = ()


def open_target_in_preview(
    target: PreviewTarget,
    *,
    pane: str | None = None,
    opener_lookup: Callable[[str], str | None] = shutil.which,
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> PreviewOpenResult:
    if preview_pane_user_disabled():
        return PreviewOpenResult(False, "preview_pane_disabled", target=target)
    preview_pane = str(pane or os.environ.get("AGENTHUB_PREVIEW_PANE") or "").strip()
    if not preview_pane:
        return PreviewOpenResult(False, "preview_pane_unavailable", target=target)
    command = preview_command_for_target(target, opener_lookup=opener_lookup)
    if not command:
        if target.kind == "url":
            return _open_url_opener_install_prompt(
                target,
                preview_pane,
                opener_lookup=opener_lookup,
                run=run,
            )
        if target.kind == "dir":
            return _open_directory_opener_install_prompt(
                target,
                preview_pane,
                opener_lookup=opener_lookup,
                run=run,
            )
        return PreviewOpenResult(False, "preview_opener_unavailable", target=target)
    shell_command = preview_shell_command(command)
    preview_pane = ensure_preview_pane(preview_pane, run=run)
    if not preview_pane:
        return PreviewOpenResult(False, "preview_pane_unavailable", target=target)
    tmux_command = ("tmux", "respawn-pane", "-k", "-t", preview_pane, "--", shell_command)
    try:
        completed = run(list(tmux_command), check=False)
    except Exception:
        return PreviewOpenResult(False, "tmux_respawn_failed", target=target, command=tmux_command)
    return_code = int(getattr(completed, "returncode", 1) or 0)
    if return_code != 0:
        revived_pane = (
            "" if _tmux_pane_exists(preview_pane, run=run) else _split_preview_pane(run=run)
        )
        if revived_pane:
            os.environ["AGENTHUB_PREVIEW_PANE"] = revived_pane
            retry_command = ("tmux", "respawn-pane", "-k", "-t", revived_pane, "--", shell_command)
            try:
                retry_completed = run(list(retry_command), check=False)
            except Exception:
                return PreviewOpenResult(
                    False, "tmux_respawn_failed", target=target, command=retry_command
                )
            if int(getattr(retry_completed, "returncode", 1) or 0) == 0:
                return PreviewOpenResult(True, "opened", target=target, command=retry_command)
        return PreviewOpenResult(False, "tmux_respawn_failed", target=target, command=tmux_command)
    return PreviewOpenResult(True, "opened", target=target, command=tmux_command)


def ensure_preview_pane(
    pane: str,
    *,
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> str:
    preview_pane = str(pane or "").strip()
    if not preview_pane:
        return ""
    if _tmux_pane_exists(preview_pane, run=run):
        return preview_pane
    revived_pane = _split_preview_pane(run=run)
    if revived_pane:
        os.environ["AGENTHUB_PREVIEW_PANE"] = revived_pane
    return revived_pane


def open_preview_pane(
    *,
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> str:
    preview_pane = str(os.environ.get("AGENTHUB_PREVIEW_PANE") or "").strip()
    if preview_pane and _tmux_pane_exists(preview_pane, run=run):
        return preview_pane
    revived_pane = _split_preview_pane(run=run)
    if revived_pane:
        os.environ["AGENTHUB_PREVIEW_PANE"] = revived_pane
        os.environ["AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW"] = "1"
    return revived_pane


def preview_pane_user_disabled() -> bool:
    return str(os.environ.get("AGENTHUB_PREVIEW_DISABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def set_preview_pane_user_disabled(disabled: bool) -> None:
    if disabled:
        os.environ["AGENTHUB_PREVIEW_DISABLED"] = "1"
    else:
        os.environ.pop("AGENTHUB_PREVIEW_DISABLED", None)


def close_preview_pane(
    pane: str | None = None,
    *,
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> bool:
    preview_pane = str(pane or os.environ.get("AGENTHUB_PREVIEW_PANE") or "").strip()
    if not preview_pane:
        return False
    tui_panes = {
        str(os.environ.get("AGENTHUB_TUI_PANE") or "").strip(),
        str(os.environ.get("TMUX_PANE") or "").strip(),
    }
    if preview_pane in tui_panes:
        return False
    if not _tmux_pane_exists(preview_pane, run=run):
        if pane is None:
            os.environ.pop("AGENTHUB_PREVIEW_PANE", None)
        return False
    try:
        completed = run(["tmux", "kill-pane", "-t", preview_pane], check=False)
    except Exception:
        return False
    if int(getattr(completed, "returncode", 1) or 0) != 0:
        return False
    if pane is None:
        os.environ.pop("AGENTHUB_PREVIEW_PANE", None)
    return True


def _tmux_pane_exists(
    pane: str,
    *,
    run: Callable[..., subprocess.CompletedProcess[Any]],
) -> bool:
    try:
        completed = run(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_id}"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return False
    if int(getattr(completed, "returncode", 1) or 0) != 0:
        return False
    resolved_pane = str(getattr(completed, "stdout", "") or "").strip()
    return resolved_pane == pane


def preview_pane_exists(
    pane: str | None = None,
    *,
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> bool:
    preview_pane = str(pane or os.environ.get("AGENTHUB_PREVIEW_PANE") or "").strip()
    if not preview_pane:
        return False
    return _tmux_pane_exists(preview_pane, run=run)


def _split_preview_pane(
    *,
    run: Callable[..., subprocess.CompletedProcess[Any]],
) -> str:
    workspace = str(
        os.environ.get("AGENTHUB_PREVIEW_WORKSPACE") or os.environ.get("AGENTHUB_STARTUP_CWD") or ""
    )
    tui_pane = str(os.environ.get("AGENTHUB_TUI_PANE") or os.environ.get("TMUX_PANE") or "").strip()
    command = ["tmux", "split-window", "-d", "-h", "-l", "50%", "-P", "-F", "#{pane_id}"]
    if tui_pane:
        command.extend(["-t", tui_pane])
    if workspace:
        command.extend(["-c", workspace])
    command.append(tmux_preview_ready_shell_command())
    try:
        completed = run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    if int(getattr(completed, "returncode", 1) or 0) != 0:
        return ""
    output_lines = str(getattr(completed, "stdout", "") or "").strip().splitlines()
    return output_lines[-1].strip() if output_lines else ""


def tmux_preview_ready_shell_command(*, shell: str | None = None) -> str:
    shell_path = str(shell or os.environ.get("SHELL") or "/bin/bash").strip() or "/bin/bash"
    return (
        "printf 'AgentHub Preview ready\\n"
        "/preview [open|close|toggle|status]\\n'; "
        f"exec {shlex.quote(shell_path)}"
    )


def preview_shell_command(command: Sequence[str], *, shell: str | None = None) -> str:
    target_command = " ".join(shlex.quote(str(part)) for part in command)
    shell_path = str(shell or os.environ.get("SHELL") or "/bin/bash").strip() or "/bin/bash"
    return f"{target_command}; exec {shlex.quote(shell_path)}"


def url_opener_install_command(
    *,
    command_lookup: Callable[[str], str | None] = shutil.which,
) -> str:
    install_command, _uninstall_command = url_opener_package_commands(command_lookup=command_lookup)
    return install_command


def url_opener_package_commands(
    *,
    command_lookup: Callable[[str], str | None] = shutil.which,
) -> tuple[str, str]:
    if command_lookup("apt"):
        return ("sudo apt update && sudo apt install w3m", "sudo apt remove w3m")
    if command_lookup("apt-get"):
        return ("sudo apt-get update && sudo apt-get install w3m", "sudo apt-get remove w3m")
    if command_lookup("brew"):
        return ("brew install w3m", "brew uninstall w3m")
    if command_lookup("dnf"):
        return ("sudo dnf install w3m", "sudo dnf remove w3m")
    if command_lookup("yum"):
        return ("sudo yum install w3m", "sudo yum remove w3m")
    if command_lookup("pacman"):
        return ("sudo pacman -S w3m", "sudo pacman -R w3m")
    if command_lookup("zypper"):
        return ("sudo zypper install w3m", "sudo zypper remove w3m")
    if command_lookup("apk"):
        return ("sudo apk add w3m", "sudo apk del w3m")
    return ("", "")


def directory_opener_install_command(
    *,
    command_lookup: Callable[[str], str | None] = shutil.which,
) -> str:
    return ""


def directory_opener_package_commands(
    *,
    command_lookup: Callable[[str], str | None] = shutil.which,
) -> tuple[str, str]:
    return ("", "")


def url_opener_install_prompt_shell_command(
    install_command: str,
    *,
    uninstall_command: str = "",
    shell: str | None = None,
) -> str:
    shell_path = str(shell or os.environ.get("SHELL") or "/bin/bash").strip() or "/bin/bash"
    lines = [
        "AgentHub URL preview needs a terminal browser.",
        "Install w3m, then click the URL again.",
    ]
    script = f"printf '%s\\n' {' '.join(shlex.quote(line) for line in lines)}; "
    install_command = str(install_command or "").strip()
    if install_command:
        script += (
            f"printf '%s\\n' {shlex.quote(f'Uninstall later: {uninstall_command}')}; "
            if uninstall_command
            else ""
        )
        script += (
            "printf '%s\\n' 'Press Enter to run the suggested command, or edit it first.'; "
            f"read -e -i {shlex.quote(install_command)} -p '$ ' agenthub_preview_install_cmd; "
            'if [ -n "$agenthub_preview_install_cmd" ]; then '
            'eval "$agenthub_preview_install_cmd"; '
            "fi; "
        )
    else:
        script += (
            "printf '%s\\n' "
            "'No supported package manager was detected. Install w3m or lynx manually.'; "
        )
    script += f"exec {shlex.quote(shell_path)}"
    return f"bash -lc {shlex.quote(script)}"


def directory_opener_install_prompt_shell_command(
    *,
    shell: str | None = None,
) -> str:
    shell_path = str(shell or os.environ.get("SHELL") or "/bin/bash").strip() or "/bin/bash"
    lines = [
        "AgentHub directory preview needs a terminal file manager.",
        "Install one of: yazi, mc, ranger.",
        "  yazi: https://yazi-rs.github.io",
    ]
    script = f"printf '%s\\n' {' '.join(shlex.quote(line) for line in lines)}; "
    script += f"exec {shlex.quote(shell_path)}"
    return f"bash -lc {shlex.quote(script)}"


def preview_command_for_target(
    target: PreviewTarget,
    *,
    opener_lookup: Callable[[str], str | None] = shutil.which,
) -> tuple[str, ...]:
    if target.kind == "url":
        resolved_w3m = opener_lookup("w3m")
        if resolved_w3m:
            return (resolved_w3m, "-o", "use_mouse=1", target.value)
        resolved_lynx = opener_lookup("lynx")
        if resolved_lynx:
            return (resolved_lynx, "-use_mouse", target.value)
        return ()
    if target.kind == "dir":
        resolved_yazi = opener_lookup("yazi")
        if resolved_yazi:
            return (resolved_yazi, target.value)
        resolved_mc = opener_lookup("mc")
        if resolved_mc:
            return (resolved_mc, target.value)
        resolved_ranger = opener_lookup("ranger")
        if resolved_ranger:
            return (resolved_ranger, target.value)
        resolved_ls = opener_lookup("ls")
        if resolved_ls:
            return (resolved_ls, "-la", "--color=auto", target.value)
        return ()
    if target.kind != "file":
        return ()
    line_arg = f"+{target.line_number}" if target.line_number else None
    for opener in ("nvim", "vim"):
        resolved = opener_lookup(opener)
        if resolved:
            mouse_args = ("-c", "set mouse=a")
            number_args = ("-c", "set number") if target.line_number else ()
            if line_arg:
                return (resolved, "-R", *mouse_args, *number_args, line_arg, "--", target.value)
            return (resolved, "-R", *mouse_args, "--", target.value)
    resolved_less = opener_lookup("less")
    if resolved_less:
        if line_arg:
            return (resolved_less, line_arg, "--", target.value)
        return (resolved_less, "--", target.value)
    return ()


def _open_directory_opener_install_prompt(
    target: PreviewTarget,
    preview_pane: str,
    *,
    opener_lookup: Callable[[str], str | None],
    run: Callable[..., subprocess.CompletedProcess[Any]],
) -> PreviewOpenResult:
    preview_pane = ensure_preview_pane(preview_pane, run=run)
    if not preview_pane:
        return PreviewOpenResult(False, "preview_pane_unavailable", target=target)
    shell_command = directory_opener_install_prompt_shell_command()
    tmux_command = ("tmux", "respawn-pane", "-k", "-t", preview_pane, "--", shell_command)
    try:
        completed = run(list(tmux_command), check=False)
    except Exception:
        return PreviewOpenResult(
            False,
            "preview_opener_install_prompt_failed",
            target=target,
            command=tmux_command,
        )
    if int(getattr(completed, "returncode", 1) or 0) != 0:
        return PreviewOpenResult(
            False,
            "preview_opener_install_prompt_failed",
            target=target,
            command=tmux_command,
        )
    return PreviewOpenResult(
        True,
        "preview_opener_install_prompted",
        target=target,
        command=tmux_command,
    )


def _open_url_opener_install_prompt(
    target: PreviewTarget,
    preview_pane: str,
    *,
    opener_lookup: Callable[[str], str | None],
    run: Callable[..., subprocess.CompletedProcess[Any]],
) -> PreviewOpenResult:
    preview_pane = ensure_preview_pane(preview_pane, run=run)
    if not preview_pane:
        return PreviewOpenResult(False, "preview_pane_unavailable", target=target)
    install_command, uninstall_command = url_opener_package_commands(command_lookup=opener_lookup)
    shell_command = url_opener_install_prompt_shell_command(
        install_command,
        uninstall_command=uninstall_command,
    )
    tmux_command = ("tmux", "respawn-pane", "-k", "-t", preview_pane, "--", shell_command)
    try:
        completed = run(list(tmux_command), check=False)
    except Exception:
        return PreviewOpenResult(
            False,
            "preview_opener_install_prompt_failed",
            target=target,
            command=tmux_command,
        )
    if int(getattr(completed, "returncode", 1) or 0) != 0:
        return PreviewOpenResult(
            False,
            "preview_opener_install_prompt_failed",
            target=target,
            command=tmux_command,
        )
    return PreviewOpenResult(
        True,
        "preview_opener_install_prompted",
        target=target,
        command=tmux_command,
    )
