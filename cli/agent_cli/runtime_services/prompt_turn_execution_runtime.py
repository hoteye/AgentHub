from __future__ import annotations

from typing import Any
from uuid import uuid4

from cli.agent_cli.debug_timeline import (
    log_timeline,
    summarize_input_items_tail,
    timeline_debug_enabled,
)
from cli.agent_cli.models import default_response_items
from cli.agent_cli.runtime_services import (
    prompt_turn_reconstruction_runtime as prompt_turn_reconstruction_runtime_service,
)

_CONTEXT_OVERFLOW_ERROR_MARKERS = (
    "prompt is too long",
    "context length",
    "context window",
    "maximum context length",
    "context_length_exceeded",
    "too many input tokens",
    "too many tokens",
    "input is too long",
)


def _provider_request_session_id(runtime: Any) -> str:
    thread_id = str(getattr(runtime, "thread_id", "") or "").strip()
    if thread_id:
        return thread_id
    existing = str(getattr(runtime, "_provider_request_session_id", "") or "").strip()
    if existing:
        return existing
    generated = str(uuid4())
    runtime._provider_request_session_id = generated
    return generated


def _provider_error_diagnostics(exc: Exception) -> dict[str, Any]:
    raw = getattr(exc, "agenthub_provider_diagnostics", None)
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _is_provider_context_overflow_error(exc: Exception) -> bool:
    diagnostics = _provider_error_diagnostics(exc)
    if str(diagnostics.get("classification") or "").strip().lower() == "prompt_too_long":
        return True
    text = f"{type(exc).__name__}: {exc}".strip().lower()
    if not text:
        text = ""
    candidates = [text]
    for key in ("failure_code", "code", "error_code", "reason", "message"):
        value = diagnostics.get(key)
        if value is None:
            continue
        candidate = str(value).strip().lower()
        if candidate:
            candidates.append(candidate)
    return any(
        marker in candidate
        for candidate in candidates
        for marker in _CONTEXT_OVERFLOW_ERROR_MARKERS
    )


def _history_compaction_diagnostics(*, error_type: str, error_text: str) -> dict[str, str]:
    return {
        "mode": "reactive_retry",
        "reason": "provider_context_overflow_retry",
        "trigger_error_type": str(error_type or "").strip(),
        "trigger_error_text": str(error_text or "").strip(),
    }


def _merge_history_compaction_diagnostics(
    protocol_diagnostics: dict[str, Any] | None,
    history_compaction: dict[str, str] | None,
) -> dict[str, Any]:
    merged = dict(protocol_diagnostics or {})
    if not history_compaction:
        return merged
    existing = merged.get("history_compaction")
    if isinstance(existing, dict):
        merged["history_compaction"] = {
            **dict(existing),
            **dict(history_compaction),
        }
        return merged
    merged["history_compaction"] = dict(history_compaction)
    return merged


def _attach_history_compaction_failure_diagnostics(
    exc: Exception,
    *,
    history_compaction: dict[str, str],
) -> None:
    diagnostics = _provider_error_diagnostics(exc)
    existing = diagnostics.get("history_compaction")
    if isinstance(existing, dict):
        diagnostics["history_compaction"] = {
            **dict(existing),
            **dict(history_compaction),
        }
    else:
        diagnostics["history_compaction"] = dict(history_compaction)
    exc.agenthub_provider_diagnostics = diagnostics
    exc.agenthub_history_compaction_diagnostics = dict(diagnostics["history_compaction"])


def _emit_reactive_compaction(
    runtime: Any,
    *,
    replacement_history,
    error_type: str,
    error_text: str,
) -> None:
    metadata = _history_compaction_diagnostics(
        error_type=error_type,
        error_text=error_text,
    )
    if runtime.thread_store is not None and runtime.thread_id:
        update_active = True
        update_active_getter = getattr(runtime, "thread_store_update_active_getter", None)
        if callable(update_active_getter):
            update_active = bool(update_active_getter())
        payload = runtime.thread_store.append_compacted(
            runtime.thread_id,
            replacement_history=replacement_history,
            metadata=metadata,
            update_active=update_active,
        )
    else:
        payload = {
            "type": "compacted",
            "thread_id": str(runtime.thread_id or ""),
            "timestamp": runtime._current_datetime().isoformat(),
            "replacement_history": list(replacement_history or []),
            **metadata,
        }
    if timeline_debug_enabled():
        log_timeline(
            "runtime.conversation.compact.provider_overflow_retry",
            thread_id=runtime.thread_id,
            error_type=metadata["trigger_error_type"],
            error_text=metadata["trigger_error_text"],
            replacement_history_count=len(list(replacement_history or [])),
            replacement_history_tail=summarize_input_items_tail(
                runtime._planner_message_history_input_items(replacement_history),
                tail_len=4,
            ),
        )
    prompt_turn_reconstruction_runtime_service.append_rollout_item(runtime, payload)


def _validated_reactive_compaction_replacement_history(
    replacement_history: Any,
) -> list[dict[str, str]]:
    validated: list[dict[str, str]] = []
    for raw in list(replacement_history or []):
        if not isinstance(raw, dict):
            raise RuntimeError("invalid reactive compaction replacement history")
        role = str(raw.get("role") or "").strip().lower()
        content = str(raw.get("content") or "").strip()
        if role != "assistant" or not content.startswith("Previous conversation summary:\n"):
            raise RuntimeError("invalid reactive compaction replacement history")
        validated.append({"role": "assistant", "content": content})
    return validated


def execute_planned_prompt(
    runtime: Any,
    text: str,
    *,
    prompt_attachments,
    emit_live_turn_event_fn,
) -> dict[str, Any]:
    runtime._maybe_auto_compact_history()
    current_dt = runtime._current_datetime()
    agent_plan = runtime.agent.plan
    active_run_token_getter = getattr(runtime, "active_run_token", None)
    provider_turn_id = ""
    if callable(active_run_token_getter):
        try:
            provider_turn_id = str(active_run_token_getter() or "").strip()
        except Exception:
            provider_turn_id = ""

    def _build_planning_state() -> dict[str, Any]:
        had_environment_snapshot = bool(runtime._environment_context_snapshot)
        had_workspace_snapshot = runtime._workspace_snapshot_has_context(
            runtime._workspace_context_snapshot,
        )
        pending_environment_messages, next_environment_snapshot = (
            runtime._environment_context_turn_update(
                current_dt=current_dt,
            )
        )
        pending_context_messages, pending_context_items, next_workspace_snapshot = (
            runtime._workspace_context_turn_update()
        )
        prefer_restored_environment_history = not had_environment_snapshot and bool(
            runtime._environment_context_history
        )
        prefer_restored_workspace_history = not had_workspace_snapshot and bool(
            runtime._context_update_history
        )
        planner_history = runtime._planner_history()
        turn_prelude_items = runtime._planner_context_input_items(
            environment_snapshot=next_environment_snapshot,
            workspace_snapshot=next_workspace_snapshot,
            pending_environment_messages=pending_environment_messages,
            pending_context_messages=pending_context_messages,
            pending_context_items=pending_context_items,
            environment_baseline_missing=not had_environment_snapshot,
            workspace_baseline_missing=not had_workspace_snapshot,
            prefer_restored_environment_history=prefer_restored_environment_history,
            prefer_restored_workspace_history=prefer_restored_workspace_history,
        )
        protocol_diagnostics = runtime._request_contract_payload(
            environment_snapshot=next_environment_snapshot,
            workspace_snapshot=next_workspace_snapshot,
            prelude_items=turn_prelude_items,
        )
        planner_input_items = [*runtime._planner_conversation_input_items(), *turn_prelude_items]
        if timeline_debug_enabled():
            log_timeline(
                "runtime.handle_prompt.planner_input",
                user_text=text,
                planner_history_count=len(list(planner_history or [])),
                planner_input_count=len(list(planner_input_items or [])),
                planner_input_tail=summarize_input_items_tail(planner_input_items, tail_len=8),
                attachment_count=len(list(prompt_attachments or [])),
            )
        return {
            "pending_environment_messages": pending_environment_messages,
            "next_environment_snapshot": next_environment_snapshot,
            "pending_context_messages": pending_context_messages,
            "pending_context_items": pending_context_items,
            "next_workspace_snapshot": next_workspace_snapshot,
            "prefer_restored_environment_history": prefer_restored_environment_history,
            "prefer_restored_workspace_history": prefer_restored_workspace_history,
            "planner_history": planner_history,
            "planner_input_items": planner_input_items,
            "protocol_diagnostics": protocol_diagnostics,
        }

    def _build_plan_kwargs(planning_state: dict[str, Any]) -> dict[str, Any]:
        plan_kwargs = runtime._filter_handler_kwargs(
            agent_plan,
            {
                "history": planning_state["planner_history"],
                "tool_executor": runtime._structured_tool_executor,
                "attachments": prompt_attachments,
                "input_items": planning_state["planner_input_items"],
                "prompt_cache_key": runtime.thread_id,
                "turn_event_callback": emit_live_turn_event_fn,
                "pending_input_items_getter": getattr(
                    runtime, "take_pending_steer_input_items", None
                ),
                "current_dt": current_dt,
                "environment_snapshot": planning_state["next_environment_snapshot"],
                "provider_session_id": _provider_request_session_id(runtime),
                "provider_turn_id": provider_turn_id or None,
                "provider_sandbox_mode": str(
                    getattr(runtime.runtime_policy, "sandbox_mode", "") or ""
                ).strip()
                or None,
            },
        )
        if "input_items" in plan_kwargs:
            if "history" in plan_kwargs:
                plan_kwargs["history"] = []
            return plan_kwargs
        if "history" in plan_kwargs:
            plan_kwargs["history"] = runtime._planner_history_with_context_updates(
                planner_history=planning_state["planner_history"],
                environment_snapshot=(
                    None
                    if planning_state["prefer_restored_environment_history"]
                    else planning_state["next_environment_snapshot"]
                ),
                workspace_snapshot=(
                    None
                    if planning_state["prefer_restored_workspace_history"]
                    else planning_state["next_workspace_snapshot"]
                ),
            )
        return plan_kwargs

    planning_state = _build_planning_state()
    reactive_compaction_applied = False
    reactive_compaction_error: Exception | None = None
    try:
        intent = agent_plan(text, **_build_plan_kwargs(planning_state))
    except Exception as exc:
        if not _is_provider_context_overflow_error(exc):
            raise
        replacement_history = _validated_reactive_compaction_replacement_history(
            runtime._build_auto_compaction_replacement_history()
        )
        if not replacement_history:
            raise
        _emit_reactive_compaction(
            runtime,
            replacement_history=replacement_history,
            error_type=type(exc).__name__,
            error_text=str(exc),
        )
        reactive_compaction_applied = True
        reactive_compaction_error = exc
        planning_state = _build_planning_state()
        try:
            intent = agent_plan(text, **_build_plan_kwargs(planning_state))
        except Exception as retry_exc:
            _attach_history_compaction_failure_diagnostics(
                retry_exc,
                history_compaction=_history_compaction_diagnostics(
                    error_type=type(exc).__name__,
                    error_text=str(exc),
                ),
            )
            raise
    extra_activity_events = list(intent.activity_events or [])
    commentary_text = str(intent.commentary_text or "")
    response_items = list(intent.response_items or [])
    protocol_diagnostics = dict(planning_state["protocol_diagnostics"] or {})
    protocol_diagnostics = runtime._merge_protocol_diagnostics(
        protocol_diagnostics,
        dict(intent.protocol_diagnostics or {}),
    )
    if reactive_compaction_applied:
        protocol_diagnostics = _merge_history_compaction_diagnostics(
            protocol_diagnostics,
            _history_compaction_diagnostics(
                error_type=(
                    type(reactive_compaction_error).__name__
                    if reactive_compaction_error is not None
                    else ""
                ),
                error_text=str(reactive_compaction_error or ""),
            ),
        )
    timings = dict(intent.timings or {})
    intent_result = runtime._execute_agent_intent_result(intent)
    assistant_text = intent_result.assistant_text
    if intent.command_text and not response_items:
        response_items = list(
            default_response_items(
                commentary_text=commentary_text,
                assistant_text=str(intent.assistant_text or assistant_text or ""),
            )
        )
    if intent_result.turn_events:
        turn_events = [
            dict(item) for item in list(intent_result.turn_events or []) if isinstance(item, dict)
        ]
    elif intent_result.item_events:
        turn_events = runtime._turn_events_from_item_events(
            assistant_text=assistant_text,
            response_items=response_items,
            item_events=list(intent_result.item_events or []),
        )
    else:
        turn_events = []
    return {
        "assistant_text": assistant_text,
        "commentary_text": commentary_text,
        "response_items": response_items,
        "protocol_diagnostics": protocol_diagnostics,
        "timings": timings,
        "events": list(intent_result.tool_events or []),
        "turn_events": turn_events,
        "extra_activity_events": extra_activity_events,
        "source_text": intent.command_text or text,
        "pending_environment_messages": planning_state["pending_environment_messages"],
        "pending_context_messages": planning_state["pending_context_messages"],
        "pending_context_items": planning_state["pending_context_items"],
        "next_environment_snapshot": planning_state["next_environment_snapshot"],
        "next_workspace_snapshot": planning_state["next_workspace_snapshot"],
    }
