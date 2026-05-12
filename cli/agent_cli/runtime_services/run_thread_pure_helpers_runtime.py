from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import PromptAttachment


def attachment_reference_path(attachment: Any) -> str:
    if isinstance(attachment, PromptAttachment):
        return str(attachment.path or attachment.name or "").strip()
    if isinstance(attachment, dict):
        return str(attachment.get("path") or attachment.get("name") or "").strip()
    return str(getattr(attachment, "path", None) or getattr(attachment, "name", None) or "").strip()


def steer_message_text(text: str, attachments: list[PromptAttachment] | None) -> str:
    lines = [str(text or "").strip()]
    reference_paths = [
        reference
        for reference in (attachment_reference_path(item) for item in list(attachments or []))
        if reference
    ]
    if reference_paths:
        lines.extend(["", "Attached references:"])
        lines.extend(f"- {path}" for path in reference_paths)
    return "\n".join(lines).strip()


def build_steer_message_input_item(
    *,
    text: str,
    attachments: list[PromptAttachment] | None,
    planner_message_input_item_builder: Callable[[str, str], Any] | None,
) -> dict[str, Any] | None:
    message_text = steer_message_text(text, attachments)
    if not message_text:
        return None
    if callable(planner_message_input_item_builder):
        try:
            item = planner_message_input_item_builder("user", message_text)
        except Exception:
            item = None
        if isinstance(item, dict):
            return dict(item)
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": message_text}],
    }


def take_pending_steer_items(items: list[Any], *, limit: int | None) -> list[dict[str, Any]]:
    if limit == 0:
        return []
    if limit is None or limit >= len(items):
        selected = [dict(item) for item in items if isinstance(item, dict)]
        items.clear()
        return selected
    selected = [dict(item) for item in items[:limit] if isinstance(item, dict)]
    del items[:limit]
    return selected
