from __future__ import annotations

import os
import shlex
import shutil
from collections.abc import Callable, Sequence

from cli.agent_cli.ui.transcript_preview_target import PreviewTarget


def tmux_display_message_command(pane: str) -> list[str]:
    return ["tmux", "display-message", "-p", "-t", pane, "#{pane_id}"]


def tmux_kill_pane_command(pane: str) -> list[str]:
    return ["tmux", "kill-pane", "-t", pane]


def tmux_respawn_pane_command(pane: str, shell_command: str) -> tuple[str, ...]:
    return ("tmux", "respawn-pane", "-k", "-t", pane, "--", shell_command)


def tmux_split_preview_pane_command(*, workspace: str, tui_pane: str) -> list[str]:
    command = ["tmux", "split-window", "-d", "-h", "-l", "50%", "-P", "-F", "#{pane_id}"]
    if tui_pane:
        command.extend(["-t", tui_pane])
    if workspace:
        command.extend(["-c", workspace])
    command.append(tmux_preview_ready_shell_command())
    return command


def tmux_pane_border_style_commands(
    panes: Sequence[str],
    *,
    border_bg: str,
) -> tuple[list[str], ...]:
    commands: list[list[str]] = []
    for target in panes:
        commands.append(
            ["tmux", "set-option", "-w", "-t", target, "pane-border-style", f"fg={border_bg}"]
        )
        commands.append(
            [
                "tmux",
                "set-option",
                "-w",
                "-t",
                target,
                "pane-active-border-style",
                f"fg={border_bg}",
            ]
        )
    return tuple(commands)


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
    file_lower = target.value.lower()
    if file_lower.endswith(".md") or file_lower.endswith(".markdown"):
        resolved_glow = opener_lookup("glow")
        if resolved_glow:
            return (resolved_glow, "--style", "dark", "--", target.value)
        resolved_mdcat = opener_lookup("mdcat")
        if resolved_mdcat:
            return (resolved_mdcat, "--", target.value)
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
