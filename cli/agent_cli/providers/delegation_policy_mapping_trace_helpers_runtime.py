from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any


def normalized_trace_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def canonical_planner_tool_name(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    lowered = normalized.lower()
    if lowered == "agent":
        return "spawn_agent"
    if lowered == "sendmessage":
        return "send_input"
    if lowered == "wait":
        return "wait_agent"
    return normalized


def canonicalized_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(arguments or {})
    canonical_tool_name = canonical_planner_tool_name(tool_name)
    if canonical_tool_name == "spawn_agent":
        if not str(payload.get("task") or "").strip():
            prompt = str(payload.get("prompt") or payload.get("message") or "").strip()
            if prompt:
                payload["task"] = prompt
        if "async" not in payload and "run_in_background" in payload:
            payload["async"] = payload.get("run_in_background")
        payload.pop("prompt", None)
        payload.pop("run_in_background", None)
        subagent_type = str(payload.get("subagent_type") or "").strip().lower()
        if subagent_type == "explore":
            payload.setdefault("role", "subagent")
            payload.setdefault("reason", "research_side_task")
            payload.setdefault("task_shape", "read_only")
        return payload
    if canonical_tool_name == "send_input":
        if not str(payload.get("target") or "").strip():
            target = str(
                payload.get("to") or payload.get("agent_id") or payload.get("id") or ""
            ).strip()
            if target:
                payload["target"] = target
        payload.pop("to", None)
        return payload
    return payload


def canonicalized_tool_calls(tool_calls: Iterable[Any]) -> list[Any]:
    normalized_calls: list[Any] = []
    for call in list(tool_calls or []):
        canonical_name = canonical_planner_tool_name(getattr(call, "name", ""))
        canonical_arguments = canonicalized_tool_arguments(
            getattr(call, "name", ""),
            getattr(call, "arguments", {}),
        )
        if canonical_name == getattr(call, "name", ""):
            if canonical_arguments == (getattr(call, "arguments", {}) or {}):
                normalized_calls.append(call)
            else:
                normalized_calls.append(
                    SimpleNamespace(
                        name=canonical_name,
                        arguments=canonical_arguments,
                        call_id=getattr(call, "call_id", ""),
                    )
                )
            continue
        normalized_calls.append(
            SimpleNamespace(
                name=canonical_name,
                arguments=canonical_arguments,
                call_id=getattr(call, "call_id", ""),
            )
        )
    return normalized_calls


def delegation_execution_mode_and_reason(summary: dict[str, Any]) -> tuple[str, str]:
    decision = (
        str(
            summary.get("delegation_policy_decision") or summary.get("orchestration_decision") or ""
        )
        .strip()
        .lower()
    )
    if not decision or decision in {"stay_local", "none"}:
        return ("", "")
    task_shape = str(summary.get("task_shape") or "").strip().lower()
    if task_shape in {"workspace_mutating", "context_sensitive"}:
        return ("serial", f"task_shape:{task_shape}")
    if task_shape in {"long_running", "read_only"}:
        return ("parallel", f"task_shape:{task_shape}")
    wait_required = normalized_trace_bool(summary.get("wait_required"))
    if wait_required is True:
        return ("serial", "wait_required:true")
    if wait_required is False and decision in {"wait_later", "delegate_async", "delegate"}:
        return ("parallel", "wait_required:false")
    delegation_mode = str(summary.get("delegation_mode") or "").strip().lower()
    if delegation_mode == "sync":
        return ("serial", "delegation_mode:sync")
    if delegation_mode == "background":
        return ("parallel", "delegation_mode:background")
    if decision in {
        "delegate_sync",
        "wait_now",
        "delegate_and_wait",
        "resume_child",
        "close_child",
    }:
        return ("serial", f"decision:{decision}")
    if decision in {"delegate_async", "wait_later", "delegate", "wait", "retry_child"}:
        return ("parallel", f"decision:{decision}")
    return ("", "")


def orchestration_execution_mode_and_reason(summary: dict[str, Any]) -> tuple[str, str]:
    return delegation_execution_mode_and_reason(summary)


def action_execution_mode(action: dict[str, Any]) -> str:
    tool_name = str(action.get("tool_name") or "").strip().lower()
    if tool_name == "spawn_agent":
        async_mode = normalized_trace_bool(action.get("async"))
        if async_mode is not None:
            return "parallel" if async_mode else "serial"
        planner_policy = str(action.get("planner_policy") or "").strip().lower()
        if planner_policy == "delegate_sync":
            return "serial"
        if planner_policy in {"delegate_async", "delegate"}:
            return "parallel"
        return ""
    if tool_name == "wait_agent":
        wait_required = normalized_trace_bool(action.get("wait_required"))
        if wait_required is not None:
            return "serial" if wait_required else "parallel"
        planner_policy = str(action.get("planner_policy") or "").strip().lower()
        if planner_policy == "wait_now":
            return "serial"
        if planner_policy == "wait_later":
            return "parallel"
        return ""
    if tool_name == "agent_workflow":
        return "parallel"
    if tool_name == "recover_agent":
        return "serial"
    return ""
