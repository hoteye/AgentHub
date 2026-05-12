from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.providers.availability_registry import AvailabilityRegistry
from cli.agent_cli.runtime import AgentCliRuntime


def test_runtime_init_loads_persisted_registry_and_skips_startup_warmup() -> None:
    loaded_registry = AvailabilityRegistry()
    loaded_registry.mark_success(provider_name="openai", model="gpt-5.4", latency_ms=123)
    agent = SimpleNamespace()
    state_path = Path("/tmp/provider_availability_state.json")

    with patch(
        "cli.agent_cli.runtime.provider_availability_persistence_runtime_service.provider_availability_state_path",
        return_value=state_path,
    ), patch(
        "cli.agent_cli.runtime.provider_availability_persistence_runtime_service.load_persisted_availability_registry",
        return_value=loaded_registry,
    ), patch(
        "cli.agent_cli.runtime.runtime_runtime.bootstrap_runtime_environment",
        return_value=Path("/tmp"),
    ), patch(
        "cli.agent_cli.runtime.runtime_runtime.runtime_init_state",
        return_value={},
    ), patch.object(
        AgentCliRuntime,
        "_build_mcp_runtime",
        return_value=None,
    ), patch.object(
        AgentCliRuntime,
        "_sync_request_user_input_mode_from_provider",
        return_value=False,
    ), patch(
        "cli.agent_cli.runtime.provider_availability_refresh_runtime_service.schedule_startup_warmup",
    ) as startup_warmup:
        runtime = AgentCliRuntime(agent=agent)

    assert runtime.availability_registry is loaded_registry
    assert runtime.provider_availability_state_path == state_path
    assert getattr(agent, "_provider_availability_registry", None) is loaded_registry
    assert getattr(agent, "_provider_availability_state_path", None) == state_path
    startup_warmup.assert_not_called()
