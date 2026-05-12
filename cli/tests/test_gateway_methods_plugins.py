from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.gateway_core.models import ConnectorRegistration, TriggerRegistration
from cli.agent_cli.gateway_server.dispatcher import dispatch_gateway_method

class _PluginManager:
    @staticmethod
    def list_plugins() -> list[dict[str, object]]:
        return [
            {
                "plugin_id": "github_phase1",
                "config_name": "github_phase1",
                "name": "github_phase1",
                "version": "1.0.0",
                "description": "GitHub workflow plugin",
                "enabled": True,
                "connector_count": 1,
                "trigger_count": 1,
                "app_count": 0,
                "tool_count": 2,
                "command_count": 1,
                "workflow_count": 1,
                "policy_count": 0,
                "skill_root_count": 0,
                "mcp_server_count": 0,
            },
            {
                "plugin_id": "sample@test",
                "config_name": "sample@test",
                "name": "sample",
                "version": "0.2.0",
                "description": "Sample app connector plugin",
                "enabled": False,
                "connector_count": 0,
                "trigger_count": 1,
                "app_count": 1,
                "tool_count": 0,
                "command_count": 0,
                "workflow_count": 1,
                "policy_count": 0,
                "skill_root_count": 0,
                "mcp_server_count": 0,
            },
        ]

    @staticmethod
    def workspace_trust_level() -> str:
        return "trusted"

    @staticmethod
    def connector_registrations() -> list[ConnectorRegistration]:
        return [
            ConnectorRegistration(
                connector_key="github_webhook",
                plugin_name="github_phase1",
                display_name="GitHub Webhook",
                version="1",
                connector_kind="inbound",
                supports_webhook=True,
                supports_polling=False,
                supports_actions=True,
                event_types=["github.issues.opened"],
                action_types=["github.issues.create"],
            )
        ]

    @staticmethod
    def trigger_registrations() -> list[TriggerRegistration]:
        return [
            TriggerRegistration(
                trigger_key="github_issue_opened",
                plugin_name="github_phase1",
                trigger_kind="event",
                connector_key="github_webhook",
                event_types=["github.issues.opened"],
                workflow_name="handle_github_issue_opened",
                priority=10,
            ),
            TriggerRegistration(
                trigger_key="sample_app_event",
                plugin_name="sample",
                trigger_kind="event",
                connector_key=None,
                event_types=["sample.connected"],
                workflow_name="handle_sample_event",
                priority=50,
            ),
        ]

    @staticmethod
    def effective_app_connectors() -> list[dict[str, object]]:
        return [
            {
                "connector_id": "sample_app",
                "plugin_name": "sample",
                "display_name": "Sample App",
                "connector_kind": "app",
                "supports_webhook": False,
                "supports_polling": False,
                "supports_actions": True,
                "enabled": True,
                "health": "ready",
                "event_types": [],
                "action_types": ["sample.invoke"],
                "source_kind": "plugin_app",
            },
            {
                "connector_id": "legacy_app",
                "plugin_name": "sample",
            },
        ]

class _Runtime:
    def __init__(self, *, approval_policy: str = "on-request") -> None:
        self.tools = SimpleNamespace(_plugin_manager=_PluginManager())
        self._approval_policy = approval_policy

    def runtime_policy_status(self) -> dict[str, str]:
        return {"approval_policy": self._approval_policy, "network_access": "enabled"}

    def _tool_capabilities(self) -> dict[str, object]:
        return {
            "ok": True,
            "count": 7,
            "workspace_trust": "trusted",
            "mcp_servers": {
                "sample": {"url": "https://user.example/mcp"},
                "docs": {"url": "https://docs.example/mcp"},
            },
            "app_connectors": [
                {
                    "connector_id": "sample_app",
                    "plugin_name": "sample",
                    "display_name": "Sample App",
                    "connector_kind": "app",
                    "supports_actions": True,
                    "enabled": True,
                    "source_kind": "plugin_app",
                },
                {
                    "connector_id": "legacy_app",
                    "plugin_name": "sample",
                },
            ],
        }

    @property
    def tools(self):  # type: ignore[override]
        return self._tools

    @tools.setter
    def tools(self, value):
        value.capabilities = self._tool_capabilities
        self._tools = value

def test_plugins_list_exposes_plugin_control_plane_state() -> None:
    outcome = dispatch_gateway_method(
        method="plugins.list",
        params={},
        runtime=_Runtime(),
        client_info={"name": "gateway-ui"},
    )

    assert outcome.ok is True
    assert outcome.result["workspaceTrust"] == "trusted"
    assert outcome.result["runtimeRegistry"]["workspaceTrust"] == "trusted"
    assert outcome.result["runtimeRegistry"]["toolCount"] == 7
    assert outcome.result["runtimePolicy"]["approval_policy"] == "on-request"
    assert outcome.result["counts"] == {
        "plugins": 2,
        "enabled": 1,
        "withErrors": 0,
    }
    sample = next(item for item in outcome.result["plugins"] if item["name"] == "sample")
    assert sample["health"] == "warning"
    assert sample["app_count"] == 1

def test_plugins_connectors_list_combines_gateway_and_app_connectors_and_derives_approval() -> None:
    outcome = dispatch_gateway_method(
        method="plugins.connectors.list",
        params={},
        runtime=_Runtime(approval_policy="on-request"),
        client_info={"name": "gateway-ui"},
    )

    assert outcome.ok is True
    connector_by_id = {item["connector_id"]: item for item in outcome.result["connectors"]}

    github = connector_by_id["github_webhook"]
    assert github["source_kind"] == "gateway"
    assert github["approval_required"] is True
    assert isinstance(github["approval_required"], bool)
    assert github["enabled"] is True
    assert github["approval"]["required"] is True
    assert github["approval"]["policy"] == "on-request"
    assert github["approval"]["resolver"] == "approvals.resolve"
    assert github["approval"]["action_policy"]["action_kind"] == "connector"
    assert github["approval"]["action_policy"]["decision"] == "requires_approval"
    assert github["approval"]["action_policy"]["requirement"] == "needs_approval"
    assert github["approval"]["action_policy"]["matched_rules"][0]["rule_id"] == "connector.action.approval_required"
    assert github["approval"]["action_policy"]["metadata"]["resolver"] == "approvals.resolve"

    sample_app = connector_by_id["sample_app"]
    assert sample_app["source_kind"] == "plugin_app"
    assert sample_app["approval_required"] is True
    assert isinstance(sample_app["approval_required"], bool)
    assert sample_app["enabled"] is False
    assert sample_app["connector_key"] == "sample_app"
    assert sample_app["approval"]["required"] is True
    assert sample_app["approval"]["policy"] == "on-request"
    assert sample_app["approval"]["resolver"] == "approvals.resolve"
    assert sample_app["approval"]["action_policy"]["decision"] == "requires_approval"

    legacy_app = connector_by_id["legacy_app"]
    assert legacy_app["display_name"] == "legacy_app"
    assert legacy_app["connector_kind"] == "app"
    assert legacy_app["approval_required"] is True
    assert isinstance(legacy_app["approval_required"], bool)
    assert legacy_app["approval"]["required"] is True
    assert legacy_app["approval"]["policy"] == "on-request"
    assert legacy_app["approval"]["resolver"] == "approvals.resolve"
    assert legacy_app["approval"]["action_policy"]["decision"] == "requires_approval"
    assert outcome.result["counts"]["approvalRequired"] == 3
    assert isinstance(outcome.result["counts"]["approvalRequired"], int)
    assert outcome.result["runtimeRegistry"]["toolCount"] == 7
    assert outcome.result["runtimeRegistry"]["source"] == "tools.capabilities"

def test_plugins_connectors_list_keeps_stable_approval_fields_when_policy_is_never() -> None:
    outcome = dispatch_gateway_method(
        method="plugins.connectors.list",
        params={},
        runtime=_Runtime(approval_policy="never"),
        client_info={"name": "gateway-ui"},
    )

    assert outcome.ok is True
    connector_by_id = {item["connector_id"]: item for item in outcome.result["connectors"]}

    for connector_id in ("github_webhook", "sample_app", "legacy_app"):
        connector = connector_by_id[connector_id]
        assert connector["approval_required"] is False
        assert isinstance(connector["approval_required"], bool)
        assert connector["approval"]["required"] is False
        assert isinstance(connector["approval"]["required"], bool)
        assert connector["approval"]["policy"] == "never"
        assert connector["approval"]["resolver"] == "approvals.resolve"
        assert connector["approval"]["action_policy"]["decision"] == "allowed"
        assert connector["approval"]["action_policy"]["requirement"] == "skip"
        assert connector["approval"]["action_policy"]["metadata"]["resolver"] == "approvals.resolve"

    assert outcome.result["counts"]["approvalRequired"] == 0

def test_plugins_triggers_list_supports_plugin_filter_and_tracks_plugin_enabled_state() -> None:
    outcome = dispatch_gateway_method(
        method="plugins.triggers.list",
        params={"pluginName": "sample"},
        runtime=_Runtime(),
        client_info={"name": "gateway-ui"},
    )

    assert outcome.ok is True
    assert outcome.result["counts"] == {
        "triggers": 1,
        "enabled": 0,
    }
    assert outcome.result["triggers"] == [
        {
            "trigger_key": "sample_app_event",
            "plugin_name": "sample",
            "trigger_kind": "event",
            "connector_key": None,
            "event_types": ["sample.connected"],
            "workflow_name": "handle_sample_event",
            "priority": 50,
            "enabled": False,
            "health": "warning",
            "filters": {},
            "metadata": {},
        }
    ]
