from __future__ import annotations

from typing import Any

from textual.document._document import Selection
from textual.events import MouseDown, MouseMove, MouseUp

from cli.agent_cli.ui import transcript_preview_pane, transcript_selection_range_runtime


def on_mouse_down(area: Any, event: MouseDown) -> None:
    if event.button == 3:
        area._right_click_copy_handled_on_mouse_down = False
        click_streak = register_right_click_streak(
            area,
            int(getattr(event, "x", 0)),
            int(getattr(event, "y", 0)),
        )
        selected_text = area.selected_text.strip()
        has_selection = bool(selected_text)
        area._right_click_copy_pending = False
        area._right_click_paste_text = None
        if click_streak >= 2:
            if hasattr(event, "stop"):
                event.stop()
            if hasattr(event, "prevent_default"):
                event.prevent_default()
            candidate = selected_text or str(area._last_right_click_copied_text or "").strip()
            if candidate:
                try:
                    area.app._arm_prompt_paste_suppression(candidate)
                except Exception:
                    pass
                paste_text_into_prompt(area, candidate)
            return
        if has_selection:
            if hasattr(event, "stop"):
                event.stop()
            if hasattr(event, "prevent_default"):
                event.prevent_default()
            copied = copy_selection_to_clipboard(area)
            if copied:
                area._last_right_click_copied_text = selected_text
                clear_selection(area)
                area._right_click_copy_handled_on_mouse_down = True
            try:
                area.app._arm_prompt_paste_suppression()
            except Exception:
                pass
        return
    if event.button != 1:
        return
    if hasattr(event, "stop"):
        event.stop()
    if hasattr(event, "prevent_default"):
        event.prevent_default()
    location = area.get_target_document_location(event)
    row, column = location
    click_streak = register_click_streak(
        area, int(getattr(event, "x", 0)), int(getattr(event, "y", 0))
    )
    area._preview_click_candidate = None
    if click_streak >= 4:
        select_all_document(area)
        area._drag_anchor_location = None
        area._is_drag_selecting = False
        area._suppress_left_mouse_up_copy = True
        try:
            area.release_mouse()
        except Exception:
            pass
        return
    if click_streak == 2:
        select_word_at(area, row, column)
        area._drag_anchor_location = area.selection.start
        area._is_drag_selecting = True
        area.capture_mouse()
        return
    if click_streak >= 3:
        area.select_line(row)
        area._drag_anchor_location = area.selection.start
        area._is_drag_selecting = True
        area.capture_mouse()
        return
    area.selection = Selection.cursor(location)
    area._drag_anchor_location = location
    area._preview_click_candidate = location
    area._is_drag_selecting = True
    area.capture_mouse()


def on_mouse_move(area: Any, event: MouseMove) -> None:
    if not area._is_drag_selecting or area._drag_anchor_location is None:
        try:
            location = area.get_target_document_location(event)
        except Exception:
            transcript_preview_pane.clear_hover_target(area)
            return
        transcript_preview_pane.update_hover_target_for_area(area, location)
        return
    if hasattr(event, "stop"):
        event.stop()
    if hasattr(event, "prevent_default"):
        event.prevent_default()
    target = area.get_target_document_location(event)
    current_selection = area.selection
    transcript_preview_pane.clear_hover_target(area)
    if current_selection.start == area._drag_anchor_location and current_selection.end == target:
        return
    area._preview_click_candidate = None
    area.selection = Selection(area._drag_anchor_location, target)


def on_mouse_up(area: Any, event: MouseUp) -> None:
    end_drag_selection(area)
    if event.button not in {1, 3}:
        return
    selected_text = area.selected_text.strip()
    if event.button == 3:
        copied = False
        copied_text = ""
        paste_text = str(area._right_click_paste_text or "").strip()
        handled_on_mouse_down = bool(
            getattr(area, "_right_click_copy_handled_on_mouse_down", False)
        )
        if not handled_on_mouse_down and area._right_click_copy_pending:
            copied = copy_selection_to_clipboard(area)
            if copied:
                copied_text = selected_text
        elif not handled_on_mouse_down and selected_text:
            copied = copy_selection_to_clipboard(area)
            if copied:
                copied_text = selected_text
        if copied:
            area._last_right_click_copied_text = copied_text
            clear_selection(area)
        if paste_text:
            paste_text_into_prompt(area, paste_text)
        area._right_click_copy_pending = False
        area._right_click_copy_handled_on_mouse_down = False
        area._right_click_paste_text = None
        if copied:
            try:
                area.app._arm_prompt_paste_suppression()
            except Exception:
                pass
            if hasattr(event, "stop"):
                event.stop()
            if hasattr(event, "prevent_default"):
                event.prevent_default()
        return
    if area._suppress_left_mouse_up_copy:
        area._suppress_left_mouse_up_copy = False
        area._preview_click_candidate = None
        try:
            area.app._focus_input()
        except Exception:
            pass
        return
    click_candidate = getattr(area, "_preview_click_candidate", None)
    if (
        click_candidate is not None
        and not selected_text
        and getattr(area, "_click_streak", 0) == 1
        and transcript_preview_pane.open_preview_target_for_area(area, click_candidate)
    ):
        area._preview_click_candidate = None
        try:
            area.app._focus_input()
        except Exception:
            pass
        if hasattr(event, "stop"):
            event.stop()
        if hasattr(event, "prevent_default"):
            event.prevent_default()
        return
    area._preview_click_candidate = None
    copy_selection_to_clipboard(area)
    try:
        area.app._focus_input()
    except Exception:
        pass


def copy_selection_to_clipboard(area: Any) -> bool:
    selected_text = area.selected_text.strip()
    if not selected_text:
        return False
    area.app.copy_to_clipboard(selected_text)
    return True


def clear_selection(area: Any) -> None:
    try:
        area.selection = Selection.cursor(area.selection.end)
    except Exception:
        return


def on_leave(area: Any, _event: Any) -> None:
    transcript_preview_pane.clear_hover_target(area)


def paste_text_into_prompt(area: Any, text: str) -> None:
    paste_text = str(text or "")
    if not paste_text:
        return
    try:
        area.app._arm_prompt_paste_suppression()
    except Exception:
        pass
    try:
        area.app._insert_paste_text(paste_text)
        area.app._refresh_prompt_composer()
        area.app._focus_input()
    except Exception:
        return


def register_click_streak(area: Any, x: int, y: int) -> int:
    return transcript_selection_range_runtime.register_click_streak(area, x, y)


def register_right_click_streak(area: Any, x: int, y: int) -> int:
    return transcript_selection_range_runtime.register_right_click_streak(area, x, y)


def end_drag_selection(area: Any) -> None:
    if not area._is_drag_selecting:
        return
    area._is_drag_selecting = False
    area._drag_anchor_location = None
    try:
        area.release_mouse()
    except Exception:
        pass


def select_word_at(area: Any, row: int, column: int) -> None:
    transcript_selection_range_runtime.select_word_at(area, row, column)


def select_all_document(area: Any) -> None:
    try:
        area.select_all()
        return
    except Exception:
        pass
    try:
        line_count = int(getattr(area.document, "line_count", 0) or 0)
    except Exception:
        line_count = 0
    if line_count <= 0:
        area.selection = Selection.cursor((0, 0))
        return
    last_row = line_count - 1
    try:
        last_column = len(area.document[last_row])
    except Exception:
        last_column = 0
    area.selection = Selection((0, 0), (last_row, last_column))
