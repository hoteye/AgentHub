from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cli.agent_cli.models import PromptAttachment


def init_handle_prompt_state(text: str, attachments: list[PromptAttachment]) -> dict[str, Any]:
    return {
        "user_text": text,
        "assistant_text": "",
        "command_display_text": "",
        "commentary_text": "",
        "events": [],
        "extra_activity_events": [],
        "response_items": [],
        "source_text": text,
        "handled_as_command": False,
        "response_plan": None,
        "protocol_diagnostics": {},
        "timings": {},
        "turn_events": [],
        "pending_environment_messages": [],
        "pending_context_messages": [],
        "pending_context_items": [],
        "next_environment_snapshot": {},
        "next_workspace_snapshot": {},
        "prompt_attachments": list(attachments or []),
        "emitted_turn_event_counts": {},
    }


def emit_live_turn_event(runtime: Any, state: dict[str, Any], event: dict[str, Any]) -> None:
    if not isinstance(event, dict):
        return
    signature = runtime._turn_event_replay_signature(event)
    if (
        str(event.get("type") or "").strip() == "turn.started"
        and int(state["emitted_turn_event_counts"].get(signature) or 0) > 0
    ):
        return
    state["emitted_turn_event_counts"][signature] = (
        int(state["emitted_turn_event_counts"].get(signature) or 0) + 1
    )
    runtime._emit_turn_event(dict(event))


def apply_command_result(
    runtime: Any, state: dict[str, Any], text: str, command_result: Any
) -> None:
    state["handled_as_command"] = True
    state["assistant_text"] = command_result.assistant_text
    state["command_display_text"] = str(getattr(command_result, "command_display_text", "") or "")
    state["protocol_diagnostics"] = {
        "protocol_path": {
            "kind": "host_slash_command",
            "source": "host",
            "provider_used": False,
            "parity_evaluable": False,
            "reason": "explicit_slash_command",
        }
    }
    state["events"] = list(command_result.tool_events or [])
    turn_events = [
        dict(item) for item in list(command_result.turn_events or []) if isinstance(item, dict)
    ]
    if not turn_events:
        turn_events = runtime._turn_events_from_item_events(
            assistant_text=state["assistant_text"],
            item_events=list(command_result.item_events or []),
        )
    state["turn_events"] = turn_events
    for event in state["events"]:
        runtime._apply_tool_state(event)
    runtime._append_history("user", text)
    runtime._append_history("assistant", state["assistant_text"])


def apply_planned_result(runtime: Any, state: dict[str, Any], text: str, planned: Any) -> None:
    state["assistant_text"], state["events"] = planned
    state["protocol_diagnostics"] = {
        "protocol_path": {
            "kind": "host_local_plan",
            "source": "host",
            "provider_used": False,
            "parity_evaluable": False,
            "reason": "runtime_local_plan",
        }
    }
    if runtime.last_plan is not None and runtime._last_plan_text == text:
        state["response_plan"] = dict(runtime.last_plan)


def apply_planned_prompt_result(
    state: dict[str, Any], planned_prompt: dict[str, Any], text: str
) -> None:
    state["assistant_text"] = str(planned_prompt.get("assistant_text") or "")
    state["commentary_text"] = str(planned_prompt.get("commentary_text") or "")
    state["response_items"] = list(planned_prompt.get("response_items") or [])
    state["protocol_diagnostics"] = dict(planned_prompt.get("protocol_diagnostics") or {})
    state["timings"] = dict(planned_prompt.get("timings") or {})
    state["events"] = list(planned_prompt.get("events") or [])
    state["turn_events"] = [
        dict(item)
        for item in list(planned_prompt.get("turn_events") or [])
        if isinstance(item, dict)
    ]
    state["extra_activity_events"] = list(planned_prompt.get("extra_activity_events") or [])
    state["source_text"] = str(planned_prompt.get("source_text") or text)
    state["pending_environment_messages"] = list(
        planned_prompt.get("pending_environment_messages") or []
    )
    state["pending_context_messages"] = list(planned_prompt.get("pending_context_messages") or [])
    state["pending_context_items"] = list(planned_prompt.get("pending_context_items") or [])
    state["next_environment_snapshot"] = dict(planned_prompt.get("next_environment_snapshot") or {})
    state["next_workspace_snapshot"] = dict(planned_prompt.get("next_workspace_snapshot") or {})


def apply_post_prompt_updates(runtime: Any, state: dict[str, Any], text: str) -> None:
    for event in state["events"]:
        runtime._apply_tool_state(event)
    runtime._append_history("user", text)
    runtime._append_history("assistant", state["assistant_text"])
    runtime._apply_turn_context_updates(
        pending_environment_messages=state["pending_environment_messages"],
        pending_context_messages=state["pending_context_messages"],
        pending_context_items=state["pending_context_items"],
        next_environment_snapshot=state["next_environment_snapshot"],
        next_workspace_snapshot=state["next_workspace_snapshot"],
    )


def replay_response_turn_events(runtime: Any, state: dict[str, Any], response: Any) -> None:
    for event in list(response.turn_events or []):
        if isinstance(event, dict):
            signature = runtime._turn_event_replay_signature(event)
            remaining = int(state["emitted_turn_event_counts"].get(signature) or 0)
            if remaining > 0:
                state["emitted_turn_event_counts"][signature] = remaining - 1
                continue
            runtime._emit_turn_event(dict(event))


def persist_response(runtime: Any, state: dict[str, Any], response: Any) -> None:
    if runtime.thread_store is not None and runtime.thread_id:
        update_active = True
        update_active_getter = getattr(runtime, "thread_store_update_active_getter", None)
        if callable(update_active_getter):
            update_active = bool(update_active_getter())
        prelude_items = runtime._turn_context_rollout_items(
            pending_environment_messages=state["pending_environment_messages"],
            pending_context_messages=state["pending_context_messages"],
            pending_context_items=state["pending_context_items"],
            next_environment_snapshot=state["next_environment_snapshot"],
            next_workspace_snapshot=state["next_workspace_snapshot"],
        )
        if prelude_items:
            persisted_items = runtime.thread_store.append_rollout_items(
                runtime.thread_id,
                prelude_items,
                update_active=update_active,
            )
            for item in persisted_items:
                runtime._append_rollout_item(item)
        rollout_item = runtime.thread_store.append_turn(
            runtime.thread_id,
            response,
            runtime_state=runtime._snapshot_thread_state(),
            update_active=update_active,
        )
        if isinstance(rollout_item, dict):
            runtime._append_rollout_item(rollout_item)
        return
    runtime._append_history_turn(
        {
            "turn_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "user_text": state["user_text"],
            "commentary_text": state["commentary_text"],
            "assistant_text": state["assistant_text"],
            "command_display_text": state["command_display_text"],
            "assistant_history_text": state["assistant_text"],
            "response_items": [item.to_dict() for item in list(response.response_items or [])],
            "handled_as_command": state["handled_as_command"],
            "status": dict(response.status or {}),
            "protocol_diagnostics": dict(response.protocol_diagnostics or {}),
            "runtime_state": runtime._snapshot_thread_state(),
            "attachments": [item.to_dict() for item in list(state["prompt_attachments"] or [])],
            "tool_events": [item.to_dict() for item in list(state["events"] or [])],
            "activity_events": [item.to_dict() for item in list(response.activity_events or [])],
            "reference_context_items": [
                item.to_dict() for item in list(state["pending_context_items"] or [])
            ],
            "turn_events": [
                dict(item) for item in list(response.turn_events or []) if isinstance(item, dict)
            ],
        }
    )
