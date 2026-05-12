from __future__ import annotations

from cli.agent_cli.app_server_protocol_runtime import (
    APP_SERVER_BASE_METHODS,
    APP_SERVER_GATEWAY_EXTENSION_METHODS,
    REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS,
    app_server_gateway_extension_methods,
)
from cli.agent_cli.gateway_protocol import GatewayAuthContext, MethodMetadata, MethodRegistry, default_method_registry
from cli.agent_cli.gateway_protocol import methods_runtime as methods_runtime_service
from cli.agent_cli.gateway_server.dispatcher import gateway_dispatcher_methods

def test_gateway_protocol_default_methods_expose_initial_metadata() -> None:
    registry = default_method_registry()

    browser_proxy = registry.require("browser.proxy")
    access_posture = registry.require("access.posture.get")
    nodes_list = registry.require("nodes.list")
    approval_resolve = registry.require("approvals.resolve")
    connect_initialize = registry.require("connect.initialize")
    github_dispatch = registry.require("github.actions.dispatch")
    plugins_list = registry.require("plugins.list")
    workflows_resume = registry.require("workflows.resume")
    logs_tail = registry.require("logs.tail")

    assert browser_proxy.family == "browser"
    assert access_posture.family == "access"
    assert access_posture.auth_required is False
    assert nodes_list.family == "nodes"
    assert nodes_list.required_scopes == ["gateway.read"]
    assert browser_proxy.control_plane_write is True
    assert browser_proxy.required_scopes == ["browser.write"]
    assert approval_resolve.required_scopes == ["approvals.resolve"]
    assert connect_initialize.auth_required is False
    assert github_dispatch.required_scopes == ["github.write"]
    assert plugins_list.family == "plugins"
    assert plugins_list.required_scopes == ["plugins.read"]
    assert workflows_resume.control_plane_write is True
    assert workflows_resume.idempotent is False
    assert logs_tail.required_scopes == ["gateway.read"]
    assert logs_tail.idempotent is True

def test_gateway_protocol_method_registry_rejects_duplicates() -> None:
    registry = MethodRegistry()
    registry.register(MethodMetadata(method="health.get", family="health"))

    try:
        registry.register(MethodMetadata(method="health.get", family="health"))
    except ValueError as exc:
        assert "duplicate gateway method" in str(exc)
    else:
        raise AssertionError("expected ValueError")

def test_gateway_protocol_auth_context_supports_roles_and_scopes() -> None:
    context = GatewayAuthContext(
        actor_id="operator-1",
        client_type="gui",
        roles=["operator"],
        scopes=["gateway.read", "browser.write"],
    )

    assert context.has_role("operator") is True
    assert context.has_scope("browser.write") is True
    assert context.has_any_scope(["gateway.write", "gateway.read"]) is True


def test_gateway_protocol_default_method_payload_order_snapshot() -> None:
    methods = [str(item.get("method") or "") for item in methods_runtime_service.default_method_payloads()]
    assert methods[:8] == [
        "connect.initialize",
        "connect.capabilities",
        "connect.ping",
        "access.posture.get",
        "nodes.list",
        "config.validate",
        "config.apply",
        "config.restart.report",
    ]
    assert methods[-3:] == ["workflows.get", "workflows.resume", "logs.tail"]


def test_app_server_gateway_extension_method_order_guard() -> None:
    expected = [
        "access.posture.get",
        "approvals.get",
        "approvals.list",
        "approvals.resolve",
        "browser.playbook.run",
        "browser.proxy",
        "browser.workflow.run",
        "config.apply",
        "config.restart.report",
        "config.validate",
        "connect.capabilities",
        "connect.initialize",
        "connect.ping",
        "gateway.events.list",
        "gateway.state.get",
        "gateway.trace.timeline",
        "gateway.workflows.list",
        "github.actions.dispatch",
        "github.comments.create",
        "github.issues.create",
        "github.webhook.ingest",
        "health.get",
        "health.probes",
        "logs.tail",
        "nodes.list",
        "plugins.connectors.list",
        "plugins.list",
        "plugins.triggers.list",
        "workflows.get",
        "workflows.list",
        "workflows.resume",
    ]
    extension_methods = app_server_gateway_extension_methods()
    assert extension_methods == expected
    assert extension_methods == list(APP_SERVER_GATEWAY_EXTENSION_METHODS)
    assert list(APP_SERVER_GATEWAY_EXTENSION_METHODS) == expected
    derived = [item for item in gateway_dispatcher_methods() if item not in set(APP_SERVER_BASE_METHODS)]
    assert derived == expected


def test_app_server_method_surface_boundary_has_no_overlap_or_duplicates() -> None:
    base_methods = list(APP_SERVER_BASE_METHODS)
    extension_methods = list(app_server_gateway_extension_methods())
    combined = [*base_methods, *extension_methods]

    assert len(combined) == len(set(combined))
    assert set(base_methods).isdisjoint(set(extension_methods))
    assert all("/" not in item for item in extension_methods)


def test_app_server_method_family_guard_snapshot() -> None:
    base_methods = list(APP_SERVER_BASE_METHODS)
    extension_methods = list(app_server_gateway_extension_methods())

    assert all("." not in item for item in base_methods)
    assert all(item == "initialize" or "/" in item for item in base_methods)
    assert all("." in item and "/" not in item for item in extension_methods)


def test_app_server_method_name_uniqueness_casefold_guard() -> None:
    base_methods = [str(item or "") for item in list(APP_SERVER_BASE_METHODS)]
    extension_methods = [str(item or "") for item in list(app_server_gateway_extension_methods())]
    combined = [*base_methods, *extension_methods]
    combined_casefold = [item.casefold() for item in combined]

    assert len(combined) == len(set(combined))
    assert len(combined_casefold) == len(set(combined_casefold))


def test_unsupported_replacement_targets_reachable_from_method_surface() -> None:
    reachable = set(APP_SERVER_BASE_METHODS) | set(app_server_gateway_extension_methods())
    for method, replacement in REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS.items():
        replacement_key = str(replacement or "").strip()
        assert replacement_key in reachable, f"replacement target is unreachable: {method} -> {replacement_key}"


def test_gateway_facing_unsupported_replacements_reachable_from_method_surface() -> None:
    reachable = set(APP_SERVER_BASE_METHODS) | set(app_server_gateway_extension_methods())
    gateway_facing_unsupported = ("turn/interrupt", "skills/list", "config/read")
    for method in gateway_facing_unsupported:
        replacement_key = str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS.get(method) or "").strip()
        assert replacement_key, f"missing replacement for gateway-facing unsupported method: {method}"
        assert replacement_key in reachable, f"gateway-facing replacement unreachable: {method} -> {replacement_key}"


def test_gateway_facing_unsupported_replacement_uniqueness_guard() -> None:
    gateway_facing_unsupported = ("turn/interrupt", "skills/list", "config/read")
    observed_pairs = [
        (
            str(method or "").strip(),
            str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS.get(method) or "").strip(),
        )
        for method in gateway_facing_unsupported
    ]
    assert all(method and replacement for method, replacement in observed_pairs)
    assert len(observed_pairs) == len({method.casefold() for method, _ in observed_pairs})
    assert len(observed_pairs) == len({(method.casefold(), replacement.casefold()) for method, replacement in observed_pairs})


def test_gateway_facing_unsupported_methods_remain_outside_capability_surface() -> None:
    base_methods = set(APP_SERVER_BASE_METHODS)
    extension_methods = set(APP_SERVER_GATEWAY_EXTENSION_METHODS)
    capability_surface = base_methods | extension_methods
    gateway_facing_unsupported = {"turn/interrupt", "skills/list", "config/read"}

    assert gateway_facing_unsupported.isdisjoint(capability_surface)

    mapped_replacements = {
        str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS.get(method) or "").strip()
        for method in gateway_facing_unsupported
    }
    assert all(mapped_replacements)
    assert mapped_replacements.issubset(capability_surface)
