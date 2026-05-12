from __future__ import annotations

from dataclasses import dataclass

from rich.cells import cell_len

_ELLIPSIS = "..."
_MIN_MEANINGFUL_LEFT_WIDTH = 5


@dataclass(frozen=True, slots=True)
class BottomDockLineLayout:
    line: str
    left_text: str
    right_text: str
    right_visible: bool


def _normalize_text(value: str) -> str:
    return str(value or "").replace("\r", "\n").replace("\n", " ")


def _truncate_text(value: str, width: int) -> str:
    total_width = max(0, int(width))
    text = _normalize_text(value)
    if total_width <= 0 or not text:
        return ""
    if cell_len(text) <= total_width:
        return text
    if total_width <= len(_ELLIPSIS):
        return _ELLIPSIS[:total_width]

    target_width = total_width - len(_ELLIPSIS)
    current = ""
    for char in text:
        if cell_len(current + char) > target_width:
            break
        current += char
    return f"{current}{_ELLIPSIS}"


def layout_bottom_dock_line(
    *,
    left: str,
    right: str,
    width: int,
    hide_right_when_needed: bool = False,
    prefer_hiding_right_when_left_present: bool = False,
) -> BottomDockLineLayout:
    total_width = max(1, int(width))
    resolved_left = _normalize_text(left)
    resolved_right = _normalize_text(right)

    if not resolved_left.strip() and not resolved_right.strip():
        return BottomDockLineLayout(line="", left_text="", right_text="", right_visible=False)
    if not resolved_left.strip():
        rendered_right = _truncate_text(resolved_right, total_width)
        return BottomDockLineLayout(
            line=rendered_right,
            left_text="",
            right_text=rendered_right,
            right_visible=bool(rendered_right),
        )
    if not resolved_right.strip():
        rendered_left = _truncate_text(resolved_left, total_width)
        return BottomDockLineLayout(
            line=rendered_left,
            left_text=rendered_left,
            right_text="",
            right_visible=False,
        )

    right_width = cell_len(resolved_right)
    left_width = cell_len(resolved_left)
    if left_width + right_width + 1 <= total_width:
        padding = max(1, total_width - left_width - right_width)
        return BottomDockLineLayout(
            line=f"{resolved_left}{' ' * padding}{resolved_right}",
            left_text=resolved_left,
            right_text=resolved_right,
            right_visible=True,
        )

    if prefer_hiding_right_when_left_present:
        rendered_left = _truncate_text(resolved_left, total_width)
        return BottomDockLineLayout(
            line=rendered_left,
            left_text=rendered_left,
            right_text="",
            right_visible=False,
        )

    if hide_right_when_needed:
        rendered_left = _truncate_text(resolved_left, total_width)
        return BottomDockLineLayout(
            line=rendered_left,
            left_text=rendered_left,
            right_text="",
            right_visible=False,
        )

    max_left_width = total_width - right_width - 1
    if max_left_width > 0:
        truncated_left = _truncate_text(resolved_left, max_left_width)
        meaningful_left = (
            cell_len(truncated_left.strip()) >= _MIN_MEANINGFUL_LEFT_WIDTH
            or truncated_left == resolved_left
        )
        if (
            meaningful_left
            and truncated_left
            and cell_len(truncated_left) + right_width + 1 <= total_width
        ):
            padding = max(1, total_width - cell_len(truncated_left) - right_width)
            return BottomDockLineLayout(
                line=f"{truncated_left}{' ' * padding}{resolved_right}",
                left_text=truncated_left,
                right_text=resolved_right,
                right_visible=True,
            )

    rendered_right = _truncate_text(resolved_right, total_width)
    return BottomDockLineLayout(
        line=rendered_right,
        left_text="",
        right_text=rendered_right,
        right_visible=bool(rendered_right),
    )


def compose_bottom_dock_line(
    *,
    left: str,
    right: str,
    width: int,
    hide_right_when_needed: bool = False,
    prefer_hiding_right_when_left_present: bool = False,
) -> str:
    return layout_bottom_dock_line(
        left=left,
        right=right,
        width=width,
        hide_right_when_needed=hide_right_when_needed,
        prefer_hiding_right_when_left_present=prefer_hiding_right_when_left_present,
    ).line


def compose_left_right_line(
    *,
    left: str,
    right: str,
    width: int,
    crop_one_line_fn,
    prefer_left_on_overflow: bool = True,
) -> str:
    total_width = max(1, int(width))
    resolved_left = _normalize_text(left)
    resolved_right = _normalize_text(right)

    if not resolved_left.strip():
        return crop_one_line_fn(resolved_right, total_width)
    if not resolved_right.strip():
        return crop_one_line_fn(resolved_left, total_width)
    if cell_len(resolved_left) + cell_len(resolved_right) + 1 <= total_width:
        return compose_bottom_dock_line(left=resolved_left, right=resolved_right, width=total_width)

    if prefer_left_on_overflow:
        return compose_bottom_dock_line(
            left=resolved_left,
            right=resolved_right,
            width=total_width,
            hide_right_when_needed=False,
        )

    preferred = resolved_left if prefer_left_on_overflow else resolved_right
    return crop_one_line_fn(preferred, total_width)
