from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from cli.agent_cli.gateway_api.gui_http_server import build_gui_bridge_http_handler
from cli.agent_cli.gateway_server.control_ui_contract import CONTROL_UI_BOOTSTRAP_CONFIG_PATH
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_paths import runtime_project_root
from shared.web_automation.proxy_client import HttpBrowserProxyClient


class _ServerAgent:
    def __init__(self) -> None:
        self.provider_model = "gpt-5.4"
        self.model_key = "gpt_54"
        self.reasoning_effort = "high"
        self.delegate_overrides: dict[str, dict[str, object]] = {}

    def _apply_model(self, selector: str) -> None:
        mapping = {
            "gpt_54": ("gpt_54", "gpt-5.4"),
            "gpt-5.4": ("gpt_54", "gpt-5.4"),
            "gpt_54_mini": ("gpt_54_mini", "gpt-5.4-mini"),
            "gpt-5.4-mini": ("gpt_54_mini", "gpt-5.4-mini"),
        }
        normalized = str(selector or "").strip()
        if normalized.lower() in {"default", "auto", "inherit"}:
            normalized = "gpt_54"
        self.model_key, self.provider_model = mapping[normalized]

    def provider_status(self) -> dict[str, str]:
        delegate_subagent = "openai | gpt-5.4 | reasoning=high | source=inherit_main"
        delegate_teammate = "openai | gpt-5.4 | reasoning=high | source=inherit_main"
        teammate_override = self.delegate_overrides.get("teammate")
        if isinstance(teammate_override, dict):
            model_text = str(teammate_override.get("model") or "").strip().lower()
            resolved_model = (
                "gpt-5.4" if model_text in {"default", "auto", "inherit"} else "gpt-5.4-mini"
            )
            delegate_teammate = (
                f"{str(teammate_override.get('provider') or 'openai') or 'openai'} | {resolved_model} | "
                f"reasoning={str(teammate_override.get('reasoning_effort') or 'high')} | "
                f"timeout={str(teammate_override.get('timeout') or '30')} | "
                "source=session_override"
            )
        return {
            "provider_name": "openai",
            "provider_model": self.provider_model,
            "model_key": self.model_key,
            "provider_reasoning_effort": self.reasoning_effort,
            "provider_label": f"openai | {self.provider_model}",
            "delegate_subagent": delegate_subagent,
            "delegate_teammate": delegate_teammate,
        }

    def available_models(self, provider_name=None):
        del provider_name
        return [
            {"model_key": "gpt_54", "model_id": "gpt-5.4"},
            {"model_key": "gpt_54_mini", "model_id": "gpt-5.4-mini"},
        ]

    def configure_model_selection(self, *, model=None, reasoning_effort=None):
        if model is not None:
            self._apply_model(str(model))
        if reasoning_effort is not None:
            effort = str(reasoning_effort).strip().lower()
            self.reasoning_effort = "high" if effort in {"default", "auto", "inherit"} else effort
        return self.provider_status()

    def configure_delegate_selection(
        self,
        role_name,
        *,
        model=None,
        provider=None,
        reasoning_effort=None,
        timeout=None,
        clear=False,
    ):
        if clear:
            self.delegate_overrides.pop(str(role_name), None)
            return self.provider_status()
        payload: dict[str, object] = {"source": "session_override"}
        if model is not None:
            payload["model"] = str(model)
        if provider is not None:
            payload["provider"] = str(provider)
        if reasoning_effort is not None:
            payload["reasoning_effort"] = str(reasoning_effort)
        if timeout is not None:
            payload["timeout"] = int(timeout)
        self.delegate_overrides[str(role_name)] = payload
        return self.provider_status()

    def session_delegate_overrides(self):
        return {role_name: dict(payload) for role_name, payload in self.delegate_overrides.items()}

    def plan(self, text: str, history=None, *, tool_executor=None, attachments=None):
        raise NotImplementedError


class GuiHttpServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.browser_env_patch = patch.dict(
            os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False
        )
        self.browser_env_patch.start()
        self.runtime = AgentCliRuntime(agent=_ServerAgent())
        self.runtime.tools._plugin_manager = PluginManager(
            plugin_root=runtime_project_root() / "plugins",
            state_path=Path(self.temp_dir.name) / "plugin_state.json",
        )
        handler = build_gui_bridge_http_handler(runtime=self.runtime, base_path="/gui")
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/gui"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.browser_env_patch.stop()
        self.temp_dir.cleanup()

    def test_requests_endpoint_returns_bridge_response_without_read_only_events(self) -> None:
        request = Request(
            f"{self.base_url}/requests",
            data=json.dumps(
                {
                    "request_id": "req_settings",
                    "action": "settings.get",
                    "payload": {},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["model"], "gpt-5.4")
        self.assertEqual(payload["data"]["reasoningEffort"], "high")
        self.assertIn("delegationModels", payload["data"])
        self.assertIn("teammate", payload["data"]["delegationModels"])

        with urlopen(f"{self.base_url}/events?cursor=0", timeout=5) as response:
            events = json.loads(response.read().decode("utf-8"))
        self.assertTrue(events["ok"])
        self.assertEqual(events["next_cursor"], 0)
        self.assertEqual(events["events"], [])

    def test_browser_request_generates_tool_event(self) -> None:
        request = Request(
            f"{self.base_url}/requests",
            data=json.dumps(
                {
                    "request_id": "req_browser_status",
                    "action": "browser.status",
                    "payload": {},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["action"], "status")

        with urlopen(f"{self.base_url}/events?cursor=0", timeout=5) as response:
            events = json.loads(response.read().decode("utf-8"))
        self.assertTrue(events["events"])
        self.assertIn(events["events"][0]["kind"], {"browser_state_changed", "tool_event"})

    def test_browser_proxy_http_route_returns_proxy_payload(self) -> None:
        request = Request(
            f"{self.base_url}/browser-proxy/profiles",
            method="GET",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], 200)
        self.assertIn("profiles", payload["result"])

    def test_browser_proxy_artifact_route_serves_runtime_artifact_bytes(self) -> None:
        start_request = Request(
            f"{self.base_url}/browser-proxy/start",
            data=json.dumps({"profile": "openclaw"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(start_request, timeout=10) as response:
            self.assertEqual(response.status, 200)

        open_request = Request(
            f"{self.base_url}/browser-proxy/tabs/open",
            data=json.dumps(
                {"profile": "openclaw", "url": "https://example.com/gui-artifact"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(open_request, timeout=10) as response:
            self.assertEqual(response.status, 200)

        shot_request = Request(
            f"{self.base_url}/browser-proxy/screenshot",
            data=json.dumps({"profile": "openclaw"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(shot_request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        artifact_path = payload["result"]["artifact"]["path"]
        with urlopen(
            f"{self.base_url}/browser-proxy/artifact?path={quote(artifact_path, safe='')}",
            timeout=5,
        ) as response:
            content = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/png")
            self.assertEqual(response.headers.get("X-AgentHub-Artifact-Path"), artifact_path)
            self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertGreater(len(content), 0)

    def test_http_browser_proxy_client_can_talk_to_gui_http_server(self) -> None:
        client = HttpBrowserProxyClient(
            base_url=f"{self.base_url}/browser-proxy", inject_loopback_auth=False
        )

        started = client.browser_proxy(method="POST", path="/start", body={"profile": "openclaw"})
        opened = client.browser_proxy(
            method="POST",
            path="/tabs/open",
            body={"profile": "openclaw", "url": "https://example.com/gui-proxy"},
        )
        status = client.browser_proxy(method="GET", path="/", query={"profile": "openclaw"})

        self.assertEqual(started["status"], 200)
        self.assertTrue(started["result"]["ok"])
        self.assertEqual(opened["status"], 200)
        self.assertEqual(opened["result"]["url"], "https://example.com/gui-proxy")
        self.assertEqual(status["status"], 200)
        self.assertTrue(status["result"]["running"])
        self.assertEqual(status["result"]["profile"], "openclaw")

    def test_health_and_cors_preflight(self) -> None:
        request = Request(
            f"{self.base_url}/health",
            method="OPTIONS",
        )
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertEqual(
                response.headers.get("Access-Control-Allow-Methods"), "GET, POST, DELETE, OPTIONS"
            )

        with urlopen(f"{self.base_url}/health", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")

    def test_invalid_options_path_returns_404_with_cors_headers(self) -> None:
        request = Request(
            f"{self.base_url}/not-found",
            method="OPTIONS",
        )
        with self.assertRaises(HTTPError) as excinfo:
            urlopen(request, timeout=5)

        response = excinfo.exception
        self.assertEqual(response.code, 404)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_unknown_get_route_returns_404_json_with_security_headers(self) -> None:
        with self.assertRaises(HTTPError) as excinfo:
            urlopen(f"{self.base_url}/missing-route", timeout=5)

        response = excinfo.exception
        self.assertEqual(response.code, 404)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload, {"ok": False, "error": "not_found"})
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")

    def test_unknown_post_route_returns_404_json_with_security_headers(self) -> None:
        request = Request(
            f"{self.base_url}/missing-route",
            data=json.dumps({"ok": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as excinfo:
            urlopen(request, timeout=5)

        response = excinfo.exception
        self.assertEqual(response.code, 404)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload, {"ok": False, "error": "not_found"})
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")

    def test_requests_endpoint_rejects_invalid_json(self) -> None:
        request = Request(
            f"{self.base_url}/requests",
            data=b"{",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as excinfo:
            urlopen(request, timeout=5)

        response = excinfo.exception
        self.assertEqual(response.code, 400)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertIn("invalid_json:", payload["error"])
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")

    def test_browser_proxy_rejects_non_object_json_body(self) -> None:
        request = Request(
            f"{self.base_url}/browser-proxy/start",
            data=json.dumps(["bad-body"]).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as excinfo:
            urlopen(request, timeout=5)

        response = excinfo.exception
        self.assertEqual(response.code, 400)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload, {"ok": False, "error": "invalid_body"})

    def test_browser_proxy_rejects_invalid_timeout_query(self) -> None:
        request = Request(
            f"{self.base_url}/browser-proxy/profiles?timeoutMs=bad",
            method="GET",
        )
        with self.assertRaises(HTTPError) as excinfo:
            urlopen(request, timeout=5)

        response = excinfo.exception
        self.assertEqual(response.code, 400)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertIn("invalid literal for int()", payload["error"])

    def test_plugin_and_settings_requests_emit_state_events(self) -> None:
        plugin_request = Request(
            f"{self.base_url}/requests",
            data=json.dumps(
                {
                    "request_id": "req_plugin_enable",
                    "action": "plugin.enable",
                    "payload": {"plugin_id": "demo_plugin"},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(plugin_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["plugin"]["plugin_id"], "demo_plugin")

        settings_request = Request(
            f"{self.base_url}/requests",
            data=json.dumps(
                {
                    "request_id": "req_settings_update",
                    "action": "settings.update",
                    "payload": {
                        "model": "gpt_54_mini",
                        "reasoningEffort": "medium",
                        "browserHeadless": True,
                        "runtimePolicy": {"approval_policy": "never"},
                        "delegationModels": {
                            "teammate": {
                                "model": "gpt_54_mini",
                                "provider": "openai",
                                "reasoningEffort": "medium",
                                "timeout": 30,
                            }
                        },
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(settings_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["model"], "gpt-5.4-mini")
        self.assertEqual(payload["data"]["reasoningEffort"], "medium")
        self.assertTrue(payload["data"]["delegationModels"]["teammate"]["overrideActive"])
        self.assertEqual(payload["data"]["delegationModels"]["teammate"]["model"], "gpt_54_mini")
        self.assertTrue(payload["data"]["browserHeadless"])
        self.assertEqual(payload["data"]["runtimePolicy"]["approval_policy"], "never")

        with urlopen(f"{self.base_url}/events?cursor=0", timeout=5) as response:
            events = json.loads(response.read().decode("utf-8"))
        event_kinds = [item["kind"] for item in events["events"]]
        self.assertIn("plugin_state_changed", event_kinds)
        self.assertIn("settings_changed", event_kinds)

    def test_control_ui_bootstrap_and_state_http_endpoints(self) -> None:
        with urlopen(f"{self.base_url}{CONTROL_UI_BOOTSTRAP_CONFIG_PATH}", timeout=5) as response:
            bootstrap = json.loads(response.read().decode("utf-8"))
        self.assertEqual(bootstrap["basePath"], "/gui")
        self.assertIn("gateway_events", bootstrap["gateway"]["streams"])
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")

        with urlopen(f"{self.base_url}/control-ui/state?limit=5", timeout=5) as response:
            state = json.loads(response.read().decode("utf-8"))
        self.assertTrue(state["ok"])
        self.assertIn("health", state["data"])
        self.assertIn("events", state["data"])

    def test_gateway_events_http_endpoint_exposes_broadcast_frames(self) -> None:
        self.runtime.gateway_broadcaster.publish(
            stream="approvals",
            event="approval.updated",
            payload={"approval_id": "approval_1"},
        )

        with urlopen(
            f"{self.base_url}/gateway-events?cursor=0&stream=approvals", timeout=5
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertEqual([item["stream"] for item in payload["events"]], ["approvals"])

    def test_control_ui_state_rejects_invalid_limit_query(self) -> None:
        with self.assertRaises(HTTPError) as excinfo:
            urlopen(f"{self.base_url}/control-ui/state?limit=bad", timeout=5)

        response = excinfo.exception
        self.assertEqual(response.code, 400)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload, {"ok": False, "error": "invalid_limit"})
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")

    def test_gateway_events_rejects_invalid_cursor_query(self) -> None:
        with self.assertRaises(HTTPError) as excinfo:
            urlopen(f"{self.base_url}/gateway-events?cursor=bad", timeout=5)

        response = excinfo.exception
        self.assertEqual(response.code, 400)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload, {"ok": False, "error": "invalid_cursor"})
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")

    def test_gateway_aware_bridge_actions_dispatch_through_requests_endpoint(self) -> None:
        connect_request = Request(
            f"{self.base_url}/requests",
            data=json.dumps(
                {
                    "request_id": "req_connect_initialize",
                    "action": "connect.initialize",
                    "payload": {},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(connect_request, timeout=5) as response:
            connect_payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(connect_payload["ok"])
        self.assertIn("methods", connect_payload["data"])

        health_request = Request(
            f"{self.base_url}/requests",
            data=json.dumps(
                {
                    "request_id": "req_health_get",
                    "action": "health.get",
                    "payload": {},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(health_request, timeout=5) as response:
            health_payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(health_payload["ok"])
        self.assertEqual(health_payload["data"]["status"], "ok")

        state_request = Request(
            f"{self.base_url}/requests",
            data=json.dumps(
                {
                    "request_id": "req_gateway_state",
                    "action": "gateway.state.get",
                    "payload": {"limit": 5},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(state_request, timeout=5) as response:
            state_payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(state_payload["ok"])
        self.assertIn("events", state_payload["data"])

        approvals_request = Request(
            f"{self.base_url}/requests",
            data=json.dumps(
                {
                    "request_id": "req_approvals_list",
                    "action": "approvals.list",
                    "payload": {"limit": 5},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(approvals_request, timeout=5) as response:
            approvals_payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(approvals_payload["ok"])
        self.assertIn("approvalTickets", approvals_payload["data"])

    def test_browser_proxy_artifact_route_rejects_invalid_path(self) -> None:
        request = Request(
            f"{self.base_url}/browser-proxy/artifact?path={quote('/tmp/not-agenthub-artifact.png', safe='')}",
            method="GET",
        )
        with self.assertRaises(Exception) as excinfo:
            urlopen(request, timeout=5)

        response = excinfo.exception
        self.assertEqual(getattr(response, "code", None), 404)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)
