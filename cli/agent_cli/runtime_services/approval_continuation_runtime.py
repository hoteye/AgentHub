from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_services import (
    approval_continuation_runtime_record_helpers_runtime as record_helpers,
)
from cli.agent_cli.runtime_services import (
    approval_continuation_runtime_replay_helpers_runtime as replay_helpers,
)

_CONTINUATION_KEY = record_helpers._CONTINUATION_KEY
_CONTINUATION_RESULT_KEY = record_helpers._CONTINUATION_RESULT_KEY
_SCHEMA_VERSION = record_helpers._SCHEMA_VERSION
_PREVIOUS_RESPONSE_ID_UNSUPPORTED_MARKERS = replay_helpers._PREVIOUS_RESPONSE_ID_UNSUPPORTED_MARKERS
_GENERIC_CHAT_PLANNER_KINDS = replay_helpers._GENERIC_CHAT_PLANNER_KINDS
_GENERIC_CHAT_WIRE_APIS = replay_helpers._GENERIC_CHAT_WIRE_APIS

_now_iso = record_helpers._now_iso
_dict = record_helpers._dict
_list_of_dicts = record_helpers._list_of_dicts
_first_approval_event = record_helpers._first_approval_event
_approval_id_from_event = record_helpers._approval_id_from_event
_action_id_for_approval = record_helpers._action_id_for_approval
_provider_context_from_event = record_helpers._provider_context_from_event
_continuation_record = record_helpers._continuation_record
_record_is_usable = record_helpers._record_is_usable
attach_pending_tool_continuation = record_helpers.attach_pending_tool_continuation
attach_pending_tool_continuations_for_results = (
    record_helpers.attach_pending_tool_continuations_for_results
)
runtime_from_tool_executor = record_helpers.runtime_from_tool_executor
pending_tool_continuation = record_helpers.pending_tool_continuation
_persist_metadata_updates = record_helpers._persist_metadata_updates
persist_continuation_result = record_helpers.persist_continuation_result
persisted_continuation_result = record_helpers.persisted_continuation_result
continuation_result_for_resume_only = record_helpers.continuation_result_for_resume_only

_text_mentions_previous_response_id_unsupported = (
    replay_helpers._text_mentions_previous_response_id_unsupported
)
_intent_mentions_previous_response_id_unsupported = (
    replay_helpers._intent_mentions_previous_response_id_unsupported
)
_intent_is_degraded_provider_failure = replay_helpers._intent_is_degraded_provider_failure
_runtime_provider_field = replay_helpers._runtime_provider_field
_runtime_uses_generic_chat_continuation = replay_helpers._runtime_uses_generic_chat_continuation
_degraded_generic_chat_intent = replay_helpers._degraded_generic_chat_intent
_serialized_arguments = replay_helpers._serialized_arguments
replay_items_without_orphan_tool_outputs = replay_helpers.replay_items_without_orphan_tool_outputs
_direct_tool_call_replay_items_from_provider_context = (
    replay_helpers._direct_tool_call_replay_items_from_provider_context
)
_tool_call_replay_items_from_executed_events = (
    replay_helpers._tool_call_replay_items_from_executed_events
)
_tool_call_replay_items = replay_helpers._tool_call_replay_items
_action_result_payload = replay_helpers._action_result_payload
_approved_from_decision_response = replay_helpers._approved_from_decision_response
_tool_event_for_decision = replay_helpers._tool_event_for_decision
build_approval_tool_output_items = replay_helpers.build_approval_tool_output_items


def prepare_resume_after_approval(
    runtime: Any,
    *,
    approval_id: str,
    decision_response: dict[str, Any],
) -> dict[str, Any]:
    continuation = pending_tool_continuation(runtime, approval_id)
    if not continuation:
        return {
            "continuation_attempted": False,
            "continuation_status": "missing_context",
        }
    if not _record_is_usable(continuation):
        return {
            "continuation_attempted": False,
            "continuation_status": "missing_context",
        }
    tool_output_items = build_approval_tool_output_items(
        continuation=continuation,
        decision_response=decision_response,
    )
    if not tool_output_items:
        return {
            "continuation_attempted": False,
            "continuation_status": "tool_output_shape_error",
        }
    return {
        "continuation_attempted": False,
        "continuation_status": "tool_result_built",
        "approval_id": str(continuation.get("approval_id") or "").strip(),
        "action_id": str(continuation.get("action_id") or "").strip(),
        "provider_session_kind": str(continuation.get("provider_session_kind") or "").strip(),
        "previous_response_id": str(continuation.get("previous_response_id") or "").strip(),
        "provider_call_id": str(continuation.get("provider_call_id") or "").strip(),
        "function_call_name": str(continuation.get("function_call_name") or "").strip(),
        "provider_tool_type": str(continuation.get("provider_tool_type") or "").strip(),
        "continuation_input_items": _list_of_dicts(continuation.get("continuation_input_items")),
        "tool_call_replay_items": _tool_call_replay_items(continuation),
        "replay_input_items": _list_of_dicts(continuation.get("replay_input_items")),
        "tool_output_items": tool_output_items,
    }


def resume_after_approval(runtime: Any, *, continuation_result: dict[str, Any]) -> Any | None:
    if str(continuation_result.get("continuation_status") or "") != "tool_result_built":
        return None
    previous_response_id = str(continuation_result.get("previous_response_id") or "").strip()
    tool_output_items = _list_of_dicts(continuation_result.get("tool_output_items"))
    if not tool_output_items:
        continuation_result["continuation_attempted"] = False
        continuation_result["continuation_status"] = "missing_context"
        return None
    continuation_items = _list_of_dicts(continuation_result.get("continuation_input_items"))
    tool_call_replay_items = _list_of_dicts(continuation_result.get("tool_call_replay_items"))
    replay_items = _list_of_dicts(continuation_result.get("replay_input_items"))
    if continuation_items:
        base_items = continuation_items
    elif tool_call_replay_items:
        filtered_replay_items, stripped_call_ids = replay_items_without_orphan_tool_outputs(
            replay_items
        )
        if stripped_call_ids:
            continuation_result["stripped_orphan_replay_tool_outputs"] = stripped_call_ids
        base_items = [*filtered_replay_items, *tool_call_replay_items]
    else:
        base_items = replay_items
    if _runtime_uses_generic_chat_continuation(runtime, continuation_result):
        return _degraded_generic_chat_intent(continuation_result)
    if not previous_response_id and not base_items:
        continuation_result["continuation_attempted"] = False
        continuation_result["continuation_status"] = "missing_context"
        return None
    planner = getattr(runtime, "agent", None)
    plan_fn = getattr(planner, "plan", None)
    tool_executor = getattr(runtime, "_structured_tool_executor", None)
    if not callable(plan_fn) or tool_executor is None:
        continuation_result["continuation_attempted"] = False
        continuation_result["continuation_status"] = "missing_runtime"
        return None

    def _run_resume(*, input_items: list[dict[str, Any]], resume_response_id: str | None) -> Any:
        kwargs = {
            "tool_executor": tool_executor,
            "input_items": input_items,
            "initial_previous_response_id": resume_response_id,
            "prompt_cache_key": str(getattr(runtime, "thread_id", "") or "") or None,
            "turn_event_callback": getattr(runtime, "_emit_turn_event", None),
        }
        filter_kwargs = getattr(runtime, "_filter_callable_kwargs", None)
        if not callable(filter_kwargs):
            filter_kwargs = getattr(planner, "_filter_callable_kwargs", None)
        if callable(filter_kwargs):
            kwargs = filter_kwargs(plan_fn, kwargs)
        return plan_fn("", [], **kwargs)

    input_items = [*base_items, *tool_output_items]
    try:
        intent = _run_resume(
            input_items=input_items,
            resume_response_id=previous_response_id or None,
        )
    except Exception as exc:
        if (
            previous_response_id
            and base_items
            and _text_mentions_previous_response_id_unsupported(exc)
        ):
            try:
                intent = _run_resume(
                    input_items=[*base_items, *tool_output_items],
                    resume_response_id=None,
                )
            except Exception as retry_exc:
                continuation_result["continuation_attempted"] = True
                continuation_result["continuation_status"] = "provider_rejected_context"
                continuation_result["error"] = str(retry_exc)
                continuation_result["retry_without_previous_response_id"] = True
                return None
            continuation_result["retry_without_previous_response_id"] = True
        else:
            continuation_result["continuation_attempted"] = True
            continuation_result["continuation_status"] = "failed"
            continuation_result["error"] = str(exc)
            return None
    if (
        previous_response_id
        and base_items
        and _intent_mentions_previous_response_id_unsupported(intent)
    ):
        try:
            intent = _run_resume(
                input_items=[*base_items, *tool_output_items],
                resume_response_id=None,
            )
        except Exception as exc:
            continuation_result["continuation_attempted"] = True
            continuation_result["continuation_status"] = "provider_rejected_context"
            continuation_result["error"] = str(exc)
            continuation_result["retry_without_previous_response_id"] = True
            return None
        continuation_result["retry_without_previous_response_id"] = True
        if _intent_is_degraded_provider_failure(intent):
            continuation_result["continuation_attempted"] = True
            continuation_result["continuation_status"] = "provider_rejected_context"
            continuation_result["assistant_text"] = str(getattr(intent, "assistant_text", "") or "")
            return None
    elif _intent_is_degraded_provider_failure(intent):
        continuation_result["continuation_attempted"] = True
        continuation_result["continuation_status"] = "failed"
        continuation_result["assistant_text"] = str(getattr(intent, "assistant_text", "") or "")
        return None
    continuation_result["continuation_attempted"] = True
    continuation_result["continuation_status"] = "completed"
    continuation_result["assistant_text"] = str(getattr(intent, "assistant_text", "") or "")
    return intent
