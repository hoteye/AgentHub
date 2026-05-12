from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CONTROL_PLANE_WRITE_BUDGET_MAX_REQUESTS = 3
CONTROL_PLANE_WRITE_BUDGET_WINDOW_MS = 60_000


@dataclass
class _Bucket:
    count: int
    window_start_ms: int


@dataclass(frozen=True)
class WriteBudgetDecision:
    allowed: bool
    retry_after_ms: int
    remaining: int
    key: str
    limit: int
    window_ms: int


def _normalize_part(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    normalized = value.strip()
    return normalized if normalized else fallback


def _lookup_path(payload: Any, path: tuple[str, ...]) -> Any:
    current = payload
    for part in path:
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
            continue
        if hasattr(current, part):
            current = getattr(current, part)
            continue
        return None
    return current


def resolve_control_plane_write_budget_key(client: Any | None) -> str:
    device_id = _normalize_part(
        _lookup_path(client, ("connect", "device", "id"))
        or _lookup_path(client, ("device", "id"))
        or _lookup_path(client, ("device_id",)),
        "unknown-device",
    )
    client_ip = _normalize_part(
        _lookup_path(client, ("clientIp",))
        or _lookup_path(client, ("client_ip",)),
        "unknown-ip",
    )
    if device_id == "unknown-device" and client_ip == "unknown-ip":
        conn_id = _normalize_part(
            _lookup_path(client, ("connId",))
            or _lookup_path(client, ("conn_id",)),
            "",
        )
        if conn_id:
            return f"{device_id}|{client_ip}|conn={conn_id}"
    return f"{device_id}|{client_ip}"


class ControlPlaneWriteBudget:
    def __init__(
        self,
        *,
        max_requests: int = CONTROL_PLANE_WRITE_BUDGET_MAX_REQUESTS,
        window_ms: int = CONTROL_PLANE_WRITE_BUDGET_WINDOW_MS,
    ) -> None:
        if int(max_requests) <= 0:
            raise ValueError("max_requests must be positive")
        if int(window_ms) <= 0:
            raise ValueError("window_ms must be positive")
        self.max_requests = int(max_requests)
        self.window_ms = int(window_ms)
        self._buckets: dict[str, _Bucket] = {}

    def consume(self, *, client: Any | None, now_ms: int | None = None) -> WriteBudgetDecision:
        current_ms = int(now_ms if now_ms is not None else __import__("time").time() * 1000)
        key = resolve_control_plane_write_budget_key(client)
        bucket = self._buckets.get(key)

        if bucket is None or current_ms - bucket.window_start_ms >= self.window_ms:
            self._buckets[key] = _Bucket(count=1, window_start_ms=current_ms)
            return WriteBudgetDecision(
                allowed=True,
                retry_after_ms=0,
                remaining=max(0, self.max_requests - 1),
                key=key,
                limit=self.max_requests,
                window_ms=self.window_ms,
            )

        if bucket.count >= self.max_requests:
            retry_after_ms = max(0, bucket.window_start_ms + self.window_ms - current_ms)
            return WriteBudgetDecision(
                allowed=False,
                retry_after_ms=retry_after_ms,
                remaining=0,
                key=key,
                limit=self.max_requests,
                window_ms=self.window_ms,
            )

        bucket.count += 1
        return WriteBudgetDecision(
            allowed=True,
            retry_after_ms=0,
            remaining=max(0, self.max_requests - bucket.count),
            key=key,
            limit=self.max_requests,
            window_ms=self.window_ms,
        )

    def reset(self) -> None:
        self._buckets.clear()


_DEFAULT_WRITE_BUDGET = ControlPlaneWriteBudget()


def consume_control_plane_write_budget(*, client: Any | None, now_ms: int | None = None) -> WriteBudgetDecision:
    return _DEFAULT_WRITE_BUDGET.consume(client=client, now_ms=now_ms)


class __testing:
    @staticmethod
    def reset_control_plane_write_budget_state() -> None:
        _DEFAULT_WRITE_BUDGET.reset()


__all__ = [
    "CONTROL_PLANE_WRITE_BUDGET_MAX_REQUESTS",
    "CONTROL_PLANE_WRITE_BUDGET_WINDOW_MS",
    "ControlPlaneWriteBudget",
    "WriteBudgetDecision",
    "consume_control_plane_write_budget",
    "resolve_control_plane_write_budget_key",
]
