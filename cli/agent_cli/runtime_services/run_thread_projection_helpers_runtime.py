from __future__ import annotations

from typing import Any, Callable, Mapping

from cli.agent_cli.command_execution_summary_runtime import (
    command_activity_params,
    command_display_text_from_mapping,
)
from cli.agent_cli.models import ActivityEvent, ToolEvent


def resumed_planner_state(
    payload: Mapping[str, Any] | None,
    *,
    normalized_history_item_fn: Callable[[Any], Any],
    normalized_planner_input_item_fn: Callable[[Any], Any],
    planner_history_limit: int,
) -> dict[str, list[Any]]:
    planner_history: list[Any] = []
    planner_input_items: list[Any] = []
    if not isinstance(payload, Mapping):
        return {
            "planner_history": planner_history,
            "planner_input_items": planner_input_items,
        }
    for item in list(payload.get("planner_history") or []):
        normalized = normalized_history_item_fn(item)
        if normalized is not None:
            planner_history.append(normalized)
    for item in list(payload.get("planner_input_items") or []):
        normalized_item = normalized_planner_input_item_fn(item)
        if normalized_item is not None:
            planner_input_items.append(normalized_item)
    return {
        "planner_history": planner_history,
        "planner_input_items": planner_input_items[-planner_history_limit:],
    }


def filtered_delegated_agents(
    items: list[Any],
    *,
    restored_agent_ids: set[str],
) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in list(items or [])
        if isinstance(item, dict)
        and str(item.get("agent_id") or "").strip() in restored_agent_ids
    ]


def shell_started_activity(payload: Mapping[str, Any]) -> ActivityEvent:
    command = _shell_command(payload)
    command_params = command_activity_params({"command": command})
    display_command = command_display_text_from_mapping(command_params, single_line=True) or command
    return ActivityEvent(
        title=f"Running {display_command}",
        status="running",
        kind="command",
        code="command.run",
        params=command_params,
    )


def shell_output_activity(payload: Mapping[str, Any]) -> ActivityEvent | None:
    text = str(payload.get("text") or "").strip()
    if not text:
        return None
    return ActivityEvent(
        title=text[:400],
        status="info",
        detail=str(payload.get("stream") or "stdout"),
        kind="command_output",
        code="command.output",
        params={"stream": str(payload.get("stream") or "stdout")},
    )


def shell_completed_tool_event(payload: Mapping[str, Any]) -> ToolEvent:
    return ToolEvent(
        name="shell",
        ok=bool(payload.get("ok")),
        summary=_shell_completion_summary(payload),
        payload={
            "command": _shell_command(payload),
            "returncode": payload.get("returncode"),
            "stdout": payload.get("stdout") or "",
            "stderr": payload.get("stderr") or "",
            "timed_out": bool(payload.get("timed_out")),
            "interrupted": bool(payload.get("interrupted")),
            "duration_ms": payload.get("duration_ms"),
        },
    )


def running_activity_for_tool(tool_name: str) -> ActivityEvent:
    return ActivityEvent(
        title=f"Running {tool_name}",
        status="running",
        kind="tool",
        code="tool.run",
        params={"tool_name": tool_name},
    )


def plan_activity_event(plan: Mapping[str, Any]) -> ActivityEvent | None:
    steps = plan.get("steps") or []
    if not steps:
        return None
    detail = "\n".join(
        f"{index}. {step.get('tool_name')}"
        for index, step in enumerate(steps[:8], start=1)
    )
    return ActivityEvent(
        title="Updated Plan",
        status="info",
        detail=detail,
        kind="plan",
        code="plan.update",
        params={"steps": [str(step.get("tool_name") or "").strip() for step in steps[:8]]},
    )


def shell_phase(payload: Mapping[str, Any]) -> str:
    return str(payload.get("phase") or "").strip().lower()


def _shell_command(payload: Mapping[str, Any]) -> str:
    return str(payload.get("command") or "").strip() or "command"


def _shell_completion_summary(payload: Mapping[str, Any]) -> str:
    if payload.get("interrupted"):
        return "shell interrupted"
    if payload.get("timed_out"):
        return "shell timeout"
    return f"shell rc={payload.get('returncode')}"
