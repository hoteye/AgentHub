from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from cli.agent_cli.gateway_protocol.auth_context import GatewayAuthContext
from cli.agent_cli.gateway_protocol.errors import ErrorCodes, GatewayProtocolError
from cli.agent_cli.gateway_protocol.methods import MethodMetadata, default_method_registry
from cli.agent_cli.gateway_server.roles import (
    GATEWAY_OPERATOR_ROLE,
    expand_gateway_scopes,
    is_role_authorized_for_method,
    normalize_gateway_roles,
    parse_gateway_role,
    resolve_allowed_roles_for_method,
)


@dataclass(slots=True, frozen=True)
class GatewayAuthorizationDecision:
    method: str
    allowed: bool
    code: str | None = None
    reason: str | None = None
    auth_required: bool = True
    control_plane_write: bool = False
    required_scopes: list[str] = field(default_factory=list)
    missing_scopes: list[str] = field(default_factory=list)
    allowed_roles: list[str] = field(default_factory=list)

    def require_allowed(self) -> None:
        if self.allowed:
            return
        raise GatewayProtocolError(
            self.code or ErrorCodes.FORBIDDEN,
            self.reason or "gateway method is not authorized",
            details={
                "method": self.method,
                "required_scopes": list(self.required_scopes),
                "missing_scopes": list(self.missing_scopes),
                "allowed_roles": list(self.allowed_roles),
                "control_plane_write": self.control_plane_write,
            },
        )


@lru_cache(maxsize=1)
def _frozen_method_registry() -> dict[str, MethodMetadata]:
    return {item.method: item for item in default_method_registry().list()}


def resolve_method_metadata(method: str, metadata: MethodMetadata | None = None) -> MethodMetadata | None:
    if metadata is not None:
        return metadata
    return _frozen_method_registry().get(str(method or "").strip())


def resolve_required_scopes_for_method(method: str, metadata: MethodMetadata | None = None) -> list[str]:
    resolved = resolve_method_metadata(method, metadata)
    if resolved is None:
        return []
    return [str(item).strip() for item in resolved.required_scopes if str(item).strip()]


def is_auth_required_for_method(method: str, metadata: MethodMetadata | None = None) -> bool:
    resolved = resolve_method_metadata(method, metadata)
    if resolved is None:
        return True
    return bool(resolved.auth_required)


def is_control_plane_write_method(method: str, metadata: MethodMetadata | None = None) -> bool:
    resolved = resolve_method_metadata(method, metadata)
    if resolved is None:
        return False
    return bool(resolved.control_plane_write)


def authorize_gateway_method(
    *,
    method: str,
    auth: GatewayAuthContext | None,
    metadata: MethodMetadata | None = None,
) -> GatewayAuthorizationDecision:
    normalized_method = str(method or "").strip()
    resolved = resolve_method_metadata(normalized_method, metadata)
    auth_required = is_auth_required_for_method(normalized_method, resolved)
    control_plane_write = is_control_plane_write_method(normalized_method, resolved)
    required_scopes = resolve_required_scopes_for_method(normalized_method, resolved)
    allowed_roles = list(resolve_allowed_roles_for_method(normalized_method))

    if not auth_required:
        return GatewayAuthorizationDecision(
            method=normalized_method,
            allowed=True,
            auth_required=False,
            control_plane_write=control_plane_write,
            required_scopes=required_scopes,
            allowed_roles=allowed_roles,
        )

    if auth is None or not auth.authenticated:
        return GatewayAuthorizationDecision(
            method=normalized_method,
            allowed=False,
            code=ErrorCodes.UNAUTHORIZED,
            reason="authenticated gateway auth context is required",
            auth_required=auth_required,
            control_plane_write=control_plane_write,
            required_scopes=required_scopes,
            allowed_roles=allowed_roles,
        )

    roles = _resolve_context_roles(auth)
    if not roles:
        return GatewayAuthorizationDecision(
            method=normalized_method,
            allowed=False,
            code=ErrorCodes.FORBIDDEN,
            reason="gateway role is required",
            auth_required=auth_required,
            control_plane_write=control_plane_write,
            required_scopes=required_scopes,
            allowed_roles=allowed_roles,
        )

    if allowed_roles and not any(is_role_authorized_for_method(role, normalized_method) for role in roles):
        return GatewayAuthorizationDecision(
            method=normalized_method,
            allowed=False,
            code=ErrorCodes.FORBIDDEN,
            reason=f"gateway role is not authorized for method: {normalized_method}",
            auth_required=auth_required,
            control_plane_write=control_plane_write,
            required_scopes=required_scopes,
            allowed_roles=allowed_roles,
        )

    granted_scopes = expand_gateway_scopes(auth.scopes)
    missing_scopes = [scope for scope in required_scopes if scope not in granted_scopes]
    if missing_scopes:
        return GatewayAuthorizationDecision(
            method=normalized_method,
            allowed=False,
            code=ErrorCodes.FORBIDDEN,
            reason=f"missing required gateway scope for method: {normalized_method}",
            auth_required=auth_required,
            control_plane_write=control_plane_write,
            required_scopes=required_scopes,
            missing_scopes=missing_scopes,
            allowed_roles=allowed_roles,
        )

    return GatewayAuthorizationDecision(
        method=normalized_method,
        allowed=True,
        auth_required=auth_required,
        control_plane_write=control_plane_write,
        required_scopes=required_scopes,
        allowed_roles=allowed_roles,
    )


def require_gateway_authorized(
    *,
    method: str,
    auth: GatewayAuthContext | None,
    metadata: MethodMetadata | None = None,
) -> GatewayAuthorizationDecision:
    decision = authorize_gateway_method(method=method, auth=auth, metadata=metadata)
    decision.require_allowed()
    return decision


def _resolve_context_roles(auth: GatewayAuthContext) -> list[str]:
    collected: list[str] = []
    if auth.role:
        parsed = parse_gateway_role(auth.role)
        if parsed:
            collected.append(parsed)
    collected.extend(normalize_gateway_roles(auth.roles))
    if not collected and GATEWAY_OPERATOR_ROLE in resolve_allowed_roles_for_method("connect.initialize"):
        parsed_primary = parse_gateway_role(auth.primary_role or "")
        if parsed_primary:
            collected.append(parsed_primary)
    return normalize_gateway_roles(collected)
