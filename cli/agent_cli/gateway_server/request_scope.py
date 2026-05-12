from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, TypeVar

ScopeResultT = TypeVar("ScopeResultT")


def _copy_map(value: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(value or {})


@dataclass(slots=True, frozen=True)
class GatewayRequestScope:
    request_id: str
    method: str
    ingress_kind: str
    actor_id: str
    trace_id: str | None = None
    correlation_id: str | None = None
    client_id: str | None = None
    conn_id: str | None = None
    plugin_id: str | None = None
    auth: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_GATEWAY_REQUEST_SCOPE: ContextVar[GatewayRequestScope | None] = ContextVar(
    "agenthub_gateway_request_scope",
    default=None,
)


def gateway_request_scope(
    *,
    request_id: str,
    method: str,
    ingress_kind: str,
    actor_id: str,
    trace_id: str | None = None,
    correlation_id: str | None = None,
    client_id: str | None = None,
    conn_id: str | None = None,
    plugin_id: str | None = None,
    auth: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> GatewayRequestScope:
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise ValueError("request_id is required")
    normalized_method = str(method or "").strip()
    if not normalized_method:
        raise ValueError("method is required")
    normalized_ingress = str(ingress_kind or "").strip()
    if not normalized_ingress:
        raise ValueError("ingress_kind is required")
    normalized_actor = str(actor_id or "").strip()
    if not normalized_actor:
        raise ValueError("actor_id is required")
    return GatewayRequestScope(
        request_id=normalized_request_id,
        method=normalized_method,
        ingress_kind=normalized_ingress,
        actor_id=normalized_actor,
        trace_id=str(trace_id).strip() if trace_id is not None else None,
        correlation_id=str(correlation_id).strip() if correlation_id is not None else None,
        client_id=str(client_id).strip() if client_id is not None else None,
        conn_id=str(conn_id).strip() if conn_id is not None else None,
        plugin_id=str(plugin_id).strip() if plugin_id is not None else None,
        auth=_copy_map(auth),
        metadata=_copy_map(metadata),
    )


def with_gateway_request_scope(
    scope: GatewayRequestScope,
    run: Callable[[], ScopeResultT],
) -> ScopeResultT:
    token = _GATEWAY_REQUEST_SCOPE.set(scope)
    try:
        return run()
    finally:
        _GATEWAY_REQUEST_SCOPE.reset(token)


def with_gateway_plugin_scope(
    plugin_id: str,
    run: Callable[[], ScopeResultT],
) -> ScopeResultT:
    current = _GATEWAY_REQUEST_SCOPE.get()
    normalized_plugin_id = str(plugin_id or "").strip()
    if current is None or not normalized_plugin_id:
        return run()
    scoped = GatewayRequestScope(
        request_id=current.request_id,
        method=current.method,
        ingress_kind=current.ingress_kind,
        actor_id=current.actor_id,
        trace_id=current.trace_id,
        correlation_id=current.correlation_id,
        client_id=current.client_id,
        conn_id=current.conn_id,
        plugin_id=normalized_plugin_id,
        auth=_copy_map(current.auth),
        metadata=_copy_map(current.metadata),
    )
    return with_gateway_request_scope(scoped, run)


def get_gateway_request_scope() -> GatewayRequestScope | None:
    return _GATEWAY_REQUEST_SCOPE.get()


__all__ = [
    "GatewayRequestScope",
    "gateway_request_scope",
    "get_gateway_request_scope",
    "with_gateway_plugin_scope",
    "with_gateway_request_scope",
]
