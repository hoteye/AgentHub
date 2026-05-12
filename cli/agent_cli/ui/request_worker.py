from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from time import perf_counter
from typing import Any

from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.ui.runtime_bridge import (
    QueuedRuntimeRequest,
    RuntimeRequestPriority,
    normalize_runtime_request_priority,
)

_PRIORITY_ORDER: dict[RuntimeRequestPriority, int] = {
    "now": 0,
    "next": 1,
    "later": 2,
}


def _priority_rank(priority: str | None) -> int:
    normalized = normalize_runtime_request_priority(priority, default="next")
    return _PRIORITY_ORDER[normalized]


def _select_next_pending_index(pending: list[tuple[int, QueuedRuntimeRequest]]) -> int:
    best_index = 0
    best_rank = _priority_rank(pending[0][1].priority)
    best_sequence = int(pending[0][0])
    for index in range(1, len(pending)):
        sequence, request = pending[index]
        rank = _priority_rank(request.priority)
        if rank < best_rank or (rank == best_rank and int(sequence) < best_sequence):
            best_index = index
            best_rank = rank
            best_sequence = int(sequence)
    return best_index


def _request_uses_busy_indicator(request: QueuedRuntimeRequest) -> bool:
    return not str(getattr(request, "text", "") or "").strip().startswith("/")


async def _run_runtime_request_in_daemon_thread(runtime, request: QueuedRuntimeRequest) -> Any:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[Any] = loop.create_future()

    def _publish_result(result: Any) -> None:
        if not future.done():
            future.set_result(result)

    def _publish_exception(error: BaseException) -> None:
        if not future.done():
            future.set_exception(error)

    def _worker() -> None:
        try:
            result = runtime.handle_prompt(
                request.text,
                attachments=request.attachments,
            )
        except BaseException as exc:
            try:
                loop.call_soon_threadsafe(_publish_exception, exc)
            except RuntimeError:
                pass
        else:
            try:
                loop.call_soon_threadsafe(_publish_result, result)
            except RuntimeError:
                pass

    thread = threading.Thread(
        target=_worker,
        name="agenthub-runtime-request",
        daemon=True,
    )
    thread.start()
    return await future


async def enqueue_runtime_request(
    queue: asyncio.Queue[QueuedRuntimeRequest],
    text: str,
    attachments: list,
    *,
    display_text: str | None = None,
    display_attachments: list | None = None,
    priority: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    normalized_priority = normalize_runtime_request_priority(priority, default="next")
    if timeline_debug_enabled():
        log_timeline(
            "ui.request_queue.enqueue",
            text_preview=str(text or "")[:200],
            attachment_count=len(list(attachments or [])),
            deferred_echo=bool(display_text is not None),
            priority=normalized_priority,
            queue_size_before=queue.qsize(),
        )
    await queue.put(
        QueuedRuntimeRequest(
            text=text,
            attachments=list(attachments),
            display_text=display_text,
            display_attachments=(
                list(display_attachments) if display_attachments is not None else None
            ),
            priority=normalized_priority,
            metadata=dict(metadata or {}),
        )
    )
    if timeline_debug_enabled():
        log_timeline(
            "ui.request_queue.enqueued",
            text_preview=str(text or "")[:200],
            attachment_count=len(list(attachments or [])),
            deferred_echo=bool(display_text is not None),
            priority=normalized_priority,
            queue_size_after=queue.qsize(),
        )


async def request_worker_loop(
    *,
    queue: asyncio.Queue[QueuedRuntimeRequest],
    runtime,
    set_busy: Callable[[bool], None],
    on_request_start: Callable[[str], None] | None,
    on_request_echo: Callable[..., None] | None,
    begin_activity_capture: Callable[[], None],
    render_response: Callable[[object], None],
    handle_response: Callable[[object], None],
    write_assistant_reply: Callable[[str], None],
    on_idle: Callable[[], None],
    prepare_runtime_request: Callable[[QueuedRuntimeRequest], QueuedRuntimeRequest] | None = None,
    on_task_run_start: Callable[[QueuedRuntimeRequest], object] | None = None,
    on_task_run_response: Callable[[object, object], None] | None = None,
    on_task_run_error: Callable[[object, BaseException], None] | None = None,
) -> None:
    pending_requests: list[tuple[int, QueuedRuntimeRequest]] = []
    next_sequence = 0
    try:
        while True:
            if not pending_requests:
                request = await queue.get()
                pending_requests.append((next_sequence, request))
                next_sequence += 1
            while True:
                try:
                    queued_request = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                pending_requests.append((next_sequence, queued_request))
                next_sequence += 1
            selection_index = _select_next_pending_index(pending_requests)
            _sequence, request = pending_requests.pop(selection_index)
            started_at = perf_counter()
            use_busy_indicator = _request_uses_busy_indicator(request)
            if timeline_debug_enabled():
                log_timeline(
                    "ui.request_worker.start",
                    text_preview=str(request.text or "")[:200],
                    attachment_count=len(list(request.attachments or [])),
                    priority=normalize_runtime_request_priority(request.priority, default="next"),
                    queue_size_after_get=queue.qsize(),
                    pending_prefetched_count=len(pending_requests),
                    busy_indicator=use_busy_indicator,
                )
            if use_busy_indicator:
                set_busy(True)
            if callable(on_request_echo) and request.display_text is not None:
                try:
                    on_request_echo(
                        str(request.display_text),
                        attachments=list(
                            request.display_attachments
                            if request.display_attachments is not None
                            else request.attachments
                        ),
                    )
                except Exception:
                    pass
            if callable(on_request_start):
                try:
                    on_request_start(str(request.text or ""))
                except Exception:
                    pass
            begin_activity_capture()
            task_run = None
            if callable(on_task_run_start):
                try:
                    task_run = on_task_run_start(request)
                except Exception:
                    task_run = None
            runtime_request = request
            if callable(prepare_runtime_request):
                try:
                    runtime_request = prepare_runtime_request(request)
                except Exception:
                    runtime_request = request
            try:
                response = await _run_runtime_request_in_daemon_thread(runtime, runtime_request)
            except Exception as exc:
                if timeline_debug_enabled():
                    log_timeline(
                        "ui.request_worker.error",
                        text_preview=str(request.text or "")[:200],
                        duration_ms=int((perf_counter() - started_at) * 1000),
                        error=str(exc),
                        queue_size_current=queue.qsize(),
                        pending_prefetched_count=len(pending_requests),
                    )
                write_assistant_reply(f"Execution failed: {exc}")
                if callable(on_task_run_error):
                    try:
                        on_task_run_error(task_run, exc)
                    except Exception:
                        pass
            else:
                if timeline_debug_enabled():
                    log_timeline(
                        "ui.request_worker.finish",
                        text_preview=str(request.text or "")[:200],
                        duration_ms=int((perf_counter() - started_at) * 1000),
                        handled_as_command=bool(getattr(response, "handled_as_command", False)),
                        queue_size_current=queue.qsize(),
                        pending_prefetched_count=len(pending_requests),
                    )
                render_response(response)
                handle_response(response)
                if callable(on_task_run_response):
                    try:
                        on_task_run_response(task_run, response)
                    except Exception:
                        pass
            finally:
                queue.task_done()
                if queue.empty() and not pending_requests:
                    set_busy(False)
                    on_idle()
    except asyncio.CancelledError:
        return


async def wait_for_runtime_idle(queue: asyncio.Queue[QueuedRuntimeRequest]) -> None:
    await queue.join()
    await asyncio.sleep(0)
