from __future__ import annotations

from typing import Any

try:
    from cli.scripts.run_multiturn_planning_probe_case_helpers import CaseSpec
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from run_multiturn_planning_probe_case_helpers import CaseSpec  # type: ignore[no-redef]


def _looks_like_provider_unavailable(text: str) -> bool:
    normalized = str(text or "").lower()
    needles = (
        "proxy_unavailable",
        "all accounts are currently unavailable",
        "当前 provider 调用失败",
        "provider failure",
        "provider 暂不可用",
    )
    return any(needle in normalized for needle in needles)


def _todo_events(turn_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for event in list(turn_events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "todo_list":
            continue
        events.append({"type": str(event.get("type") or "").strip(), "item": dict(item)})
    return events


def _latest_todo_item(todo_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in list(todo_events or []):
        item = event.get("item")
        if isinstance(item, dict):
            latest = dict(item)
    return latest


def _latest_open_todo_item(todo_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    running: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in list(todo_events or []):
        event_type = str(event.get("type") or "").strip()
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        if event_type == "item.completed":
            running.pop(item_id, None)
            order = [candidate for candidate in order if candidate != item_id]
            continue
        running[item_id] = dict(item)
        order = [candidate for candidate in order if candidate != item_id]
        order.append(item_id)
    for item_id in reversed(order):
        item = running.get(item_id)
        if item is not None:
            return dict(item)
    return None


def _plan_from_todo_item(item: dict[str, Any] | None) -> list[dict[str, Any]]:
    plan = (item or {}).get("plan")
    if not isinstance(plan, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in plan:
        if not isinstance(entry, dict):
            continue
        step = str(entry.get("step") or "").strip()
        status = str(entry.get("status") or "").strip()
        if not step:
            continue
        normalized.append({"step": step, "status": status})
    return normalized


def _plan_signature(plan: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(str(entry.get("step") or "").strip() for entry in list(plan or []))


def _max_in_progress_count(todo_events: list[dict[str, Any]]) -> int:
    max_count = 0
    for event in list(todo_events or []):
        item = event.get("item")
        plan = _plan_from_todo_item(item if isinstance(item, dict) else None)
        in_progress_count = sum(1 for entry in plan if str(entry.get("status") or "").strip() == "in_progress")
        if in_progress_count > max_count:
            max_count = in_progress_count
    return max_count


def _all_plan_steps_completed(plan: list[dict[str, Any]]) -> bool:
    return bool(plan) and all(str(entry.get("status") or "").strip() == "completed" for entry in plan)


def _agenthub_turn_summary(payload: dict[str, Any]) -> dict[str, Any]:
    tool_events = [item for item in list(payload.get("tool_events") or []) if isinstance(item, dict)]
    response_items = [item for item in list(payload.get("response_items") or []) if isinstance(item, dict)]
    turn_events = [item for item in list(payload.get("turn_events") or []) if isinstance(item, dict)]
    todo_events = _todo_events(turn_events)
    latest_todo = _latest_todo_item(todo_events)
    latest_plan = _plan_from_todo_item(latest_todo)
    return {
        "assistant_text": str(payload.get("assistant_text") or ""),
        "commentary_text": str(payload.get("commentary_text") or ""),
        "tool_event_count": len(tool_events),
        "tool_names": [str(item.get("name") or "") for item in tool_events],
        "update_plan_count": sum(1 for item in tool_events if str(item.get("name") or "").strip() == "update_plan"),
        "response_item_types": [str(item.get("type") or "") for item in response_items],
        "turn_event_count": len(turn_events),
        "todo_event_count": len(todo_events),
        "todo_started_count": sum(1 for item in todo_events if item.get("type") == "item.started"),
        "todo_updated_count": sum(1 for item in todo_events if item.get("type") == "item.updated"),
        "todo_completed_count": sum(1 for item in todo_events if item.get("type") == "item.completed"),
        "has_update_plan": any(str(item.get("name") or "").strip() == "update_plan" for item in tool_events),
        "has_todo_list": bool(todo_events),
        "latest_todo_plan": latest_plan,
        "latest_todo_signature": list(_plan_signature(latest_plan)),
        "latest_todo_all_completed": _all_plan_steps_completed(latest_plan),
        "stale_open_todo": _latest_open_todo_item(todo_events) is not None,
        "max_in_progress_count": _max_in_progress_count(todo_events),
        "status": dict(payload.get("status") or {}),
        "protocol_diagnostics": dict(payload.get("protocol_diagnostics") or {}),
    }


def _evaluate_case(
    *,
    case: CaseSpec,
    turns: list[dict[str, Any]],
    validation_results: list[dict[str, Any]],
    provider_failure: bool,
    provider_failure_reason: str,
) -> dict[str, Any]:
    plan_turns = [int(turn.get("turn")) for turn in turns if turn.get("parsed", {}).get("has_todo_list")]
    latest_signatures = [
        tuple(turn.get("parsed", {}).get("latest_todo_signature") or [])
        for turn in turns
        if turn.get("parsed", {}).get("latest_todo_signature")
    ]
    unique_signatures = []
    for signature in latest_signatures:
        if signature not in unique_signatures:
            unique_signatures.append(signature)
    last_inventory = {str(item.get("path") or "") for item in list((turns[-1] if turns else {}).get("files_after") or [])}
    issues: list[str] = []
    if provider_failure:
        issues.append(f"provider failure: {provider_failure_reason or 'unknown'}")
    if case.expect_no_plan:
        if plan_turns:
            issues.append(f"expected no planning, but todo_list appeared on turns {plan_turns}")
    else:
        if len(plan_turns) < int(case.min_plan_turns or 0):
            issues.append(f"expected at least {case.min_plan_turns} plan-bearing turns, got {len(plan_turns)}")
        if case.require_replan and len(unique_signatures) < 2:
            issues.append("expected a replan across turns, but plan signatures did not change")
    for turn in turns:
        parsed = dict(turn.get("parsed") or {})
        turn_id = int(turn.get("turn") or 0)
        if parsed.get("has_todo_list"):
            if parsed.get("stale_open_todo"):
                issues.append(f"turn {turn_id}: todo_list remained open at turn end")
            if int(parsed.get("max_in_progress_count") or 0) > 1:
                issues.append(f"turn {turn_id}: more than one in_progress plan step observed")
            if not parsed.get("latest_todo_all_completed"):
                issues.append(f"turn {turn_id}: latest todo_list snapshot was not fully completed")
    for expected in list(case.expected_files or ()):
        if expected not in last_inventory:
            issues.append(f"missing expected file: {expected}")
    for forbidden in list(case.forbidden_files or ()):
        if forbidden in last_inventory:
            issues.append(f"unexpected leftover file: {forbidden}")
    for result in list(validation_results or []):
        if int(result.get("returncode") or 0) != 0:
            issues.append(f"validation failed: {result.get('name')} rc={result.get('returncode')}")
    return {
        "passed": not issues,
        "issues": issues,
        "plan_turns": plan_turns,
        "unique_plan_signatures": [list(signature) for signature in unique_signatures],
        "replan_detected": len(unique_signatures) >= 2,
        "validation_results": validation_results,
        "final_inventory": sorted(path for path in last_inventory if path),
        "provider_failure": provider_failure,
        "provider_failure_reason": provider_failure_reason,
    }
