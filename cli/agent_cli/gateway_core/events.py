from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Dict, Optional

from .models import GatewayEvent, gateway_event_from_mapping


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_id(prefix: str, *parts: object) -> str:
    digest = sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def create_gateway_event(
    *,
    event_type: str,
    source_kind: str,
    source_id: str,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    connector_key: Optional[str] = None,
    plugin_name: Optional[str] = None,
    tenant_id: Optional[str] = None,
    occurred_at: Optional[str] = None,
    received_at: Optional[str] = None,
    trace_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> GatewayEvent:
    safe_received_at = str(received_at or _utc_now_text())
    safe_occurred_at = str(occurred_at or safe_received_at)
    safe_trace_id = str(trace_id or _stable_id("trace", source_kind, source_id, event_type, safe_received_at))
    safe_event_id = str(event_id or _stable_id("evt", safe_trace_id, event_type, source_id, safe_occurred_at))
    return GatewayEvent(
        event_id=safe_event_id,
        event_type=str(event_type or "").strip(),
        source_kind=str(source_kind or "").strip(),
        source_id=str(source_id or "").strip(),
        connector_key=str(connector_key).strip() if connector_key is not None else None,
        plugin_name=str(plugin_name).strip() if plugin_name is not None else None,
        tenant_id=str(tenant_id).strip() if tenant_id is not None else None,
        occurred_at=safe_occurred_at,
        received_at=safe_received_at,
        trace_id=safe_trace_id,
        correlation_id=str(correlation_id).strip() if correlation_id is not None else None,
        causation_id=str(causation_id).strip() if causation_id is not None else None,
        payload=dict(payload or {}),
        metadata=dict(metadata or {}),
    )


def gateway_event_from_dict(payload: Dict[str, Any]) -> GatewayEvent:
    return gateway_event_from_mapping(payload)
