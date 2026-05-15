from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.ui.runtime_bridge import QueuedRuntimeRequest
from cli.agent_cli.ui.tab_task_run import TabTaskRun


def child_tab_ids(manager: Any, parent_tab_id: str) -> list[str]:
    return [
        tab_id
        for tab_id in manager._tab_order
        if str(getattr(manager._tabs.get(tab_id), "parent_tab_id", "") or "") == parent_tab_id
    ]


def child_task_runs(manager: Any, parent_tab_id: str) -> list[TabTaskRun]:
    runs: list[TabTaskRun] = []
    for tab_id in child_tab_ids(manager, parent_tab_id):
        session = manager._tabs.get(tab_id)
        if session is None:
            continue
        runs.extend(list(getattr(session, "task_history", []) or []))
        current = getattr(session, "current_task_run", None)
        if current is not None:
            runs.append(current)
    return runs


def fork_child_tab(manager: Any, from_tab_id: str) -> str:
    source = manager._tabs.get(from_tab_id)
    if source is None:
        return ""
    tab_id = manager.fork_tab(from_tab_id)
    if not tab_id:
        return ""
    child = manager._tabs.get(tab_id)
    source.role = "master"
    source.parent_tab_id = ""
    if child is not None:
        child.role = "child"
        child.parent_tab_id = source.tab_id
        child.custom_label = (
            child.custom_label or f"child {len(child_tab_ids(manager, source.tab_id))}"
        )
    manager.save_manifest()
    return tab_id


def dispatch_visible_child_task(
    manager: Any,
    *,
    parent_tab_id: str,
    task_text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if manager._app is not None:
        call_from_thread = getattr(manager._app, "call_from_thread", None)
        if callable(call_from_thread):
            try:
                return dict(
                    call_from_thread(
                        dispatch_visible_child_task_on_app_thread,
                        manager,
                        parent_tab_id=parent_tab_id,
                        task_text=task_text,
                        metadata=dict(metadata or {}),
                    )
                )
            except RuntimeError:
                pass
    return dispatch_visible_child_task_on_app_thread(
        manager,
        parent_tab_id=parent_tab_id,
        task_text=task_text,
        metadata=dict(metadata or {}),
    )


def dispatch_visible_child_task_on_app_thread(
    manager: Any,
    *,
    parent_tab_id: str,
    task_text: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    parent = manager._tabs.get(parent_tab_id)
    if parent is None:
        raise RuntimeError(f"unknown parent tab: {parent_tab_id}")
    previous_active = manager._active_tab_id
    child_tab_id = manager.fork_child_tab(parent_tab_id)
    if not child_tab_id:
        raise RuntimeError("unable to create visible child tab")
    child = manager._tabs.get(child_tab_id)
    if child is None:
        raise RuntimeError("visible child tab was not created")
    card_id = str(metadata.get("card_id") or "").strip()
    run_id = str(metadata.get("run_id") or "").strip()
    child.task_run_serial = max(0, int(child.task_run_serial or 0)) + 1
    task_run_id = f"{child_tab_id}-run-{child.task_run_serial}"
    if card_id:
        child.custom_label = f"{card_id}"
    if previous_active in manager._tabs and manager._active_tab_id != previous_active:
        manager.switch_to_tab(previous_active)
    child.request_queue.put_nowait(
        QueuedRuntimeRequest(
            text=str(task_text or ""),
            attachments=[],
            display_text=str(task_text or ""),
            display_attachments=[],
            priority="next",
            metadata={
                "orchestration": {
                    "run_id": run_id,
                    "card_id": card_id,
                    "attempt": int(metadata.get("attempt") or 0),
                },
                "agenthub_task_run_id": task_run_id,
                **dict(metadata or {}),
            },
        )
    )
    provider = ""
    model = ""
    try:
        status = dict(child.runtime.agent.provider_status() or {})
        provider = str(status.get("provider_name") or status.get("provider") or "")
        model = str(status.get("provider_model") or status.get("model_key") or "")
    except Exception:
        pass
    manager.save_manifest()
    return {
        "tab_id": child_tab_id,
        "task_id": f"{run_id}:{card_id}:{int(metadata.get('attempt') or 0)}",
        "task_run_id": task_run_id,
        "provider_name": provider,
        "model": model,
        "route_label": "dispatch_visible_child_tab",
    }


def send_visible_child_task(
    manager: Any,
    *,
    parent_tab_id: str,
    child_tab_id: str,
    task_text: str,
    interrupt: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if manager._app is not None:
        call_from_thread = getattr(manager._app, "call_from_thread", None)
        if callable(call_from_thread):
            try:
                return dict(
                    call_from_thread(
                        send_visible_child_task_on_app_thread,
                        manager,
                        parent_tab_id=parent_tab_id,
                        child_tab_id=child_tab_id,
                        task_text=task_text,
                        interrupt=interrupt,
                        metadata=dict(metadata or {}),
                    )
                )
            except RuntimeError:
                pass
    return send_visible_child_task_on_app_thread(
        manager,
        parent_tab_id=parent_tab_id,
        child_tab_id=child_tab_id,
        task_text=task_text,
        interrupt=interrupt,
        metadata=dict(metadata or {}),
    )


def send_visible_child_task_on_app_thread(
    manager: Any,
    *,
    parent_tab_id: str,
    child_tab_id: str,
    task_text: str,
    interrupt: bool,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    child = manager._tabs.get(child_tab_id)
    if child is None:
        raise RuntimeError(f"unknown child tab: {child_tab_id}")
    actual_parent = str(getattr(child, "parent_tab_id", "") or "").strip()
    if actual_parent != parent_tab_id:
        raise RuntimeError(f"tab {child_tab_id} is not a child of {parent_tab_id}")
    if child.request_queue is None:
        raise RuntimeError(f"child tab {child_tab_id} has no request queue")
    child.task_run_serial = max(0, int(child.task_run_serial or 0)) + 1
    task_run_id = f"{child_tab_id}-run-{child.task_run_serial}"
    child.request_queue.put_nowait(
        QueuedRuntimeRequest(
            text=str(task_text or ""),
            attachments=[],
            display_text=str(task_text or ""),
            display_attachments=[],
            priority="now" if interrupt else "next",
            metadata={
                "visible_child": {
                    "parent_tab_id": parent_tab_id,
                    "child_tab_id": child_tab_id,
                    "interrupt": bool(interrupt),
                },
                "agenthub_task_run_id": task_run_id,
                **dict(metadata or {}),
            },
        )
    )
    return {
        "tab_id": child_tab_id,
        "parent_tab_id": parent_tab_id,
        "task_run_id": task_run_id,
        "queued": True,
        "priority": "now" if interrupt else "next",
        "route_label": "send_visible_child_tab",
    }


def visible_child_task_run_snapshots(manager: Any, parent_tab_id: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for tab_id in child_tab_ids(manager, parent_tab_id):
        session = manager._tabs.get(tab_id)
        if session is None:
            continue
        for run in list(getattr(session, "task_history", []) or []):
            runs.append(run.to_dict())
        current = getattr(session, "current_task_run", None)
        if current is not None:
            runs.append(current.to_dict())
        queue = getattr(session, "request_queue", None)
        if queue is None:
            continue
        try:
            queued_items = list(getattr(queue, "_queue", []) or [])
        except Exception:
            queued_items = []
        for request in queued_items:
            metadata = getattr(request, "metadata", None)
            if not isinstance(metadata, dict):
                metadata = {}
            task_run_id = str(metadata.get("agenthub_task_run_id") or "").strip()
            if not task_run_id:
                continue
            runs.append(
                {
                    "run_id": task_run_id,
                    "tab_id": tab_id,
                    "parent_tab_id": parent_tab_id,
                    "provider": "",
                    "engine": str(getattr(session, "engine", "") or ""),
                    "state": "queued",
                    "terminal_state": "",
                    "terminal_reason": "",
                    "objective_state": "not_reported",
                    "started_at": 0.0,
                    "finished_at": None,
                    "user_prompt": str(getattr(request, "text", "") or ""),
                    "summary": "",
                    "error_message": "",
                    "transcript_range": [0, 0],
                    "provider_terminal_event": None,
                    "status_snapshot": dict(getattr(session, "status_data", {}) or {}),
                    "assignment_ref": manager._assignment_ref_from_request(request),
                }
            )
    return runs


def child_task_update_payload(manager: Any, run: TabTaskRun) -> dict[str, Any]:
    payload = run.to_dict()
    child = manager._tabs.get(run.tab_id)
    child_name = ""
    if child is not None:
        child_name = str(child.custom_label or child.thread_name or "").strip()
    payload["child_display_tab"] = manager.display_tab_label(run.tab_id)
    payload["child_label"] = child_name or payload["child_display_tab"]
    return payload


def child_task_update_notice(payload: dict[str, Any]) -> str:
    label = str(payload.get("child_label") or payload.get("child_display_tab") or "-")
    terminal = str(payload.get("terminal_state") or "-")
    objective = str(payload.get("objective_state") or "-")
    run_id = str(payload.get("run_id") or "-")
    summary = " ".join(str(payload.get("summary") or "").split())
    if len(summary) > 160:
        summary = summary[:157].rstrip() + "..."
    suffix = f" summary={summary}" if summary else ""
    return (
        f"Child tab {label} finished: terminal={terminal} "
        f"objective={objective} run_id={run_id}{suffix}"
    )


def append_system_notice_to_tab(manager: Any, tab_id: str, text: str, *, unread: bool) -> None:
    session = manager._tabs.get(tab_id)
    if session is None:
        return
    app = manager._app
    if app is not None:
        write_notice = getattr(app, "_write_system_notice", None)
        if tab_id == manager._active_tab_id and callable(write_notice):
            write_notice(text)
            session.transcript_entries = list(getattr(app, "_transcript_entries", []) or [])
            session.transcript_lines = list(getattr(app, "_transcript_lines", []) or [])
            return
        run_with_state = getattr(app, "_run_with_tab_transcript_state", None)
        mark_updated = getattr(app, "_mark_tab_transcript_updated", None)
        if callable(write_notice) and callable(run_with_state):
            run_with_state(session, lambda: write_notice(text))
            if callable(mark_updated):
                mark_updated(tab_id, unread=unread)
            return
    from cli.agent_cli.ui.transcript_history import system_notice_entry
    from cli.agent_cli.ui.transcript_visual_rendering import render_transcript_entries

    session.transcript_entries = [
        *list(session.transcript_entries or []),
        system_notice_entry(text),
    ]
    session.transcript_lines = render_transcript_entries(session.transcript_entries)
    session.transcript_dirty = True
    if unread:
        session.has_unread_output = True


def publish_child_task_run_update(manager: Any, run: TabTaskRun) -> None:
    parent_tab_id = str(run.parent_tab_id or "").strip()
    if not parent_tab_id:
        return
    parent = manager._tabs.get(parent_tab_id)
    if parent is None:
        return
    payload = child_task_update_payload(manager, run)
    run_id = str(payload.get("run_id") or "").strip()
    existing_ids = {
        str(item.get("run_id") or "").strip()
        for item in list(parent.child_task_inbox or [])
        if isinstance(item, dict)
    }
    if run_id and run_id not in existing_ids:
        parent.child_task_inbox.append(payload)
    append_system_notice_to_tab(
        manager,
        parent_tab_id,
        child_task_update_notice(payload),
        unread=parent_tab_id != manager._active_tab_id,
    )


def child_task_updates_context_text(updates: list[dict[str, Any]]) -> str:
    payload = json.dumps(updates, ensure_ascii=True, indent=2, sort_keys=True)
    return (
        "\n\n<agenthub_visible_child_task_updates>\n"
        "These visible child tab TaskRun results completed since your previous "
        "turn. Use them as structured context; do not ask the user to paste "
        "child transcripts.\n"
        f"{payload}\n"
        "</agenthub_visible_child_task_updates>"
    )


def prepare_runtime_request_for_tab(
    manager: Any,
    tab_id: str,
    request: QueuedRuntimeRequest,
) -> QueuedRuntimeRequest:
    session = manager._tabs.get(tab_id)
    if session is None:
        return request
    text = str(getattr(request, "text", "") or "")
    if text.strip().startswith("/"):
        return request
    updates = [
        dict(item)
        for item in list(getattr(session, "child_task_inbox", []) or [])
        if isinstance(item, dict)
    ]
    if not updates:
        return request
    session.child_task_inbox = []
    metadata = dict(getattr(request, "metadata", None) or {})
    metadata["visible_child_task_updates"] = updates
    return QueuedRuntimeRequest(
        text=text + child_task_updates_context_text(updates),
        attachments=list(getattr(request, "attachments", []) or []),
        display_text=getattr(request, "display_text", None),
        display_attachments=getattr(request, "display_attachments", None),
        priority=getattr(request, "priority", "next"),
        metadata=metadata,
    )
