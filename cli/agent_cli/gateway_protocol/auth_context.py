from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable


def _copy_map(value: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return dict(value or {})


def _copy_unique_list(values: Iterable[str] | None = None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values or []:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


@dataclass(slots=True, frozen=True)
class GatewayAuthContext:
    actor_id: str
    role: str | None = None
    client_id: str | None = None
    client_type: str | None = None
    tenant_id: str | None = None
    authenticated: bool = True
    auth_source: str | None = None
    trust_level: str | None = None
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        normalized = str(scope or "").strip()
        return bool(normalized) and normalized in self.scopes

    def has_any_scope(self, scopes: Iterable[str]) -> bool:
        return any(self.has_scope(item) for item in scopes)

    def has_role(self, role: str) -> bool:
        normalized = str(role or "").strip()
        return bool(normalized) and (normalized == self.role or normalized in self.roles)

    def has_all_scopes(self, scopes: Iterable[str]) -> bool:
        return all(self.has_scope(item) for item in scopes)

    @property
    def primary_role(self) -> str | None:
        return self.role or (self.roles[0] if self.roles else None)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def auth_context(
    *,
    actor_id: str,
    role: str | None = None,
    client_id: str | None = None,
    client_type: str | None = None,
    tenant_id: str | None = None,
    authenticated: bool = True,
    auth_source: str | None = None,
    trust_level: str | None = None,
    roles: Iterable[str] | None = None,
    scopes: Iterable[str] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> GatewayAuthContext:
    normalized_actor_id = str(actor_id or "").strip()
    if not normalized_actor_id:
        raise ValueError("actor_id is required")
    normalized_role = str(role).strip() if role is not None else None
    normalized_roles = _copy_unique_list(roles)
    if normalized_role and normalized_role not in normalized_roles:
        normalized_roles.insert(0, normalized_role)
    elif normalized_role is None and normalized_roles:
        normalized_role = normalized_roles[0]
    return GatewayAuthContext(
        actor_id=normalized_actor_id,
        role=normalized_role or None,
        client_id=str(client_id).strip() if client_id is not None else None,
        client_type=str(client_type).strip() if client_type is not None else None,
        tenant_id=str(tenant_id).strip() if tenant_id is not None else None,
        authenticated=bool(authenticated),
        auth_source=str(auth_source).strip() if auth_source is not None else None,
        trust_level=str(trust_level).strip() if trust_level is not None else None,
        roles=normalized_roles,
        scopes=_copy_unique_list(scopes),
        metadata=_copy_map(metadata),
    )


def anonymous_auth_context(
    *,
    client_id: str | None = None,
    client_type: str | None = None,
    metadata: Dict[str, Any] | None = None,
) -> GatewayAuthContext:
    return auth_context(
        actor_id="anonymous",
        client_id=client_id,
        client_type=client_type,
        authenticated=False,
        auth_source="anonymous",
        trust_level="untrusted",
        metadata=metadata,
    )
