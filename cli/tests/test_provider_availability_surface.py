from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.agent_provider_runtime import provider_status
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.providers.availability_registry import AvailabilityRegistry
from cli.agent_cli.providers.planner_status import PlannerStatusMixin


@dataclass
class _ProviderPaths:
    config_path: Path
    auth_path: Path


class _PlannerStub:
    def public_summary(self):
        return {
            "configured": True,
            "provider_name": "openai",
            "model": "gpt-5.4",
            "model_key": "gpt_54",
            "planner_kind": "openai_responses",
            "wire_api": "responses",
            "base_url": "https://example.invalid",
            "reasoning_effort": "high",
            "source": "test",
            "config_path": "/tmp/config.toml",
            "auth_path": "/tmp/auth.json",
        }


class _AgentStub:
    def __init__(self, *, planner_enabled: bool) -> None:
        self._provider_paths = _ProviderPaths(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )
        self._planner = _PlannerStub() if planner_enabled else None
        self._planner_runtime_error = None
        self._planner_error = ""
        self._session_provider_env_overrides = {
            "AGENT_CLI_PROVIDER": "openai",
            "AGENT_CLI_MODEL": "gpt_54",
        }
        self._session_route_overrides = {}
        self._session_delegation_overrides = {}
        self.host_platform = current_host_platform()
        self._provider_availability_registry = AvailabilityRegistry()

    def _planner_runtime_error_diagnostic_lines(self):
        return []


def test_provider_status_ready_includes_availability_surface_fields() -> None:
    agent = _AgentStub(planner_enabled=True)
    checked_at = datetime.now(timezone.utc)
    agent._provider_availability_registry.mark_failure(
        provider_name="openai",
        model="gpt-5.4",
        failure_code="rate_limited",
        failure_reason="429",
        checked_at=checked_at,
        latency_ms=420,
    )

    status = provider_status(agent)

    assert status["availability_status"] == "unavailable"
    assert status["availability_known"] is True
    assert status["availability_failure_code"] == "rate_limited"
    assert status["availability_failure_reason"] == "429"
    assert status["availability_last_latency_ms"] == 420
    assert status["availability_avg_latency_ms"] == 420
    assert status["availability_failure_count"] == 1
    assert status["availability_consecutive_failures"] == 1
    assert status["availability_snapshot_freshness"] == "fresh"
    assert status["availability_stale"] is False
    assert status["availability_stale_after_seconds"] == 18000
    assert status["availability"]["status"] == "unavailable"
    assert status["availability"]["last_latency_ms"] == 420
    assert status["availability"]["snapshot_freshness"] == "fresh"
    assert "availability_checked_at" in status


def test_provider_status_pending_path_includes_availability_surface_fields() -> None:
    agent = _AgentStub(planner_enabled=False)
    checked_at = datetime.now(timezone.utc)
    agent._provider_availability_registry.mark_success(
        provider_name="openai",
        model="gpt_54",
        checked_at=checked_at,
        latency_ms=210,
    )

    status = provider_status(agent)

    assert status["availability_status"] == "available"
    assert status["availability_known"] is True
    assert status["availability_failure_code"] == ""
    assert status["availability_failure_reason"] == ""
    assert status["availability_success_count"] == 1
    assert status["availability_last_latency_ms"] == 210
    assert status["availability_avg_latency_ms"] == 210
    assert status["availability_snapshot_freshness"] == "fresh"
    assert status["availability"]["status"] == "available"


def test_provider_status_uses_configured_stale_after_seconds() -> None:
    agent = _AgentStub(planner_enabled=True)
    agent._provider_availability_registry.mark_success(
        provider_name="openai",
        model="gpt-5.4",
        checked_at=datetime.now(timezone.utc) - timedelta(seconds=50),
        latency_ms=180,
    )

    with patch(
        "cli.agent_cli.agent_provider_status_runtime.availability_feature_config_runtime.provider_availability_feature_settings",
        return_value={"stale_after_seconds": 45, "config_source": "workspace_config"},
    ):
        status = provider_status(agent)

    assert status["availability_stale"] is True
    assert status["availability_snapshot_freshness"] == "stale"
    assert status["availability_stale_after_seconds"] == 45


class _RouteResolutionStub:
    def __init__(self, provider_name: str, model: str, *, source: str = "route") -> None:
        self._provider_name = provider_name
        self._model = model
        self.source = source
        self.config = SimpleNamespace(
            provider_name=provider_name,
            model=model,
            model_key=model.replace("-", "_"),
            base_url="https://example.invalid" if provider_name == "openai" else "https://glm.invalid",
        )

    def public_summary(self):
        return {
            "provider_name": self._provider_name,
            "model": self._model,
            "source": self.source,
        }


class _PlannerConfigStub:
    provider_name = "openai"
    model = "gpt-5.4"
    model_key = "gpt_54"
    base_url = "https://example.invalid"

    def public_summary(self):
        return {
            "configured": True,
            "provider_name": "openai",
            "model": "gpt-5.4",
        }


class _PlannerStatusStub(PlannerStatusMixin):
    def __init__(self) -> None:
        self.config = _PlannerConfigStub()
        self.cwd = "."
        self.plugin_manager_factory = None
        self._route_resolution_cache = {}
        self._delegation_resolution_cache = {}
        self._provider_availability_registry = AvailabilityRegistry()
        self._provider_availability_registry.mark_success(provider_name="openai", model="gpt-5.4", latency_ms=180)
        self._provider_availability_registry.mark_failure(
            provider_name="glm",
            model="glm-5",
            failure_code="timeout",
            failure_reason="request timeout",
            latency_ms=950,
        )

    def _route_status_specs(self):
        return {"tool_followup": {}}

    def _delegation_status_specs(self):
        return {"subagent": {}}

    def _resolve_route(self, *args, **kwargs):
        return _RouteResolutionStub("glm", "glm-5")

    def _resolve_delegation(self, *args, **kwargs):
        return _RouteResolutionStub("openai", "gpt-5.4")


def test_planner_public_summary_includes_availability_surface_for_main_route_and_delegation() -> None:
    planner = _PlannerStatusStub()

    summary = planner.public_summary()

    assert summary["availability_status"] == "available"
    assert summary["availability_known"] is True
    assert summary["availability_last_latency_ms"] == 180
    assert summary["routes"]["tool_followup"]["availability_status"] == "unavailable"
    assert summary["routes"]["tool_followup"]["availability_failure_code"] == "timeout"
    assert summary["routes"]["tool_followup"]["availability_last_latency_ms"] == 950
    assert summary["delegation"]["subagent"]["availability_status"] == "available"


def test_planner_public_summary_marks_unknown_when_route_selection_missing_provider_or_model() -> None:
    class _UnknownRoutePlanner(_PlannerStatusStub):
        def _resolve_route(self, *args, **kwargs):
            return _RouteResolutionStub("", "")

    planner = _UnknownRoutePlanner()
    summary = planner.public_summary()

    assert summary["routes"]["tool_followup"]["availability_status"] == "unknown"
    assert summary["routes"]["tool_followup"]["availability_known"] is False


def test_planner_public_summary_marks_effective_main_fallback_when_route_is_known_unavailable() -> None:
    planner = _PlannerStatusStub()

    summary = planner.public_summary()
    route_summary = summary["routes"]["tool_followup"]

    assert route_summary["availability_status"] == "unavailable"
    assert route_summary["availability_fallback_to_main"] is True
    assert route_summary["effective_provider_name"] == "openai"
    assert route_summary["effective_model"] == "gpt-5.4"
    assert route_summary["effective_source"].endswith("availability_fallback_main")


def test_workspace_prompt_addendum_includes_agent_cli_home_skills_without_plugin_manager() -> None:
    planner = _PlannerStatusStub()
    captured: dict[str, object] = {}

    def _fake_render_workspace_prompt_addendum(cwd, *, extra_skill_roots=None):
        captured["cwd"] = cwd
        captured["extra_skill_roots"] = list(extra_skill_roots or [])
        return "workspace addendum"

    with patch(
        "cli.agent_cli.providers.planner_status.agent_cli_home_skill_roots",
        return_value=["/tmp/agent_cli_home/skills"],
    ), patch(
        "cli.agent_cli.providers.planner_status.render_workspace_prompt_addendum",
        side_effect=_fake_render_workspace_prompt_addendum,
    ):
        rendered = planner.workspace_prompt_addendum()

    assert rendered == "workspace addendum"
    assert captured["cwd"] == "."
    assert captured["extra_skill_roots"] == ["/tmp/agent_cli_home/skills"]
