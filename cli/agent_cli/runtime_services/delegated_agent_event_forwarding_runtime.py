from __future__ import annotations

import json
import time
import uuid
from typing import Any

_FORWARDED_EVENT_TYPES = {"item.started", "item.updated", "item.completed", "provider.retry"}
_PROGRESS_ITEM_TYPES = {"command_execution", "mcp_tool_call", "function_call", "custom_tool_call"}


def runtime_turn_event_emitter(runtime: Any):
    emitter = getattr(runtime, "_emit_turn_event", None)
    if callable(emitter):
        return emitter
    callback = getattr(runtime, "turn_event_callback", None)
    if callable(callback):
        return lambda event: callback(dict(event))
    return None


def emit_delegated_task_started(
    runtime: Any,
    *,
    task_id: str,
    task_text: str,
    description: str,
    role: str,
    subagent_type: str | None,
) -> None:
    emitter = runtime_turn_event_emitter(runtime)
    if not callable(emitter):
        return
    emitter(
        {
            "type": "system",
            "subtype": "task_started",
            "task_id": task_id,
            "description": str(description or task_text or "delegated agent").strip(),
            "task_type": "local_agent",
            "prompt": str(task_text or ""),
            "role": str(role or "").strip() or "subagent",
            "subagent_type": str(subagent_type or "").strip() or None,
        }
    )


def delegated_child_turn_event_callback(
    runtime: Any,
    *,
    task_id: str | None = None,
    task_text: str = "",
    description: str = "",
    role: str = "subagent",
    subagent_type: str | None = None,
):
    emitter = runtime_turn_event_emitter(runtime)
    if not callable(emitter):
        return _noop_turn_event_callback
    resolved_task_id = str(task_id or "").strip() or f"delegate_{uuid.uuid4().hex[:12]}"
    resolved_description = str(description or task_text or "delegated agent").strip()
    started_at = time.perf_counter()
    progress_state = {"tool_uses": 0}
    item_ids: dict[tuple[str, str, str, str], str] = {}
    loose_item_ids: dict[tuple[str, str, str], str] = {}
    used_item_ids: set[str] = set()

    def _callback(event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        event_type = str(event.get("type") or "").strip()
        if event_type not in _FORWARDED_EVENT_TYPES:
            return
        forwarded = _delegated_event(
            event,
            task_id=resolved_task_id,
            role=role,
            subagent_type=subagent_type,
            item_id_mapper=lambda item: _mapped_item_id(
                item,
                event_type=event_type,
                task_id=resolved_task_id,
                item_ids=item_ids,
                loose_item_ids=loose_item_ids,
                used_item_ids=used_item_ids,
            ),
        )
        if _should_emit_progress(forwarded):
            progress_state["tool_uses"] = int(progress_state.get("tool_uses") or 0) + 1
            emitter(
                _task_progress_event(
                    forwarded,
                    task_id=resolved_task_id,
                    description=resolved_description,
                    started_at=started_at,
                    tool_uses=progress_state["tool_uses"],
                )
            )
        emitter(forwarded)

    return _callback


def _noop_turn_event_callback(_event: dict[str, Any]) -> None:
    """Keep delegated child requests on streaming transport even without a UI sink."""


def _delegated_event(
    event: dict[str, Any],
    *,
    task_id: str,
    role: str,
    subagent_type: str | None,
    item_id_mapper=None,
) -> dict[str, Any]:
    copied = dict(event)
    copied["delegated_agent"] = {
        "task_id": task_id,
        "role": str(role or "").strip() or "subagent",
        "subagent_type": str(subagent_type or "").strip() or None,
    }
    item = copied.get("item")
    if isinstance(item, dict):
        copied["item"] = _delegated_item(
            item,
            task_id=task_id,
            role=role,
            subagent_type=subagent_type,
            item_id_mapper=item_id_mapper,
        )
    return copied


def _delegated_item(
    item: dict[str, Any],
    *,
    task_id: str,
    role: str,
    subagent_type: str | None,
    item_id_mapper=None,
) -> dict[str, Any]:
    copied = dict(item)
    item_id = str(copied.get("id") or copied.get("call_id") or "").strip()
    if item_id:
        mapped_id = item_id_mapper(item) if callable(item_id_mapper) else ""
        copied["id"] = mapped_id or f"{task_id}:{item_id}"
    call_id = str(copied.get("call_id") or "").strip()
    if call_id:
        copied["call_id"] = f"{task_id}:{call_id}"
    copied["delegated_agent"] = {
        "task_id": task_id,
        "role": str(role or "").strip() or "subagent",
        "subagent_type": str(subagent_type or "").strip() or None,
    }
    return copied


def _mapped_item_id(
    item: dict[str, Any],
    *,
    event_type: str,
    task_id: str,
    item_ids: dict[tuple[str, str, str, str], str],
    loose_item_ids: dict[tuple[str, str, str], str],
    used_item_ids: set[str],
) -> str:
    original_id = str(item.get("id") or item.get("call_id") or "").strip()
    if not original_id:
        return ""
    key = _item_identity_key(item, original_id=original_id)
    existing = item_ids.get(key)
    if existing:
        return existing
    loose_key = key[:3]
    if str(event_type or "").strip() != "item.started":
        loose_existing = loose_item_ids.get(loose_key)
        if loose_existing:
            item_ids[key] = loose_existing
            return loose_existing
    base = f"{task_id}:{original_id}"
    candidate = base
    suffix = 2
    while candidate in used_item_ids:
        candidate = f"{base}:{suffix}"
        suffix += 1
    item_ids[key] = candidate
    loose_item_ids.setdefault(loose_key, candidate)
    used_item_ids.add(candidate)
    return candidate


def _item_identity_key(item: dict[str, Any], *, original_id: str) -> tuple[str, str, str, str]:
    arguments = item.get("arguments")
    if arguments is None:
        arguments = item.get("function_call_arguments")
    try:
        arguments_key = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
    except TypeError:
        arguments_key = repr(arguments)
    return (
        original_id,
        str(item.get("type") or "").strip(),
        _tool_name(item),
        str(item.get("command") or arguments_key or "").strip(),
    )


def _should_emit_progress(event: dict[str, Any]) -> bool:
    if str(event.get("type") or "").strip() != "item.started":
        return False
    item = event.get("item")
    if not isinstance(item, dict):
        return False
    return str(item.get("type") or "").strip() in _PROGRESS_ITEM_TYPES


def _task_progress_event(
    event: dict[str, Any],
    *,
    task_id: str,
    description: str,
    started_at: float,
    tool_uses: int,
) -> dict[str, Any]:
    item = event.get("item")
    item_map = dict(item) if isinstance(item, dict) else {}
    last_tool_name = _tool_name(item_map)
    return {
        "type": "system",
        "subtype": "task_progress",
        "task_id": task_id,
        "description": _progress_description(item_map, fallback=description),
        "usage": {
            "total_tokens": 0,
            "tool_uses": max(1, int(tool_uses)),
            "duration_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
        },
        "last_tool_name": last_tool_name or None,
    }


def _tool_name(item: dict[str, Any]) -> str:
    return str(
        item.get("tool")
        or item.get("name")
        or item.get("function_call_name")
        or item.get("type")
        or ""
    ).strip()


def _progress_description(item: dict[str, Any], *, fallback: str) -> str:
    item_type = str(item.get("type") or "").strip()
    if item_type == "command_execution":
        command = str(item.get("command") or "").strip()
        return f"Running {command}" if command else "Running command"
    tool_name = _tool_name(item)
    if item_type in {"mcp_tool_call", "function_call", "custom_tool_call"} and tool_name:
        return f"Running {tool_name}"
    return str(fallback or "delegated agent").strip()


__all__ = [
    "delegated_child_turn_event_callback",
    "emit_delegated_task_started",
    "runtime_turn_event_emitter",
]
