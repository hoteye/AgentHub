from __future__ import annotations

from types import SimpleNamespace

import pytest

from cli.agent_cli.gateway_server.write_budget import (
    CONTROL_PLANE_WRITE_BUDGET_MAX_REQUESTS,
    CONTROL_PLANE_WRITE_BUDGET_WINDOW_MS,
    ControlPlaneWriteBudget,
    __testing,
    consume_control_plane_write_budget,
    resolve_control_plane_write_budget_key,
)

def test_resolve_control_plane_write_budget_key_prefers_device_id_and_client_ip() -> None:
    client = SimpleNamespace(
        connect=SimpleNamespace(device=SimpleNamespace(id="device-7")),
        clientIp="203.0.113.7",
        connId="conn-7",
    )

    assert resolve_control_plane_write_budget_key(client) == "device-7|203.0.113.7"

def test_resolve_control_plane_write_budget_key_falls_back_to_conn_id_when_identity_is_missing() -> None:
    client = {"connId": "conn-123"}

    assert resolve_control_plane_write_budget_key(client) == "unknown-device|unknown-ip|conn=conn-123"

def test_consume_control_plane_write_budget_allows_up_to_limit_then_blocks_until_window_resets() -> None:
    budget = ControlPlaneWriteBudget(max_requests=3, window_ms=1_000)
    client = {"connect": {"device": {"id": "device-1"}}, "clientIp": "198.51.100.1"}

    first = budget.consume(client=client, now_ms=10_000)
    second = budget.consume(client=client, now_ms=10_100)
    third = budget.consume(client=client, now_ms=10_200)
    blocked = budget.consume(client=client, now_ms=10_300)
    reset = budget.consume(client=client, now_ms=11_001)

    assert first.allowed is True
    assert first.remaining == 2
    assert second.allowed is True
    assert second.remaining == 1
    assert third.allowed is True
    assert third.remaining == 0
    assert blocked.allowed is False
    assert blocked.remaining == 0
    assert blocked.retry_after_ms == 700
    assert reset.allowed is True
    assert reset.remaining == 2

def test_control_plane_write_budget_isolated_by_resolved_key() -> None:
    budget = ControlPlaneWriteBudget(max_requests=1, window_ms=5_000)

    first = budget.consume(client={"clientIp": "198.51.100.1"}, now_ms=1_000)
    second = budget.consume(client={"clientIp": "198.51.100.2"}, now_ms=1_001)
    blocked = budget.consume(client={"clientIp": "198.51.100.1"}, now_ms=1_002)

    assert first.allowed is True
    assert second.allowed is True
    assert blocked.allowed is False
    assert blocked.key == first.key
    assert second.key != first.key

def test_default_consumer_exposes_openclaw_aligned_defaults_and_testing_reset_hook() -> None:
    __testing.reset_control_plane_write_budget_state()
    client = {"clientIp": "203.0.113.9"}

    decisions = [
        consume_control_plane_write_budget(client=client, now_ms=20_000 + offset)
        for offset in (0, 1, 2, 3)
    ]

    assert decisions[0].limit == CONTROL_PLANE_WRITE_BUDGET_MAX_REQUESTS
    assert decisions[0].window_ms == CONTROL_PLANE_WRITE_BUDGET_WINDOW_MS
    assert [item.allowed for item in decisions] == [True, True, True, False]

    __testing.reset_control_plane_write_budget_state()
    allowed_again = consume_control_plane_write_budget(client=client, now_ms=20_004)
    assert allowed_again.allowed is True

def test_constructor_rejects_non_positive_limits() -> None:
    with pytest.raises(ValueError, match="max_requests must be positive"):
        ControlPlaneWriteBudget(max_requests=0)

    with pytest.raises(ValueError, match="window_ms must be positive"):
        ControlPlaneWriteBudget(window_ms=0)
