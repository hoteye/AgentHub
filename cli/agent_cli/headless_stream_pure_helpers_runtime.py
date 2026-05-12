from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TextIO

from cli.agent_cli.models import PromptResponse

if TYPE_CHECKING:
    from cli.agent_cli.runtime import AgentCliRuntime


def stream_prompt_jsonl(
    runner: AgentCliRuntime,
    prompt: str,
    *,
    output_stream: TextIO,
    request_id: str | None,
    codex_jsonl: bool = False,
    headless_thread_id_fn: Callable[[AgentCliRuntime], str],
    emit_reference_jsonl_event_fn: Callable[..., None],
    turn_event_signature_fn: Callable[[dict[str, Any]], str],
    turn_event_backfill_signature_fn: Callable[[dict[str, Any]], str],
    temporary_turn_event_callback_fn: Callable[[AgentCliRuntime, Any], Any],
    canonical_turn_events_fn: Callable[..., list[dict[str, Any]]],
) -> PromptResponse:
    thread_id = headless_thread_id_fn(runner)
    seen_event_signatures: set[str] = set()
    pending_codex_events: dict[str, list[dict[str, Any]]] = {}
    suppressed_codex_call_ids: set[str] = set()
    codex_item_id_by_raw_id: dict[str, str] = {}
    codex_next_item_index = 0

    def _event_seen(event: dict[str, Any]) -> bool:
        return (
            turn_event_signature_fn(event) in seen_event_signatures
            or turn_event_backfill_signature_fn(event) in seen_event_signatures
        )

    def _remember_event(event: dict[str, Any]) -> None:
        seen_event_signatures.add(turn_event_signature_fn(event))
        seen_event_signatures.add(turn_event_backfill_signature_fn(event))

    def _emit_payload(payload: dict[str, Any]) -> None:
        nonlocal codex_next_item_index
        if codex_jsonl:
            payload, codex_next_item_index = _codex_jsonl_project_event(
                payload,
                item_id_by_raw_id=codex_item_id_by_raw_id,
                next_item_index=codex_next_item_index,
            )
        emit_reference_jsonl_event_fn(
            output_stream,
            payload,
            request_id=request_id,
            codex_jsonl=codex_jsonl,
        )

    def _flush_pending_codex_events() -> None:
        if not pending_codex_events:
            return
        pending = [event for events in pending_codex_events.values() for event in events]
        pending_codex_events.clear()
        for payload in pending:
            _emit_payload(payload)

    def _emit_turn_event(event: Any) -> None:
        if not isinstance(event, dict):
            return
        payload = dict(event)
        if _event_seen(payload):
            return
        if _suppress_codex_jsonl_event(
            payload,
            codex_jsonl=codex_jsonl,
            pending_function_call_events=pending_codex_events,
            suppressed_call_ids=suppressed_codex_call_ids,
        ):
            _remember_event(payload)
            return
        if _suppress_reference_jsonl_event(payload):
            return
        _remember_event(payload)
        if _is_turn_terminal_event(payload):
            _flush_pending_codex_events()
        _emit_payload(payload)

    emit_reference_jsonl_event_fn(
        output_stream,
        {"type": "thread.started", "thread_id": thread_id},
        request_id=request_id,
        codex_jsonl=codex_jsonl,
    )
    with temporary_turn_event_callback_fn(runner, _emit_turn_event):
        response = runner.handle_prompt(prompt)
    for event in canonical_turn_events_fn(response):
        payload = dict(event)
        if _event_seen(payload):
            continue
        if _suppress_codex_jsonl_event(
            payload,
            codex_jsonl=codex_jsonl,
            pending_function_call_events=pending_codex_events,
            suppressed_call_ids=suppressed_codex_call_ids,
        ):
            _remember_event(payload)
            continue
        if _suppress_reference_jsonl_event(payload):
            continue
        _remember_event(payload)
        if _is_turn_terminal_event(payload):
            _flush_pending_codex_events()
        _emit_payload(payload)
    _flush_pending_codex_events()
    return response


def _suppress_codex_jsonl_event(
    event: dict[str, Any],
    *,
    codex_jsonl: bool,
    pending_function_call_events: dict[str, list[dict[str, Any]]],
    suppressed_call_ids: set[str],
) -> bool:
    if not codex_jsonl:
        return False
    item = event.get("item")
    if not isinstance(item, dict):
        return False
    item_type = str(item.get("type") or "").strip()
    call_id = str(item.get("call_id") or item.get("id") or "").strip()
    if item_type in _CODEX_TYPED_TOOL_ITEM_TYPES and call_id:
        suppressed_call_ids.add(call_id)
        pending_function_call_events.pop(call_id, None)
        return False
    if item_type != "function_call" or not call_id:
        return False
    if call_id in suppressed_call_ids:
        return True
    pending_function_call_events.setdefault(call_id, []).append(dict(event))
    return True


def _codex_jsonl_project_event(
    event: dict[str, Any],
    *,
    item_id_by_raw_id: dict[str, str],
    next_item_index: int,
) -> tuple[dict[str, Any], int]:
    projected = dict(event)
    item = projected.get("item")
    if not isinstance(item, dict):
        return _codex_jsonl_project_turn_event(projected), next_item_index
    item_type = str(item.get("type") or "").strip()
    raw_id = str(item.get("id") or item.get("call_id") or "").strip()
    item_id = item_id_by_raw_id.get(raw_id) if raw_id else None
    if item_id is None:
        item_id = f"item_{next_item_index}"
        next_item_index += 1
        if raw_id:
            item_id_by_raw_id[raw_id] = item_id
    if str(projected.get("type") or "").strip() == "item.completed" and raw_id:
        if item_type not in {"todo_list"}:
            item_id_by_raw_id.pop(raw_id, None)
    projected["item"] = _codex_jsonl_project_item(item, item_id=item_id)
    return projected, next_item_index


def _codex_jsonl_project_turn_event(event: dict[str, Any]) -> dict[str, Any]:
    if str(event.get("type") or "").strip() != "turn.completed":
        return event
    usage = event.get("usage")
    normalized_usage = dict(usage) if isinstance(usage, dict) else {}
    return {
        **event,
        "usage": {
            "input_tokens": _codex_jsonl_usage_int(normalized_usage.get("input_tokens")),
            "cached_input_tokens": _codex_jsonl_usage_int(
                normalized_usage.get("cached_input_tokens")
            ),
            "output_tokens": _codex_jsonl_usage_int(normalized_usage.get("output_tokens")),
        },
    }


def _codex_jsonl_project_item(item: dict[str, Any], *, item_id: str) -> dict[str, Any]:
    item_type = str(item.get("type") or "").strip()
    if item_type == "agent_message":
        return {
            "id": item_id,
            "type": "agent_message",
            "text": str(item.get("text") or ""),
        }
    if item_type == "reasoning":
        return {
            "id": item_id,
            "type": "reasoning",
            "text": str(item.get("text") or ""),
        }
    if item_type == "command_execution":
        return {
            "id": item_id,
            "type": "command_execution",
            "command": str(item.get("command") or ""),
            "aggregated_output": str(item.get("aggregated_output") or ""),
            "exit_code": item.get("exit_code") if item.get("exit_code") is not None else None,
            "status": str(item.get("status") or ""),
        }
    projected = {
        key: value
        for key, value in dict(item or {}).items()
        if key
        not in {"call_id", "provider_item_id", "function_call_arguments", "function_call_name"}
    }
    projected["id"] = item_id
    return projected


def _codex_jsonl_usage_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


_CODEX_TYPED_TOOL_ITEM_TYPES: frozenset[str] = frozenset(
    {
        "command_execution",
        "mcp_tool_call",
        "todo_list",
        "file_change",
        "web_search",
        "collab_tool_call",
        "error",
    }
)


def _is_turn_terminal_event(event: dict[str, Any]) -> bool:
    return str(event.get("type") or "").strip() in {"turn.completed", "turn.failed"}


def _suppress_reference_jsonl_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("type") or "").strip()
    if event_type not in {"item.started", "item.updated"}:
        return False
    item = event.get("item")
    if not isinstance(item, dict):
        return False
    return str(item.get("type") or "").strip() in {"agent_message", "reasoning"}


def turn_event_signature(event: dict[str, Any]) -> str:
    try:
        return json.dumps(event, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(event)


@contextmanager
def temporary_activity_callback(
    runner: AgentCliRuntime,
    callback: Any,
) -> Iterator[None]:
    previous = getattr(runner, "activity_callback", None)
    runner.activity_callback = callback
    try:
        yield
    finally:
        runner.activity_callback = previous


@contextmanager
def temporary_turn_event_callback(
    runner: AgentCliRuntime,
    callback: Any,
) -> Iterator[None]:
    previous = getattr(runner, "turn_event_callback", None)
    runner.turn_event_callback = callback
    try:
        yield
    finally:
        runner.turn_event_callback = previous
