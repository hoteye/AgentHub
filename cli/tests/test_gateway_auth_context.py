from __future__ import annotations

from cli.agent_cli.gateway_api.auth import resolve_gateway_auth_context
from cli.agent_cli.gateway_protocol.auth_context import anonymous_auth_context, auth_context

def test_auth_context_normalizes_primary_role_and_unique_lists() -> None:
    context = auth_context(
        actor_id="operator-1",
        role="operator",
        roles=["operator", "operator", "system"],
        scopes=["gateway.read", "gateway.read", "browser.write"],
        auth_source="local",
        trust_level="trusted",
    )

    assert context.role == "operator"
    assert context.primary_role == "operator"
    assert context.roles == ["operator", "system"]
    assert context.scopes == ["gateway.read", "browser.write"]
    assert context.auth_source == "local"
    assert context.trust_level == "trusted"

def test_resolve_gateway_auth_context_expands_role_default_and_implied_scopes() -> None:
    context = resolve_gateway_auth_context(
        actor_id="operator-1",
        role="operator",
        scopes=["github.write"],
        auth_source="local",
        trust_level="trusted",
        client_type="gui",
    )

    assert context.role == "operator"
    assert context.has_role("operator") is True
    assert context.has_scope("gateway.read") is True
    assert context.has_scope("gateway.write") is True
    assert context.has_scope("approvals.resolve") is True
    assert context.has_scope("approvals.read") is True
    assert context.has_scope("github.write") is True
    assert context.has_scope("github.read") is True
    assert context.client_type == "gui"

def test_anonymous_auth_context_is_unauthenticated() -> None:
    context = anonymous_auth_context(client_type="ws")

    assert context.actor_id == "anonymous"
    assert context.authenticated is False
    assert context.auth_source == "anonymous"
    assert context.trust_level == "untrusted"
    assert context.client_type == "ws"

def test_resolve_gateway_auth_context_can_derive_primary_role_from_roles_without_role_arg() -> None:
    context = resolve_gateway_auth_context(
        actor_id="system-1",
        roles=["system", "operator", "system"],
        scopes=["plugins.write"],
        auth_source="gateway",
        trust_level="trusted",
        client_id="client-1",
    )

    assert context.role == "system"
    assert context.primary_role == "system"
    assert context.roles == ["system", "operator"]
    assert context.has_scope("plugins.write") is True
    assert context.has_scope("plugins.read") is True
    assert context.client_id == "client-1"

def test_resolve_gateway_auth_context_can_disable_role_default_scopes() -> None:
    context = resolve_gateway_auth_context(
        actor_id="webhook-1",
        role="webhook",
        scopes=["github.read"],
        auth_source="shared-secret",
        trust_level="external",
        include_role_default_scopes=False,
    )

    assert context.role == "webhook"
    assert context.scopes == ["github.read"]
    assert context.has_scope("github.write") is False
