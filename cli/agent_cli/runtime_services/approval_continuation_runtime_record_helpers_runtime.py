from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


_CONTINUATION_KEY = "pending_tool_continuation"
_CONTINUATION_RESULT_KEY = "approval_continuation_result"
_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    return [dict(item) for item in list(value or []) if isinstance(item, dict)]


def _first_approval_event(events: Iterable[Any]) -> Any | None:
    for event in list(events or []):
        name = str(getattr(event, "name", "") or "").strip().lower()
        if name.endswith("_approval_requested"):
            return event
    return None


def _approval_id_from_event(event: Any) -> str:
    payload = _dict(getattr(event, "payload", None))
    return str(payload.get("approval_id") or "").strip()


def _action_id_for_approval(runtime: Any, approval_id: str) -> str:
    ticket = runtime.gateway_state_store.get_approval_ticket(approval_id)
    return str(getattr(ticket, "action_id", "") or "").strip() if ticket is not None else ""


def _provider_context_from_event(event: Any, *, fallback_call_id: str) -> Dict[str, Any]:
    payload = _dict(getattr(event, "payload", None))
    raw_item = _dict(payload.get("provider_raw_item"))
    return {
        "provider_call_id": str(payload.get("provider_call_id") or fallback_call_id or "").strip(),
        "function_call_name": str(payload.get("function_call_name") or "").strip(),
        "function_call_arguments": _dict(payload.get("function_call_arguments")),
        "provider_tool_type": str(payload.get("provider_tool_type") or "").strip(),
        "provider_raw_item": raw_item,
        "planner_execution_tool": str(payload.get("planner_execution_tool") or "").strip(),
    }


def _continuation_record(
    *,
    approval_id: str,
    action_id: str,
    previous_response_id: str,
    result: Any,
    approval_event: Any,
    replay_input_items: List[Dict[str, Any]],
    continuation_input_items: List[Dict[str, Any]],
    executed_item_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    provider_context = _provider_context_from_event(
        approval_event,
        fallback_call_id=str(getattr(result, "call_id", "") or "").strip(),
    )
    provider_raw_item = _dict(provider_context.get("provider_raw_item"))
    provider_session_kind = str(provider_raw_item.get("provider_session_kind") or "").strip()
    return {
        "schema_version": _SCHEMA_VERSION,
        "approval_id": approval_id,
        "action_id": action_id,
        "provider_session_kind": provider_session_kind,
        "previous_response_id": str(previous_response_id or "").strip(),
        "provider_call_id": str(provider_context.get("provider_call_id") or "").strip(),
        "function_call_name": str(provider_context.get("function_call_name") or "").strip(),
        "function_call_arguments": _dict(provider_context.get("function_call_arguments")),
        "provider_tool_type": str(provider_context.get("provider_tool_type") or "").strip(),
        "provider_raw_item": provider_raw_item,
        "planner_execution_tool": str(provider_context.get("planner_execution_tool") or "").strip(),
        "command_text": str(getattr(result, "command_text", "") or "").strip(),
        "replay_input_items": _list_of_dicts(replay_input_items),
        "continuation_input_items": _list_of_dicts(continuation_input_items),
        "executed_item_events_before_approval": _list_of_dicts(executed_item_events),
        "created_at": _now_iso(),
        "status": "pending",
    }


def _record_is_usable(record: Dict[str, Any]) -> bool:
    required = (
        "approval_id",
        "action_id",
        "previous_response_id",
        "provider_call_id",
        "function_call_name",
        "function_call_arguments",
        "replay_input_items",
    )
    return all(key in record for key in required)


def attach_pending_tool_continuation(
    runtime: Any,
    *,
    approval_event: Any,
    result: Any,
    previous_response_id: str | None,
    replay_input_items: List[Dict[str, Any]],
    continuation_input_items: List[Dict[str, Any]] | None = None,
    executed_item_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    approval_id = _approval_id_from_event(approval_event)
    if not approval_id:
        return {"continuation_status": "missing_context", "reason": "missing_approval_id"}
    action_id = _action_id_for_approval(runtime, approval_id)
    if not action_id:
        return {"continuation_status": "missing_context", "reason": "missing_action_id"}
    record = _continuation_record(
        approval_id=approval_id,
        action_id=action_id,
        previous_response_id=str(previous_response_id or "").strip(),
        result=result,
        approval_event=approval_event,
        replay_input_items=replay_input_items,
        continuation_input_items=list(continuation_input_items or []),
        executed_item_events=executed_item_events,
    )
    if not _record_is_usable(record):
        return {"continuation_status": "missing_context", "reason": "missing_required_fields"}
    action_request = runtime.gateway_state_store.get_action_request(action_id)
    approval_ticket = runtime.gateway_state_store.get_approval_ticket(approval_id)
    if action_request is None or approval_ticket is None:
        return {"continuation_status": "missing_context", "reason": "missing_gateway_record"}
    action_metadata = _dict(getattr(action_request, "metadata", None))
    action_metadata[_CONTINUATION_KEY] = dict(record)
    runtime.save_gateway_action_request(replace(action_request, metadata=action_metadata))
    ticket_metadata = _dict(getattr(approval_ticket, "metadata", None))
    ticket_metadata[_CONTINUATION_KEY] = dict(record)
    runtime.save_gateway_approval_ticket(replace(approval_ticket, metadata=ticket_metadata))
    return {"continuation_status": "pending", "approval_id": approval_id, "action_id": action_id}


def attach_pending_tool_continuations_for_results(
    runtime: Any,
    *,
    execution_results: List[Any],
    previous_response_id: str | None,
    replay_input_items: List[Dict[str, Any]],
    continuation_input_items: List[Dict[str, Any]] | None = None,
    executed_item_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    attached: List[Dict[str, Any]] = []
    for result in list(execution_results or []):
        event = _first_approval_event(getattr(result, "events", []) or [])
        if event is None:
            continue
        attached.append(
            attach_pending_tool_continuation(
                runtime,
                approval_event=event,
                result=result,
                previous_response_id=previous_response_id,
                replay_input_items=replay_input_items,
                continuation_input_items=list(continuation_input_items or []),
                executed_item_events=executed_item_events,
            )
        )
    return attached


def runtime_from_tool_executor(tool_executor: Any) -> Any | None:
    return getattr(tool_executor, "runtime_owner", None)


def pending_tool_continuation(runtime: Any, approval_id: str) -> Dict[str, Any] | None:
    ticket = runtime.gateway_state_store.get_approval_ticket(str(approval_id or "").strip())
    if ticket is None:
        return None
    action = runtime.gateway_state_store.get_action_request(str(getattr(ticket, "action_id", "") or ""))
    for item in (action, ticket):
        metadata = _dict(getattr(item, "metadata", None))
        record = _dict(metadata.get(_CONTINUATION_KEY))
        if record:
            return record
    return None


def _persist_metadata_updates(
    runtime: Any,
    *,
    approval_id: str,
    updates: Dict[str, Any],
) -> bool:
    ticket = runtime.gateway_state_store.get_approval_ticket(str(approval_id or "").strip())
    if ticket is None:
        return False
    action = runtime.gateway_state_store.get_action_request(str(getattr(ticket, "action_id", "") or ""))
    saved = False
    if action is not None:
        action_metadata = _dict(getattr(action, "metadata", None))
        action_metadata.update(updates)
        runtime.save_gateway_action_request(replace(action, metadata=action_metadata))
        saved = True
    ticket_metadata = _dict(getattr(ticket, "metadata", None))
    ticket_metadata.update(updates)
    runtime.save_gateway_approval_ticket(replace(ticket, metadata=ticket_metadata))
    return True if ticket is not None else saved


def persist_continuation_result(
    runtime: Any,
    approval_id: str,
    continuation_result: Dict[str, Any],
) -> bool:
    payload = _dict(continuation_result)
    if not payload:
        return False
    retryable = _dict(payload.get("retryable_continuation_result"))
    if not retryable and _list_of_dicts(payload.get("tool_output_items")):
        retryable = dict(payload)
        retryable["continuation_status"] = "tool_result_built"
        retryable["continuation_attempted"] = False
        retryable.pop("assistant_text", None)
        retryable.pop("error", None)
        retryable.pop("updated_at", None)
        retryable.pop("retryable_continuation_result", None)
    if retryable:
        payload["retryable_continuation_result"] = retryable
    payload["updated_at"] = _now_iso()
    return _persist_metadata_updates(
        runtime,
        approval_id=approval_id,
        updates={_CONTINUATION_RESULT_KEY: payload},
    )


def persisted_continuation_result(runtime: Any, approval_id: str) -> Dict[str, Any] | None:
    ticket = runtime.gateway_state_store.get_approval_ticket(str(approval_id or "").strip())
    if ticket is None:
        return None
    action = runtime.gateway_state_store.get_action_request(str(getattr(ticket, "action_id", "") or ""))
    for item in (action, ticket):
        metadata = _dict(getattr(item, "metadata", None))
        result = _dict(metadata.get(_CONTINUATION_RESULT_KEY))
        if result:
            return result
    return None


def continuation_result_for_resume_only(runtime: Any, approval_id: str) -> Dict[str, Any]:
    persisted = persisted_continuation_result(runtime, approval_id)
    if persisted:
        retryable = _dict(persisted.get("retryable_continuation_result"))
        if retryable:
            retryable["resume_only_from_status"] = str(persisted.get("continuation_status") or "").strip()
            return retryable
        if str(persisted.get("continuation_status") or "") == "tool_result_built":
            return persisted
    return {
        "approval_id": str(approval_id or "").strip(),
        "continuation_attempted": False,
        "continuation_status": "missing_context",
        "reason": "missing_persisted_continuation_result",
    }
