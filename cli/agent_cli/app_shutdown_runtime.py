from __future__ import annotations

import asyncio
from typing import Any

from cli.agent_cli.startup_debug import startup_log


def request_worker_tasks_for_shutdown(app: Any) -> list[Any]:
    tasks: list[Any] = []
    mgr = getattr(app, "_tab_manager", None)
    if mgr is not None:
        for tab_id in list(mgr._tabs.keys()):
            session = mgr.get(tab_id)
            if session and session.request_worker_task is not None:
                tasks.append(session.request_worker_task)
        return tasks
    task = app._request_worker_task
    if task is not None:
        tasks.append(task)
    return tasks


async def cancel_and_wait_for_tasks(tasks: list[Any]) -> None:
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass


async def close_codex_sidecar_kernel(app: Any) -> None:
    kernel = getattr(app, "_codex_sidecar_kernel", None)
    if kernel is None:
        return
    try:
        await kernel.aclose()
    except Exception:
        pass
    app._codex_sidecar_kernel = None


async def on_unmount(app: Any) -> None:
    startup_log("app.on_unmount.begin")
    app._begin_shutdown()
    mgr = getattr(app, "_tab_manager", None)
    if mgr is not None:
        mgr.stop_scroll_capture_timer()
        mgr.save_manifest()
    tasks = request_worker_tasks_for_shutdown(app)
    await cancel_and_wait_for_tasks(tasks)
    await close_codex_sidecar_kernel(app)
    startup_log("app.on_unmount.end")


__all__ = [
    "cancel_and_wait_for_tasks",
    "close_codex_sidecar_kernel",
    "on_unmount",
    "request_worker_tasks_for_shutdown",
]
