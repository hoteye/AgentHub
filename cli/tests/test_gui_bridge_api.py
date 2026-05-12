from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.gateway_api.gui_bridge_api import dispatch_gui_bridge_action
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.models import AgentIntent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_paths import runtime_project_root
from cli.agent_cli.thread_store import ThreadStore
from shared.web_automation import client as browser_client_module
from shared.web_automation.service import BrowserService


class _BridgeAgent:
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
        return AgentIntent(assistant_text=f"echo: {text}")


class GuiBridgeApiTest(unittest.TestCase):
    @staticmethod
    def _write_file(path: Path, contents: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ThreadStore(Path(self.temp_dir.name))
        self.runtime = AgentCliRuntime(agent=_BridgeAgent(), thread_store=self.store)
        self.runtime.tools._plugin_manager = PluginManager(
            plugin_root=runtime_project_root() / "plugins",
            state_path=Path(self.temp_dir.name) / "plugin_state.json",
        )
        self.runtime.start_thread(name="GUI Test Thread")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_settings_get_returns_provider_and_workspace_metadata(self) -> None:
        workspace = Path(self.temp_dir.name) / "gui-workspace"
        workspace.mkdir()
        self.runtime.set_cwd(workspace)
        response = dispatch_gui_bridge_action(
            self.runtime, action="settings.get", request_id="req_settings"
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "req_settings")
        self.assertEqual(response["data"]["model"], "gpt-5.4")
        self.assertEqual(response["data"]["reasoningEffort"], "high")
        self.assertIn("delegationModels", response["data"])
        self.assertIn("subagent", response["data"]["delegationModels"])
        self.assertFalse(response["data"]["delegationModels"]["teammate"]["overrideActive"])
        self.assertIn("workspaceRoot", response["data"])
        self.assertEqual(response["data"]["workspaceRoot"], str(workspace.resolve()))
        self.assertIn("runtimePolicy", response["data"])
        self.assertIn("runtimeRegistry", response["data"])
        self.assertIn("toolCount", response["data"]["runtimeRegistry"])

    def test_settings_and_connector_list_include_plugin_mcp_and_app_connectors(self) -> None:
        root = Path(self.temp_dir.name)
        reference_home = root / "home"
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        plugin_root = reference_home / "plugins" / "cache" / "test" / "sample" / "local"
        self._write_file(
            plugin_root / ".agent_cli_legacy-plugin" / "plugin.json",
            '{"name":"sample","description":"sample"}',
        )
        self._write_file(
            plugin_root / ".mcp.json",
            '{"mcpServers":{"docs":{"type":"http","url":"https://docs.example/mcp"}}}',
        )
        self._write_file(
            plugin_root / ".app.json", '{"apps":{"example":{"id":"connector_example"}}}'
        )
        self._write_file(
            reference_home / "config.toml",
            (
                "[features]\nplugins = true\n"
                '\n[plugins."sample@test"]\nenabled = true\n'
                '\n[mcp_servers.sample]\nurl = "https://user.example/mcp"\n'
                f'\n[projects."{str(workspace.resolve()).replace(chr(92), "/")}"]\n'
                'trust_level = "trusted"\n'
            ),
        )
        self.runtime.tools._plugin_manager = PluginManager(
            reference_home=reference_home,
            bundled_plugin_root=root / "bundled-empty",
            cwd=workspace,
        )
        self.runtime.set_cwd(workspace)

        settings = dispatch_gui_bridge_action(
            self.runtime, action="settings.get", request_id="req_plugin_settings"
        )
        connectors = dispatch_gui_bridge_action(
            self.runtime, action="connector.list", request_id="req_plugin_connectors"
        )

        self.assertTrue(settings["ok"])
        self.assertEqual(settings["data"]["workspaceTrust"], "trusted")
        mcp_by_name = {item["name"]: item for item in settings["data"]["mcpServers"]}
        self.assertEqual(mcp_by_name["sample"]["source"], "user")
        self.assertEqual(mcp_by_name["docs"]["source"], "plugin")
        self.assertEqual(settings["data"]["appConnectors"][0]["connector_id"], "connector_example")

        self.assertTrue(connectors["ok"])
        self.assertIn("runtimeRegistry", connectors["data"])
        self.assertIn("runtimePolicy", connectors["data"])
        connector_by_key = {
            item["connector_key"]: item for item in connectors["data"]["connectors"]
        }
        self.assertEqual(connector_by_key["connector_example"]["source_kind"], "plugin_app")
        self.assertEqual(connector_by_key["connector_example"]["connector_kind"], "app")

    def test_settings_and_connector_list_prefer_canonical_plugin_manager_metadata(self) -> None:
        plugin_manager = self.runtime.tools._plugin_manager
        with (
            patch.object(
                plugin_manager,
                "gui_bridge_metadata",
                return_value={
                    "mcpServers": [
                        {
                            "name": "canonical_docs",
                            "source": "plugin",
                            "config": {"type": "http", "url": "https://canonical.example/mcp"},
                        }
                    ],
                    "appConnectors": [
                        {
                            "connector_id": "canonical_connector",
                            "plugin_name": "canonical_plugin",
                            "display_name": "Canonical Connector",
                            "connector_kind": "app",
                            "supports_actions": True,
                            "source_kind": "plugin_app",
                        }
                    ],
                },
                create=True,
            ),
            patch.object(
                plugin_manager,
                "configured_mcp_servers",
                return_value={"fallback_mcp": {"url": "https://fallback.example/mcp"}},
            ),
            patch.object(plugin_manager, "user_configured_mcp_servers", return_value={}),
            patch.object(
                plugin_manager,
                "effective_app_connectors",
                return_value=[
                    {"connector_id": "fallback_connector", "plugin_name": "fallback_plugin"}
                ],
            ),
            patch.object(
                self.runtime.tools,
                "list_plugins",
                return_value=SimpleNamespace(payload={"plugins": []}),
            ),
        ):
            settings = dispatch_gui_bridge_action(
                self.runtime,
                action="settings.get",
                request_id="req_canonical_settings",
            )
            connectors = dispatch_gui_bridge_action(
                self.runtime,
                action="connector.list",
                request_id="req_canonical_connectors",
            )

        self.assertTrue(settings["ok"])
        mcp_names = {item["name"] for item in settings["data"]["mcpServers"]}
        self.assertIn("canonical_docs", mcp_names)
        self.assertNotIn("fallback_mcp", mcp_names)
        app_connector_ids = {item["connector_id"] for item in settings["data"]["appConnectors"]}
        self.assertIn("canonical_connector", app_connector_ids)
        self.assertNotIn("fallback_connector", app_connector_ids)
        self.assertTrue(connectors["ok"])
        connector_by_key = {
            item["connector_key"]: item for item in connectors["data"]["connectors"]
        }
        canonical = connector_by_key["canonical_connector"]
        self.assertEqual(canonical["display_name"], "Canonical Connector")
        self.assertEqual(canonical["plugin_name"], "canonical_plugin")
        self.assertEqual(canonical["source_kind"], "plugin_app")

    def test_settings_get_merges_runtime_mcp_status_over_canonical_metadata(self) -> None:
        class _PluginManagerStub:
            @staticmethod
            def gui_bridge_metadata():
                return {
                    "mcpServers": [
                        {
                            "name": "atlas",
                            "source": "plugin",
                            "plugin_name": "atlas_plugin",
                            "config": {"url": "https://canonical.example/mcp"},
                        }
                    ]
                }

            @staticmethod
            def workspace_trust_level() -> str:
                return "trusted"

        self.runtime.tools._plugin_manager = _PluginManagerStub()
        with patch.object(
            self.runtime.tools,
            "capabilities",
            return_value={
                "ok": True,
                "tools": [{"name": "shell"}],
                "count": 1,
                "workspace_trust": "trusted",
                "mcp_server_entries": [
                    {
                        "name": "atlas",
                        "source": "workspace",
                        "status": "connected",
                        "enabled": True,
                        "scope": "workspace",
                        "projection_state": "ready",
                        "config": {"url": "https://runtime.example/mcp"},
                    }
                ],
            },
        ):
            settings = dispatch_gui_bridge_action(
                self.runtime,
                action="settings.get",
                request_id="req_runtime_mcp_merge",
            )

        self.assertTrue(settings["ok"])
        atlas = next(item for item in settings["data"]["mcpServers"] if item["name"] == "atlas")
        self.assertEqual(atlas["source"], "workspace")
        self.assertEqual(atlas["status"], "connected")
        self.assertEqual(atlas["projection_state"], "ready")
        self.assertEqual(atlas["plugin_name"], "atlas_plugin")
        self.assertEqual(atlas["config"]["url"], "https://runtime.example/mcp")

    def test_settings_get_merges_runtime_mcp_server_map_over_canonical_metadata(self) -> None:
        class _PluginManagerStub:
            @staticmethod
            def gui_bridge_metadata():
                return {
                    "mcpServers": [
                        {
                            "name": "atlas",
                            "source": "plugin",
                            "plugin_name": "atlas_plugin",
                            "config": {"url": "https://canonical.example/mcp"},
                        }
                    ]
                }

            @staticmethod
            def workspace_trust_level() -> str:
                return "trusted"

        self.runtime.tools._plugin_manager = _PluginManagerStub()
        with patch.object(
            self.runtime.tools,
            "capabilities",
            return_value={
                "ok": True,
                "tools": [{"name": "shell"}],
                "count": 1,
                "workspace_trust": "trusted",
                "mcp_servers": {
                    "atlas": {
                        "source": "runtime_dynamic",
                        "status": "connected",
                        "enabled": True,
                        "projection_state": "ready",
                        "url": "https://runtime.example/mcp",
                    }
                },
            },
        ):
            settings = dispatch_gui_bridge_action(
                self.runtime,
                action="settings.get",
                request_id="req_runtime_mcp_map_merge",
            )

        self.assertTrue(settings["ok"])
        atlas = next(item for item in settings["data"]["mcpServers"] if item["name"] == "atlas")
        self.assertEqual(atlas["source"], "runtime_dynamic")
        self.assertEqual(atlas["status"], "connected")
        self.assertEqual(atlas["projection_state"], "ready")
        self.assertEqual(atlas["plugin_name"], "atlas_plugin")
        self.assertEqual(atlas["config"]["url"], "https://runtime.example/mcp")

    def test_connector_list_app_approval_required_follows_runtime_policy(self) -> None:
        plugin_manager = self.runtime.tools._plugin_manager
        self.runtime.configure_runtime_policy(approval_policy="on-request")

        with (
            patch.object(
                plugin_manager,
                "gui_bridge_metadata",
                return_value={
                    "appConnectors": [
                        {
                            "connector_id": "approval_connector",
                            "plugin_name": "approval_plugin",
                            "supports_actions": True,
                            "approval_required": False,
                        }
                    ]
                },
                create=True,
            ),
            patch.object(
                self.runtime.tools,
                "list_plugins",
                return_value=SimpleNamespace(payload={"plugins": []}),
            ),
        ):
            connectors_enabled = dispatch_gui_bridge_action(
                self.runtime,
                action="connector.list",
                request_id="req_approval_enabled",
            )
            self.runtime.configure_runtime_policy(approval_policy="never")
            connectors_disabled = dispatch_gui_bridge_action(
                self.runtime,
                action="connector.list",
                request_id="req_approval_disabled",
            )

        enabled_item = next(
            item
            for item in connectors_enabled["data"]["connectors"]
            if item["connector_key"] == "approval_connector"
        )
        disabled_item = next(
            item
            for item in connectors_disabled["data"]["connectors"]
            if item["connector_key"] == "approval_connector"
        )
        self.assertTrue(enabled_item["approval_required"])
        self.assertFalse(disabled_item["approval_required"])
        self.assertTrue(enabled_item["approval"]["required"])
        self.assertFalse(disabled_item["approval"]["required"])
        self.assertEqual(enabled_item["approval"]["policy"], "on-request")
        self.assertEqual(disabled_item["approval"]["policy"], "never")
        self.assertEqual(enabled_item["approval"]["resolver"], "approvals.resolve")
        self.assertEqual(disabled_item["approval"]["resolver"], "approvals.resolve")

    def test_connector_list_prefers_routed_gateway_contract_without_reappending_metadata(
        self,
    ) -> None:
        plugin_manager = self.runtime.tools._plugin_manager
        with (
            patch(
                "cli.agent_cli.gateway_api.gui_bridge_api.dispatch_gateway_method",
                return_value=SimpleNamespace(
                    ok=True,
                    result={
                        "connectors": [
                            {
                                "connector_id": "routed_connector",
                                "connector_key": "routed_connector",
                                "plugin_name": "routed_plugin",
                                "supports_actions": True,
                                "approval_required": False,
                                "approval": {
                                    "required": False,
                                    "policy": "on-request",
                                    "resolver": "approvals.resolve",
                                },
                                "enabled": True,
                                "health": "ready",
                                "source_kind": "gateway",
                            }
                        ],
                        "runtimeRegistry": {"source": "tools.capabilities"},
                        "runtimePolicy": {"approval_policy": "on-request"},
                    },
                ),
            ),
            patch.object(
                plugin_manager,
                "gui_bridge_metadata",
                return_value={
                    "appConnectors": [
                        {
                            "connector_id": "metadata_connector",
                            "plugin_name": "metadata_plugin",
                            "supports_actions": True,
                        }
                    ]
                },
                create=True,
            ),
        ):
            connectors = dispatch_gui_bridge_action(
                self.runtime,
                action="connector.list",
                request_id="req_routed_connector_contract",
            )

        self.assertTrue(connectors["ok"])
        self.assertEqual(len(connectors["data"]["connectors"]), 1)
        routed = connectors["data"]["connectors"][0]
        self.assertEqual(routed["connector_key"], "routed_connector")
        self.assertFalse(routed["approval_required"])
        self.assertEqual(routed["approval"]["required"], False)
        self.assertEqual(routed["approval"]["policy"], "on-request")
        self.assertEqual(routed["approval"]["resolver"], "approvals.resolve")
        self.assertNotIn(
            "metadata_connector",
            {item["connector_key"] for item in connectors["data"]["connectors"]},
        )

    def test_connector_list_fallback_applies_plugin_enabled_state_to_app_connectors(self) -> None:
        plugin_manager = self.runtime.tools._plugin_manager
        self.runtime.configure_runtime_policy(approval_policy="on-request")

        with (
            patch(
                "cli.agent_cli.gateway_api.gui_bridge_api.dispatch_gateway_method",
                return_value=SimpleNamespace(ok=False, error_message="unavailable", error_data={}),
            ),
            patch.object(
                self.runtime.tools,
                "list_plugins",
                return_value=SimpleNamespace(
                    payload={"plugins": [{"plugin_id": "disabled_plugin", "enabled": False}]}
                ),
            ),
            patch.object(
                plugin_manager,
                "gui_bridge_metadata",
                return_value={
                    "appConnectors": [
                        {
                            "connector_id": "disabled_app",
                            "plugin_name": "disabled_plugin",
                            "supports_actions": True,
                            "enabled": True,
                        }
                    ]
                },
                create=True,
            ),
            patch.object(
                self.runtime,
                "gateway_registry",
                return_value=SimpleNamespace(list_connectors=lambda: []),
            ),
        ):
            connectors = dispatch_gui_bridge_action(
                self.runtime,
                action="connector.list",
                request_id="req_fallback_connector_contract",
            )

        self.assertTrue(connectors["ok"])
        disabled = next(
            item
            for item in connectors["data"]["connectors"]
            if item["connector_key"] == "disabled_app"
        )
        self.assertFalse(disabled["enabled"])
        self.assertEqual(disabled["health"], "warning")
        self.assertTrue(disabled["approval_required"])

    def test_unsupported_action_returns_v1_error(self) -> None:
        response = dispatch_gui_bridge_action(
            self.runtime, action="unknown.action", request_id="req_unknown"
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "unknown.action.unsupported")

    def test_gateway_dispatch_actions_use_gui_client_identity(self) -> None:
        with patch(
            "cli.agent_cli.gateway_api.gui_bridge_api.dispatch_gateway_method"
        ) as dispatch_mock:
            dispatch_mock.return_value = SimpleNamespace(ok=True, result={"status": "ok"})

            response = dispatch_gui_bridge_action(
                self.runtime,
                action="health.get",
                request_id="req_health_identity",
                payload={},
            )

        self.assertTrue(response["ok"])
        kwargs = dispatch_mock.call_args.kwargs
        self.assertEqual(kwargs["method"], "health.get")
        self.assertEqual(kwargs["request_id"], "req_health_identity")
        self.assertEqual(kwargs["client_info"], {"name": "gui_http_server", "clientType": "gui"})

    def test_logs_tail_dispatches_through_gateway_method_surface(self) -> None:
        with patch(
            "cli.agent_cli.gateway_api.gui_bridge_api.dispatch_gateway_method"
        ) as dispatch_mock:
            dispatch_mock.return_value = SimpleNamespace(
                ok=True,
                result={
                    "source": "gateway.audit_records",
                    "label": "Gateway Audit Records",
                    "path": "/tmp/audit_records.jsonl",
                    "lines": ["line-1", "line-2"],
                    "text": "line-1\nline-2",
                    "lineCount": 2,
                    "truncated": False,
                    "availableSources": [],
                },
            )

            response = dispatch_gui_bridge_action(
                self.runtime,
                action="logs.tail",
                request_id="req_logs_tail",
                payload={"source": "gateway.audit_records", "lines": 2},
            )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["source"], "gateway.audit_records")
        kwargs = dispatch_mock.call_args.kwargs
        self.assertEqual(kwargs["method"], "logs.tail")
        self.assertEqual(kwargs["params"]["lines"], 2)

    def test_nodes_list_dispatches_through_gateway_method_surface(self) -> None:
        with patch(
            "cli.agent_cli.gateway_api.gui_bridge_api.dispatch_gateway_method"
        ) as dispatch_mock:
            dispatch_mock.return_value = SimpleNamespace(
                ok=True,
                result={
                    "nodes": [
                        {"nodeId": "node.local.app_server", "kind": "local", "status": "online"}
                    ],
                    "summary": {"totalNodes": 1},
                },
            )

            response = dispatch_gui_bridge_action(
                self.runtime,
                action="nodes.list",
                request_id="req_nodes_list",
                payload={"limit": 12},
            )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["summary"]["totalNodes"], 1)
        kwargs = dispatch_mock.call_args.kwargs
        self.assertEqual(kwargs["method"], "nodes.list")
        self.assertEqual(kwargs["params"]["limit"], 12)

    def test_workflows_detail_and_resume_dispatch_through_gateway_method_surface(self) -> None:
        with patch(
            "cli.agent_cli.gateway_api.gui_bridge_api.dispatch_gateway_method"
        ) as dispatch_mock:
            dispatch_mock.return_value = SimpleNamespace(
                ok=True,
                result={"workflowRun": {"workflow_run_id": "wf_1"}, "resumeRequested": True},
            )

            detail = dispatch_gui_bridge_action(
                self.runtime,
                action="workflows.get",
                request_id="req_workflow_get",
                payload={"workflowRunId": "wf_1"},
            )
            resumed = dispatch_gui_bridge_action(
                self.runtime,
                action="workflows.resume",
                request_id="req_workflow_resume",
                payload={"workflowRunId": "wf_1", "decidedBy": "gui-test"},
            )

        self.assertTrue(detail["ok"])
        self.assertTrue(resumed["ok"])
        methods = [call.kwargs["method"] for call in dispatch_mock.call_args_list]
        self.assertEqual(methods, ["workflows.get", "workflows.resume"])

    def test_browser_status_maps_browser_client_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_service = browser_client_module._service
            try:
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    Path(temp_dir).mkdir(parents=True, exist_ok=True)
                    browser_client_module.replace_service(BrowserService())
                    response = dispatch_gui_bridge_action(
                        self.runtime,
                        action="browser.status",
                        request_id="req_browser",
                    )
                self.assertTrue(response["ok"])
                self.assertEqual(response["data"]["action"], "status")
                self.assertIn("running", response["data"])
            finally:
                browser_client_module.replace_service(old_service)

    def test_browser_proxy_routes_through_gateway_dispatcher(self) -> None:
        with patch(
            "cli.agent_cli.gateway_api.gui_bridge_api.dispatch_gateway_method"
        ) as dispatch_mock:
            dispatch_mock.return_value = SimpleNamespace(
                ok=True,
                result={"status": 200, "result": {"ok": True, "path": "/profiles"}},
            )

            response = dispatch_gui_bridge_action(
                self.runtime,
                action="browser.proxy",
                request_id="req_browser_proxy",
                payload={"method": "GET", "path": "/profiles", "profile": "openclaw"},
            )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["status"], 200)
        self.assertEqual(response["data"]["result"]["path"], "/profiles")
        kwargs = dispatch_mock.call_args.kwargs
        self.assertEqual(kwargs["method"], "browser.proxy")
        self.assertEqual(kwargs["params"]["path"], "/profiles")

    def test_approval_and_audit_routes_return_runtime_state(self) -> None:
        action_request = self.runtime.request_gateway_action(
            action_type="demo.noop",
            connector_key="demo_connector",
            plugin_name="demo_plugin",
            request_payload={"action": "noop"},
            requested_by="tester",
            trace_id="trace_demo_gui",
            event_id="event_demo_gui",
            approval_required=True,
            approval_summary="Approve gui bridge noop",
        )
        approval_id = action_request["approval_ticket"].approval_id

        approvals = dispatch_gui_bridge_action(
            self.runtime, action="approval.list", request_id="req_approvals"
        )
        self.assertTrue(approvals["ok"])
        self.assertEqual(approvals["data"]["approvals"][0]["approval_id"], approval_id)
        self.assertIn("approval_diagnostics", approvals["data"])
        self.assertGreaterEqual(approvals["data"]["pending_count"], 1)

        resolved = dispatch_gui_bridge_action(
            self.runtime,
            action="approval.resolve",
            request_id="req_resolve",
            payload={"approval_id": approval_id, "decision": "approved", "decided_by": "gui-test"},
        )
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["data"]["status"], "approved")
        self.assertEqual(resolved["data"]["approval_ticket"]["approval_id"], approval_id)
        self.assertEqual(resolved["data"]["turn_events"][0]["type"], "turn.started")
        self.assertEqual(resolved["data"]["turn_events"][-1]["type"], "turn.completed")
        self.assertIn("tool_events", resolved["data"])
        completed_items = [
            dict(item.get("item") or {})
            for item in list(resolved["data"].get("item_events") or [])
            if str(item.get("type") or "") == "item.completed"
        ]
        self.assertTrue(
            any(str(item.get("tool") or "") == "approval_decision" for item in completed_items)
        )

        audit = dispatch_gui_bridge_action(
            self.runtime,
            action="audit.list",
            request_id="req_audit",
            payload={"trace_id": "trace_demo_gui"},
        )
        self.assertTrue(audit["ok"])
        self.assertGreaterEqual(len(audit["data"]["records"]), 1)

    def test_approval_resolve_rejects_invalid_payload(self) -> None:
        response = dispatch_gui_bridge_action(
            self.runtime,
            action="approval.resolve",
            request_id="req_bad_approval",
            payload={"approval_id": "", "decision": "later"},
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "approval.resolve.invalid_payload")

    def test_thread_list_and_resume_return_runtime_thread_state(self) -> None:
        workspace = Path(self.temp_dir.name) / "thread-workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / ".git").write_text("", encoding="utf-8")
        (workspace / "AENGTHUB.md").write_text("gui bridge workspace guidance", encoding="utf-8")
        self.runtime.set_cwd(workspace)
        self.runtime.handle_prompt("hello gui thread")

        listed = dispatch_gui_bridge_action(
            self.runtime,
            action="thread.list",
            request_id="req_thread_list",
            payload={"limit": 5},
        )
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["data"]["threads"][0]["name"], "GUI Test Thread")
        thread_id = listed["data"]["threads"][0]["thread_id"]
        self.assertFalse(listed["data"]["threads"][0]["ephemeral"])
        self.assertEqual(listed["data"]["threads"][0]["status"], "idle")
        self.assertTrue(Path(listed["data"]["threads"][0]["path"]).is_absolute())
        self.assertIn("provider_status", listed["data"]["threads"][0]["metadata"])
        self.assertIn("runtime_policy", listed["data"]["threads"][0]["metadata"])

        resumed = dispatch_gui_bridge_action(
            self.runtime,
            action="thread.resume",
            request_id="req_thread_resume",
            payload={"thread_id": thread_id},
        )
        self.assertTrue(resumed["ok"])
        self.assertEqual(resumed["data"]["thread"]["thread_id"], thread_id)
        self.assertEqual(resumed["data"]["thread"]["status"], "idle")
        self.assertFalse(resumed["data"]["thread"]["ephemeral"])
        self.assertEqual(resumed["data"]["resume_diagnostics"]["selected_source"], "thread_id")
        self.assertIn("runtime", resumed["data"])
        self.assertIn("runtime_policy", resumed["data"]["thread"]["metadata"])
        self.assertGreaterEqual(len(resumed["data"]["history"]), 2)
        self.assertGreaterEqual(len(resumed["data"]["turns"]), 1)
        self.assertIn("assistant_text", resumed["data"]["turns"][0])
        self.assertIn("activity_events", resumed["data"]["turns"][0])
        self.assertIn("response_items", resumed["data"]["turns"][0])
        self.assertIn("turn_events", resumed["data"]["turns"][0])
        self.assertIn("protocol_diagnostics", resumed["data"]["turns"][0])
        self.assertIn("request_contract", resumed["data"]["turns"][0]["protocol_diagnostics"])
        self.assertIn("workspace_context_snapshot", resumed["data"]["turns"][0]["runtime_state"])
        self.assertIn("context_update_history", resumed["data"]["turns"][0]["runtime_state"])

    def test_thread_list_filters_by_cwd_for_project_menu(self) -> None:
        first_workspace = Path(self.temp_dir.name) / "first-project"
        second_workspace = Path(self.temp_dir.name) / "second-project"
        first_workspace.mkdir(parents=True, exist_ok=True)
        second_workspace.mkdir(parents=True, exist_ok=True)

        self.runtime.start_thread(name="first project", cwd=str(first_workspace))
        self.runtime.handle_prompt("first project prompt")
        self.runtime.start_thread(name="second project", cwd=str(second_workspace))
        self.runtime.handle_prompt("second project prompt")

        listed = dispatch_gui_bridge_action(
            self.runtime,
            action="thread.list",
            request_id="req_thread_list_cwd",
            payload={"limit": 5, "cwd": str(first_workspace)},
        )

        self.assertTrue(listed["ok"])
        self.assertEqual([item["name"] for item in listed["data"]["threads"]], ["first project"])
        self.assertEqual(listed["data"]["threads"][0]["cwd"], str(first_workspace.resolve()))

    def test_task_and_chat_responses_include_transcript_payloads(self) -> None:
        task_run = dispatch_gui_bridge_action(
            self.runtime,
            action="task.run",
            request_id="req_task_run_payload",
            payload={"text": "inspect thread payload"},
        )
        self.assertTrue(task_run["ok"])
        self.assertIn("assistant_text", task_run["data"])
        self.assertIn("response_items", task_run["data"])
        self.assertIn("tool_events", task_run["data"])
        self.assertIn("activity_events", task_run["data"])
        self.assertIn("turn_events", task_run["data"])
        self.assertIn("protocol_diagnostics", task_run["data"])
        self.assertIn("request_contract", task_run["data"]["protocol_diagnostics"])

        chat_send = dispatch_gui_bridge_action(
            self.runtime,
            action="chat.send",
            request_id="req_chat_send_payload",
            payload={"text": "continue the same thread"},
        )
        self.assertTrue(chat_send["ok"])
        self.assertEqual(chat_send["data"]["user_text"], "continue the same thread")
        self.assertIn("assistant_text", chat_send["data"])
        self.assertIn("response_items", chat_send["data"])
        self.assertIn("activity_events", chat_send["data"])
        self.assertIn("turn_events", chat_send["data"])
        self.assertIn("protocol_diagnostics", chat_send["data"])
        self.assertIn("request_contract", chat_send["data"]["protocol_diagnostics"])

    def test_shell_run_executes_command_and_records_thread_turn(self) -> None:
        workspace = Path(self.temp_dir.name) / "shell-project"
        workspace.mkdir(parents=True, exist_ok=True)
        command = "printf gui-shell-ok"

        response = dispatch_gui_bridge_action(
            self.runtime,
            action="shell.run",
            request_id="req_shell_run",
            payload={"command": command, "cwd": str(workspace), "timeout_ms": 10000},
        )

        self.assertTrue(response["ok"])
        self.assertTrue(response["data"]["accepted"])
        self.assertEqual(response["data"]["command"], command)
        self.assertEqual(response["data"]["exit_code"], 0)
        self.assertEqual(response["data"]["stdout"], "gui-shell-ok")
        self.assertIn("tool_events", response["data"])
        self.assertEqual(response["data"]["tool_events"][0]["payload"]["stdout"], "gui-shell-ok")
        self.assertIn("activity_events", response["data"])
        self.assertIn("turn_events", response["data"])

        resumed = dispatch_gui_bridge_action(
            self.runtime,
            action="thread.resume",
            request_id="req_shell_resume",
            payload={"thread_id": response["data"]["thread_id"]},
        )
        self.assertTrue(resumed["ok"])
        shell_turn = resumed["data"]["turns"][-1]
        self.assertEqual(shell_turn["user_text"], f"/shell {command}")
        self.assertEqual(shell_turn["tool_events"][0]["payload"]["stdout"], "gui-shell-ok")

    def test_chat_send_can_start_project_scoped_thread_from_codex_gui_contract(self) -> None:
        workspace = Path(self.temp_dir.name) / "codex-project"
        workspace.mkdir(parents=True, exist_ok=True)
        self.runtime.thread_id = None

        response = dispatch_gui_bridge_action(
            self.runtime,
            action="chat.send",
            request_id="req_chat_send_project_cwd",
            payload={
                "text": "start in selected project",
                "cwd": str(workspace),
                "workspaceRoots": [str(workspace)],
                "new_thread": True,
            },
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["cwd"], str(workspace.resolve()))
        self.assertEqual(response["data"]["workspaceRoots"], [str(workspace)])
        self.assertEqual(self.runtime.cwd, workspace.resolve())
        self.assertIsNotNone(response["data"]["thread_id"])
        listed = dispatch_gui_bridge_action(
            self.runtime,
            action="thread.list",
            request_id="req_thread_list_project_cwd_after_send",
            payload={"limit": 5, "cwd": str(workspace)},
        )
        self.assertTrue(listed["ok"])
        self.assertEqual(
            [item["thread_id"] for item in listed["data"]["threads"]],
            [response["data"]["thread_id"]],
        )

    def test_task_stop_returns_error_when_no_active_run_exists(self) -> None:
        response = dispatch_gui_bridge_action(
            self.runtime,
            action="task.stop",
            request_id="req_task_stop",
            payload={"task_id": "task-1"},
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "task.stop.no_active_run")
        self.assertEqual(response["error"]["detail"]["task_id"], "task-1")

    def test_browser_workflow_unknown_action_returns_unsupported_error(self) -> None:
        response = dispatch_gui_bridge_action(
            self.runtime,
            action="browser.workflow.unknown",
            request_id="req_browser_workflow_unknown",
            payload={},
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "browser.workflow.unknown.unsupported")

    def test_gui_bridge_wraps_runtime_exception_as_failed_error(self) -> None:
        with patch.object(self.runtime, "handle_prompt", side_effect=RuntimeError("boom")):
            response = dispatch_gui_bridge_action(
                self.runtime,
                action="task.run",
                request_id="req_task_exception",
                payload={"text": "explode"},
            )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "task.run.failed")
        self.assertEqual(response["error"]["message"], "boom")

    def test_plugin_controls_return_normalized_plugin_state(self) -> None:
        listed = dispatch_gui_bridge_action(
            self.runtime, action="plugin.list", request_id="req_plugin_list"
        )

        self.assertTrue(listed["ok"])
        plugin_ids = {item["plugin_id"] for item in listed["data"]["plugins"]}
        self.assertIn("psbc_policy", plugin_ids)
        self.assertIn("demo_plugin", plugin_ids)

        enabled = dispatch_gui_bridge_action(
            self.runtime,
            action="plugin.enable",
            request_id="req_plugin_enable",
            payload={"plugin_id": "demo_plugin"},
        )
        self.assertTrue(enabled["ok"])
        self.assertEqual(enabled["data"]["plugin"]["plugin_id"], "demo_plugin")
        self.assertTrue(enabled["data"]["plugin"]["enabled"])

        disabled = dispatch_gui_bridge_action(
            self.runtime,
            action="plugin.disable",
            request_id="req_plugin_disable",
            payload={"plugin_id": "demo_plugin"},
        )
        self.assertTrue(disabled["ok"])
        self.assertFalse(disabled["data"]["plugin"]["enabled"])

        reloaded = dispatch_gui_bridge_action(
            self.runtime,
            action="plugin.reload",
            request_id="req_plugin_reload",
            payload={"plugin_id": "demo_plugin"},
        )
        self.assertTrue(reloaded["ok"])
        self.assertEqual(reloaded["data"]["operation"], "reload")
        self.assertGreaterEqual(len(reloaded["data"]["plugins"]), 1)

        connectors = dispatch_gui_bridge_action(
            self.runtime,
            action="connector.list",
            request_id="req_connector_list",
        )
        self.assertTrue(connectors["ok"])
        connector_keys = {item["connector_key"] for item in connectors["data"]["connectors"]}
        self.assertIn("github_webhook", connector_keys)
        github = next(
            item
            for item in connectors["data"]["connectors"]
            if item["connector_key"] == "github_webhook"
        )
        self.assertTrue(github["approval_required"])

    def test_settings_update_applies_model_reasoning_runtime_policy_and_gui_preferences(
        self,
    ) -> None:
        updated = dispatch_gui_bridge_action(
            self.runtime,
            action="settings.update",
            request_id="req_settings_update",
            payload={
                "model": "gpt_54_mini",
                "reasoningEffort": "xhigh",
                "browserHeadless": True,
                "pluginAutoLoad": False,
                "runtimePolicy": {
                    "approval_policy": "never",
                    "sandbox_mode": "read-only",
                    "web_search_mode": "disabled",
                    "network_access": "disabled",
                },
                "delegationModels": {
                    "teammate": {
                        "model": "gpt_54_mini",
                        "provider": "openai",
                        "reasoningEffort": "medium",
                        "timeout": 30,
                    }
                },
            },
        )

        self.assertTrue(updated["ok"])
        self.assertEqual(updated["data"]["model"], "gpt-5.4-mini")
        self.assertEqual(updated["data"]["reasoningEffort"], "xhigh")
        self.assertTrue(updated["data"]["delegationModels"]["teammate"]["overrideActive"])
        self.assertEqual(updated["data"]["delegationModels"]["teammate"]["model"], "gpt_54_mini")
        self.assertEqual(
            updated["data"]["delegationModels"]["teammate"]["reasoningEffort"], "medium"
        )
        self.assertTrue(updated["data"]["browserHeadless"])
        self.assertFalse(updated["data"]["pluginAutoLoad"])
        self.assertEqual(updated["data"]["runtimePolicy"]["approval_policy"], "never")
        self.assertEqual(updated["data"]["runtimePolicy"]["sandbox_mode"], "read-only")
        self.assertEqual(updated["data"]["runtimePolicy"]["web_search_mode"], "disabled")
        self.assertEqual(updated["data"]["runtimePolicy"]["network_access"], "restricted")

    def test_config_contract_validates_and_applies_settings_changes(self) -> None:
        next_workspace = Path(self.temp_dir.name) / "config-next"
        next_workspace.mkdir(parents=True, exist_ok=True)

        validated = dispatch_gui_bridge_action(
            self.runtime,
            action="config.validate",
            request_id="req_config_validate",
            payload={
                "model": "gpt_54_mini",
                "reasoningEffort": "medium",
                "workspaceRoot": str(next_workspace),
                "browserHeadless": True,
                "runtimePolicy": {
                    "approval_policy": "never",
                    "network_access": "disabled",
                },
                "delegationModels": {
                    "teammate": {
                        "model": "inherit",
                        "timeout": 20,
                    }
                },
            },
        )

        self.assertTrue(validated["ok"])
        self.assertIn("model", validated["data"]["applyableFields"])
        self.assertIn("reasoningEffort", validated["data"]["applyableFields"])
        self.assertIn("workspaceRoot", validated["data"]["applyableFields"])
        self.assertIn("delegationModels.teammate", validated["data"]["applyableFields"])
        self.assertTrue(validated["data"]["restart"]["required"])
        self.assertFalse(validated["data"]["restart"]["allowed"])

        applied = dispatch_gui_bridge_action(
            self.runtime,
            action="config.apply",
            request_id="req_config_apply",
            payload={
                "model": "gpt_54_mini",
                "reasoningEffort": "medium",
                "workspaceRoot": str(next_workspace),
                "browserHeadless": True,
                "runtimePolicy": {
                    "approval_policy": "never",
                    "network_access": "disabled",
                },
                "delegationModels": {
                    "teammate": {
                        "model": "inherit",
                        "timeout": 20,
                    }
                },
            },
        )

        self.assertTrue(applied["ok"])
        self.assertEqual(applied["data"]["status"], "applied")
        self.assertEqual(applied["data"]["settings"]["model"], "gpt-5.4-mini")
        self.assertEqual(applied["data"]["settings"]["reasoningEffort"], "medium")
        self.assertTrue(
            applied["data"]["settings"]["delegationModels"]["teammate"]["overrideActive"]
        )
        self.assertEqual(
            applied["data"]["settings"]["delegationModels"]["teammate"]["model"], "inherit"
        )
        self.assertEqual(applied["data"]["settings"]["delegationModels"]["teammate"]["timeout"], 20)
        self.assertEqual(
            applied["data"]["settings"]["workspaceRoot"], str(next_workspace.resolve())
        )
        self.assertTrue(applied["data"]["settings"]["browserHeadless"])
        self.assertEqual(applied["data"]["settings"]["runtimePolicy"]["approval_policy"], "never")
        self.assertEqual(
            applied["data"]["settings"]["runtimePolicy"]["network_access"], "restricted"
        )

    def test_config_restart_report_exposes_truthful_manual_restart_posture(self) -> None:
        report = dispatch_gui_bridge_action(
            self.runtime,
            action="config.restart.report",
            request_id="req_restart_report",
            payload={"pluginAutoLoad": False},
        )

        self.assertTrue(report["ok"])
        self.assertTrue(report["data"]["required"])
        self.assertFalse(report["data"]["allowed"])
        self.assertEqual(report["data"]["mode"], "manual")
        self.assertIn("operator", report["data"]["blockedReason"])
