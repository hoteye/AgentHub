from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import ToolEvent


_ORCHESTRATION_TRACE_TOOLS = {"spawn_agent", "wait_agent", "agent_workflow", "recover_agent"}


def normalized_trace_number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
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


def normalized_trace_int(value: Any) -> int | None:
    number = normalized_trace_number(value)
    if number is None:
        return None
    try:
        return int(number)
    except (TypeError, ValueError):
        return None


def normalized_trace_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def non_empty_trace_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _trace_text(payload: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = non_empty_trace_text(payload.get(key))
        if text:
            return text
    return ""


def orchestration_outcome_for_event(event: ToolEvent) -> Dict[str, Any] | None:
    payload = event.payload if isinstance(event.payload, dict) else {}
    tool_name = non_empty_trace_text(payload.get("function_call_name"), event.name)
    if tool_name not in _ORCHESTRATION_TRACE_TOOLS:
        return None
    execution_tool = non_empty_trace_text(payload.get("planner_execution_tool"), event.name, tool_name)
    outcome: Dict[str, Any] = {
        "tool_name": tool_name,
        "execution_tool": execution_tool,
        "ok": bool(event.ok),
    }

    status = non_empty_trace_text(payload.get("status"))
    if status:
        outcome["status"] = status

    wait_reason = non_empty_trace_text(payload.get("wait_reason"), payload.get("last_wait_reason"))
    if wait_reason:
        outcome["wait_reason"] = wait_reason

    wait_blocked_ms = normalized_trace_int(payload.get("wait_blocked_ms"))
    if wait_blocked_ms is None:
        wait_blocked_ms = normalized_trace_int(payload.get("last_wait_blocked_ms"))
    if wait_blocked_ms is not None:
        outcome["wait_blocked_ms"] = wait_blocked_ms

    wait_timeout_ms = normalized_trace_int(payload.get("timeout_ms"))
    if wait_timeout_ms is not None:
        outcome["wait_timeout_ms"] = wait_timeout_ms

    timeout_budget_seconds = normalized_trace_number(payload.get("timeout_budget_seconds"))
    if timeout_budget_seconds is not None:
        outcome["timeout_budget_seconds"] = timeout_budget_seconds

    timeout_hit = False
    for field_name in ("timeout_hit", "wait_timed_out", "timed_out", "last_wait_timed_out"):
        if field_name in payload:
            normalized = normalized_trace_bool(payload.get(field_name))
            if normalized is True:
                timeout_hit = True
                break
    if timeout_hit:
        outcome["timeout_hit"] = True
        timeout_reason = non_empty_trace_text(payload.get("timeout_reason"))
        if not timeout_reason and normalized_trace_bool(payload.get("wait_timed_out")):
            timeout_reason = "wait_timeout"
        if timeout_reason:
            outcome["timeout_reason"] = timeout_reason
        timeout_source = non_empty_trace_text(payload.get("timeout_source"))
        if timeout_source:
            outcome["timeout_source"] = timeout_source

    terminal_reason = non_empty_trace_text(payload.get("terminal_reason")).lower()
    cancel_requested = normalized_trace_bool(payload.get("cancel_requested")) is True
    cancelled = (
        cancel_requested
        or str(status).strip().lower() == "cancelled"
        or terminal_reason in {"cancelled", "close_requested", "closed_by_request"}
    )
    if cancelled:
        outcome["cancelled"] = True
        if cancel_requested:
            outcome["cancel_requested"] = True

    failure_reason = non_empty_trace_text(payload.get("error"), payload.get("failure"), payload.get("reason"), event.summary)
    failed = (not bool(event.ok) or str(status).strip().lower() == "failed") and not timeout_hit and not cancelled
    if failed:
        outcome["failed"] = True
        if failure_reason:
            outcome["failure_reason"] = failure_reason
    return outcome


def annotate_trace_with_orchestration_outcomes(
    trace_entry: Dict[str, Any],
    execution_results: List[Any],
    *,
    batch_execution_ms: int,
) -> None:
    outcomes: List[Dict[str, Any]] = []
    for result in list(execution_results or []):
        events = list(result.events or [])
        if not events:
            continue
        outcome = orchestration_outcome_for_event(events[-1])
        if outcome is not None:
            outcomes.append(outcome)
    if not outcomes:
        return

    trace_entry["delegation_observation_source"] = "tool_execution"
    trace_entry["delegation_tool_execution_ms"] = int(batch_execution_ms)
    trace_entry["delegation_outcomes"] = outcomes

    wait_outcome = next(
        (item for item in outcomes if item.get("wait_blocked_ms") not in (None, "")),
        None,
    )
    if isinstance(wait_outcome, dict):
        trace_entry["delegation_wait_observed_ms"] = int(wait_outcome["wait_blocked_ms"])

    timeout_outcome = next((item for item in outcomes if item.get("timeout_hit") is True), None)
    cancelled_outcome = next((item for item in outcomes if item.get("cancelled") is True), None)
    failed_outcome = next((item for item in outcomes if item.get("failed") is True), None)

    if timeout_outcome is not None:
        trace_entry["delegation_timeout_hit"] = True
        if non_empty_trace_text(timeout_outcome.get("timeout_reason")):
            trace_entry["delegation_timeout_reason"] = non_empty_trace_text(timeout_outcome.get("timeout_reason"))
        if non_empty_trace_text(timeout_outcome.get("timeout_source")):
            trace_entry["delegation_timeout_source"] = non_empty_trace_text(timeout_outcome.get("timeout_source"))
    if cancelled_outcome is not None:
        trace_entry["delegation_cancelled"] = True
    if failed_outcome is not None:
        trace_entry["delegation_failed"] = True
        if non_empty_trace_text(failed_outcome.get("failure_reason")):
            trace_entry["delegation_failure_reason"] = non_empty_trace_text(failed_outcome.get("failure_reason"))

    if timeout_outcome is not None:
        trace_entry["delegation_outcome"] = "timed_out"
    elif cancelled_outcome is not None:
        trace_entry["delegation_outcome"] = "cancelled"
    elif failed_outcome is not None:
        trace_entry["delegation_outcome"] = "failed"
    else:
        trace_entry["delegation_outcome"] = "completed"

    budget_snapshot: Dict[str, Any] = {}
    if trace_entry.get("timeout_budget_seconds") not in (None, ""):
        budget_snapshot["timeout_budget_seconds"] = trace_entry["timeout_budget_seconds"]
    if trace_entry.get("wait_timeout_ms") not in (None, ""):
        budget_snapshot["wait_timeout_ms"] = trace_entry["wait_timeout_ms"]
    if isinstance(wait_outcome, dict) and wait_outcome.get("wait_blocked_ms") not in (None, ""):
        budget_snapshot["wait_observed_ms"] = int(wait_outcome["wait_blocked_ms"])
    if isinstance(timeout_outcome, dict):
        if timeout_outcome.get("timeout_budget_seconds") not in (None, ""):
            budget_snapshot["timeout_budget_seconds"] = timeout_outcome["timeout_budget_seconds"]
        if timeout_outcome.get("wait_timeout_ms") not in (None, ""):
            budget_snapshot["wait_timeout_ms"] = int(timeout_outcome["wait_timeout_ms"])
    if budget_snapshot:
        trace_entry["delegation_budget_snapshot"] = budget_snapshot
