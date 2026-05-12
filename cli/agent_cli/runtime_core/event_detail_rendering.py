from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core.event_detail_rendering_runtime import (
    first_excerpt_text as _runtime_first_excerpt_text,
    render_activity_detail_for_event as _render_activity_detail_for_event,
    render_detail_for_event as _render_detail_for_event,
)


def activity_detail_for_event(event: ToolEvent) -> str:
    return _render_activity_detail_for_event(event)


def detail_for_event(event: ToolEvent) -> str:
    return _render_detail_for_event(event)


def _first_excerpt_text(payload: dict[str, Any]) -> str:
    return _runtime_first_excerpt_text(payload)
