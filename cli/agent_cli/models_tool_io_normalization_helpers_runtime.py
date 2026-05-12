from __future__ import annotations

from typing import Any

from cli.agent_cli.models_tool_io_pure_helpers_runtime import (
    compact_argument_map,
    first_change_path,
    tool_event_payload,
)
from cli.agent_cli.web_search_argument_projection_runtime import (
    derived_web_search_arguments_from_payload as _derived_web_search_arguments_from_payload_shared,
    looks_like_web_search_result_payload as _looks_like_web_search_result_payload_shared,
    normalized_web_search_mcp_call_arguments as _normalized_web_search_mcp_call_arguments_shared,
)


def _tool_event_model() -> Any:
    from cli.agent_cli.models import ToolEvent

    return ToolEvent


def normalized_tool_events(tool_events: list[Any] | None) -> list[Any]:
    tool_event_model = _tool_event_model()
    normalized: list[Any] = []
    for raw_event in list(tool_events or []):
        if isinstance(raw_event, tool_event_model):
            normalized.append(
                tool_event_model(
                    name=str(raw_event.name or ""),
                    ok=bool(raw_event.ok),
                    summary=str(raw_event.summary or ""),
                    payload=tool_event_payload(raw_event),
                )
            )
            continue
        if isinstance(raw_event, dict):
            normalized.append(tool_event_model.from_dict(raw_event))
    return normalized


def tool_event_call_id(tool_event: Any) -> str:
    payload = tool_event_payload(tool_event)
    return str(payload.get("provider_call_id") or payload.get("call_id") or "").strip()


def tool_event_provider_item_type(tool_event: Any) -> str:
    payload = tool_event_payload(tool_event)
    return str(payload.get("provider_tool_type") or "").strip().lower()


def tool_event_provider_raw_item(tool_event: Any) -> dict[str, Any]:
    payload = tool_event_payload(tool_event)
    raw_item = payload.get("provider_raw_item")
    if isinstance(raw_item, dict):
        return dict(raw_item)
    return {}


def derived_function_call_arguments_from_payload(
    *,
    tool_name: str,
    payload: dict[str, Any],
) -> Any:
    normalized_name = str(tool_name or "").strip().lower()
    if normalized_name == "web_search":
        return compact_argument_map(_derived_web_search_arguments_from_payload_shared(payload))
    if normalized_name == "apply_patch":
        request_kind = str(payload.get("request_kind") or "").strip().lower()
        if request_kind == "structured_write":
            arguments = compact_argument_map(
                {
                    "file_path": str(payload.get("file_path") or "").strip() or first_change_path(payload),
                    "content": payload.get("content"),
                }
            )
            if arguments:
                return arguments
        if request_kind == "structured_edit":
            arguments = compact_argument_map(
                {
                    "file_path": str(payload.get("file_path") or "").strip() or first_change_path(payload),
                    "old_string": payload.get("old_string"),
                    "new_string": payload.get("new_string"),
                    "replace_all": payload.get("replace_all"),
                }
            )
            if arguments:
                return arguments
    return {}


def effective_function_call_name(tool_event: Any) -> str:
    payload = tool_event_payload(tool_event)
    explicit = str(payload.get("function_call_name") or "").strip()
    if explicit:
        return explicit
    if str(getattr(tool_event, "name", "") or "").strip() == "apply_patch":
        source_tool_name = str(payload.get("source_tool_name") or "").strip()
        if source_tool_name:
            return source_tool_name
    return str(getattr(tool_event, "name", "") or "").strip()


def normalized_web_search_turn_item_arguments(arguments: Any) -> Any:
    if not _looks_like_web_search_result_payload_shared(arguments):
        return arguments
    return _normalized_web_search_mcp_call_arguments_shared(
        {
            "tool": "web_search",
            "arguments": arguments,
            "result": {"structured_content": arguments} if isinstance(arguments, dict) else {},
        }
    )


def tool_event_function_call_arguments(tool_event: Any) -> Any:
    payload = tool_event_payload(tool_event)
    normalized_name = str(getattr(tool_event, "name", "") or "").strip()
    if "function_call_arguments" in payload:
        arguments = payload.get("function_call_arguments")
        if arguments is not None:
            return arguments
    derived_arguments = derived_function_call_arguments_from_payload(
        tool_name=normalized_name,
        payload=payload,
    )
    arguments = payload.get("arguments")
    if arguments is not None:
        if normalized_name == "web_search":
            normalized_arguments = normalized_web_search_turn_item_arguments(arguments)
            if normalized_arguments is not None:
                return normalized_arguments
        if _looks_like_web_search_result_payload_shared(arguments) and derived_arguments:
            return derived_arguments
        return arguments
    if normalized_name == "exec_command":
        argument_payload: dict[str, Any] = {"cmd": str(payload.get("command") or "").strip()}
        for key in (
            "workdir",
            "shell",
            "tty",
            "login",
            "yield_time_ms",
            "max_output_tokens",
            "sandbox_permissions",
            "justification",
            "prefix_rule",
            "additional_permissions",
        ):
            if payload.get(key) is not None:
                argument_payload[key] = payload.get(key)
        return argument_payload
    if normalized_name == "write_stdin":
        argument_payload = {"session_id": payload.get("session_id")}
        for key in ("chars", "yield_time_ms", "max_output_tokens"):
            if payload.get(key) is not None:
                argument_payload[key] = payload.get(key)
        return argument_payload
    if normalized_name == "apply_patch":
        if derived_arguments:
            return derived_arguments
        return {"patch": str(payload.get("patch") or payload.get("input") or payload.get("command") or "").strip()}
    if derived_arguments:
        return derived_arguments
    return {}


__all__ = [
    "derived_function_call_arguments_from_payload",
    "effective_function_call_name",
    "normalized_tool_events",
    "normalized_web_search_turn_item_arguments",
    "tool_event_call_id",
    "tool_event_function_call_arguments",
    "tool_event_provider_item_type",
    "tool_event_provider_raw_item",
]
