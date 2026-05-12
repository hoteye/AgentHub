from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from cli.agent_cli.gateway_server.request_scope import get_gateway_request_scope


@dataclass(slots=True, frozen=True)
class GatewayBroadcastFrame:
    cursor: int
    stream: str
    event: str
    payload: Any
    created_at: str
    request_id: str | None = None
    trace_id: str | None = None
    correlation_id: str | None = None
    actor_id: str | None = None
    ingress_kind: str | None = None
    method: str | None = None
    plugin_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["type"] = "event"
        return payload


@dataclass(slots=True, frozen=True)
class GatewayBroadcastSubscription:
    subscription_id: str
    streams: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subscriptionId": self.subscription_id,
            "streams": list(self.streams),
        }


class GatewayEventBroadcaster:
    def __init__(self, *, max_frames: int = 500) -> None:
        self._frames: deque[GatewayBroadcastFrame] = deque(maxlen=max(1, int(max_frames)))
        self._next_cursor = 1
        self._subscriptions: dict[str, tuple[tuple[str, ...], Callable[[GatewayBroadcastFrame], None] | None]] = {}

    @staticmethod
    def normalize_streams(streams: Iterable[str] | None = None) -> tuple[str, ...]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in streams or []:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return tuple(normalized)

    def publish(
        self,
        *,
        stream: str,
        event: str,
        payload: Any,
        trace_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GatewayBroadcastFrame:
        scope = get_gateway_request_scope()
        frame = GatewayBroadcastFrame(
            cursor=self._next_cursor,
            stream=str(stream or "").strip() or "gateway_events",
            event=str(event or "").strip() or "gateway.event",
            payload=payload,
            created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            request_id=scope.request_id if scope is not None else None,
            trace_id=str(trace_id or (scope.trace_id if scope is not None else "")).strip() or None,
            correlation_id=(
                str(correlation_id or (scope.correlation_id if scope is not None else "")).strip() or None
            ),
            actor_id=scope.actor_id if scope is not None else None,
            ingress_kind=scope.ingress_kind if scope is not None else None,
            method=scope.method if scope is not None else None,
            plugin_id=scope.plugin_id if scope is not None else None,
        )
        self._next_cursor += 1
        self._frames.append(frame)
        for streams, callback in list(self._subscriptions.values()):
            if streams and frame.stream not in streams:
                continue
            if callback is None:
                continue
            callback(frame)
        return frame

    def list_since(self, cursor: int = 0, *, streams: Iterable[str] | None = None) -> dict[str, Any]:
        safe_cursor = max(0, int(cursor))
        stream_filter = set(self.normalize_streams(streams))
        items = [
            item.to_dict()
            for item in self._frames
            if item.cursor > safe_cursor and (not stream_filter or item.stream in stream_filter)
        ]
        next_cursor = self._frames[-1].cursor if self._frames else safe_cursor
        return {
            "events": items,
            "next_cursor": next_cursor,
        }

    def subscribe(
        self,
        *,
        subscription_id: str,
        streams: Iterable[str] | None = None,
        callback: Callable[[GatewayBroadcastFrame], None] | None = None,
    ) -> GatewayBroadcastSubscription:
        normalized_id = str(subscription_id or "").strip()
        if not normalized_id:
            raise ValueError("subscription_id is required")
        normalized_streams = self.normalize_streams(streams)
        self._subscriptions[normalized_id] = (normalized_streams, callback)
        return GatewayBroadcastSubscription(subscription_id=normalized_id, streams=normalized_streams)

    def unsubscribe(self, subscription_id: str) -> bool:
        normalized_id = str(subscription_id or "").strip()
        return self._subscriptions.pop(normalized_id, None) is not None

    def subscriptions(self) -> list[GatewayBroadcastSubscription]:
        return [
            GatewayBroadcastSubscription(subscription_id=key, streams=value[0])
            for key, value in sorted(self._subscriptions.items())
        ]


__all__ = [
    "GatewayBroadcastFrame",
    "GatewayBroadcastSubscription",
    "GatewayEventBroadcaster",
]
