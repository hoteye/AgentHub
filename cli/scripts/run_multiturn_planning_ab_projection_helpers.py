from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _codex_todo_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "todo_list":
            continue
        results.append({"type": str(event.get("type") or "").strip(), "item": dict(item)})
    return results


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
    if isinstance(plan, list):
        normalized: list[dict[str, Any]] = []
        for entry in plan:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("step") or "").strip()
            status = str(entry.get("status") or "").strip()
            if text:
                normalized.append({"step": text, "status": status})
        if normalized:
            return normalized
    items = (item or {}).get("items")
    normalized_items: list[dict[str, Any]] = []
    if isinstance(items, list):
        for entry in items:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            normalized_items.append(
                {
                    "step": text,
                    "status": "completed" if bool(entry.get("completed")) else "pending",
                }
            )
    return normalized_items


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


def _parse_codex_stdout(stdout_text: str, last_message_path: Path) -> dict[str, Any]:
    raw_events: list[dict[str, Any]] = []
    item_counts: dict[str, int] = {}
    completed_item_counts: dict[str, int] = {}
    errors: list[str] = []
    agent_messages: list[str] = []
    thread_id = ""
    turn_completed = 0
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if not isinstance(event, dict):
            continue
        raw_events.append(event)
        event_type = str(event.get("type") or "")
        if event_type == "thread.started":
            thread_id = str(event.get("thread_id") or thread_id)
        elif event_type == "turn.completed":
            turn_completed += 1
        elif event_type == "error":
            message = str(event.get("message") or "").strip()
            if message:
                errors.append(message)
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type:
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
            if event_type == "item.completed":
                completed_item_counts[item_type] = completed_item_counts.get(item_type, 0) + 1
        if item_type == "agent_message":
            text = str(item.get("text") or "").strip()
            if text:
                agent_messages.append(text)
        elif item_type == "error":
            message = str(item.get("message") or "").strip()
            if message:
                errors.append(message)
    assistant_text = ""
    if last_message_path.exists():
        assistant_text = last_message_path.read_text(encoding="utf-8").strip()
    if not assistant_text and agent_messages:
        assistant_text = agent_messages[-1]
    todo_events = _codex_todo_events(raw_events)
    latest_todo = _latest_todo_item(todo_events)
    latest_plan = _plan_from_todo_item(latest_todo)
    return {
        "assistant_text": assistant_text,
        "thread_id": thread_id,
        "item_counts": item_counts,
        "completed_item_counts": completed_item_counts,
        "agent_message_count": len(agent_messages),
        "turn_completed": turn_completed,
        "errors": errors,
        "todo_event_count": len(todo_events),
        "has_todo_list": bool(todo_events),
        "latest_todo_plan": latest_plan,
        "latest_todo_signature": list(_plan_signature(latest_plan)),
        "latest_todo_all_completed": _all_plan_steps_completed(latest_plan),
        "stale_open_todo": _latest_open_todo_item(todo_events) is not None,
        "max_in_progress_count": _max_in_progress_count(todo_events),
    }
