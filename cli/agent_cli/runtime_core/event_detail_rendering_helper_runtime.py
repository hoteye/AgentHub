from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import ToolEvent, tool_event_is_soft_failure
from cli.agent_cli.runtime_core import event_detail_rendering_approval_runtime as approval_runtime
from cli.agent_cli.runtime_core import event_detail_formatting_runtime as formatting_runtime


def render_view_image_activity(payload: dict[str, Any]) -> str:
    return formatting_runtime.render_view_image_text(payload, separator=" | ")


def render_apply_patch_activity(event: ToolEvent) -> str:
    return approval_runtime.apply_patch_activity(event.payload or {}, ok=event.ok)


def render_patch_approval_requested_activity(event: ToolEvent) -> str:
    return approval_runtime.patch_approval_requested_activity(event.payload or {}, ok=event.ok)


def render_generic_approval_requested_activity(event: ToolEvent) -> str:
    return approval_runtime.generic_approval_requested_activity(event.payload or {}, ok=event.ok)


def render_approval_list_activity(event: ToolEvent) -> str:
    return approval_runtime.approval_list_activity(event.payload or {}, ok=event.ok)


def render_approval_decision_activity(event: ToolEvent) -> str:
    return approval_runtime.approval_decision_activity(event.payload or {}, ok=event.ok)


def render_file_activity(event: ToolEvent, *, append_elapsed_detail_fn: Callable[[str, dict[str, Any]], str]) -> str:
    payload = event.payload or {}
    return formatting_runtime.render_file_activity(
        event,
        payload,
        is_soft_failure=tool_event_is_soft_failure(event),
        append_elapsed_detail_fn=append_elapsed_detail_fn,
    )


def render_web_activity(event: ToolEvent, *, append_elapsed_detail_fn: Callable[[str, dict[str, Any]], str], first_excerpt_text_fn: Callable[[dict[str, Any]], str]) -> str:
    payload = event.payload or {}
    return formatting_runtime.render_web_activity(
        event,
        payload,
        append_elapsed_detail_fn=append_elapsed_detail_fn,
        first_excerpt_text_fn=first_excerpt_text_fn,
    )


def render_prepare_send_detail(payload: dict[str, Any], *, draft_limit: int) -> str:
    return formatting_runtime.render_prepare_send_detail(payload, draft_limit=draft_limit)


def render_send_reply_detail(payload: dict[str, Any]) -> str:
    return formatting_runtime.render_send_reply_detail(payload)


def render_apply_patch_detail(event: ToolEvent) -> str:
    return approval_runtime.apply_patch_detail(event.payload or {}, ok=event.ok)


def render_approval_detail(event: ToolEvent) -> str:
    return approval_runtime.approval_detail(event.name, event.payload or {}, ok=event.ok)


def render_file_detail(event: ToolEvent) -> str:
    payload = event.payload or {}
    return formatting_runtime.render_file_detail(
        event,
        payload,
        is_soft_failure=tool_event_is_soft_failure(event),
    )


def render_web_detail(event: ToolEvent, *, first_excerpt_text_fn: Callable[[dict[str, Any]], str]) -> str:
    payload = event.payload or {}
    return formatting_runtime.render_web_detail(
        event,
        payload,
        first_excerpt_text_fn=first_excerpt_text_fn,
    )
