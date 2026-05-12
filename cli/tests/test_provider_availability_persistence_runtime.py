from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cli.agent_cli.providers.availability_persistence_runtime import (
    load_persisted_availability_registry,
    persist_availability_registry,
)
from cli.agent_cli.providers.availability_registry import AvailabilityRegistry


def test_persist_and_load_registry_round_trip(tmp_path) -> None:
    path = tmp_path / "provider_availability_state.json"
    registry = AvailabilityRegistry()
    checked_at = datetime(2026, 4, 18, 1, 0, 0, tzinfo=timezone.utc)
    registry.mark_success(
        provider_name="openai",
        model="gpt-5.4",
        checked_at=checked_at,
        latency_ms=321,
    )
    registry.mark_failure(
        provider_name="anthropic",
        model="claude-sonnet-4-6",
        failure_code="rate_limited",
        failure_reason="429",
        checked_at=checked_at + timedelta(seconds=5),
        retry_after=timedelta(seconds=12),
        latency_ms=654,
    )

    persist_availability_registry(registry, path=path)
    restored = load_persisted_availability_registry(path=path)

    openai = restored.get("openai", "gpt_54")
    anthropic = restored.get("anthropic", "claude-sonnet-4-6")

    assert openai is not None
    assert openai.status.value == "available"
    assert openai.last_latency_ms == 321
    assert anthropic is not None
    assert anthropic.status.value == "unavailable"
    assert anthropic.failure_code == "rate_limited"
    assert anthropic.retry_after is not None
    assert int(anthropic.retry_after.total_seconds()) == 12


def test_load_persisted_registry_returns_empty_registry_for_missing_file(tmp_path) -> None:
    restored = load_persisted_availability_registry(path=tmp_path / "missing.json")

    assert restored.status("openai", "gpt-5.4").value == "unknown"
