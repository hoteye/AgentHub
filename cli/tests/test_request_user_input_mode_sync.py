from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli import runtime as runtime_module


def test_runtime_init_syncs_request_user_input_default_mode() -> None:
    with (
        patch.object(runtime_module.runtime_runtime, "bootstrap_runtime_environment", return_value=Path.cwd()),
        patch.object(
            runtime_module.runtime_runtime,
            "runtime_init_state",
            return_value={},
        ),
        patch.object(
            runtime_module.AgentCliRuntime,
            "_sync_request_user_input_mode_from_provider",
            return_value=True,
        ) as sync_mock,
    ):
        runtime_module.AgentCliRuntime(agent=SimpleNamespace())
    sync_mock.assert_called_once()


def test_configure_model_selection_syncs_request_user_input_default_mode() -> None:
    runtime_stub = SimpleNamespace(
        agent=SimpleNamespace(),
        _sync_request_user_input_mode_from_provider=lambda: None,
    )
    with (
        patch.object(
            runtime_module.runtime_runtime,
            "configure_model_selection",
            return_value={"provider_ready": "true", "provider_model": "gpt-5.4"},
        ) as configure_mock,
        patch.object(runtime_stub, "_sync_request_user_input_mode_from_provider") as sync_mock,
    ):
        status = runtime_module.AgentCliRuntime.configure_model_selection(
            runtime_stub,
            model="gpt-5.4",
        )

    assert status["provider_ready"] == "true"
    configure_mock.assert_called_once()
    sync_mock.assert_called_once()


def test_restore_provider_state_syncs_request_user_input_default_mode() -> None:
    runtime_stub = SimpleNamespace(
        _sync_request_user_input_mode_from_provider=lambda: None,
    )
    state = {"provider_name": "reference", "model": "gpt-5.4"}
    with (
        patch.object(runtime_module, "_ORIGINAL_RESTORE_PROVIDER_STATE") as restore_mock,
        patch.object(runtime_stub, "_sync_request_user_input_mode_from_provider") as sync_mock,
    ):
        runtime_module.AgentCliRuntime._restore_provider_state(runtime_stub, state)

    restore_mock.assert_called_once_with(runtime_stub, state)
    sync_mock.assert_called_once()
