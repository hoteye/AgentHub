from __future__ import annotations

import asyncio
import threading
import unittest
from contextlib import suppress
from types import SimpleNamespace

from cli.agent_cli.ui.request_worker import enqueue_runtime_request, request_worker_loop
from cli.agent_cli.ui.runtime_bridge import QueuedRuntimeRequest, normalize_runtime_request_priority


class _RuntimeStub:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.daemon_flags: list[bool] = []

    def handle_prompt(self, text: str, *, attachments: list | None = None):  # noqa: ANN201
        del attachments
        self.calls.append(str(text or ""))
        self.daemon_flags.append(bool(threading.current_thread().daemon))
        return SimpleNamespace(assistant_text=f"ok:{text}", handled_as_command=False)


class _FailingRuntimeStub:
    def handle_prompt(self, text: str, *, attachments: list | None = None):  # noqa: ANN201
        del text, attachments
        raise RuntimeError("boom")


class RequestQueuePrioritySemanticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_request_worker_respects_now_next_later_priority(self) -> None:
        queue: asyncio.Queue[QueuedRuntimeRequest] = asyncio.Queue()
        runtime = _RuntimeStub()
        busy_events: list[bool] = []
        idle_events: list[str] = []

        await enqueue_runtime_request(queue, "normal", [], priority="next")
        await enqueue_runtime_request(queue, "deferred", [], priority="later")
        await enqueue_runtime_request(queue, "urgent", [], priority="now")

        worker = asyncio.create_task(
            request_worker_loop(
                queue=queue,
                runtime=runtime,
                set_busy=lambda value: busy_events.append(bool(value)),
                on_request_start=None,
                on_request_echo=None,
                begin_activity_capture=lambda: None,
                render_response=lambda _response: None,
                handle_response=lambda _response: None,
                write_assistant_reply=lambda _text: None,
                on_idle=lambda: idle_events.append("idle"),
            )
        )
        await queue.join()
        await asyncio.sleep(0)
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

        self.assertEqual(runtime.calls, ["urgent", "normal", "deferred"])
        self.assertEqual(runtime.daemon_flags, [True, True, True])
        self.assertTrue(any(busy_events))
        self.assertEqual(idle_events, ["idle"])

    async def test_request_worker_preserves_fifo_within_same_priority(self) -> None:
        queue: asyncio.Queue[QueuedRuntimeRequest] = asyncio.Queue()
        runtime = _RuntimeStub()

        await enqueue_runtime_request(queue, "next-1", [], priority="next")
        await enqueue_runtime_request(queue, "next-2", [], priority="next")
        await enqueue_runtime_request(queue, "next-3", [], priority="next")

        worker = asyncio.create_task(
            request_worker_loop(
                queue=queue,
                runtime=runtime,
                set_busy=lambda _value: None,
                on_request_start=None,
                on_request_echo=None,
                begin_activity_capture=lambda: None,
                render_response=lambda _response: None,
                handle_response=lambda _response: None,
                write_assistant_reply=lambda _text: None,
                on_idle=lambda: None,
            )
        )
        await queue.join()
        await asyncio.sleep(0)
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

        self.assertEqual(runtime.calls, ["next-1", "next-2", "next-3"])

    async def test_request_worker_does_not_mark_slash_commands_busy(self) -> None:
        queue: asyncio.Queue[QueuedRuntimeRequest] = asyncio.Queue()
        runtime = _RuntimeStub()
        busy_events: list[bool] = []

        await enqueue_runtime_request(queue, "/provider openai", [], priority="next")

        worker = asyncio.create_task(
            request_worker_loop(
                queue=queue,
                runtime=runtime,
                set_busy=lambda value: busy_events.append(bool(value)),
                on_request_start=None,
                on_request_echo=None,
                begin_activity_capture=lambda: None,
                render_response=lambda _response: None,
                handle_response=lambda _response: None,
                write_assistant_reply=lambda _text: None,
                on_idle=lambda: None,
            )
        )
        await queue.join()
        await asyncio.sleep(0)
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

        self.assertEqual(runtime.calls, ["/provider openai"])
        self.assertNotIn(True, busy_events)

    async def test_enqueue_runtime_request_normalizes_unknown_priority_to_next(self) -> None:
        queue: asyncio.Queue[QueuedRuntimeRequest] = asyncio.Queue()

        await enqueue_runtime_request(queue, "unknown-priority", [], priority="unexpected")
        queued = queue.get_nowait()
        self.assertEqual(queued.priority, "next")
        queue.task_done()

    def test_normalize_runtime_request_priority_uses_alias_fallback(self) -> None:
        self.assertEqual(normalize_runtime_request_priority("now"), "now")
        self.assertEqual(normalize_runtime_request_priority("later"), "later")
        self.assertEqual(normalize_runtime_request_priority("unsupported"), "next")

    async def test_request_worker_emits_task_run_callbacks_for_success(self) -> None:
        queue: asyncio.Queue[QueuedRuntimeRequest] = asyncio.Queue()
        runtime = _RuntimeStub()
        started: list[str] = []
        completed: list[tuple[object, str]] = []

        await enqueue_runtime_request(queue, "hello", [], priority="next")

        worker = asyncio.create_task(
            request_worker_loop(
                queue=queue,
                runtime=runtime,
                set_busy=lambda _value: None,
                on_request_start=None,
                on_request_echo=None,
                begin_activity_capture=lambda: None,
                render_response=lambda _response: None,
                handle_response=lambda _response: None,
                write_assistant_reply=lambda _text: None,
                on_idle=lambda: None,
                on_task_run_start=lambda request: started.append(request.text) or "run-1",
                on_task_run_response=lambda task_run, response: completed.append(
                    (task_run, response.assistant_text)
                ),
            )
        )
        await queue.join()
        await asyncio.sleep(0)
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

        self.assertEqual(started, ["hello"])
        self.assertEqual(completed, [("run-1", "ok:hello")])

    async def test_request_worker_emits_task_run_callbacks_for_error(self) -> None:
        queue: asyncio.Queue[QueuedRuntimeRequest] = asyncio.Queue()
        errors: list[tuple[object, str]] = []
        replies: list[str] = []

        await enqueue_runtime_request(queue, "hello", [], priority="next")

        worker = asyncio.create_task(
            request_worker_loop(
                queue=queue,
                runtime=_FailingRuntimeStub(),
                set_busy=lambda _value: None,
                on_request_start=None,
                on_request_echo=None,
                begin_activity_capture=lambda: None,
                render_response=lambda _response: None,
                handle_response=lambda _response: None,
                write_assistant_reply=replies.append,
                on_idle=lambda: None,
                on_task_run_start=lambda _request: "run-1",
                on_task_run_error=lambda task_run, error: errors.append((task_run, str(error))),
            )
        )
        await queue.join()
        await asyncio.sleep(0)
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

        self.assertEqual(errors, [("run-1", "boom")])
        self.assertEqual(replies, ["Execution failed: boom"])
