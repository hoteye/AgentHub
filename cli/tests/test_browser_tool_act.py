from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.provider import _tool_specs
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event
from cli.agent_cli.tools import ToolRegistry
from cli.agent_cli.ui.transcript_formatting import format_browser_activity_lines
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService

class BrowserToolActTranscriptTest(unittest.TestCase):
    def test_browser_action_rendering_surfaces_act_ref_and_message(self) -> None:
        event = ToolEvent(
            name="browser_action",
            ok=True,
            summary="browser action",
            payload={
                "action": "click",
                "operation": "act",
                "target_id": "tab-123",
                "ref": "r1",
                "message": "Clicked ref r1",
            },
        )
        activities = activity_events_for_tool_event(event)
        self.assertEqual(len(activities), 1)
        lines = format_browser_activity_lines(activities[0])
        self.assertTrue(any("action=click" in line for line in lines))
        self.assertTrue(any("ref=r1" in line for line in lines))
        self.assertTrue(any("msg=Clicked ref r1" in line for line in lines))

class BrowserToolActExecutionTest(unittest.TestCase):
    def test_tool_registry_normalizes_extended_act_payload_and_kind_alias(self) -> None:
        class _FakeBrowserClient:
            def __init__(self) -> None:
                self.request = None

            def perform(self, **kwargs):
                self.request = dict(kwargs)
                return {
                    "ok": True,
                    "kind": "double_click",
                    "message": "Double-clicked ref r7",
                }

            def status(self):
                return SimpleNamespace(active_tab="tab-9")

            def tabs(self, profile=None):
                return [SimpleNamespace(tab_id="tab-9")]

        tools = ToolRegistry()
        fake_client = _FakeBrowserClient()
        tools._browser_client = fake_client

        event = tools.browser("act", kind="double-click", ref="r7")

        self.assertTrue(event.ok)
        self.assertEqual(event.name, "browser_action")
        self.assertEqual(fake_client.request["kind"], "double_click")
        self.assertEqual(event.payload["operation"], "act")
        self.assertEqual(event.payload["action"], "double_click")
        self.assertEqual(event.payload["ref"], "r7")
        self.assertEqual(event.payload["target_id"], "tab-9")

    def test_provider_browser_schema_includes_extended_act_kind_enum(self) -> None:
        specs = _tool_specs(current_host_platform())
        browser_spec = next(item for item in specs if item["function"]["name"] == "browser")
        kind_enum = browser_spec["function"]["parameters"]["properties"]["kind"]["enum"]

        for item in ("double_click", "check", "uncheck", "focus", "clear"):
            self.assertIn(item, kind_enum)

    def test_runtime_browser_act_supports_extended_positional_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/login")

                    double_clicked = runtime.handle_prompt("/browser act double_click r1").tool_events[0]
                    self.assertTrue(double_clicked.ok)
                    self.assertEqual(double_clicked.payload["action"], "double_click")
                    self.assertEqual(double_clicked.payload["ref"], "r1")

                    focused = runtime.handle_prompt("/browser act focus r1").tool_events[0]
                    self.assertTrue(focused.ok)
                    self.assertEqual(focused.payload["action"], "focus")
                    self.assertEqual(focused.payload["ref"], "r1")

                    checked = runtime.handle_prompt("/browser act check r1").tool_events[0]
                    self.assertTrue(checked.ok)
                    self.assertEqual(checked.payload["action"], "check")
                    self.assertEqual(checked.payload["form_state"]["r1"], "checked")

                    unchecked = runtime.handle_prompt("/browser act uncheck r1").tool_events[0]
                    self.assertTrue(unchecked.ok)
                    self.assertEqual(unchecked.payload["action"], "uncheck")
                    self.assertEqual(unchecked.payload["form_state"]["r1"], "unchecked")

                    runtime.handle_prompt("/browser act type r1 alice")
                    cleared = runtime.handle_prompt("/browser act clear r1").tool_events[0]
                    self.assertTrue(cleared.ok)
                    self.assertEqual(cleared.payload["action"], "clear")
                    self.assertEqual(cleared.payload["form_state"]["r1"], "")
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_runtime_browser_act_updates_snapshot_and_console_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    opened = runtime.handle_prompt("/browser open --url https://example.com/login")
                    tab_id = opened.tool_events[0].payload["target_id"]

                    click = runtime.handle_prompt("/browser act click --ref r1")
                    click_event = click.tool_events[0]
                    self.assertEqual(click_event.name, "browser_action")
                    self.assertTrue(click_event.ok)
                    self.assertEqual(click_event.payload["action"], "click")
                    self.assertEqual(click_event.payload["operation"], "act")
                    self.assertEqual(click_event.payload["target_id"], tab_id)
                    self.assertEqual(click_event.payload["ref"], "r1")

                    typed = runtime.handle_prompt("/browser act type --ref r1 --text alice")
                    typed_event = typed.tool_events[0]
                    self.assertTrue(typed_event.ok)
                    self.assertEqual(typed_event.payload["action"], "type")
                    self.assertEqual(typed_event.payload["form_state"]["r1"], "alice")

                    focused = runtime.handle_prompt("/browser act focus --ref r1")
                    focused_event = focused.tool_events[0]
                    self.assertTrue(focused_event.ok)
                    self.assertEqual(focused_event.payload["action"], "focus")

                    cleared = runtime.handle_prompt("/browser act clear --ref r1")
                    cleared_event = cleared.tool_events[0]
                    self.assertTrue(cleared_event.ok)
                    self.assertEqual(cleared_event.payload["action"], "clear")
                    self.assertEqual(cleared_event.payload["form_state"]["r1"], "")

                    checked = runtime.handle_prompt("/browser act check --ref r1")
                    checked_event = checked.tool_events[0]
                    self.assertTrue(checked_event.ok)
                    self.assertEqual(checked_event.payload["action"], "check")
                    self.assertEqual(checked_event.payload["form_state"]["r1"], "checked")

                    unchecked = runtime.handle_prompt("/browser act uncheck --ref r1")
                    unchecked_event = unchecked.tool_events[0]
                    self.assertTrue(unchecked_event.ok)
                    self.assertEqual(unchecked_event.payload["action"], "uncheck")
                    self.assertEqual(unchecked_event.payload["form_state"]["r1"], "unchecked")

                    double_clicked = runtime.handle_prompt("/browser act double_click --ref r1")
                    double_clicked_event = double_clicked.tool_events[0]
                    self.assertTrue(double_clicked_event.ok)
                    self.assertEqual(double_clicked_event.payload["action"], "double_click")

                    filled = runtime.handle_prompt(
                        '/browser act fill --fields-json \'[{"ref":"r1","value":"alice@example.com"}]\''
                    )
                    filled_event = filled.tool_events[0]
                    self.assertTrue(filled_event.ok)
                    self.assertEqual(filled_event.payload["action"], "fill")
                    self.assertEqual(filled_event.payload["count"], 1)
                    self.assertEqual(filled_event.payload["form_state"]["r1"], "alice@example.com")

                    waited = runtime.handle_prompt("/browser act wait --time-ms 25")
                    waited_event = waited.tool_events[0]
                    self.assertTrue(waited_event.ok)
                    self.assertEqual(waited_event.payload["action"], "wait")
                    self.assertEqual(waited_event.payload["result"]["time_ms"], 25)

                    snapshot = runtime.handle_prompt("/browser snapshot")
                    snapshot_event = snapshot.tool_events[0]
                    self.assertTrue(snapshot_event.ok)
                    self.assertIn("Field r1: alice@example.com", snapshot_event.payload["text"])

                    console = runtime.handle_prompt("/browser console")
                    console_event = console.tool_events[0]
                    self.assertTrue(console_event.ok)
                    self.assertEqual(console_event.payload["target_id"], tab_id)
                    self.assertGreaterEqual(console_event.payload["count"], 5)
                    messages = [entry["message"] for entry in console_event.payload["entries"]]
                    self.assertIn("Clicked ref r1", messages)
                    self.assertIn("Double-clicked ref r1", messages)
                    self.assertIn("Focused ref r1", messages)
                    self.assertIn("Cleared ref r1", messages)
                    self.assertIn("Checked ref r1", messages)
                    self.assertIn("Unchecked ref r1", messages)
                    self.assertIn("Filled 1 field(s)", messages)
                    self.assertIn("Waited for 25ms", messages)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
