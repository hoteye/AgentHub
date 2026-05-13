from __future__ import annotations

import asyncio
from typing import Any


def _create_request_queue() -> asyncio.Queue[Any]:
    return asyncio.Queue()


def _start_tab_request_worker_task(session: Any, app: Any, tab_id: str) -> None:
    async def _tab_worker() -> None:
        from cli.agent_cli.ui import request_worker_loop

        await request_worker_loop(
            queue=session.request_queue,
            runtime=lambda _session=session: _session.runtime,
            set_busy=lambda b, _tid=tab_id: app._set_busy_for_tab(_tid, b),
            on_request_start=lambda t, _tid=tab_id: app._on_request_start_for_tab(_tid, t),
            begin_activity_capture=lambda _tid=tab_id: app._begin_activity_capture_for_tab(_tid),
            render_response=lambda r, _tid=tab_id: app._render_response_for_tab(_tid, r),
            handle_response=lambda r, _tid=tab_id: app._handle_response_for_tab(_tid, r),
            write_assistant_reply=lambda t, _tid=tab_id: app._write_reply_for_tab(_tid, t),
            on_idle=lambda _tid=tab_id: app._on_idle_for_tab(_tid),
            prepare_runtime_request=lambda request, _tid=tab_id: (
                app._tab_manager.prepare_runtime_request_for_tab(_tid, request)
                if getattr(app, "_tab_manager", None) is not None
                else request
            ),
            on_request_echo=lambda text, attachments=None, _tid=tab_id: app._echo_prompt_for_tab(
                _tid, text, attachments=attachments
            ),
            on_task_run_start=lambda request, _tid=tab_id: (
                app._tab_manager.start_task_run(_tid, request)
                if getattr(app, "_tab_manager", None) is not None
                else None
            ),
            on_task_run_response=lambda task_run, response, _tid=tab_id: (
                app._tab_manager.complete_task_run(_tid, task_run, response)
                if getattr(app, "_tab_manager", None) is not None
                else None
            ),
            on_task_run_error=lambda task_run, error, _tid=tab_id: (
                app._tab_manager.fail_task_run(_tid, task_run, error)
                if getattr(app, "_tab_manager", None) is not None
                else None
            ),
        )

    session.request_worker_task = asyncio.create_task(_tab_worker())


def _cancel_tab_request_worker_task(session: Any | None) -> None:
    if session is None or session.request_worker_task is None:
        return
    session.request_worker_task.cancel()
    session.request_worker_task = None
