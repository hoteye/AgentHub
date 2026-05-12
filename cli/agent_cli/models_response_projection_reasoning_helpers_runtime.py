from __future__ import annotations

import json
from typing import Any, Dict

from cli.agent_cli import models_turn_events_helpers as models_turn_events_helpers_service
from cli.agent_cli.models import ResponseInputItem


def shared_replay_reasoning_projection(
    item: Dict[str, Any],
    *,
    source: str = "tool_history_projection",
) -> Dict[str, Any]:
    normalized = ResponseInputItem.from_dict(item).to_dict()
    if str(normalized.get("type") or "").strip().lower() != "reasoning":
        return {"input_item": None, "diagnostic": None}
    content = normalized.get("content")
    return models_turn_events_helpers_service.shared_replay_reasoning_projection_from_parts(
        explicit_text=models_turn_events_helpers_service.reasoning_explicit_text_from_turn_event_item(normalized),
        summary=normalized.get("summary"),
        encrypted_content=normalized.get("encrypted_content"),
        replay_content=list(content) if isinstance(content, list) and content else None,
        source=source,
        content_present=models_turn_events_helpers_service.reasoning_content_has_text(content),
    )


def reasoning_retention_diagnostic_key(diagnostic: Dict[str, Any]) -> str:
    try:
        return json.dumps(diagnostic, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(diagnostic)
