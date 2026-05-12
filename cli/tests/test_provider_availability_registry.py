from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cli.agent_cli.providers.availability_models import AvailabilityRecord, ProbeStatus
from cli.agent_cli.providers.availability_registry import AvailabilityRegistry


def test_registry_set_and_get_preserves_provider_model_dimensions() -> None:
    registry = AvailabilityRegistry()
    record = AvailabilityRecord(
        provider_name="openai",
        model="gpt-5.4",
        status=ProbeStatus.AVAILABLE,
        checked_at=datetime(2026, 4, 7, 10, 0, 0, tzinfo=timezone.utc),
    )

    registry.set(record)
    stored = registry.get("openai", "gpt-5.4")

    assert stored is not None
    assert stored.provider_name == "openai"
    assert stored.model == "gpt-5.4"
    assert stored.status == ProbeStatus.AVAILABLE


def test_mark_failure_writes_failure_fields_and_retry_after() -> None:
    registry = AvailabilityRegistry()
    checked_at = datetime(2026, 4, 7, 11, 0, 0, tzinfo=timezone.utc)
    retry_after = timedelta(seconds=90)

    record = registry.mark_failure(
        provider_name="openai",
        model="gpt-5.4",
        failure_code="rate_limited",
        failure_reason="429",
        checked_at=checked_at,
        retry_after=retry_after,
    )

    assert record.status == ProbeStatus.UNAVAILABLE
    assert record.failure_code == "rate_limited"
    assert record.failure_reason == "429"
    assert record.retry_after == retry_after
    assert record.checked_at == checked_at


def test_mark_success_clears_previous_failure_state() -> None:
    registry = AvailabilityRegistry()
    registry.mark_failure(
        provider_name="openai",
        model="gpt-5.4",
        failure_code="upstream_error",
        failure_reason="500",
        retry_after=timedelta(seconds=30),
    )

    success = registry.mark_success(provider_name="openai", model="gpt-5.4")

    assert success.status == ProbeStatus.AVAILABLE
    assert success.failure_code == ""
    assert success.failure_reason == ""
    assert success.retry_after is None


def test_registry_accumulates_latency_and_stability_counters_across_probe_results() -> None:
    registry = AvailabilityRegistry()
    first_failure_at = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
    second_failure_at = datetime(2026, 4, 7, 12, 1, 0, tzinfo=timezone.utc)
    success_at = datetime(2026, 4, 7, 12, 2, 0, tzinfo=timezone.utc)

    first_failure = registry.mark_failure(
        provider_name="openai",
        model="gpt-5.4",
        failure_code="timeout",
        failure_reason="request timeout",
        checked_at=first_failure_at,
        latency_ms=900,
    )
    second_failure = registry.mark_failure(
        provider_name="openai",
        model="gpt-5.4",
        failure_code="rate_limited",
        failure_reason="429",
        checked_at=second_failure_at,
        latency_ms=300,
    )
    success = registry.mark_success(
        provider_name="openai",
        model="gpt-5.4",
        checked_at=success_at,
        latency_ms=600,
    )

    assert first_failure.failure_count == 1
    assert first_failure.success_count == 0
    assert first_failure.consecutive_failures == 1
    assert first_failure.last_failure_at == first_failure_at
    assert first_failure.last_success_at is None
    assert first_failure.last_latency_ms == 900
    assert first_failure.avg_latency_ms == 900
    assert first_failure.latency_sample_count == 1

    assert second_failure.failure_count == 2
    assert second_failure.success_count == 0
    assert second_failure.consecutive_failures == 2
    assert second_failure.last_failure_at == second_failure_at
    assert second_failure.last_latency_ms == 300
    assert second_failure.avg_latency_ms == 600
    assert second_failure.latency_sample_count == 2

    assert success.status == ProbeStatus.AVAILABLE
    assert success.success_count == 1
    assert success.failure_count == 2
    assert success.consecutive_failures == 0
    assert success.last_success_at == success_at
    assert success.last_failure_at == second_failure_at
    assert success.last_latency_ms == 600
    assert success.avg_latency_ms == 600
    assert success.latency_sample_count == 3


def test_is_stale_uses_checked_at_and_ttl() -> None:
    registry = AvailabilityRegistry()
    checked_at = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
    registry.mark_success(provider_name="openai", model="gpt-5.4", checked_at=checked_at)

    fresh_now = checked_at + timedelta(seconds=20)
    stale_now = checked_at + timedelta(seconds=90)

    assert registry.is_stale("openai", "gpt-5.4", ttl=timedelta(seconds=60), now=fresh_now) is False
    assert registry.is_stale("openai", "gpt-5.4", ttl=timedelta(seconds=60), now=stale_now) is True
    assert registry.is_stale("openai", "unknown-model", ttl=timedelta(seconds=60), now=stale_now) is True


def test_registry_get_supports_model_alias_lookup_between_key_and_model_id() -> None:
    registry = AvailabilityRegistry()
    registry.mark_failure(
        provider_name="openai",
        model="gpt-5.4",
        failure_code="rate_limited",
        failure_reason="429",
    )

    record = registry.get("openai", "gpt_54")

    assert record is not None
    assert record.status == ProbeStatus.UNAVAILABLE
    assert record.model == "gpt-5.4"


def test_registry_status_is_unknown_for_missing_provider_or_model() -> None:
    registry = AvailabilityRegistry()

    assert registry.status("openai", "gpt-5.4") == ProbeStatus.UNKNOWN


def test_registry_payload_round_trip_preserves_probe_counters_and_timestamps() -> None:
    registry = AvailabilityRegistry()
    checked_at = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
    retry_after = timedelta(seconds=2.5)
    registry.mark_failure(
        provider_name="openai",
        model="gpt-5.4",
        failure_code="timeout",
        failure_reason="request timeout",
        checked_at=checked_at,
        retry_after=retry_after,
        latency_ms=450,
    )

    restored = AvailabilityRegistry.from_payload(registry.to_payload())
    record = restored.get("openai", "gpt_54")

    assert record is not None
    assert record.status == ProbeStatus.UNAVAILABLE
    assert record.checked_at == checked_at
    assert record.failure_code == "timeout"
    assert record.failure_reason == "request timeout"
    assert record.retry_after is not None
    assert record.retry_after.total_seconds() == 2.5
    assert record.last_latency_ms == 450
    assert record.avg_latency_ms == 450
    assert record.failure_count == 1
    assert record.consecutive_failures == 1
