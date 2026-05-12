from __future__ import annotations

from typing import Any


def _stop_and_prevent_default(event: Any) -> None:
    event.stop()
    event.prevent_default()


def handle_submission_action_key(composer: Any, event: Any) -> bool:
    if event.key == "ctrl+v":
        _stop_and_prevent_default(event)
        try:
            composer.app.paste_prompt_from_clipboard(report_empty=False)
        except Exception:
            pass
        return True
    if event.key == "enter":
        if composer.app.handle_composer_enter():
            _stop_and_prevent_default(event)
            return True
        _stop_and_prevent_default(event)
        composer.app.call_next(composer.app.action_submit_prompt)
        return True
    if event.key == "tab":
        if composer.app.complete_slash_popup():
            _stop_and_prevent_default(event)
            return True
        queue_actionable = getattr(composer.app, "_queue_prompt_actionable", None)
        if callable(queue_actionable) and bool(queue_actionable()):
            _stop_and_prevent_default(event)
            composer.app.call_next(composer.app.action_queue_prompt)
            return True
        return False
    if event.key in {"up", "ctrl+p"}:
        if composer.app.move_slash_selection(-1):
            _stop_and_prevent_default(event)
            return True
        if composer.app.browse_prompt_history(-1):
            _stop_and_prevent_default(event)
            return True
        return False
    if event.key in {"down", "ctrl+n"}:
        if composer.app.move_slash_selection(1):
            _stop_and_prevent_default(event)
            return True
        if composer.app.browse_prompt_history(1):
            _stop_and_prevent_default(event)
            return True
        return False
    return False
