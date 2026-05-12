from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cli.agent_cli import agent_provider_runtime
from cli.agent_cli.models import AgentIntent
from cli.agent_cli.providers.availability_registry import AvailabilityRegistry
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.runtime_core.provider_commands import handle_provider_command


class _AvailabilityRegistry:
    def __init__(self) -> None:
        self.success_calls: list[dict] = []
        self.failure_calls: list[dict] = []

    def mark_success(self, **kwargs):
        self.success_calls.append(dict(kwargs))

    def mark_failure(self, **kwargs):
        self.failure_calls.append(dict(kwargs))


def test_probe_provider_uses_noop_callback_and_marks_success() -> None:
    registry = _AvailabilityRegistry()
    recorded: dict[str, object] = {}
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="sk-test",
        provider_name="openai",
        planner_kind="openai_responses",
    )
    agent = SimpleNamespace(
        _planner=SimpleNamespace(public_summary=lambda: {"provider_name": "openai", "model": "gpt-5.4"}),
        _session_provider_env_overrides={},
        cwd=Path("/tmp"),
        host_platform=SimpleNamespace(),
        _plugin_manager_factory=None,
        _provider_availability_registry=registry,
    )

    def _load_provider_config(*, cwd=None, env_overrides=None):
        recorded["cwd"] = cwd
        recorded["env_overrides"] = dict(env_overrides or {})
        return config

    class _Planner:
        @staticmethod
        def public_summary():
            return config.public_summary()

        def plan(self, user_text, history, **kwargs):
            recorded["user_text"] = user_text
            recorded["history"] = list(history)
            recorded["plan_kwargs"] = dict(kwargs)
            return AgentIntent(assistant_text="OK")

    result = agent_provider_runtime.probe_provider(
        agent,
        load_provider_config_fn=_load_provider_config,
        build_planner_fn=lambda *args, **kwargs: _Planner(),
    )

    assert result["probe_status"] == "available"
    assert result["probe_transport"] == "real_provider_send"
    assert result["probe_stream_mode"] == "noop_turn_event_callback"
    assert recorded["user_text"] == agent_provider_runtime._PROBE_PROMPT
    assert recorded["history"] == []
    plan_kwargs = dict(recorded["plan_kwargs"])
    assert callable(plan_kwargs["turn_event_callback"])
    plan_kwargs["turn_event_callback"]({"type": "item.started"})
    assert registry.success_calls
    assert not registry.failure_calls


def test_probe_provider_uses_current_selection_and_marks_failure() -> None:
    registry = _AvailabilityRegistry()
    recorded: dict[str, object] = {}
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="sk-test",
        provider_name="openai",
        planner_kind="openai_responses",
    )
    agent = SimpleNamespace(
        _planner=SimpleNamespace(public_summary=lambda: {"provider_name": "openai", "model": "gpt-5.4"}),
        _session_provider_env_overrides={},
        cwd=Path("/tmp"),
        host_platform=SimpleNamespace(),
        _plugin_manager_factory=None,
        _provider_availability_registry=registry,
    )

    def _load_provider_config(*, cwd=None, env_overrides=None):
        recorded["cwd"] = cwd
        recorded["env_overrides"] = dict(env_overrides or {})
        return config

    class _Planner:
        @staticmethod
        def public_summary():
            return config.public_summary()

        def plan(self, user_text, history, **kwargs):
            recorded["user_text"] = user_text
            recorded["history"] = list(history)
            recorded["plan_kwargs"] = dict(kwargs)
            raise RuntimeError("boom")

    result = agent_provider_runtime.probe_provider(
        agent,
        load_provider_config_fn=_load_provider_config,
        build_planner_fn=lambda *args, **kwargs: _Planner(),
    )

    assert result["probe_status"] == "unavailable"
    assert result["probe_failure_code"] == "runtimeerror"
    assert "RuntimeError: boom" in result["probe_failure_reason"]
    assert dict(recorded["env_overrides"])["AGENT_CLI_PROVIDER"] == "openai"
    assert dict(recorded["env_overrides"])["AGENT_CLI_MODEL"] == "gpt-5.4"
    assert recorded["history"] == []
    assert callable(dict(recorded["plan_kwargs"])["turn_event_callback"])
    assert registry.failure_calls
    assert not registry.success_calls


def test_probe_provider_persists_availability_writeback_to_state_file(tmp_path) -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="sk-test",
        provider_name="openai",
        planner_kind="openai_responses",
    )
    registry = AvailabilityRegistry()
    state_path = tmp_path / "provider_availability_state.json"
    agent = SimpleNamespace(
        _planner=SimpleNamespace(public_summary=lambda: {"provider_name": "openai", "model": "gpt-5.4"}),
        _session_provider_env_overrides={},
        cwd=Path("/tmp"),
        host_platform=SimpleNamespace(),
        _plugin_manager_factory=None,
        _provider_availability_registry=registry,
        _provider_availability_state_path=state_path,
    )

    class _Planner:
        @staticmethod
        def public_summary():
            return config.public_summary()

        def plan(self, user_text, history, **kwargs):
            del user_text, history, kwargs
            return AgentIntent(assistant_text="OK")

    result = agent_provider_runtime.probe_provider(
        agent,
        load_provider_config_fn=lambda **kwargs: config,
        build_planner_fn=lambda *args, **kwargs: _Planner(),
    )

    assert result["probe_status"] == "available"
    restored = AvailabilityRegistry.from_payload(__import__("json").loads(state_path.read_text(encoding="utf-8")))
    record = restored.get("openai", "gpt-5.4")
    assert record is not None
    assert record.status.value == "available"


def test_provider_command_probe_renders_probe_fields() -> None:
    class _Agent:
        def provider_status(self):
            return {
                "provider_public_name": "openai",
                "provider_model": "gpt-5.4",
                "provider_ready": "true",
                "provider_source": "project_local",
            }

        def probe_provider(self, *, writeback_availability=True):
            assert writeback_availability is True
            return {
                "probe_status": "available",
                "probe_transport": "real_provider_send",
                "probe_stream_mode": "noop_turn_event_callback",
                "probe_latency_ms": 123,
                "probe_response_preview": "OK",
            }

    runtime = SimpleNamespace(agent=_Agent())
    text, events = handle_provider_command(
        runtime,
        name="provider",
        arg_text="--probe",
        switch_disabled_result=lambda exc: (str(exc), []),
    ) or ("", [])

    assert events == []
    assert "probe_status=available" in text
    assert "probe_transport=real_provider_send" in text
    assert "probe_stream_mode=noop_turn_event_callback" in text
    assert "probe_latency_ms=123" in text
    assert "probe_response_preview=OK" in text


def test_parse_args_recognizes_probe_flag() -> None:
    positionals, options = parse_args("--probe")

    assert positionals == []
    assert options == {"probe": True}


def test_providers_command_probe_renders_live_probe_summary() -> None:
    class _Agent:
        @staticmethod
        def probe_providers(*, writeback_availability=True):
            assert writeback_availability is True
            return [
                {
                    "provider_name": "openai",
                    "default_model": "gpt_54",
                    "probe_status": "available",
                    "probe_latency_ms": 111,
                    "probe_failure_code": "",
                },
                {
                    "provider_name": "anthropic",
                    "default_model": "claude_opus",
                    "probe_status": "unavailable",
                    "probe_latency_ms": 0,
                    "probe_failure_code": "timeout",
                },
            ]

    runtime = SimpleNamespace(
        agent=_Agent(),
        _parse_args=lambda arg_text: ([], {"probe": "--probe" in str(arg_text or "")}),
    )
    text, events = handle_provider_command(
        runtime,
        name="providers",
        arg_text="--probe",
        switch_disabled_result=lambda exc: (str(exc), []),
    ) or ("", [])

    assert events == []
    assert "providers=2" in text
    assert "- openai: default_model=gpt_54, probe=available, latency_ms=111" in text
    assert "- anthropic: default_model=claude_opus, probe=unavailable, failure_code=timeout" in text
