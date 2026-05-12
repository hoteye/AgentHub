from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from cli.agent_cli.provider import _tool_specs
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.runtime import AgentCliRuntime
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService

class BrowserToolActExtendedTest(unittest.TestCase):
    def test_provider_browser_schema_includes_drag_scroll_and_resize_fields(self) -> None:
        specs = _tool_specs(current_host_platform())
        browser_spec = next(item for item in specs if item["function"]["name"] == "browser")
        properties = browser_spec["function"]["parameters"]["properties"]
        kind_enum = properties["kind"]["enum"]

        for item in ("drag", "scroll_into_view", "resize"):
            self.assertIn(item, kind_enum)
        self.assertIn("start_ref", properties)
        self.assertIn("end_ref", properties)
        self.assertIn("width", properties)
        self.assertIn("height", properties)

    def test_runtime_browser_act_supports_drag_scroll_and_resize(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/workflow")

                    scroll_event = runtime.handle_prompt("/browser act scroll_into_view r1").tool_events[0]
                    self.assertTrue(scroll_event.ok)
                    self.assertEqual(scroll_event.payload["action"], "scroll_into_view")
                    self.assertEqual(scroll_event.payload["ref"], "r1")

                    drag_event = runtime.handle_prompt("/browser act drag r1 r1").tool_events[0]
                    self.assertTrue(drag_event.ok)
                    self.assertEqual(drag_event.payload["action"], "drag")
                    self.assertEqual(drag_event.payload["result"]["start_ref"], "r1")
                    self.assertEqual(drag_event.payload["result"]["end_ref"], "r1")

                    resize_event = runtime.handle_prompt("/browser act resize 1280 720").tool_events[0]
                    self.assertTrue(resize_event.ok)
                    self.assertEqual(resize_event.payload["action"], "resize")
                    self.assertEqual(resize_event.payload["result"]["width"], 1280)
                    self.assertEqual(resize_event.payload["result"]["height"], 720)

                    console = runtime.handle_prompt("/browser console").tool_events[0]
                    messages = [entry["message"] for entry in console.payload["entries"]]
                    self.assertIn("Scrolled ref r1 into view", messages)
                    self.assertIn("Dragged ref r1 to r1", messages)
                    self.assertIn("Resized viewport to 1280x720", messages)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_runtime_browser_act_reports_usage_for_invalid_resize_positionals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    response = runtime.handle_prompt("/browser act resize wide 720")

                    self.assertEqual(response.tool_events, [])
                    self.assertIn("Usage: /browser act resize <width> <height>", response.assistant_text)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())

    def test_runtime_browser_act_surfaces_missing_refs_and_invalid_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/workflow")

                    scroll_missing_ref = runtime.handle_prompt("/browser act scroll_into_view").tool_events[0]
                    self.assertFalse(scroll_missing_ref.ok)
                    self.assertIn("action requires ref", str(scroll_missing_ref.payload.get("error") or ""))

                    drag_missing_end_ref = runtime.handle_prompt("/browser act drag r1").tool_events[0]
                    self.assertFalse(drag_missing_end_ref.ok)
                    self.assertIn("action requires ref", str(drag_missing_end_ref.payload.get("error") or ""))

                    resize_invalid_dimensions = runtime.handle_prompt("/browser act resize 0 720").tool_events[0]
                    self.assertFalse(resize_invalid_dimensions.ok)
                    self.assertIn(
                        "resize requires width and height",
                        str(resize_invalid_dimensions.payload.get("error") or ""),
                    )
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(BrowserService())
