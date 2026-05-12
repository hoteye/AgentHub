from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.models import AgentIntent
from cli.agent_cli.providers.availability_registry import AvailabilityRegistry


class _SuccessfulPlanner:
    @staticmethod
    def public_summary():
        return {
            "provider_name": "openai",
            "model": "gpt-5.4",
            "model_key": "gpt_54",
        }

    def plan(self, text, history, **kwargs):
        del text, history, kwargs
        return AgentIntent(
            assistant_text="ok",
            timings={
                "total_ms": 321,
                "initial_model_ms": 300,
            },
        )


class _FailurePlanner:
    @staticmethod
    def public_summary():
        return {
            "provider_name": "openai",
            "model": "gpt-5.4",
            "model_key": "gpt_54",
        }

    def plan(self, text, history, **kwargs):
        del text, history, kwargs
        exc = RuntimeError("Error code: 503 - provider unavailable")
        setattr(
            exc,
            "agenthub_provider_diagnostics",
            {
                "failure_code": "proxy_unavailable",
                "failure_reason": "All accounts are currently unavailable.",
                "retry_after_seconds": 12,
                "planner_elapsed_ms": 480,
            },
        )
        raise exc


class _FallbackPlanner:
    @staticmethod
    def public_summary():
        return {}

    def plan(self, text, history, **kwargs):
        del text, history, kwargs
        exc = RuntimeError("quota exceeded")
        setattr(
            exc,
            "agenthub_provider_diagnostics",
            {
                "provider_name": "glm",
                "model": "glm-5",
                "error_code": "quota",
                "message": "quota exceeded",
                "retry_after_ms": 2500,
                "request_elapsed_ms": 2100,
            },
        )
        raise exc


class _TimeoutPlanner:
    @staticmethod
    def public_summary():
        return {
            "provider_name": "openai",
            "provider_model": "gpt-5.4",
            "model_key": "gpt_54",
        }

    def plan(self, text, history, **kwargs):
        del text, history, kwargs
        raise TimeoutError("request timeout")


def _agent_with_planner(planner):
    fake_paths = SimpleNamespace(
        config_path=Path("/tmp/config.toml"),
        auth_path=Path("/tmp/auth.json"),
    )
    with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
        with patch("cli.agent_cli.agent.load_provider_config", return_value=object()):
            with patch("cli.agent_cli.agent.build_planner", return_value=planner):
                return RuleBasedAgent()


def test_plan_success_marks_availability_success() -> None:
    agent = _agent_with_planner(_SuccessfulPlanner())
    registry = AvailabilityRegistry()
    agent.set_availability_registry(registry)

    agent.plan("hello", history=[])

    record = registry.get("openai", "gpt-5.4")
    assert record is not None
    assert record.status.value == "available"
    assert record.failure_code == ""
    assert record.failure_reason == ""
    assert record.success_count == 1
    assert record.failure_count == 0
    assert record.last_latency_ms == 321
    assert record.avg_latency_ms == 321


def test_plan_failure_marks_availability_failure_from_diagnostics() -> None:
    agent = _agent_with_planner(_FailurePlanner())
    registry = AvailabilityRegistry()
    agent.set_availability_registry(registry)

    agent.plan("hello", history=[])

    record = registry.get("openai", "gpt-5.4")
    assert record is not None
    assert record.status.value == "unavailable"
    assert record.failure_code == "proxy_unavailable"
    assert record.failure_reason == "All accounts are currently unavailable."
    assert record.retry_after is not None
    assert int(record.retry_after.total_seconds()) == 12
    assert record.failure_count == 1
    assert record.consecutive_failures == 1
    assert record.last_latency_ms == 480
    assert record.avg_latency_ms == 480


def test_plan_failure_can_fallback_to_diagnostics_provider_model() -> None:
    agent = _agent_with_planner(_FallbackPlanner())
    registry = AvailabilityRegistry()
    agent.set_availability_registry(registry)

    agent.plan("hello", history=[])

    record = registry.get("glm", "glm-5")
    assert record is not None
    assert record.status.value == "unavailable"
    assert record.failure_code == "quota"
    assert record.failure_reason == "quota exceeded"
    assert record.retry_after is not None
    assert int(record.retry_after.total_seconds()) == 2
    assert record.last_latency_ms == 2100


def test_plan_failure_without_diagnostics_marks_unavailable_with_timeout_code() -> None:
    agent = _agent_with_planner(_TimeoutPlanner())
    registry = AvailabilityRegistry()
    agent.set_availability_registry(registry)

    agent.plan("hello", history=[])

    record = registry.get("openai", "gpt_54")
    assert record is not None
    assert record.status.value == "unavailable"
    assert record.failure_code == "timeout"
