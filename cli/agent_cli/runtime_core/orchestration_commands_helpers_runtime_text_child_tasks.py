from __future__ import annotations

from typing import Any

__all__ = [
    "_child_tab_send_text",
    "_child_tab_spawn_text",
    "_child_task_wait_text",
]


def _child_tab_spawn_text(payload: dict[str, Any]) -> str:
    lines = ["visible child tab spawned"]
    lines.append(f"tab_id={payload.get('tab_id') or '-'}")
    lines.append(f"task_id={payload.get('task_id') or '-'}")
    lines.append(f"provider={payload.get('provider_name') or '-'}")
    lines.append(f"model={payload.get('model') or '-'}")
    lines.append(f"route_label={payload.get('route_label') or '-'}")
    return "\n".join(lines)


def _child_tab_send_text(payload: dict[str, Any]) -> str:
    lines = ["visible child tab input queued"]
    lines.append(f"tab_id={payload.get('tab_id') or '-'}")
    lines.append(f"parent_tab_id={payload.get('parent_tab_id') or '-'}")
    lines.append(f"queued={str(bool(payload.get('queued'))).lower()}")
    lines.append(f"priority={payload.get('priority') or '-'}")
    lines.append(f"route_label={payload.get('route_label') or '-'}")
    return "\n".join(lines)


def _child_task_wait_text(payload: dict[str, Any]) -> str:
    snapshots = [
        dict(item) for item in list(payload.get("task_runs") or []) if isinstance(item, dict)
    ]
    terminal = [item for item in snapshots if str(item.get("terminal_state") or "").strip()]
    lines = ["visible child task snapshots"]
    lines.append(f"parent_tab_id={payload.get('parent_tab_id') or '-'}")
    lines.append(f"child_count={payload.get('child_count') or 0}")
    lines.append(f"task_run_count={len(snapshots)}")
    lines.append(f"terminal_count={payload.get('terminal_count', len(terminal))}")
    lines.append(
        f"pending_count={payload.get('pending_count', max(0, len(snapshots) - len(terminal)))}"
    )
    lines.append(f"wait_for={payload.get('wait_for') or 'all'}")
    lines.append(f"timed_out={str(bool(payload.get('timed_out'))).lower()}")
    selected_ids = [
        str(item) for item in list(payload.get("selected_task_run_ids") or []) if str(item).strip()
    ]
    if selected_ids:
        lines.append("selected_task_run_ids=" + ",".join(selected_ids[:8]))
    for item in snapshots[:8]:
        run_id = str(item.get("run_id") or "-")
        tab_id = str(item.get("tab_id") or "-")
        state = str(item.get("state") or "-")
        terminal_state = str(item.get("terminal_state") or "-") or "-"
        objective_state = str(item.get("objective_state") or "-") or "-"
        summary = " ".join(str(item.get("summary") or "").split())
        if len(summary) > 140:
            summary = summary[:137].rstrip() + "..."
        suffix = f" summary={summary}" if summary else ""
        lines.append(
            f"- {run_id} tab={tab_id} state={state} terminal={terminal_state} objective={objective_state}{suffix}"
        )
    remaining = len(snapshots) - 8
    if remaining > 0:
        lines.append(f"- ... {remaining} more task runs")
    return "\n".join(lines)
