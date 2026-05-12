from __future__ import annotations

from typing import Any

from cli.agent_cli.ui.transcript_preview_pane_tmux import (  # noqa: F401
    PreviewOpenResult,
    close_preview_pane,
    directory_opener_install_command,
    directory_opener_install_prompt_shell_command,
    directory_opener_package_commands,
    ensure_preview_pane,
    open_preview_pane,
    open_target_in_preview,
    preview_command_for_target,
    preview_pane_exists,
    preview_pane_user_disabled,
    preview_shell_command,
    set_preview_pane_user_disabled,
    tmux_preview_ready_shell_command,
    url_opener_install_command,
    url_opener_install_prompt_shell_command,
    url_opener_package_commands,
)
from cli.agent_cli.ui.transcript_preview_target import (  # noqa: F401
    PreviewTarget,
    PreviewTargetSpan,
    clear_hover_target,
    target_at_line_column,
    target_for_area_location,
    target_span_at_line_column,
    target_span_for_area_location,
    update_hover_target_for_area,
)


def open_preview_target_for_area(area: Any, location: tuple[int, int]) -> bool:
    target = target_for_area_location(area, location)
    if target is None:
        return False
    if preview_pane_user_disabled():
        set_preview_pane_user_disabled(False)
        pane = open_preview_pane()
        if not pane:
            return False
    result = open_target_in_preview(target)
    if not result.opened:
        if result.reason != "preview_pane_unavailable":
            _notify_open_failure(area, result)
        return False
    return True


def _notify_open_failure(area: Any, result: PreviewOpenResult) -> None:
    try:
        notify = area.app.notify
    except Exception:
        return
    if not callable(notify):
        return
    if result.reason == "preview_pane_unavailable":
        message = "Preview pane is unavailable."
    elif result.reason == "preview_opener_unavailable":
        message = "No preview opener found."
    else:
        message = "Preview pane failed to open target."
    try:
        notify(message, severity="warning")
    except Exception:
        pass
