from __future__ import annotations

from typing import Any, Dict, Iterable

from cli.agent_cli.gateway_protocol.auth_context import (
    GatewayAuthContext,
    anonymous_auth_context,
    auth_context,
)
from cli.agent_cli.gateway_server.roles import normalize_gateway_roles, resolve_scopes_for_roles


def resolve_gateway_auth_context(
    *,
    actor_id: str,
    role: str | None = None,
    roles: Iterable[str] | None = None,
    scopes: Iterable[str] | None = None,
    tenant_id: str | None = None,
    auth_source: str | None = None,
    trust_level: str | None = None,
    client_id: str | None = None,
    client_type: str | None = None,
    authenticated: bool = True,
    include_role_default_scopes: bool = True,
    metadata: Dict[str, Any] | None = None,
) -> GatewayAuthContext:
    normalized_roles = normalize_gateway_roles(
        [item for item in [role, *(roles or [])] if item is not None]
    )
    primary_role = normalized_roles[0] if normalized_roles else (str(role).strip() if role is not None else None)
    effective_scopes = (
        resolve_scopes_for_roles(normalized_roles, scopes)
        if include_role_default_scopes
        else [str(item).strip() for item in (scopes or []) if str(item).strip()]
    )
    return auth_context(
        actor_id=actor_id,
        role=primary_role,
        roles=normalized_roles,
        scopes=effective_scopes,
        tenant_id=tenant_id,
        auth_source=auth_source,
        trust_level=trust_level,
        client_id=client_id,
        client_type=client_type,
        authenticated=authenticated,
        metadata=metadata,
    )


__all__ = [
    "GatewayAuthContext",
    "anonymous_auth_context",
    "auth_context",
    "resolve_gateway_auth_context",
]
