from __future__ import annotations

from typing import Any

from cli.agent_cli.debug_timeline import (
    log_timeline,
    timeline_debug_enabled,
)
from cli.agent_cli.models import (
    PromptAttachment,
    PromptResponse,
    ReferenceContextItem,
)
from cli.agent_cli.runtime_runs import RunStatus
from cli.agent_cli.runtime_services import (
    prompt_turn_context_runtime as prompt_turn_context_runtime_service,
)
from cli.agent_cli.runtime_services import (
    prompt_turn_execution_runtime as prompt_turn_execution_runtime_service,
)
from cli.agent_cli.runtime_services import (
    prompt_turn_handle_runtime as prompt_turn_handle_runtime_helpers,
)
from cli.agent_cli.runtime_services import (
    prompt_turn_history_runtime as prompt_turn_history_runtime_service,
)
from cli.agent_cli.runtime_services import (
    prompt_turn_history_state_runtime as prompt_turn_history_state_runtime_helpers,
)
from cli.agent_cli.runtime_services import (
    prompt_turn_projection_runtime as prompt_turn_projection_runtime_service,
)
from cli.agent_cli.runtime_services import (
    prompt_turn_reconstruction_runtime as prompt_turn_reconstruction_runtime_service,
)
from cli.agent_cli.runtime_services import (
    prompt_turn_run_state_runtime as prompt_turn_run_state_runtime_service,
)
from cli.agent_cli.runtime_services import (
    prompt_turn_runtime_helpers as prompt_turn_runtime_helpers_service,
)


def merge_protocol_diagnostics(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    return prompt_turn_runtime_helpers_service.merge_protocol_diagnostics(*payloads)


def assistant_text_from_turn_events(turn_events: Any) -> str:
    return prompt_turn_projection_runtime_service.assistant_text_from_turn_events(turn_events)


def turn_events_have_structured_tool_items(turn_events: Any) -> bool:
    return prompt_turn_projection_runtime_service.turn_events_have_structured_tool_items(
        turn_events
    )


def turn_replay_requires_structured_tool_output(tool_events: Any) -> bool:
    return prompt_turn_projection_runtime_service.turn_replay_requires_structured_tool_output(
        tool_events
    )


def response_items_with_canonical_final_message(
    response_items: list[dict[str, Any]],
    turn_events: Any,
) -> list[dict[str, Any]]:
    return prompt_turn_projection_runtime_service.response_items_with_canonical_final_message(
        response_items,
        turn_events,
        assistant_text_from_turn_events_fn=assistant_text_from_turn_events,
    )


def preferred_assistant_turn_text(
    *,
    turn_events: Any,
    assistant_history_text: str,
    response_item_text: str,
    assistant_fallback_text: str,
) -> str:
    return prompt_turn_projection_runtime_service.preferred_assistant_turn_text(
        turn_events=turn_events,
        assistant_history_text=assistant_history_text,
        response_item_text=response_item_text,
        assistant_fallback_text=assistant_fallback_text,
        assistant_text_from_turn_events_fn=assistant_text_from_turn_events,
        turn_events_have_structured_tool_items_fn=turn_events_have_structured_tool_items,
    )


_preview_text = prompt_turn_run_state_runtime_service.preview_text
_turn_run_id = prompt_turn_run_state_runtime_service.turn_run_id
_turn_run_manager = prompt_turn_run_state_runtime_service.turn_run_manager
_safe_turn_run_create = prompt_turn_run_state_runtime_service.safe_turn_run_create
_safe_turn_run_update = prompt_turn_run_state_runtime_service.safe_turn_run_update
_safe_turn_run_finish = prompt_turn_run_state_runtime_service.safe_turn_run_finish
_turn_cancelled = prompt_turn_run_state_runtime_service.turn_cancelled
_payload_indicates_timeout = prompt_turn_run_state_runtime_service.payload_indicates_timeout
_turn_timed_out = prompt_turn_run_state_runtime_service.turn_timed_out


def planner_conversation_input_items(runtime: Any) -> list[dict[str, Any]]:
    turn_items = runtime._planner_conversation_turn_items()
    if turn_items:
        return turn_items[-runtime._PLANNER_HISTORY_LIMIT_MESSAGES :]
    items: list[dict[str, Any]] = []
    for item in list(runtime._planner_input_items or []):
        normalized = runtime._normalized_planner_input_item(item)
        if normalized is not None:
            items.append(normalized)
    if items:
        return items[-runtime._PLANNER_HISTORY_LIMIT_MESSAGES :]
    return runtime._planner_history_input_items(runtime._planner_history())


def turn_used_provider(turn: dict[str, Any]) -> bool:
    return prompt_turn_projection_runtime_service.turn_used_provider(
        turn,
        turn_events_have_structured_tool_items_fn=turn_events_have_structured_tool_items,
    )


def planner_history(runtime: Any) -> list[dict[str, str]]:
    return prompt_turn_history_runtime_service.planner_history(runtime)


def append_context_history_item(runtime: Any, target: str, item: dict[str, str]) -> None:
    prompt_turn_context_runtime_service.append_context_history_item(runtime, target, item)


def append_reference_context_item(runtime: Any, item: dict[str, Any]) -> None:
    prompt_turn_context_runtime_service.append_reference_context_item(runtime, item)


def append_history_turn(runtime: Any, turn: dict[str, Any]) -> None:
    prompt_turn_history_state_runtime_helpers.append_history_turn(runtime, turn)


def append_history(runtime: Any, role: str, content: str) -> None:
    prompt_turn_history_state_runtime_helpers.append_history(runtime, role, content)


def apply_compaction_state(runtime: Any, replacement_history: list[dict[str, str]]) -> None:
    prompt_turn_history_state_runtime_helpers.apply_compaction_state(runtime, replacement_history)


def maybe_auto_compact_history(runtime: Any) -> None:
    prompt_turn_history_state_runtime_helpers.maybe_auto_compact_history(runtime)


def compact_history(
    runtime: Any,
    *,
    reason: str,
    trigger: str,
    instructions: str = "",
    prefer_model_summary: bool = True,
) -> dict[str, Any]:
    return prompt_turn_history_state_runtime_helpers.compact_history(
        runtime,
        reason=reason,
        trigger=trigger,
        instructions=instructions,
        prefer_model_summary=prefer_model_summary,
    )


def append_rollout_item(runtime: Any, payload: dict[str, Any]) -> None:
    prompt_turn_reconstruction_runtime_service.append_rollout_item(runtime, payload)


def turn_context_rollout_items(
    runtime: Any,
    *,
    pending_environment_messages: list[dict[str, str]],
    pending_context_messages: list[dict[str, str]],
    pending_context_items: list[ReferenceContextItem],
    next_environment_snapshot: dict[str, Any],
    next_workspace_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    return prompt_turn_context_runtime_service.turn_context_rollout_items(
        runtime,
        pending_environment_messages=pending_environment_messages,
        pending_context_messages=pending_context_messages,
        pending_context_items=pending_context_items,
        next_environment_snapshot=next_environment_snapshot,
        next_workspace_snapshot=next_workspace_snapshot,
    )


def apply_turn_context_updates(
    runtime: Any,
    *,
    pending_environment_messages: list[dict[str, str]],
    pending_context_messages: list[dict[str, str]],
    pending_context_items: list[ReferenceContextItem],
    next_environment_snapshot: dict[str, Any],
    next_workspace_snapshot: dict[str, Any],
) -> None:
    prompt_turn_context_runtime_service.apply_turn_context_updates(
        runtime,
        pending_environment_messages=pending_environment_messages,
        pending_context_messages=pending_context_messages,
        pending_context_items=pending_context_items,
        next_environment_snapshot=next_environment_snapshot,
        next_workspace_snapshot=next_workspace_snapshot,
    )


def handle_prompt(
    runtime: Any,
    text: str,
    *,
    attachments: list[PromptAttachment] | None = None,
) -> PromptResponse:
    text = (text or "").strip()
    prompt_attachments = list(attachments or [])
    if timeline_debug_enabled():
        log_timeline(
            "runtime.handle_prompt.started",
            thread_id=str(runtime.thread_id or "").strip() or None,
            user_text=text,
            attachment_count=len(prompt_attachments),
        )
    if not text:
        return runtime._build_response(
            user_text="",
            assistant_text="请输入命令或问题。",
            attachments=prompt_attachments,
            tool_events=[],
            source_text="idle",
            handled_as_command=False,
        )

    run_token = runtime._begin_run(text)
    turn_run_id = _turn_run_id(run_token)
    _safe_turn_run_create(runtime, run_id=turn_run_id, text=text)
    _safe_turn_run_update(
        runtime,
        turn_run_id,
        status=RunStatus.RUNNING,
        summary=_preview_text(text) or "running",
        payload={
            "active_run_token": run_token,
            "handled_as_command": bool(text.startswith("/")),
        },
    )
    state = prompt_turn_handle_runtime_helpers.init_handle_prompt_state(text, prompt_attachments)
    state["next_environment_snapshot"] = dict(runtime._environment_context_snapshot or {})
    state["next_workspace_snapshot"] = dict(runtime._workspace_context_snapshot or {})
    prompt_turn_handle_runtime_helpers.emit_live_turn_event(
        runtime, state, {"type": "turn.started"}
    )
    try:
        if text.startswith("/"):
            command_result = runtime._run_command_text_result(text)
            prompt_turn_handle_runtime_helpers.apply_command_result(
                runtime, state, text, command_result
            )
        else:
            if runtime._is_interrupt_requested():
                if timeline_debug_enabled():
                    log_timeline(
                        "runtime.handle_prompt.preflight_interrupt",
                        thread_id=str(runtime.thread_id or "").strip() or None,
                        user_text=text,
                        handled_as_command=False,
                    )
                state["assistant_text"], state["events"] = runtime._interrupt_tuple()
            else:
                planned = None
                if (
                    runtime._implicit_local_plan_allowed()
                    or runtime._stateful_local_plan_allowed(text)
                    or runtime._provider_ready_local_plan_allowed(text)
                ):
                    try:
                        planned = runtime._try_execute_local_plan(text)
                    except AttributeError:
                        planned = None
                if planned is not None:
                    prompt_turn_handle_runtime_helpers.apply_planned_result(
                        runtime, state, text, planned
                    )
                else:
                    planned_prompt = prompt_turn_execution_runtime_service.execute_planned_prompt(
                        runtime,
                        text,
                        prompt_attachments=prompt_attachments,
                        emit_live_turn_event_fn=lambda event: prompt_turn_handle_runtime_helpers.emit_live_turn_event(
                            runtime,
                            state,
                            event,
                        ),
                    )
                    prompt_turn_handle_runtime_helpers.apply_planned_prompt_result(
                        state, planned_prompt, text
                    )
            prompt_turn_handle_runtime_helpers.apply_post_prompt_updates(runtime, state, text)
    except Exception as exc:
        _safe_turn_run_finish(
            runtime,
            turn_run_id,
            failed=True,
            summary=_preview_text(f"{type(exc).__name__}: {exc}") or "failed",
            payload={
                "active_run_token": run_token,
                "error_type": type(exc).__name__,
                "error_text": str(exc),
            },
        )
        raise
    finally:
        runtime._finish_run(run_token)
    response = runtime._build_response(
        user_text=state["user_text"],
        assistant_text=state["assistant_text"],
        command_display_text=state["command_display_text"],
        commentary_text=state["commentary_text"],
        response_items=state["response_items"],
        attachments=prompt_attachments,
        reference_context_items=state["pending_context_items"],
        tool_events=state["events"],
        extra_activity_events=state["extra_activity_events"],
        protocol_diagnostics=state["protocol_diagnostics"],
        source_text=state["source_text"],
        handled_as_command=state["handled_as_command"],
        plan=state["response_plan"],
        timings=state["timings"],
        turn_events=state["turn_events"] or None,
    )
    prompt_turn_handle_runtime_helpers.replay_response_turn_events(runtime, state, response)
    prompt_turn_handle_runtime_helpers.persist_response(runtime, state, response)
    if timeline_debug_enabled():
        log_timeline(
            "runtime.handle_prompt.completed",
            thread_id=str(runtime.thread_id or "").strip() or None,
            user_text=state["user_text"],
            handled_as_command=state["handled_as_command"],
            assistant_text_preview=state["assistant_text"][:200],
            tool_event_count=len(state["events"]),
            response_item_count=len(list(response.response_items or [])),
            timings=dict(response.timings or {}),
        )
    prompt_turn_runtime_helpers_service.finish_turn_run(
        runtime,
        state=state,
        run_token=run_token,
        turn_run_id=turn_run_id,
        preview_text_fn=_preview_text,
        safe_turn_run_update_fn=_safe_turn_run_update,
        safe_turn_run_finish_fn=_safe_turn_run_finish,
        turn_cancelled_fn=_turn_cancelled,
        turn_timed_out_fn=_turn_timed_out,
    )
    return response
