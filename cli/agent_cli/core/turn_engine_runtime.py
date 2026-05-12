from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.models import AgentIntent, ToolEvent, tool_event_is_soft_failure

_ORCHESTRATION_CONTINUE_DECISIONS = {
    "delegate",
    "delegate_async",
    "delegate_sync",
    "delegate_and_wait",
    "wait",
    "wait_now",
    "wait_later",
    "retry_child",
    "resume_child",
}


def structured_tool_fallback_text(events: list[ToolEvent]) -> str:
    if not events:
        return "模型未返回内容。"
    last_event = events[-1]
    payload = last_event.payload or {}

    if not last_event.ok and not tool_event_is_soft_failure(last_event):
        return str(payload.get("error") or last_event.summary or "工具调用失败").strip()

    if tool_event_is_soft_failure(last_event):
        return str(payload.get("text") or last_event.summary or "").strip()

    if last_event.name == "web_fetch":
        title = str(payload.get("title") or "").strip()
        final_url = str(payload.get("final_url") or payload.get("url") or "").strip()
        if title and final_url:
            return f"已读取网页：{title}\n{final_url}"
        if title:
            return f"已读取网页：{title}"
        if final_url:
            return f"已读取网页：{final_url}"
        return "已读取网页。"

    if last_event.name in {"file_read", "read_file"}:
        path_text = str(payload.get("path") or payload.get("file_path") or "").strip()
        return f"已读取文件：{path_text}" if path_text else ""

    if last_event.name in {"file_search", "grep_files"}:
        query_text = str(payload.get("query") or payload.get("pattern") or "").strip()
        return f"已搜索文件：{query_text}" if query_text else ""

    if last_event.name in {"file_list", "list_dir"}:
        path_text = str(payload.get("path") or payload.get("dir_path") or ".").strip() or "."
        return f"已列出 {path_text} 下的文件。"

    if last_event.name == "patch_approval_requested":
        approval_id = str(payload.get("approval_id") or "").strip()
        commands = approval_contract_runtime.approval_option_commands(
            approval_id,
            payload.get("available_decisions"),
        )
        if approval_id:
            return f"已提交补丁审批：{approval_id}\n" + "\n".join(
                commands or [f"/approve {approval_id}", f"/reject {approval_id}"]
            )
        return "已提交补丁审批。"

    if last_event.name == "shell_approval_requested":
        approval_id = str(payload.get("approval_id") or "").strip()
        command = str(payload.get("command") or "").strip()
        commands = approval_contract_runtime.approval_option_commands(
            approval_id,
            payload.get("available_decisions"),
        )
        if approval_id and command:
            return (
                f"已提交命令审批：{approval_id}\n"
                + "\n".join(commands or [f"/approve {approval_id}", f"/reject {approval_id}"])
                + "\n"
                f"{command}"
            )
        if approval_id:
            return f"已提交命令审批：{approval_id}\n" + "\n".join(
                commands or [f"/approve {approval_id}", f"/reject {approval_id}"]
            )
        return "已提交命令审批。"

    if last_event.name == "background_teammate_approval_requested":
        approval_id = str(payload.get("approval_id") or "").strip()
        commands = approval_contract_runtime.approval_option_commands(
            approval_id,
            payload.get("available_decisions"),
        )
        if approval_id:
            return f"已提交后台 teammate 审批：{approval_id}\n" + "\n".join(
                commands or [f"/approve {approval_id}", f"/reject {approval_id}"]
            )
        return "已提交后台 teammate 审批。"

    return "已完成工具调用，但模型未返回可展示的最终答案。"


def _normalized_number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    if number != number:
        return None
    if number.is_integer():
        return int(number)
    return number


def _normalized_int(value: Any) -> int | None:
    number = _normalized_number(value)
    if number is None:
        return None
    try:
        return int(number)
    except (TypeError, ValueError):
        return None


def _non_empty_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _trace_text(trace_entry: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(trace_entry.get(key) or "").strip()
        if text:
            return text
    return ""


def orchestration_budget_timeout_strategy(trace_entry: dict[str, Any]) -> dict[str, Any]:
    decision = _trace_text(
        trace_entry,
        "delegation_policy_decision",
        "orchestration_decision",
    ).lower()
    if not decision:
        return {}

    budget_snapshot = trace_entry.get("delegation_budget_snapshot")
    if not isinstance(budget_snapshot, dict):
        budget_snapshot = trace_entry.get("orchestration_budget_snapshot")
    budget_snapshot = budget_snapshot if isinstance(budget_snapshot, dict) else {}
    wait_timeout_ms = _normalized_int(
        trace_entry.get("wait_timeout_ms")
        if trace_entry.get("wait_timeout_ms") not in (None, "")
        else budget_snapshot.get("wait_timeout_ms")
    )
    wait_observed_ms = _normalized_int(
        trace_entry.get("delegation_wait_observed_ms")
        if trace_entry.get("delegation_wait_observed_ms") not in (None, "")
        else (
            trace_entry.get("orchestration_wait_observed_ms")
            if trace_entry.get("orchestration_wait_observed_ms") not in (None, "")
            else budget_snapshot.get("wait_observed_ms")
        )
    )
    budget_hit = (
        wait_timeout_ms is not None
        and wait_observed_ms is not None
        and wait_observed_ms >= wait_timeout_ms
    )
    timeout_hit = bool(
        trace_entry.get("delegation_timeout_hit")
        if "delegation_timeout_hit" in trace_entry
        else trace_entry.get("orchestration_timeout_hit")
    )
    timed_out = (
        _trace_text(
            trace_entry,
            "delegation_outcome",
            "orchestration_outcome",
        ).lower()
        == "timed_out"
    )

    if timeout_hit or timed_out:
        return {
            "delegation_strategy": "stop_and_return",
            "delegation_strategy_reason": _non_empty_text(
                trace_entry.get("delegation_timeout_reason"),
                trace_entry.get("orchestration_timeout_reason"),
                "timeout_hit",
            ),
            "delegation_continue_main_thread": False,
            "delegation_budget_hit": bool(budget_hit),
            "delegation_strategy_source": "budget_timeout_policy",
        }
    if budget_hit:
        return {
            "delegation_strategy": "stop_and_return",
            "delegation_strategy_reason": "wait_timeout_budget_hit",
            "delegation_continue_main_thread": False,
            "delegation_budget_hit": True,
            "delegation_strategy_source": "budget_timeout_policy",
        }
    continue_delegation = decision in _ORCHESTRATION_CONTINUE_DECISIONS
    return {
        "delegation_strategy": "downgrade_continue",
        "delegation_strategy_reason": "budget_not_hit",
        "delegation_continue_main_thread": continue_delegation,
        "delegation_budget_hit": False,
        "delegation_strategy_source": "budget_timeout_policy",
    }


def should_stop_after_orchestration(trace_entry: dict[str, Any]) -> bool:
    strategy = orchestration_budget_timeout_strategy(trace_entry)
    return str(strategy.get("delegation_strategy") or "").strip() == "stop_and_return"


def invoke_handler(
    handler: Callable[..., AgentIntent],
    *,
    user_text: str,
    executed_events: list[ToolEvent],
    executed_item_events: list[dict[str, Any]],
    previous_response_id: str | None = None,
    continuation_input_items: list[dict[str, Any]] | None = None,
    initial_send_error: Exception | None = None,
) -> AgentIntent:
    try:
        parameter_count = len(inspect.signature(handler).parameters)
    except (TypeError, ValueError):
        parameter_count = 2
    args: list[Any] = [user_text, list(executed_events or [])]
    if parameter_count >= 3:
        args.append(
            [dict(item) for item in list(executed_item_events or []) if isinstance(item, dict)]
        )
    if parameter_count >= 4:
        args.append(str(previous_response_id or "").strip() or None)
    if parameter_count >= 5:
        args.append(
            [dict(item) for item in list(continuation_input_items or []) if isinstance(item, dict)]
        )
    if parameter_count >= 6:
        args.append(initial_send_error)
    return handler(*args)
