from __future__ import annotations

import threading
import unittest

from cli.agent_cli.runtime_core import run_lifecycle


class _FakeTools:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def interrupt_shell_sessions(
        self,
        *,
        cancel_event: threading.Event | None,
        reason: str = "user_interrupt",
    ) -> dict[str, object]:
        self.calls.append(
            {
                "cancel_event": cancel_event,
                "reason": reason,
            }
        )
        return {
            "ok": True,
            "session_ids": ["sess-1"],
            "count": 1,
        }


class _FakeRuntime:
    def __init__(self) -> None:
        self._run_state_lock = threading.Lock()
        self._active_run_token = "run-123"
        self._active_run_label = "sleep 30"
        self._cancel_event = threading.Event()
        self.thread_id = "thread-1"
        self.tools = _FakeTools()
        self.agent = self._FakeAgent()
        self.activities: list[object] = []

    class _FakeAgent:
        def __init__(self) -> None:
            self.interrupt_calls = 0

        def interrupt_active_provider_stream(self) -> bool:
            self.interrupt_calls += 1
            return True

    def _emit_activity(self, event: object) -> None:
        self.activities.append(event)


class RuntimeInterruptsTest(unittest.TestCase):
    def test_interrupt_active_run_proactively_interrupts_matching_shell_sessions(self) -> None:
        runtime = _FakeRuntime()

        result = run_lifecycle.interrupt_active_run(runtime)

        self.assertTrue(runtime._cancel_event.is_set())
        self.assertEqual(len(runtime.tools.calls), 1)
        self.assertIs(runtime.tools.calls[0]["cancel_event"], runtime._cancel_event)
        self.assertEqual(runtime.tools.calls[0]["reason"], "user_interrupt")
        self.assertTrue(result["ok"])
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["shell_session_ids"], ["sess-1"])
        self.assertEqual(result["shell_session_count"], 1)
        self.assertTrue(result["provider_stream_interrupted"])
        self.assertEqual(runtime.agent.interrupt_calls, 1)

