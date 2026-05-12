from __future__ import annotations

from typing import Any, Dict


def exit_payload(runtime: Any) -> dict[str, object]:
    thread_id = str(getattr(runtime, "thread_id", "") or "").strip()
    thread_name = str(getattr(runtime, "thread_name", "") or "").strip()
    return {
        "ok": True,
        "thread_id": thread_id,
        "thread_name": thread_name,
        "resume_command": f"agenthub resume {thread_id}" if thread_id else "",
    }


def resume_payload_text(runtime: Any, payload: Dict[str, Any]) -> str:
    thread = dict(payload.get("thread") or {})
    turns = [
        dict(item)
        for item in list(payload.get("turns") or [])
        if isinstance(item, dict)
    ]
    if thread:
        try:
            thread = runtime.describe_thread(thread, status="idle", turns=turns)
        except Exception:
            thread = dict(payload.get("thread") or {})
    lines = ["resumed thread"]
    lines.append(f"thread_id={thread.get('thread_id') or '-'}")
    lines.append(f"name={thread.get('name') or '-'}")
    lines.append(f"resume_source={payload.get('resume_source') or 'thread_id'}")
    path_text = str(thread.get("path") or "").strip()
    if path_text:
        lines.append(f"path={path_text}")
    cwd_text = str(thread.get("cwd") or "").strip()
    if cwd_text:
        lines.append(f"cwd={cwd_text}")
    lines.append(f"turns={len(turns)}")
    return "\n".join(lines)


def threads_text(runtime: Any, *, limit: int) -> str:
    thread_store = getattr(runtime, "thread_store", None)
    if thread_store is None:
        return "thread persistence is not enabled in this session"
    threads = runtime.list_threads(limit=limit)
    loaded_thread_id = str(getattr(runtime, "thread_id", "") or "").strip()
    getter = getattr(thread_store, "get_active_thread_id", None)
    active_thread_id = str(getter() or "").strip() if callable(getter) else ""
    lines = [f"threads={len(threads)}"]
    if active_thread_id:
        lines.append(f"active_thread_id={active_thread_id}")
    for item in threads:
        thread_id = str(item.get("thread_id") or "").strip()
        described = runtime.describe_thread(
            item,
            status="idle" if thread_id and thread_id == loaded_thread_id else "not_loaded",
            turns=[],
        )
        lines.append(
            " - ".join(
                [
                    f"id={described.get('thread_id') or '-'}",
                    f"name={described.get('name') or '-'}",
                    f"status={described.get('status') or '-'}",
                    f"path={described.get('path') or '-'}",
                ]
            )
        )
    return "\n".join(lines)


def exit_payload_text(runtime: Any) -> str:
    payload = exit_payload(runtime)
    thread_id = str(payload.get("thread_id") or "").strip()
    thread_name = str(payload.get("thread_name") or "").strip()
    lines = ["exiting session"]
    lines.append(f"thread_id={thread_id or '-'}")
    if thread_name:
        lines.append(f"name={thread_name}")
    resume_command = str(payload.get("resume_command") or "").strip()
    if resume_command:
        lines.append(f"resume_command={resume_command}")
    return "\n".join(lines)
