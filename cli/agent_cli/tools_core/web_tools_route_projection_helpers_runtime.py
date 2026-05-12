from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.tools_core.tool_backend_registry import backend_spec_by_id
from cli.agent_cli.tools_core import web_tools_route_payload_runtime


def annotate_web_search_payload(
    payload: Dict[str, Any] | None,
    *,
    route: dict[str, Any],
    effective_backend_id: str,
    execution_path: str,
    fallback_reason: str,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
) -> Dict[str, Any]:
    return web_tools_route_payload_runtime.annotate_web_search_payload(
        payload,
        route=route,
        effective_backend_id=effective_backend_id,
        execution_path=execution_path,
        fallback_reason=fallback_reason,
        backend_spec_by_id_fn=backend_spec_by_id_fn,
    )


def inject_route_metadata_into_result(
    result: CommandExecutionResult,
    *,
    route: dict[str, Any],
    effective_backend_id: str,
    execution_path: str,
    fallback_reason: str,
) -> CommandExecutionResult:
    for event in list(getattr(result, "tool_events", []) or []):
        if getattr(event, "name", "") != "web_search":
            continue
        event.payload = annotate_web_search_payload(
            dict(getattr(event, "payload", {}) or {}),
            route=route,
            effective_backend_id=effective_backend_id,
            execution_path=execution_path,
            fallback_reason=fallback_reason,
        )
    for event in list(getattr(result, "item_events", []) or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict) or str(item.get("tool") or "").strip() != "web_search":
            continue
        result_item = item.get("result")
        if not isinstance(result_item, dict):
            continue
        structured = result_item.get("structured_content")
        if not isinstance(structured, dict):
            continue
        result_item["structured_content"] = annotate_web_search_payload(
            structured,
            route=route,
            effective_backend_id=effective_backend_id,
            execution_path=execution_path,
            fallback_reason=fallback_reason,
        )
    return result


__all__ = [
    "annotate_web_search_payload",
    "inject_route_metadata_into_result",
]
