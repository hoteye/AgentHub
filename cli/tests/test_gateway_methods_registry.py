from __future__ import annotations

from cli.agent_cli.gateway_server import gateway_method_families, gateway_method_handlers
from cli.agent_cli.gateway_server.method_registry import GatewayServerMethodRegistry

def test_gateway_server_package_exports_expected_method_families() -> None:
    family_names = [family.family_name for family in gateway_method_families]

    assert family_names == [
        "connect",
        "config",
        "access",
        "nodes",
        "health",
        "gateway_state",
        "approvals",
        "browser",
        "github",
        "plugins",
        "workflows",
        "logs",
    ]

def test_gateway_server_merges_family_handler_maps_without_name_collisions() -> None:
    expected_methods = {
        "connect.initialize",
        "connect.capabilities",
        "connect.ping",
        "config.validate",
        "config.apply",
        "config.restart.report",
        "access.posture.get",
        "nodes.list",
        "health.get",
        "health.probes",
        "gateway.state.get",
        "gateway.events.list",
        "gateway.workflows.list",
        "gateway.trace.timeline",
        "approvals.list",
        "approvals.get",
        "approvals.resolve",
        "browser.proxy",
        "browser.workflow.run",
        "browser.playbook.run",
        "github.webhook.ingest",
        "github.actions.dispatch",
        "github.issues.create",
        "github.comments.create",
        "plugins.list",
        "plugins.connectors.list",
        "plugins.triggers.list",
        "workflows.list",
        "workflows.get",
        "workflows.resume",
        "logs.tail",
    }

    assert set(gateway_method_handlers) == expected_methods

def test_gateway_server_method_registry_exposes_metadata_and_handler_presence() -> None:
    registry = GatewayServerMethodRegistry(handlers=gateway_method_handlers)

    connect_initialize = registry.require("connect.initialize")
    access_posture = registry.require("access.posture.get")
    nodes_list = registry.require("nodes.list")
    config_apply = registry.require("config.apply")
    workflows_resume = registry.require("workflows.resume")

    assert connect_initialize.metadata.auth_required is False
    assert connect_initialize.handler_registered is True
    assert access_posture.metadata.family == "access"
    assert access_posture.metadata.control_plane_write is False
    assert access_posture.handler_registered is True
    assert nodes_list.metadata.family == "nodes"
    assert nodes_list.metadata.required_scopes == ["gateway.read"]
    assert nodes_list.handler_registered is True
    assert config_apply.metadata.control_plane_write is True
    assert config_apply.handler_registered is True
    assert workflows_resume.metadata.control_plane_write is True
    assert workflows_resume.metadata.required_scopes == ["gateway.write"]
