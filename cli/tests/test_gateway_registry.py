from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from cli.agent_cli.gateway_core import ConnectorRegistration, GatewayRegistry, TriggerRegistration, create_gateway_event
from cli.agent_cli.host.plugin_manager import PluginManager

def test_gateway_registry_registers_connectors_and_triggers() -> None:
    registry = GatewayRegistry()
    connector = ConnectorRegistration(
        connector_key="psbc_webhook",
        plugin_name="psbc_policy",
        display_name="PSBC Webhook",
        version="1",
        connector_kind="inbound",
        event_types=["policy.audit.created"],
        action_types=[],
        supports_webhook=True,
    )
    trigger = TriggerRegistration(
        trigger_key="psbc_audit_trigger",
        plugin_name="psbc_policy",
        trigger_kind="event",
        connector_key="psbc_webhook",
        event_types=["policy.audit.created"],
        workflow_name="handle_audit_case",
        priority=20,
    )

    registry.register_connector(connector)
    registry.register_trigger(trigger)

    event = create_gateway_event(
        event_type="policy.audit.created",
        source_kind="webhook",
        source_id="webhook:psbc",
        connector_key="psbc_webhook",
    )

    matches = registry.triggers_for_event(event)

    assert registry.list_connectors()[0].connector_key == "psbc_webhook"
    assert registry.list_triggers()[0].trigger_key == "psbc_audit_trigger"
    assert [item.trigger_key for item in matches] == ["psbc_audit_trigger"]

def test_gateway_registry_orders_matching_triggers_by_priority_then_key() -> None:
    registry = GatewayRegistry()
    registry.register_trigger(
        TriggerRegistration(
            trigger_key="b_trigger",
            plugin_name="demo_plugin",
            trigger_kind="event",
            connector_key=None,
            event_types=["demo.event"],
            workflow_name="workflow_b",
            priority=50,
        )
    )
    registry.register_trigger(
        TriggerRegistration(
            trigger_key="a_trigger",
            plugin_name="demo_plugin",
            trigger_kind="event",
            connector_key=None,
            event_types=["demo.event"],
            workflow_name="workflow_a",
            priority=50,
        )
    )
    registry.register_trigger(
        TriggerRegistration(
            trigger_key="fast_trigger",
            plugin_name="demo_plugin",
            trigger_kind="event",
            connector_key=None,
            event_types=["demo.event"],
            workflow_name="workflow_fast",
            priority=10,
        )
    )

    event = create_gateway_event(event_type="demo.event", source_kind="manual", source_id="cli")

    assert [item.trigger_key for item in registry.triggers_for_event(event)] == [
        "fast_trigger",
        "a_trigger",
        "b_trigger",
    ]

def test_gateway_registry_can_load_connector_and_trigger_registrations_from_plugin_manager() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "plugins" / "demo_plugin"

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_root = Path(tmpdir)
        source_root = temp_root / "source"
        plugins_root = temp_root / "plugins_target"
        state_path = temp_root / "plugin_state.json"
        source_root.mkdir(parents=True, exist_ok=True)
        copied = source_root / "demo_plugin"
        shutil.copytree(source, copied)
        (copied / "runtime.py").write_text(
            "\n".join(
                [
                    "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                    "",
                    "def runtime_hooks():",
                    "    return RuntimeHooks(",
                    "        build_connector_registrations=lambda plugin_name='demo_plugin': [",
                    "            {",
                    "                'connector_key': 'demo_webhook',",
                    "                'plugin_name': plugin_name,",
                    "                'display_name': 'Demo Webhook',",
                    "                'version': '1',",
                    "                'connector_kind': 'inbound',",
                    "                'supports_webhook': True,",
                    "                'supports_polling': False,",
                    "                'supports_actions': False,",
                    "                'event_types': ['demo.event'],",
                    "                'action_types': [],",
                    "            }",
                    "        ],",
                    "        build_trigger_registrations=lambda: [",
                    "            {",
                    "                'trigger_key': 'demo_trigger',",
                    "                'plugin_name': 'demo_plugin',",
                    "                'trigger_kind': 'event',",
                    "                'connector_key': 'demo_webhook',",
                    "                'event_types': ['demo.event'],",
                    "                'workflow_name': 'handle_demo_event',",
                    "                'priority': 10,",
                    "            }",
                    "        ],",
                    "    )",
                ]
            ),
            encoding="utf-8",
        )

        manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
        installed = manager.install_plugin(str(copied))
        assert installed["ok"] is True

        registry = GatewayRegistry().load_from_plugin_manager(manager)
        event = create_gateway_event(
            event_type="demo.event",
            source_kind="webhook",
            source_id="demo:webhook",
            connector_key="demo_webhook",
        )

        assert [item.connector_key for item in registry.list_connectors()] == ["demo_webhook"]
        assert [item.trigger_key for item in registry.triggers_for_event(event)] == ["demo_trigger"]

def test_gateway_registry_rejects_duplicate_connector_key() -> None:
    registry = GatewayRegistry()
    registry.register_connector(
        ConnectorRegistration(
            connector_key="demo_webhook",
            plugin_name="plugin_a",
            display_name="Demo A",
            version="1",
            connector_kind="inbound",
            event_types=["demo.event"],
            action_types=[],
        )
    )

    with pytest.raises(ValueError, match=r"duplicate connector_key 'demo_webhook'.*plugin_a"):
        registry.register_connector(
            ConnectorRegistration(
                connector_key="demo_webhook",
                plugin_name="plugin_b",
                display_name="Demo B",
                version="1",
                connector_kind="inbound",
                event_types=["demo.event"],
                action_types=[],
            )
        )

def test_gateway_registry_rejects_duplicate_trigger_key() -> None:
    registry = GatewayRegistry()
    registry.register_trigger(
        TriggerRegistration(
            trigger_key="demo_trigger",
            plugin_name="plugin_a",
            trigger_kind="event",
            connector_key="demo_webhook",
            event_types=["demo.event"],
            workflow_name="workflow_a",
        )
    )

    with pytest.raises(ValueError, match=r"duplicate trigger_key 'demo_trigger'.*plugin_a"):
        registry.register_trigger(
            TriggerRegistration(
                trigger_key="demo_trigger",
                plugin_name="plugin_b",
                trigger_kind="event",
                connector_key="demo_webhook",
                event_types=["demo.event"],
                workflow_name="workflow_b",
            )
        )
