from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.provider import _tool_specs
from cli.agent_cli.runtime import AgentCliRuntime
from shared.web_automation import client as browser_client_module
from shared.web_automation.client import BrowserClient
from shared.web_automation.observe import append_console_entry
from shared.web_automation.service import BrowserService

class BrowserToolStateControlsTest(unittest.TestCase):
    def test_provider_browser_schema_includes_debug_and_state_actions(self) -> None:
        specs = _tool_specs(current_host_platform())
        browser_spec = next(item for item in specs if item["function"]["name"] == "browser")
        properties = browser_spec["function"]["parameters"]["properties"]
        action_enum = set(properties["action"]["enum"])

        self.assertTrue(
            {"errors", "requests", "highlight", "trace_start", "trace_stop", "cookies", "storage_state"}.issubset(
                action_enum
            )
        )
        self.assertIn("method", properties)
        self.assertIn("outcome", properties)

    def test_highlight_returns_ref_scoped_preview_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            old_service = browser_client_module._service
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    client = BrowserClient()

                    self.assertTrue(client.perform(action="start")["ok"])
                    opened = client.perform(action="open", url="https://example.com/report")
                    self.assertTrue(opened["ok"])

                    snapshot = client.perform(action="snapshot")
                    self.assertTrue(snapshot["ok"])
                    ref = snapshot["refs"][0]["ref"]

                    highlighted = client.perform(action="highlight", ref=ref, time_ms=150)

                    self.assertTrue(highlighted["ok"])
                    self.assertEqual(highlighted["action"], "highlight")
                    self.assertEqual(highlighted["ref"], ref)
                    self.assertEqual(highlighted["target_id"], opened["target_id"])
                    self.assertEqual(highlighted["highlight_mode"], "synthetic_preview")
                    self.assertEqual(highlighted["duration_ms"], 150)
                    artifact = highlighted["artifact"]
                    self.assertEqual(artifact["kind"], "screenshot")
                    self.assertEqual(artifact["ref"], ref)
                    self.assertTrue(Path(artifact["path"]).exists())

                    tab = browser_client_module._service.list_tabs()[0]
                    self.assertEqual(tab.artifacts[-1].kind, "screenshot")
                    self.assertEqual(tab.artifacts[-1].ref, ref)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(old_service)

    def test_runtime_browser_debug_and_state_commands_are_exposed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            old_service = browser_client_module._service
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    opened = runtime.handle_prompt("/browser open --url https://example.com/report").tool_events[0]
                    runtime.handle_prompt("/browser snapshot")

                    highlighted = runtime.handle_prompt("/browser highlight --ref r1 --time-ms 90").tool_events[0]
                    started = runtime.handle_prompt("/browser trace_start").tool_events[0]
                    stopped = runtime.handle_prompt("/browser trace_stop --path captures/report-trace.json").tool_events[0]
                    cookies = runtime.handle_prompt("/browser cookies").tool_events[0]
                    storage_state = runtime.handle_prompt("/browser storage_state").tool_events[0]

                    self.assertEqual(highlighted.name, "browser_action")
                    self.assertTrue(highlighted.ok)
                    self.assertEqual(highlighted.payload["action"], "highlight")
                    self.assertEqual(highlighted.payload["ref"], "r1")
                    self.assertEqual(highlighted.payload["duration_ms"], 90)
                    self.assertTrue(Path(highlighted.payload["path"]).exists())

                    self.assertEqual(started.name, "browser_action")
                    self.assertTrue(started.ok)
                    self.assertEqual(started.payload["action"], "trace_start")
                    self.assertEqual(started.payload["target_id"], opened.payload["target_id"])
                    self.assertIn("trace_id", started.payload)

                    self.assertEqual(stopped.name, "browser_action")
                    self.assertTrue(stopped.ok)
                    self.assertEqual(stopped.payload["action"], "trace_stop")
                    self.assertEqual(stopped.payload["format"], "zip")
                    self.assertTrue(str(stopped.payload["path"]).endswith("captures/report-trace.json"))
                    self.assertTrue(Path(stopped.payload["path"]).exists())

                    self.assertEqual(cookies.name, "browser_action")
                    self.assertTrue(cookies.ok)
                    self.assertEqual(cookies.payload["action"], "cookies")
                    self.assertEqual(cookies.payload["count"], 0)

                    self.assertEqual(storage_state.name, "browser_action")
                    self.assertTrue(storage_state.ok)
                    self.assertEqual(storage_state.payload["action"], "storage_state")
                    self.assertEqual(storage_state.payload["count"], 0)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(old_service)

    def test_runtime_browser_errors_and_requests_commands_emit_debug_views(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            old_service = browser_client_module._service
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    runtime.handle_prompt("/browser open --url https://example.com/report")
                    tab = browser_client_module._service.list_tabs()[0]
                    append_console_entry(tab, message_type="error", text="render failed", location={"url": tab.url})
                    append_console_entry(
                        tab,
                        message_type="request",
                        text="POST /api/login",
                        location={
                            "url": "https://example.com/api/login",
                            "method": "POST",
                            "status": "503",
                            "outcome": "failed",
                            "resource_type": "xhr",
                        },
                    )

                    errors = runtime.handle_prompt("/browser errors --limit 5").tool_events[0]
                    requests = runtime.handle_prompt("/browser requests --method POST --outcome failed").tool_events[0]

                    self.assertEqual(errors.name, "browser_console")
                    self.assertTrue(errors.ok)
                    self.assertEqual(errors.payload["action"], "errors")
                    self.assertEqual(errors.payload["count"], 1)
                    self.assertEqual(errors.payload["entries"][0]["message"], "render failed")

                    self.assertEqual(requests.name, "browser_console")
                    self.assertTrue(requests.ok)
                    self.assertEqual(requests.payload["action"], "requests")
                    self.assertEqual(requests.payload["count"], 1)
                    self.assertEqual(requests.payload["entries"][0]["method"], "POST")
                    self.assertEqual(requests.payload["entries"][0]["outcome"], "failed")
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(old_service)

    def test_trace_start_stop_emits_debug_bundle_with_state_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            old_service = browser_client_module._service
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    client = BrowserClient()

                    client.perform(action="start")
                    opened = client.perform(action="open", url="https://example.com/report")
                    client.perform(action="snapshot")
                    tab = browser_client_module._service.list_tabs()[0]
                    append_console_entry(tab, message_type="warning", text="slow api", location={"url": tab.url})

                    started = client.perform(action="trace_start")
                    self.assertTrue(started["ok"])
                    self.assertEqual(started["action"], "trace_start")
                    self.assertEqual(started["capture_mode"], "debug_bundle")
                    trace_id = started["trace_id"]

                    stopped = client.perform(action="trace_stop", path="captures/report-trace.json")

                    self.assertTrue(stopped["ok"])
                    self.assertEqual(stopped["action"], "trace_stop")
                    self.assertEqual(stopped["capture_mode"], "debug_bundle")
                    self.assertEqual(stopped["trace_id"], trace_id)
                    artifact = stopped["artifact"]
                    self.assertEqual(artifact["kind"], "trace")
                    self.assertTrue(str(artifact["path"]).endswith("captures/report-trace.json"))
                    self.assertTrue(Path(artifact["path"]).exists())

                    bundle = json.loads(Path(artifact["path"]).read_text(encoding="utf-8"))
                    self.assertEqual(bundle["trace_id"], trace_id)
                    self.assertEqual(bundle["target_id"], opened["target_id"])
                    self.assertEqual(bundle["profile"], "openclaw")
                    self.assertIn("snapshot", bundle)
                    self.assertIn("console", bundle)
                    self.assertIn("cookies", bundle)
                    self.assertIn("storage_state", bundle)
                    self.assertTrue(bundle["snapshot"]["refs"])
                    self.assertTrue(any(item["text"] == "slow api" for item in bundle["console"]))
                    self.assertEqual(bundle["cookies"], [])
                    self.assertEqual(bundle["storage_state"], {"origins": []})
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(old_service)

    def test_synthetic_cookies_and_storage_state_return_empty_runtime_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            old_service = browser_client_module._service
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    client = BrowserClient()

                    client.perform(action="start")
                    opened = client.perform(action="open", url="https://example.com/report")

                    cookies = client.perform(action="cookies")
                    storage_state = client.perform(action="storage_state")

                    self.assertTrue(cookies["ok"])
                    self.assertEqual(cookies["action"], "cookies")
                    self.assertEqual(cookies["count"], 0)
                    self.assertEqual(cookies["cookies"], [])
                    self.assertEqual(cookies["target_id"], opened["target_id"])

                    self.assertTrue(storage_state["ok"])
                    self.assertEqual(storage_state["action"], "storage_state")
                    self.assertEqual(storage_state["count"], 0)
                    self.assertEqual(storage_state["storage_state"], {"origins": []})
                    self.assertEqual(storage_state["target_id"], opened["target_id"])
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(old_service)
