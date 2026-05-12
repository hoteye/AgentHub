from __future__ import annotations

from typing import Any


def normalized_wait_timeout_ms(
    timeout_ms: Any,
    *,
    default_timeout_ms: int,
    min_timeout_ms: int,
    max_timeout_ms: int,
) -> int:
    if timeout_ms in (None, ""):
        return default_timeout_ms
    value = int(timeout_ms)
    if value <= 0:
        raise ValueError("timeout_ms must be greater than zero")
    return max(min_timeout_ms, min(max_timeout_ms, value))


def wait_timeout_seconds(timeout_ms: Any) -> float | None:
    if timeout_ms in (None, ""):
        return None
    return max(0.0, int(timeout_ms) / 1000.0)


def normalized_wait_agent_ids(agent_ids: list[str]) -> list[str]:
    normalized_ids: list[str] = []
    for raw in list(agent_ids or []):
        agent_id = str(raw or "").strip()
        if agent_id and agent_id not in normalized_ids:
            normalized_ids.append(agent_id)
    if not normalized_ids:
        raise ValueError("wait requires at least one agent id")
    return normalized_ids
