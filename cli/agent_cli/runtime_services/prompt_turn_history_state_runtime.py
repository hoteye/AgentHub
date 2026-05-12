from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cli.agent_cli.debug_timeline import (
    log_timeline,
    summarize_input_items_tail,
    timeline_debug_enabled,
)
from cli.agent_cli.models import RolloutItem
from cli.agent_cli.runtime_services import (
    context_compaction_runtime as context_compaction_runtime_service,
)
from cli.agent_cli.runtime_services import (
    prompt_turn_reconstruction_runtime as prompt_turn_reconstruction_runtime_service,
)


def append_history_turn(runtime: Any, turn: dict[str, Any]) -> None:
    payload = dict(turn or {})
    if not payload:
        return
    protocol_diagnostics = payload.get("protocol_diagnostics", {})
    provider_used = protocol_diagnostics.get("protocol_path", {}).get("provider_used", True)
    if not provider_used:
        return
    runtime.history_turns.append(payload)
    if len(runtime.history_turns) > 100:
        runtime.history_turns = runtime.history_turns[-100:]
    runtime._planner_input_items = runtime._planner_conversation_input_items()
    for context_item in list(payload.get("reference_context_items") or []):
        if isinstance(context_item, dict):
            runtime._append_reference_context_item(context_item)


def append_history(runtime: Any, role: str, content: str) -> None:
    normalized = runtime._normalized_history_item({"role": role, "content": content})
    runtime.history.append({"role": role, "content": content})
    if len(runtime.history) > 24:
        runtime.history = runtime.history[-24:]
    if normalized is not None:
        planner_item = runtime._planner_message_input_item(
            normalized["role"], normalized["content"]
        )
        if planner_item is not None:
            runtime._planner_input_items.append(planner_item)
            if len(runtime._planner_input_items) > runtime._PLANNER_HISTORY_LIMIT_MESSAGES:
                runtime._planner_input_items = runtime._planner_input_items[
                    -runtime._PLANNER_HISTORY_LIMIT_MESSAGES :
                ]


def apply_compaction_state(runtime: Any, replacement_history: list[dict[str, str]]) -> None:
    normalized_base_history: list[dict[str, str]] = []
    for item in list(replacement_history or []):
        normalized = runtime._normalized_history_item(item)
        if normalized is not None:
            normalized_base_history.append(normalized)
    runtime._base_history = normalized_base_history[-runtime._PLANNER_HISTORY_LIMIT_MESSAGES :]
    runtime.history_turns = []
    runtime.reference_context_items = []
    runtime._environment_context_snapshot = {}
    runtime._environment_context_history = []
    runtime._workspace_context_snapshot = {}
    runtime._memory_context_snapshot = {}
    runtime._context_update_history = []
    runtime.history = runtime._planner_history()
    runtime._planner_input_items = runtime._planner_base_history_input_items()


def maybe_auto_compact_history(runtime: Any) -> None:
    decision = context_compaction_runtime_service.auto_compaction_decision(runtime)
    if timeline_debug_enabled():
        log_timeline(
            "runtime.conversation.compact.pre-decision",
            thread_id=runtime.thread_id,
            **decision,
        )
    if not bool(decision.get("will_run")):
        return
    replacement_history = runtime._build_auto_compaction_replacement_history(
        prefer_model_summary=True,
    )
    if not replacement_history:
        return
    _emit_auto_compaction(runtime, replacement_history, decision)


def compact_history(
    runtime: Any,
    *,
    reason: str,
    trigger: str,
    instructions: str = "",
    prefer_model_summary: bool = True,
) -> dict[str, Any]:
    conversation_item_count = runtime._planner_conversation_item_count()
    replacement_history = runtime._build_auto_compaction_replacement_history(
        instructions=instructions,
        prefer_model_summary=prefer_model_summary,
    )
    if not replacement_history:
        return {
            "ok": False,
            "reason": "not_enough_history",
            "trigger": trigger,
            "trigger_item_count": conversation_item_count,
            "replacement_history_count": 0,
        }
    metadata: dict[str, Any] = {
        "reason": reason,
        "trigger": trigger,
        "trigger_item_count": conversation_item_count,
    }
    normalized_instructions = str(instructions or "").strip()
    if normalized_instructions:
        metadata["instructions"] = normalized_instructions
    metadata.update(dict(getattr(runtime, "_last_compaction_summary_metadata", {}) or {}))
    payload = _append_compaction_rollout_item(
        runtime,
        replacement_history,
        metadata=metadata,
    )
    prompt_turn_reconstruction_runtime_service.append_rollout_item(runtime, payload)
    return {
        "ok": True,
        "reason": reason,
        "trigger": trigger,
        "trigger_item_count": conversation_item_count,
        "replacement_history_count": len(list(replacement_history or [])),
        "payload": payload,
    }


def _emit_auto_compaction(
    runtime: Any,
    replacement_history: list[dict[str, str]],
    decision: dict[str, Any],
) -> None:
    reason = str(decision.get("trigger_reason") or "auto_pre_turn_history_limit").strip()
    metadata = {
        "reason": reason,
        "trigger_item_count": int(decision.get("conversation_item_count") or 0),
    }
    for key in ("estimated_tokens", "trigger_tokens", "context_window"):
        value = int(decision.get(key) or 0)
        if value > 0:
            metadata[key] = value
    metadata.update(dict(getattr(runtime, "_last_compaction_summary_metadata", {}) or {}))
    payload = _append_compaction_rollout_item(
        runtime,
        replacement_history,
        metadata=metadata,
    )
    if timeline_debug_enabled():
        log_timeline(
            "runtime.conversation.compact.execute",
            thread_id=runtime.thread_id,
            replacement_history_count=len(list(replacement_history or [])),
            replacement_history_tail=summarize_input_items_tail(
                runtime._planner_message_history_input_items(replacement_history),
                tail_len=4,
            ),
        )
    prompt_turn_reconstruction_runtime_service.append_rollout_item(runtime, payload)


def _append_compaction_rollout_item(
    runtime: Any,
    replacement_history: list[dict[str, str]],
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if runtime.thread_store is not None and runtime.thread_id:
        update_active = True
        update_active_getter = getattr(runtime, "thread_store_update_active_getter", None)
        if callable(update_active_getter):
            update_active = bool(update_active_getter())
        return runtime.thread_store.append_compacted(
            runtime.thread_id,
            replacement_history=replacement_history,
            metadata=metadata,
            update_active=update_active,
        )
    return RolloutItem(
        item_type="compacted",
        thread_id=str(runtime.thread_id or ""),
        timestamp=datetime.now(UTC).isoformat(),
        payload={
            "replacement_history": replacement_history,
            **dict(metadata or {}),
        },
    ).to_dict()
