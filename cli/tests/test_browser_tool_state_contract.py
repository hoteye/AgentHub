from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.provider import _command_for_tool_call, _tool_specs
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.slash_commands import slash_command_help_text
from shared.web_automation import client as browser_client_module
from shared.web_automation.client import BrowserClient
from shared.web_automation.service import BrowserService


def _client_state_contract_available() -> bool:
    required = (
        "cookies_payload",
        "storage_state_payload",
        "get_cookies",
        "set_cookies",
        "clear_cookies",
        "get_storage",
        "set_storage",
        "clear_storage",
        "highlight",
        "trace_start",
        "trace_stop",
    )
    return all(hasattr(BrowserClient, name) for name in required)


class BrowserToolStateContractTest(unittest.TestCase):
    def test_browser_client_state_mutation_payload_contract(self) -> None:
        self.assertTrue(_client_state_contract_available())
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            old_service = browser_client_module._service
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    client = BrowserClient()

                    self.assertTrue(client.perform(action="start")["ok"])
                    opened = client.perform(action="open", url="https://example.com/app")
                    target_id = opened["target_id"]

                    set_cookies_result = client.set_cookies(
                        tab_id=target_id,
                        cookies=[
                            {
                                "name": "session_id",
                                "value": "abc123",
                                "domain": "example.com",
                                "path": "/",
                            }
                        ],
                    )
                    self.assertTrue(set_cookies_result["ok"])
                    self.assertEqual(set_cookies_result["action"], "cookies_set")
                    self.assertEqual(set_cookies_result["target_id"], target_id)
                    self.assertEqual(set_cookies_result["count"], 1)

                    get_cookies_result = client.get_cookies(tab_id=target_id)
                    self.assertTrue(get_cookies_result["ok"])
                    self.assertEqual(get_cookies_result["action"], "cookies_get")
                    self.assertEqual(get_cookies_result["target_id"], target_id)
                    self.assertEqual(get_cookies_result["cookies"][0]["name"], "session_id")

                    clear_cookies_result = client.clear_cookies(tab_id=target_id)
                    self.assertTrue(clear_cookies_result["ok"])
                    self.assertEqual(clear_cookies_result["action"], "cookies_clear")
                    self.assertEqual(clear_cookies_result["target_id"], target_id)
                    self.assertEqual(clear_cookies_result["cleared"], 1)

                    set_storage_result = client.set_storage(
                        tab_id=target_id,
                        storage_kind="local",
                        items={"token": "t-1"},
                    )
                    self.assertTrue(set_storage_result["ok"])
                    self.assertEqual(set_storage_result["action"], "storage_set")
                    self.assertEqual(set_storage_result["storage_kind"], "local")
                    self.assertEqual(set_storage_result["count"], 1)

                    get_storage_result = client.get_storage(tab_id=target_id, storage_kind="local")
                    self.assertTrue(get_storage_result["ok"])
                    self.assertEqual(get_storage_result["action"], "storage_get")
                    self.assertEqual(get_storage_result["storage_kind"], "local")
                    self.assertEqual(get_storage_result["items"], {"token": "t-1"})

                    clear_storage_result = client.clear_storage(
                        tab_id=target_id, storage_kind="local"
                    )
                    self.assertTrue(clear_storage_result["ok"])
                    self.assertEqual(clear_storage_result["action"], "storage_clear")
                    self.assertEqual(clear_storage_result["storage_kind"], "local")
                    self.assertEqual(clear_storage_result["cleared"], 1)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(old_service)

    def test_browser_client_read_only_state_payload_contract(self) -> None:
        self.assertTrue(_client_state_contract_available())
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

                    cookies_result = client.cookies_payload(tab_id=opened["target_id"])  # type: ignore[attr-defined]
                    self.assertTrue(cookies_result["ok"])
                    self.assertEqual(cookies_result["action"], "cookies")
                    self.assertEqual(cookies_result["target_id"], opened["target_id"])
                    self.assertEqual(cookies_result["count"], 0)
                    self.assertEqual(cookies_result["cookies"], [])

                    storage_result = client.storage_state_payload(tab_id=opened["target_id"])  # type: ignore[attr-defined]
                    self.assertTrue(storage_result["ok"])
                    self.assertEqual(storage_result["action"], "storage_state")
                    self.assertEqual(storage_result["target_id"], opened["target_id"])
                    self.assertEqual(storage_result["count"], 0)
                    self.assertEqual(storage_result["storage_state"], {"origins": []})
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(old_service)

    def test_browser_state_schema_and_tool_call_contract(self) -> None:
        self.assertTrue(_client_state_contract_available())
        specs = _tool_specs(current_host_platform())
        browser_spec = next(item for item in specs if item["function"]["name"] == "browser")
        parameters = browser_spec["function"]["parameters"]["properties"]
        actions = set(parameters["action"]["enum"])

        self.assertTrue(
            {
                "highlight",
                "trace_start",
                "trace_stop",
                "cookies",
                "cookies_get",
                "cookies_set",
                "cookies_clear",
                "storage_state",
                "storage_get",
                "storage_set",
                "storage_clear",
            }.issubset(actions)
        )
        self.assertIn("time_ms", parameters)
        self.assertIn("path", parameters)
        self.assertIn("cookies", parameters)
        self.assertIn("items", parameters)
        self.assertIn("storage_kind", parameters)
        self.assertIn("transport", parameters)

        highlight_command = _command_for_tool_call(
            "browser",
            {"action": "highlight", "tab": "tab-1", "ref": "r1", "time_ms": 90},
            current_host_platform(),
        )
        self.assertEqual(highlight_command, "/browser highlight --tab tab-1 --ref r1 --time-ms 90")

        trace_stop_command = _command_for_tool_call(
            "browser",
            {"action": "trace_stop", "path": "captures/report-trace.json"},
            current_host_platform(),
        )
        self.assertEqual(
            trace_stop_command, "/browser trace_stop --path captures/report-trace.json"
        )

        cookies_command = _command_for_tool_call(
            "browser",
            {"action": "cookies", "tab": "tab-1"},
            current_host_platform(),
        )
        self.assertEqual(cookies_command, "/browser cookies --tab tab-1")

        cookies_set_command = _command_for_tool_call(
            "browser",
            {
                "action": "cookies_set",
                "tab": "tab-1",
                "cookies": [
                    {
                        "name": "session",
                        "value": "abc123",
                        "url": "https://example.com",
                        "httpOnly": True,
                    }
                ],
            },
            current_host_platform(),
        )
        self.assertEqual(
            cookies_set_command,
            "/browser cookies set session abc123 --tab tab-1 --url https://example.com --http-only",
        )

        storage_set_command = _command_for_tool_call(
            "browser",
            {
                "action": "storage_set",
                "tab": "tab-1",
                "storage_kind": "local",
                "items": {"theme": "dark"},
            },
            current_host_platform(),
        )
        self.assertEqual(storage_set_command, "/browser storage local set --tab tab-1 theme dark")

        transport_command = _command_for_tool_call(
            "browser",
            {"action": "status", "profile": "review", "transport": "proxy"},
            current_host_platform(),
        )
        self.assertEqual(transport_command, "/browser status --profile review --transport proxy")

    def test_browser_state_cli_regression_and_help_text(self) -> None:
        self.assertTrue(_client_state_contract_available())
        help_text = slash_command_help_text()
        self.assertIn("Use /help all to show advanced and plugin commands.", help_text)
        advanced_help_text = slash_command_help_text(include_advanced=True)
        self.assertIn("/browser <action>", advanced_help_text)
        self.assertIn("storage", advanced_help_text)
        self.assertIn("transport <local|proxy>", advanced_help_text)
        self.assertIn("method <verb>", advanced_help_text)
        self.assertIn("outcome <kind>", advanced_help_text)

        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            old_service = browser_client_module._service
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    browser_client_module.replace_service(BrowserService())
                    runtime = AgentCliRuntime()

                    runtime.handle_prompt("/browser start")
                    opened = runtime.handle_prompt(
                        "/browser open --url https://example.com/report"
                    ).tool_events[0]
                    runtime.handle_prompt("/browser snapshot")
                    transport_status_event = runtime.handle_prompt(
                        "/browser status --transport local"
                    ).tool_events[0]

                    highlight_event = runtime.handle_prompt(
                        "/browser highlight --ref r1 --time-ms 90"
                    ).tool_events[0]
                    trace_start_event = runtime.handle_prompt("/browser trace_start").tool_events[0]
                    trace_stop_event = runtime.handle_prompt(
                        "/browser trace_stop --path captures/report-trace.json"
                    ).tool_events[0]
                    cookies_event = runtime.handle_prompt("/browser cookies").tool_events[0]
                    storage_event = runtime.handle_prompt("/browser storage_state").tool_events[0]

                    self.assertTrue(transport_status_event.ok)
                    self.assertEqual(transport_status_event.payload["requested_transport"], "local")
                    self.assertEqual(highlight_event.name, "browser_action")
                    self.assertTrue(highlight_event.ok)
                    self.assertEqual(highlight_event.payload["action"], "highlight")
                    self.assertEqual(
                        highlight_event.payload["target_id"], opened.payload["target_id"]
                    )
                    self.assertTrue(Path(highlight_event.payload["path"]).exists())

                    self.assertEqual(trace_start_event.name, "browser_action")
                    self.assertTrue(trace_start_event.ok)
                    self.assertEqual(trace_start_event.payload["action"], "trace_start")
                    self.assertEqual(
                        trace_start_event.payload["target_id"], opened.payload["target_id"]
                    )
                    self.assertIn("trace_id", trace_start_event.payload)

                    self.assertEqual(trace_stop_event.name, "browser_action")
                    self.assertTrue(trace_stop_event.ok)
                    self.assertEqual(trace_stop_event.payload["action"], "trace_stop")
                    self.assertEqual(
                        trace_stop_event.payload["target_id"], opened.payload["target_id"]
                    )
                    self.assertTrue(Path(trace_stop_event.payload["path"]).exists())

                    self.assertEqual(cookies_event.name, "browser_action")
                    self.assertTrue(cookies_event.ok)
                    self.assertEqual(cookies_event.payload["action"], "cookies")
                    self.assertEqual(
                        cookies_event.payload["target_id"], opened.payload["target_id"]
                    )
                    self.assertEqual(cookies_event.payload["count"], 0)

                    self.assertEqual(storage_event.name, "browser_action")
                    self.assertTrue(storage_event.ok)
                    self.assertEqual(storage_event.payload["action"], "storage_state")
                    self.assertEqual(
                        storage_event.payload["target_id"], opened.payload["target_id"]
                    )
                    self.assertEqual(storage_event.payload["count"], 0)

                    cookie_set_event = runtime.handle_prompt(
                        "/browser cookies set session abc123 --url https://example.com"
                    ).tool_events[0]
                    cookie_get_event = runtime.handle_prompt("/browser cookies").tool_events[0]
                    cookie_clear_event = runtime.handle_prompt(
                        "/browser cookies clear"
                    ).tool_events[0]
                    storage_set_event = runtime.handle_prompt(
                        "/browser storage local set theme dark"
                    ).tool_events[0]
                    storage_get_event = runtime.handle_prompt(
                        "/browser storage local get"
                    ).tool_events[0]
                    storage_clear_event = runtime.handle_prompt(
                        "/browser storage local clear"
                    ).tool_events[0]

                    self.assertTrue(cookie_set_event.ok)
                    self.assertEqual(cookie_set_event.payload["action"], "cookies_set")
                    self.assertEqual(cookie_set_event.payload["count"], 1)

                    self.assertTrue(cookie_get_event.ok)
                    self.assertEqual(cookie_get_event.payload["action"], "cookies")
                    self.assertEqual(cookie_get_event.payload["cookies"][0]["name"], "session")

                    self.assertTrue(cookie_clear_event.ok)
                    self.assertEqual(cookie_clear_event.payload["action"], "cookies_clear")
                    self.assertEqual(cookie_clear_event.payload["cleared"], 1)

                    self.assertTrue(storage_set_event.ok)
                    self.assertEqual(storage_set_event.payload["action"], "storage_set")
                    self.assertEqual(storage_set_event.payload["storage_kind"], "local")
                    self.assertEqual(storage_set_event.payload["count"], 1)

                    self.assertTrue(storage_get_event.ok)
                    self.assertEqual(storage_get_event.payload["action"], "storage_get")
                    self.assertEqual(storage_get_event.payload["storage_kind"], "local")
                    self.assertEqual(storage_get_event.payload["items"], {"theme": "dark"})

                    self.assertTrue(storage_clear_event.ok)
                    self.assertEqual(storage_clear_event.payload["action"], "storage_clear")
                    self.assertEqual(storage_clear_event.payload["storage_kind"], "local")
                    self.assertEqual(storage_clear_event.payload["cleared"], 1)
            finally:
                os.chdir(old_cwd)
                browser_client_module.replace_service(old_service)
