from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cli.agent_cli.ui.transcript_preview_pane_tmux_commands import (
    directory_opener_install_command as directory_opener_install_command,
)
from cli.agent_cli.ui.transcript_preview_pane_tmux_commands import (
    directory_opener_install_prompt_shell_command,
    preview_command_for_target,
    preview_shell_command,
    tmux_display_message_command,
    tmux_kill_pane_command,
    tmux_pane_border_style_commands,
    tmux_respawn_pane_command,
    tmux_split_preview_pane_command,
    url_opener_install_prompt_shell_command,
)
from cli.agent_cli.ui.transcript_preview_pane_tmux_commands import (
    directory_opener_package_commands as directory_opener_package_commands,
)
from cli.agent_cli.ui.transcript_preview_pane_tmux_commands import (
    tmux_preview_ready_shell_command as tmux_preview_ready_shell_command,
)
from cli.agent_cli.ui.transcript_preview_pane_tmux_commands import (
    url_opener_install_command as url_opener_install_command,
)
from cli.agent_cli.ui.transcript_preview_pane_tmux_commands import (
    url_opener_package_commands as url_opener_package_commands,
)
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
    tmux_command = tmux_respawn_pane_command(preview_pane, shell_command)
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
            retry_command = tmux_respawn_pane_command(revived_pane, shell_command)
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
        completed = run(tmux_kill_pane_command(preview_pane), check=False)
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
            tmux_display_message_command(pane),
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
    command = tmux_split_preview_pane_command(workspace=workspace, tui_pane=tui_pane)
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
    new_pane = output_lines[-1].strip() if output_lines else ""
    if new_pane:
        border_bg = os.environ.get("AGENTHUB_TMUX_PANE_BORDER_BG") or "#11161c"
        for command in tmux_pane_border_style_commands(
            (new_pane, tui_pane or new_pane),
            border_bg=border_bg,
        ):
            run(command, check=False)
    return new_pane


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
    tmux_command = tmux_respawn_pane_command(preview_pane, shell_command)
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
    tmux_command = tmux_respawn_pane_command(preview_pane, shell_command)
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
