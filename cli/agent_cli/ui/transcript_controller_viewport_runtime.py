from __future__ import annotations

from cli.agent_cli.ui.widgets import TranscriptArea


def transcript_render_width(main_log: TranscriptArea) -> int:
    width = 0
    try:
        width = int(main_log.scrollable_content_region.size.width)
    except Exception:
        width = 0
    if width <= 0:
        try:
            width = int(main_log.content_size.width)
        except Exception:
            width = 0
    if width <= 0:
        try:
            width = int(main_log.size.width)
        except Exception:
            width = 0
    # TextArea soft-wrap keeps one spare cell in its internal wrapped document.
    # Align transcript formatting to that effective width so exact-width separator
    # lines do not wrap into a trailing single-character continuation.
    if hasattr(main_log, "wrapped_document") and hasattr(main_log, "gutter_width"):
        try:
            width -= int(getattr(main_log, "gutter_width", 0) or 0) + 1
        except Exception:
            pass
    return max(20, width)


def transcript_scroll_offset(main_log: TranscriptArea) -> tuple[int, int]:
    helper = getattr(main_log, "transcript_scroll_offset", None)
    if callable(helper):
        try:
            return helper()
        except Exception:
            pass
    try:
        offset = main_log.scroll_offset
    except Exception:
        return (0, 0)
    try:
        return (int(offset.x), int(offset.y))
    except Exception:
        pass
    try:
        return (int(offset[0]), int(offset[1]))
    except Exception:
        return (0, 0)


def transcript_should_follow_bottom(main_log: TranscriptArea) -> bool:
    helper = getattr(main_log, "transcript_should_follow_bottom", None)
    if callable(helper):
        try:
            return bool(helper())
        except Exception:
            pass
    try:
        if not getattr(main_log, "text", ""):
            return True
        _, scroll_y = transcript_scroll_offset(main_log)
        return int(scroll_y) >= max(0, int(main_log.max_scroll_y) - 1)
    except Exception:
        return True


def restore_transcript_viewport(
    main_log: TranscriptArea,
    *,
    scroll_x: int = 0,
    scroll_y: int = 0,
) -> None:
    helper = getattr(main_log, "restore_transcript_viewport", None)
    if callable(helper):
        try:
            helper(scroll_x=scroll_x, scroll_y=scroll_y)
            return
        except Exception:
            pass
    try:
        main_log.scroll_to(
            x=max(0, int(scroll_x)),
            y=max(0, int(scroll_y)),
            animate=False,
            immediate=True,
            force=True,
        )
    except Exception:
        return
