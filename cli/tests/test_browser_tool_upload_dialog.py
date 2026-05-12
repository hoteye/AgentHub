from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event
from cli.agent_cli.ui.transcript_formatting import format_browser_activity_lines
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService

class BrowserToolUploadDialogTranscriptTest(unittest.TestCase):
    def test_browser_upload_event_rendering_surfaces_count_and_ref(self) -> None:
        event = ToolEvent(
            name="browser_action",
            ok=True,
            summary="browser action",
            payload={
                "action": "upload",
                "operation": "hook",
                "target_id": "tab-upload",
                "ref": "r1",
                "count": 2,
                "message": "Armed upload hook for ref r1 with 2 file(s)",
            },
        )
        activities = activity_events_for_tool_event(event)
        self.assertEqual(len(activities), 1)
        lines = format_browser_activity_lines(activities[0])
        self.assertTrue(any("action=upload" in line for line in lines))
        self.assertTrue(any("ref=r1" in line for line in lines))
        self.assertTrue(any("count=2" in line for line in lines))

    def test_browser_dialog_event_rendering_surfaces_accept_state(self) -> None:
        event = ToolEvent(
            name="browser_action",
            ok=True,
            summary="browser action",
            payload={
                "action": "dialog",
                "operation": "hook",
                "target_id": "tab-dialog",
                "accept": False,
                "message": "Armed dialog hook to dismiss with prompt text",
            },
        )
        activities = activity_events_for_tool_event(event)
        lines = format_browser_activity_lines(activities[0])
        self.assertTrue(any("action=dialog" in line for line in lines))
        self.assertTrue(any("accept=False" in line for line in lines))

class BrowserToolUploadDialogExecutionTest(unittest.TestCase):
    def test_runtime_browser_upload_hook_arms_and_applies_to_click(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                upload_a = Path(temp_dir) / "upload-a.txt"
                upload_b = Path(temp_dir) / "upload-b.txt"
                upload_a.write_text("alpha", encoding="utf-8")
                upload_b.write_text("beta", encoding="utf-8")

                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/upload")

                    armed = runtime.handle_prompt(
                        f"/browser upload --ref r1 --paths {upload_a},{upload_b}"
                    )
                    armed_event = armed.tool_events[0]
                    self.assertEqual(armed_event.name, "browser_action")
                    self.assertTrue(armed_event.ok)
                    self.assertEqual(armed_event.payload["action"], "upload")
                    self.assertEqual(armed_event.payload["count"], 2)

                    armed_snapshot = runtime.handle_prompt("/browser snapshot")
                    self.assertIn("Armed upload: r1 (2 file(s))", armed_snapshot.tool_events[0].payload["text"])

                    runtime.handle_prompt("/browser act click --ref r1")

                    applied_snapshot = runtime.handle_prompt("/browser snapshot")
                    snapshot_text = applied_snapshot.tool_events[0].payload["text"]
                    self.assertNotIn("Armed upload:", snapshot_text)
                    self.assertIn(f"Upload r1: {upload_a.resolve()}, {upload_b.resolve()}", snapshot_text)

                    console = runtime.handle_prompt("/browser console")
                    messages = [entry["message"] for entry in console.tool_events[0].payload["entries"]]
                    self.assertIn("Armed upload hook for ref r1 with 2 file(s)", messages)
                    self.assertIn("Applied armed upload to ref r1 (2 file(s))", messages)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_runtime_browser_dialog_hook_arms_and_records_last_dialog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/dialog")

                    armed = runtime.handle_prompt('/browser dialog --dismiss --prompt-text "policy denied"')
                    armed_event = armed.tool_events[0]
                    self.assertEqual(armed_event.name, "browser_action")
                    self.assertTrue(armed_event.ok)
                    self.assertEqual(armed_event.payload["action"], "dialog")
                    self.assertFalse(armed_event.payload["accept"])

                    armed_snapshot = runtime.handle_prompt("/browser snapshot")
                    self.assertIn("Armed dialog: dismiss with prompt text", armed_snapshot.tool_events[0].payload["text"])

                    runtime.handle_prompt("/browser act click --ref r1")

                    final_snapshot = runtime.handle_prompt("/browser snapshot")
                    snapshot_text = final_snapshot.tool_events[0].payload["text"]
                    self.assertNotIn("Armed dialog:", snapshot_text)
                    self.assertIn("Last dialog: dismissed with prompt text", snapshot_text)

                    console = runtime.handle_prompt("/browser console")
                    messages = [entry["message"] for entry in console.tool_events[0].payload["entries"]]
                    self.assertIn("Armed dialog hook to dismiss with prompt text", messages)
                    self.assertIn("Handled armed dialog: dismissed", messages)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
