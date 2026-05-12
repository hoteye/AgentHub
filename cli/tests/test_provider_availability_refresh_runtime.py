from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cli.agent_cli.providers.availability_persistence_runtime import (
    load_persisted_availability_registry,
    persist_availability_registry,
)
from cli.agent_cli.providers.availability_registry import AvailabilityRegistry
from cli.agent_cli.runtime_services.provider_availability_refresh_runtime import (
    attach_refresh_controller,
    build_refresh_controller,
    maybe_reload_planner_for_provider_gate_update,
    refresh_controller_surface_fields,
    schedule_stale_on_use_refresh,
    schedule_startup_warmup,
)


@dataclass
class _AgentStub:
    providers: list[dict[str, object]]
    probe_results: dict[tuple[str, str], list[dict[str, object]]] = field(default_factory=dict)
    probe_calls: list[tuple[str, str]] = field(default_factory=list)

    def available_providers(self) -> list[dict[str, object]]:
        return [dict(item) for item in self.providers]

    def probe_provider(
        self,
        *,
        provider_name: str | None = None,
        model: str | None = None,
        writeback_availability: bool = True,
    ) -> dict[str, object]:
        assert writeback_availability is True
        key = (str(provider_name or ""), str(model or ""))
        self.probe_calls.append(key)
        queue = self.probe_results.get(key) or []
        if queue:
            return dict(queue.pop(0))
        return {"probe_status": "available", "probe_failure_code": ""}


@dataclass
class _RuntimeStub:
    agent: _AgentStub
    provider_availability_registry: AvailabilityRegistry = field(default_factory=AvailabilityRegistry)

    @staticmethod
    def _runtime_now_iso() -> str:
        return "2026-04-17T00:00:00+00:00"


def _provider_item(
    name: str,
    model: str,
    *,
    auth_ready: bool = True,
    base_eligible: bool = True,
    availability_status: str = "unknown",
) -> dict[str, object]:
    return {
        "provider_name": name,
        "config_provider_name": name,
        "provider_default_model_id": model,
        "default_model": model,
        "provider_auth_ready": auth_ready,
        "provider_base_eligible": base_eligible,
        "availability_status": availability_status,
    }


def test_schedule_startup_warmup_probes_auth_ready_base_eligible_targets_sync() -> None:
    runtime = _RuntimeStub(
        agent=_AgentStub(
            providers=[
                _provider_item("openai", "gpt-5.4"),
                _provider_item("anthropic", "claude-opus-4.1"),
                _provider_item("glm", "glm-5", auth_ready=False),
            ]
        )
    )
    controller = build_refresh_controller()
    attach_refresh_controller(runtime, controller)
    attach_refresh_controller(runtime.agent, controller)

    result = schedule_startup_warmup(runtime, background=False)

    assert result["scheduled"] is True
    assert result["target_count"] == 2
    assert result["started_count"] == 2
    assert runtime.agent.probe_calls == [
        ("openai", "gpt-5.4"),
        ("anthropic", "claude-opus-4.1"),
    ]
    assert refresh_controller_surface_fields(runtime)["provider_probe_in_flight_count"] == 0
    assert refresh_controller_surface_fields(runtime)["provider_probe_target_count"] == 2


def test_schedule_stale_on_use_refresh_only_probes_stale_targets() -> None:
    runtime = _RuntimeStub(
        agent=_AgentStub(
            providers=[
                _provider_item("openai", "gpt-5.4", availability_status="available"),
                _provider_item("anthropic", "claude-opus-4.1", availability_status="available"),
                _provider_item("glm", "glm-5", availability_status="unknown"),
            ]
        )
    )
    controller = build_refresh_controller()
    attach_refresh_controller(runtime, controller)
    attach_refresh_controller(runtime.agent, controller)
    runtime.provider_availability_registry.mark_success(
        provider_name="openai",
        model="gpt-5.4",
        checked_at=datetime.now(timezone.utc),
    )
    runtime.provider_availability_registry.mark_success(
        provider_name="anthropic",
        model="claude-opus-4.1",
        checked_at=datetime.now(timezone.utc) - timedelta(hours=6),
    )

    result = schedule_stale_on_use_refresh(runtime, reason="prompt_use", background=False)

    assert result["scheduled"] is True
    assert result["target_count"] == 2
    assert runtime.agent.probe_calls == [
        ("anthropic", "claude-opus-4.1"),
        ("glm", "glm-5"),
    ]


def test_schedule_stale_on_use_refresh_uses_configured_stale_after_seconds() -> None:
    runtime = _RuntimeStub(
        agent=_AgentStub(
            providers=[
                _provider_item("openai", "gpt-5.4", availability_status="available"),
                _provider_item("anthropic", "claude-opus-4.1", availability_status="available"),
            ]
        )
    )
    controller = build_refresh_controller()
    attach_refresh_controller(runtime, controller)
    attach_refresh_controller(runtime.agent, controller)
    runtime.provider_availability_registry.mark_success(
        provider_name="openai",
        model="gpt-5.4",
        checked_at=datetime.now(timezone.utc) - timedelta(seconds=50),
    )
    runtime.provider_availability_registry.mark_success(
        provider_name="anthropic",
        model="claude-opus-4.1",
        checked_at=datetime.now(timezone.utc) - timedelta(seconds=20),
    )

    with patch(
        "cli.agent_cli.runtime_services.provider_availability_refresh_runtime.provider_availability_feature_settings",
        return_value={"stale_after_seconds": 45, "config_source": "workspace_config"},
    ):
        result = schedule_stale_on_use_refresh(runtime, reason="prompt_use", background=False)
        surface = refresh_controller_surface_fields(runtime)

    assert result["scheduled"] is True
    assert result["target_count"] == 1
    assert runtime.agent.probe_calls == [("openai", "gpt-5.4")]
    assert surface["provider_probe_stale_after_seconds"] == 45


def test_schedule_stale_on_use_refresh_preserves_ttl_across_registry_reload(tmp_path) -> None:
    checked_at = datetime(2026, 4, 18, 0, 0, 0, tzinfo=timezone.utc)
    path = tmp_path / "provider_availability_state.json"
    persisted = AvailabilityRegistry()
    persisted.mark_success(
        provider_name="openai",
        model="gpt-5.4",
        checked_at=checked_at,
        latency_ms=111,
    )
    persist_availability_registry(persisted, path=path)

    runtime = _RuntimeStub(
        agent=_AgentStub(
            providers=[_provider_item("openai", "gpt-5.4", availability_status="available")]
        ),
        provider_availability_registry=load_persisted_availability_registry(path=path),
    )
    controller = build_refresh_controller()
    attach_refresh_controller(runtime, controller)
    attach_refresh_controller(runtime.agent, controller)

    with patch(
        "cli.agent_cli.providers.availability_registry.utc_now",
        return_value=checked_at + timedelta(hours=4, minutes=59),
    ):
        fresh_result = schedule_stale_on_use_refresh(runtime, reason="prompt_use", background=False)

    with patch(
        "cli.agent_cli.providers.availability_registry.utc_now",
        return_value=checked_at + timedelta(hours=5, minutes=1),
    ):
        stale_result = schedule_stale_on_use_refresh(runtime, reason="prompt_use", background=False)

    assert fresh_result["scheduled"] is False
    assert fresh_result["target_count"] == 0
    assert stale_result["scheduled"] is True
    assert stale_result["target_count"] == 1
    assert runtime.agent.probe_calls == [("openai", "gpt-5.4")]


def test_schedule_refresh_retries_soft_failures_once() -> None:
    runtime = _RuntimeStub(
        agent=_AgentStub(
            providers=[_provider_item("anthropic", "claude-opus-4.1")],
            probe_results={
                ("anthropic", "claude-opus-4.1"): [
                    {"probe_status": "unavailable", "probe_failure_code": "timeout"},
                    {"probe_status": "available", "probe_failure_code": ""},
                ]
            },
        )
    )
    controller = build_refresh_controller()
    attach_refresh_controller(runtime, controller)
    attach_refresh_controller(runtime.agent, controller)

    schedule_startup_warmup(runtime, background=False)

    assert runtime.agent.probe_calls == [
        ("anthropic", "claude-opus-4.1"),
        ("anthropic", "claude-opus-4.1"),
    ]


def test_schedule_refresh_does_not_retry_hard_failures() -> None:
    runtime = _RuntimeStub(
        agent=_AgentStub(
            providers=[_provider_item("openai", "gpt-5.4")],
            probe_results={
                ("openai", "gpt-5.4"): [
                    {"probe_status": "unavailable", "probe_failure_code": "invalid_api_key"},
                ]
            },
        )
    )
    controller = build_refresh_controller()
    attach_refresh_controller(runtime, controller)
    attach_refresh_controller(runtime.agent, controller)

    schedule_startup_warmup(runtime, background=False)

    assert runtime.agent.probe_calls == [("openai", "gpt-5.4")]


def test_maybe_reload_planner_for_provider_gate_update_reloads_managed_planner() -> None:
    reload_calls: list[str] = []

    class _Planner:
        config = type("Config", (), {"raw_provider": {"expert_review_gate_snapshot": {"expert_review_available": False}}})()

    class _ReloadAgent:
        _planner = _Planner()
        _planner_managed = True

        @staticmethod
        def provider_review_gate() -> dict[str, object]:
            return {"expert_review_available": True}

        @staticmethod
        def _reload_planner() -> None:
            reload_calls.append("reload")

    agent = _ReloadAgent()

    assert maybe_reload_planner_for_provider_gate_update(agent) is True
    assert reload_calls == ["reload"]


def test_maybe_reload_planner_for_provider_gate_update_skips_unmanaged_override() -> None:
    reload_calls: list[str] = []

    class _Planner:
        config = type("Config", (), {"raw_provider": {"expert_review_gate_snapshot": {"expert_review_available": False}}})()

    class _ReloadAgent:
        _planner = _Planner()
        _planner_managed = False

        @staticmethod
        def provider_review_gate() -> dict[str, object]:
            return {"expert_review_available": True}

        @staticmethod
        def _reload_planner() -> None:
            reload_calls.append("reload")

    agent = _ReloadAgent()

    assert maybe_reload_planner_for_provider_gate_update(agent) is False
    assert reload_calls == []
