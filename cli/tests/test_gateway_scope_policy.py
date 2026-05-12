from __future__ import annotations

import pytest

from cli.agent_cli.gateway_api.auth import resolve_gateway_auth_context
from cli.agent_cli.gateway_protocol.errors import GatewayProtocolError
from cli.agent_cli.gateway_server.authz import (
    authorize_gateway_method,
    is_control_plane_write_method,
    require_gateway_authorized,
    resolve_required_scopes_for_method,
)

def test_resolve_required_scopes_matches_frozen_method_metadata() -> None:
    assert resolve_required_scopes_for_method("connect.initialize") == []
    assert resolve_required_scopes_for_method("approvals.resolve") == ["approvals.resolve"]
    assert resolve_required_scopes_for_method("browser.proxy") == ["browser.write"]
    assert is_control_plane_write_method("browser.proxy") is True

def test_authorize_gateway_method_allows_operator_default_read_paths() -> None:
    auth = resolve_gateway_auth_context(
        actor_id="operator-1",
        role="operator",
        auth_source="local",
        trust_level="trusted",
    )

    decision = authorize_gateway_method(method="gateway.state.get", auth=auth)

    assert decision.allowed is True
    assert decision.required_scopes == ["gateway.read"]

def test_authorize_gateway_method_rejects_missing_scope() -> None:
    auth = resolve_gateway_auth_context(
        actor_id="worker-1",
        role="worker",
        scopes=["browser.read"],
        auth_source="worker",
        trust_level="trusted",
        include_role_default_scopes=False,
    )

    decision = authorize_gateway_method(method="browser.proxy", auth=auth)

    assert decision.allowed is False
    assert decision.code == "FORBIDDEN"
    assert decision.missing_scopes == ["browser.write"]

def test_authorize_gateway_method_enforces_role_policy_for_webhook_identity() -> None:
    auth = resolve_gateway_auth_context(
        actor_id="hook-1",
        role="webhook",
        scopes=["github.write"],
        auth_source="shared-secret",
        trust_level="external",
    )

    allowed = authorize_gateway_method(method="github.webhook.ingest", auth=auth)
    denied = authorize_gateway_method(method="github.actions.dispatch", auth=auth)

    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.code == "FORBIDDEN"
    assert "not authorized" in (denied.reason or "")

def test_authorize_gateway_method_allows_plugin_role_only_for_plugin_surface() -> None:
    auth = resolve_gateway_auth_context(
        actor_id="plugin-1",
        role="plugin",
        scopes=["plugins.read"],
        auth_source="plugin-runtime",
        trust_level="trusted",
        include_role_default_scopes=False,
    )

    allowed = authorize_gateway_method(method="plugins.list", auth=auth)
    denied = authorize_gateway_method(method="gateway.state.get", auth=auth)

    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.code == "FORBIDDEN"

def test_authorize_gateway_method_allows_worker_role_for_workflow_resume() -> None:
    auth = resolve_gateway_auth_context(
        actor_id="worker-1",
        role="worker",
        scopes=["gateway.write"],
        auth_source="worker",
        trust_level="trusted",
        include_role_default_scopes=False,
    )

    decision = authorize_gateway_method(method="workflows.resume", auth=auth)

    assert decision.allowed is True
    assert decision.control_plane_write is True
    assert decision.required_scopes == ["gateway.write"]

def test_require_gateway_authorized_raises_protocol_error_for_unauthenticated_context() -> None:
    auth = resolve_gateway_auth_context(
        actor_id="anon",
        role="operator",
        authenticated=False,
        auth_source="missing",
        trust_level="untrusted",
    )

    with pytest.raises(GatewayProtocolError) as excinfo:
        require_gateway_authorized(method="health.get", auth=auth)

    assert excinfo.value.code == "UNAUTHORIZED"
