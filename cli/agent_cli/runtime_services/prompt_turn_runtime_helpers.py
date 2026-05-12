from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_runs import RunStatus


def merge_protocol_diagnostics(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if isinstance(merged.get(key), dict) and isinstance(value, dict):
                merged[key] = {**dict(merged[key]), **dict(value)}
            else:
                merged[key] = value
    return merged


def finish_turn_run(runtime: Any, *, state: dict[str, Any], run_token: str, turn_run_id: str, preview_text_fn: Any, safe_turn_run_update_fn: Any, safe_turn_run_finish_fn: Any, turn_cancelled_fn: Any, turn_timed_out_fn: Any) -> None:
    cancelled = turn_cancelled_fn(state)
    timed_out = turn_timed_out_fn(state)
    if cancelled:
        safe_turn_run_update_fn(
            runtime,
            turn_run_id,
            status=RunStatus.CANCELLED,
            summary="cancelled",
            payload={
                "active_run_token": run_token,
                "assistant_text": state["assistant_text"],
                "tool_event_count": len(list(state["events"] or [])),
            },
        )
        return
    if timed_out:
        safe_turn_run_finish_fn(
            runtime,
            turn_run_id,
            timed_out=True,
            summary="timed out",
            payload={
                "active_run_token": run_token,
                "assistant_text": state["assistant_text"],
                "source_text": state["source_text"],
                "handled_as_command": bool(state["handled_as_command"]),
                "tool_event_count": len(list(state["events"] or [])),
                "protocol_diagnostics": dict(state["protocol_diagnostics"] or {}),
            },
        )
        return
    safe_turn_run_finish_fn(
        runtime,
        turn_run_id,
        failed=False,
        summary=preview_text_fn(state["assistant_text"]) or preview_text_fn(state["source_text"]) or "completed",
        payload={
            "active_run_token": run_token,
            "assistant_text": state["assistant_text"],
            "source_text": state["source_text"],
            "handled_as_command": bool(state["handled_as_command"]),
            "tool_event_count": len(list(state["events"] or [])),
        },
    )
