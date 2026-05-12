from __future__ import annotations

import unittest

from cli.agent_cli.models import PromptAttachment
from cli.agent_cli.runtime import AgentCliRuntime


class RuntimePendingSteerTest(unittest.TestCase):
    def test_steer_active_run_falls_back_when_no_active_run(self) -> None:
        runtime = AgentCliRuntime()

        payload = runtime.steer_active_run("follow up")

        self.assertFalse(payload["accepted"])
        self.assertTrue(payload["fallback_queue"])
        self.assertEqual(payload["reason"], "no_active_run")

    def test_steer_active_run_falls_back_when_not_supported(self) -> None:
        runtime = AgentCliRuntime()
        run_token = runtime._begin_run("first run")
        try:
            payload = runtime.steer_active_run("follow up")
            self.assertFalse(payload["accepted"])
            self.assertTrue(payload["fallback_queue"])
            self.assertEqual(payload["reason"], "unsupported")
        finally:
            runtime._finish_run(run_token)

    def test_steer_active_run_accepts_and_stores_pending_input_items_when_enabled(self) -> None:
        runtime = AgentCliRuntime()
        runtime._pending_steer_enabled = True
        run_token = runtime._begin_run("first run")
        try:
            payload = runtime.steer_active_run(
                "continue with detail",
                attachments=[PromptAttachment(path="notes/todo.md", name="todo.md")],
            )
            self.assertTrue(payload["accepted"])
            self.assertFalse(payload["fallback_queue"])
            self.assertEqual(payload["reason"], "accepted")

            pending_items = runtime.take_pending_steer_input_items()
            self.assertEqual(len(pending_items), 1)
            self.assertEqual(pending_items[0]["type"], "message")
            self.assertEqual(pending_items[0]["role"], "user")
            text = pending_items[0]["content"][0]["text"]
            self.assertIn("continue with detail", text)
            self.assertIn("Attached references:", text)
            self.assertIn("notes/todo.md", text)
            self.assertEqual(runtime.take_pending_steer_input_items(), [])
        finally:
            runtime._finish_run(run_token)

    def test_finish_run_clears_pending_steer_input_items(self) -> None:
        runtime = AgentCliRuntime()
        runtime._pending_steer_enabled = True
        run_token = runtime._begin_run("first run")
        runtime.steer_active_run("pending follow up")

        runtime._finish_run(run_token)

        self.assertEqual(runtime.take_pending_steer_input_items(), [])
