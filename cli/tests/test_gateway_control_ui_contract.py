from __future__ import annotations

from cli.agent_cli.gateway_core import create_gateway_event
from cli.agent_cli.gateway_core.models import ConnectorRegistration
from cli.agent_cli.gateway_core.registry import GatewayRegistry
from cli.agent_cli.gateway_server.control_ui_contract import (
    CONTROL_UI_BOOTSTRAP_CONFIG_PATH,
    build_control_ui_bootstrap,
    build_control_ui_state_snapshot,
)
from cli.agent_cli.runtime import AgentCliRuntime

class _Agent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_label": "openai | gpt-5.4",
            "provider_model": "gpt-5.4",
            "platform_family": "linux",
            "platform_os": "linux",
            "shell_kind": "bash",
        }

def test_control_ui_contract_bootstrap_and_state_snapshot() -> None:
    runtime = AgentCliRuntime(agent=_Agent())
    runtime.save_gateway_event(
        create_gateway_event(
            event_type="demo.event",
            source_kind="manual",
            source_id="tester",
            payload={"ticket": "T-1"},
        )
    )

    bootstrap = build_control_ui_bootstrap(runtime, base_path="/gui")
    state = build_control_ui_state_snapshot(runtime, limit=5)

    assert CONTROL_UI_BOOTSTRAP_CONFIG_PATH == "/__agenthub/control-ui-config.json"
    assert bootstrap["basePath"] == "/gui"
    assert bootstrap["serverVersion"]
    assert "gateway_events" in bootstrap["gateway"]["streams"]
    assert state["health"]["status"] == "ok"
    assert state["events"][0]["event_type"] == "demo.event"
    assert state["accessPosture"]["access"]["posture"] == "local-only"
    assert state["diagnostics"]["access_posture"]["summary"]["pendingPairingRequestCount"] == 0

def test_control_ui_state_snapshot_includes_gateway_connectors() -> None:
    runtime = AgentCliRuntime(agent=_Agent())

    registry = GatewayRegistry()
    registry.register_connector(
        ConnectorRegistration(
            connector_key="github_webhook",
            plugin_name="github_phase1",
            display_name="GitHub Webhook",
            version="1",
            connector_kind="inbound",
            supports_webhook=True,
            event_types=["github.issues.opened"],
            action_types=["github.issues.create"],
        )
    )
    runtime.gateway_registry = lambda: registry  # type: ignore[method-assign]

    state = build_control_ui_state_snapshot(runtime, limit=5)

    assert state["connectors"] == [
        {
            "connector_key": "github_webhook",
            "plugin_name": "github_phase1",
            "display_name": "GitHub Webhook",
            "version": "1",
            "connector_kind": "inbound",
            "description": "",
            "supports_webhook": True,
            "supports_polling": False,
            "supports_actions": False,
            "event_types": ["github.issues.opened"],
            "action_types": ["github.issues.create"],
            "config_schema_ref": None,
            "enabled_by_default": True,
            "metadata": {},
        }
    ]

def test_control_ui_state_snapshot_exposes_runtime_policy_and_approval_status() -> None:
    runtime = AgentCliRuntime(agent=_Agent())
    runtime.runtime_policy_status = lambda: {"approval_policy": "never", "network_access": "enabled"}  # type: ignore[method-assign]
    runtime.approval_status = lambda: {"pending_approvals": "2", "latest_pending_approval_id": "approval_9"}  # type: ignore[method-assign]

    state = build_control_ui_state_snapshot(runtime, limit=5)

    assert state["runtimePolicy"] == {"approval_policy": "never", "network_access": "enabled"}
    assert state["approvalStatus"] == {
        "pending_approvals": "2",
        "latest_pending_approval_id": "approval_9",
    }
    assert state["diagnostics"]["pairing_summary"]["hasNativeContract"] is False
