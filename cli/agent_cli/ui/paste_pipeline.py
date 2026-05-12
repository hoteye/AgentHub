from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable

from cli.agent_cli.models import PromptAttachment
from cli.agent_cli.ui.attachments import extract_attachment_references, normalize_pasted_path_text


def next_large_paste_placeholder(
    char_count: int,
    *,
    counters: dict[int, int],
    formatter: Callable[[int, int], str] | None = None,
) -> str:
    next_suffix = counters.get(char_count, 0) + 1
    counters[char_count] = next_suffix
    if callable(formatter):
        return str(formatter(char_count, next_suffix) or "")
    base = f"[Pasted Content {char_count} chars]"
    if next_suffix == 1:
        return base
    return f"{base} #{next_suffix}"


def retain_pending_pastes_for_text(
    text: str,
    pending_pastes: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    current = str(text or "")
    return [
        (placeholder, payload) for placeholder, payload in pending_pastes if placeholder in current
    ]


def expand_pending_pastes(
    text: str,
    pending_pastes: list[tuple[str, str]],
) -> str:
    expanded = str(text or "")
    for placeholder, payload in pending_pastes:
        if placeholder in expanded:
            expanded = expanded.replace(placeholder, payload)
    return expanded


def prepare_prompt_submission(
    display_text: str,
    *,
    pending_pastes: list[tuple[str, str]],
    windows_drive_re,
    windows_unc_re,
) -> tuple[str, list[PromptAttachment]]:
    expanded = expand_pending_pastes(display_text, pending_pastes).strip()
    plain_text, attachments = extract_attachment_references(
        expanded,
        windows_drive_re=windows_drive_re,
        windows_unc_re=windows_unc_re,
    )
    return plain_text.strip(), attachments


def insert_paste_text(
    text: str,
    *,
    large_paste_char_threshold: int,
    pending_pastes: list[tuple[str, str]],
    large_paste_counters: dict[int, int],
    windows_drive_re,
    windows_unc_re,
    placeholder_formatter: Callable[[int, int], str] | None = None,
) -> str:
    normalized = normalize_pasted_path_text(
        str(text or "").replace("\r\n", "\n").replace("\r", "\n"),
        windows_drive_re=windows_drive_re,
        windows_unc_re=windows_unc_re,
    )
    char_count = len(normalized)
    if char_count > int(large_paste_char_threshold):
        placeholder = next_large_paste_placeholder(
            char_count,
            counters=large_paste_counters,
            formatter=placeholder_formatter,
        )
        pending_pastes.append((placeholder, normalized))
        return placeholder
    return normalized


def _run_clipboard_command(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return False, ""
    if result.returncode != 0:
        return False, ""
    return True, str(result.stdout or "").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


def _write_clipboard_command(command: list[str], text: str) -> bool:
    try:
        result = subprocess.run(
            command,
            input=text,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return False
    return int(getattr(result, "returncode", 1) or 0) == 0


def _is_probably_wsl() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    release = str(platform.release() or "").lower()
    if "microsoft" in release or "wsl" in release:
        return True
    try:
        proc_version = open("/proc/version", encoding="utf-8", errors="replace").read().lower()
    except OSError:
        return False
    return "microsoft" in proc_version or "wsl" in proc_version


def _powershell_clipboard_commands() -> list[list[str]]:
    script = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Clipboard -Raw"
    commands: list[list[str]] = []
    for name in ("powershell.exe", "pwsh", "powershell"):
        if shutil.which(name):
            commands.append([name, "-NoProfile", "-Command", script])
    return commands


def _clipboard_read_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    if sys.platform.startswith("win"):
        return _powershell_clipboard_commands()
    if sys.platform == "darwin":
        if shutil.which("pbpaste"):
            commands.append(["pbpaste"])
        return commands

    if _is_probably_wsl():
        commands.extend(_powershell_clipboard_commands())
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        commands.append(["wl-paste", "--no-newline"])
    if shutil.which("xclip"):
        commands.append(["xclip", "-selection", "clipboard", "-o"])
    if shutil.which("xsel"):
        commands.append(["xsel", "--clipboard", "--output"])
    return commands


def _tmux_clipboard_write_command() -> list[str]:
    if not os.environ.get("TMUX"):
        return []
    if not shutil.which("tmux"):
        return []
    return ["tmux", "load-buffer", "-w", "-"]


def _clipboard_write_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    tmux_command = _tmux_clipboard_write_command()
    if tmux_command:
        commands.append(tmux_command)
    if sys.platform.startswith("win"):
        commands.extend(
            [
                [
                    name,
                    "-NoProfile",
                    "-Command",
                    "$input | Set-Clipboard",
                ]
                for name in ("powershell.exe", "pwsh", "powershell")
                if shutil.which(name)
            ]
        )
        return commands
    if sys.platform == "darwin":
        if shutil.which("pbcopy"):
            commands.append(["pbcopy"])
        return commands

    if _is_probably_wsl():
        commands.extend(
            [
                [
                    name,
                    "-NoProfile",
                    "-Command",
                    "$input | Set-Clipboard",
                ]
                for name in ("powershell.exe", "pwsh", "powershell")
                if shutil.which(name)
            ]
        )
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        commands.append(["wl-copy"])
    if shutil.which("xclip"):
        commands.append(["xclip", "-selection", "clipboard", "-i"])
    if shutil.which("xsel"):
        commands.append(["xsel", "--clipboard", "--input"])
    return commands


def read_clipboard_text() -> str:
    for command in _clipboard_read_commands():
        ok, text = _run_clipboard_command(command)
        if ok:
            return text
    return ""


def write_clipboard_text(text: str) -> bool:
    payload = str(text or "")
    for command in _clipboard_write_commands():
        if _write_clipboard_command(command, payload):
            return True
    return False
