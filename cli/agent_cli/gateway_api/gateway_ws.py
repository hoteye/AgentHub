from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from cli.agent_cli.gateway_server.dispatcher import gateway_dispatcher_methods


GATEWAY_WS_STREAMS = [
    "gateway_events",
    "workflow_runs",
    "approvals",
    "audit",
]


def _normalize_streams(streams: Iterable[str] | None = None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in streams or []:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def gateway_ws_capabilities() -> Dict[str, List[str]]:
    return {
        "protocolVersions": ["v1"],
        "streams": list(GATEWAY_WS_STREAMS),
        "commands": ["subscribe", "unsubscribe", "poll", "ping"],
        "methods": list(gateway_dispatcher_methods()),
    }


@dataclass(slots=True, frozen=True)
class GatewayWsSubscription:
    subscription_id: str
    streams: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subscriptionId": self.subscription_id,
            "streams": list(self.streams),
        }


def gateway_ws_subscribe(
    runtime: Any,
    *,
    subscription_id: str,
    streams: Iterable[str] | None = None,
) -> GatewayWsSubscription:
    normalized_streams = tuple(_normalize_streams(streams) or list(GATEWAY_WS_STREAMS))
    subscribe = getattr(runtime, "subscribe_gateway_broadcast")
    subscribe(subscription_id=subscription_id, streams=list(normalized_streams))
    return GatewayWsSubscription(subscription_id=str(subscription_id), streams=normalized_streams)


def gateway_ws_unsubscribe(runtime: Any, *, subscription_id: str) -> bool:
    unsubscribe = getattr(runtime, "unsubscribe_gateway_broadcast")
    return bool(unsubscribe(subscription_id))


def gateway_ws_poll(
    runtime: Any,
    *,
    cursor: int = 0,
    streams: Iterable[str] | None = None,
) -> Dict[str, Any]:
    normalized_streams = _normalize_streams(streams)
    return runtime.gateway_broadcast_since(cursor, streams=normalized_streams or None)


__all__ = [
    "GATEWAY_WS_STREAMS",
    "GatewayWsSubscription",
    "gateway_ws_capabilities",
    "gateway_ws_poll",
    "gateway_ws_subscribe",
    "gateway_ws_unsubscribe",
]
