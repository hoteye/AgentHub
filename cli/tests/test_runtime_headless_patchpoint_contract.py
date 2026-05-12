from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from cli.agent_cli import headless
from cli.agent_cli.models import AgentIntent, PromptResponse
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy


def test_runtime_module_exposes_patchable_build_symbols() -> None:
    import cli.agent_cli.runtime as runtime_module

    assert callable(getattr(runtime_module, "build_planner", None))
    assert callable(getattr(runtime_module, "build_background_task_adapter", None))


def test_runtime_build_planner_patchpoint_is_used_by_delegated_planner_path() -> None:
    class _DelegateAgent:
        def __init__(self) -> None:
            from cli.agent_cli.host_platform import current_host_platform

            self.host_platform = current_host_platform()

        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_ready": "true",
                "provider_name": "test",
                "provider_model": "test-model",
            }

        @staticmethod
        def resolve_delegate_execution(
            role_name: str,
            *,
            model: str | None = None,
            provider: str | None = None,
            reasoning_effort: str | None = None,
            timeout: int | None = None,
        ) -> Any:
            assert role_name == "subagent"
            assert model is None
            assert provider is None
            assert reasoning_effort is None
            assert timeout is None
            return SimpleNamespace(
                config=ProviderConfig(
                    model="glm-5",
                    api_key="sk-test",
                    provider_name="glm",
                    model_key="glm_5",
                    planner_kind="openai_chat",
                    wire_api="openai_chat",
                    base_url="https://glm.example/v1",
                    raw_model={},
                ),
                timeout=17,
                source="delegation",
            )

    class _DelegatedPlanner:
        @staticmethod
        def plan(
            user_text: str,
            history: list[Any],
            *,
            tool_executor: Any = None,
            attachments: list[Any] | None = None,
            input_items: list[dict[str, Any]] | None = None,
            prompt_cache_key: str | None = None,
        ) -> AgentIntent:
            assert user_text == "patchpoint delegation"
            assert history == []
            assert tool_executor is not None
            assert isinstance(input_items, list)
            assert prompt_cache_key
            return AgentIntent(assistant_text="delegated planner patched")

    runtime = AgentCliRuntime(
        agent=_DelegateAgent(),
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    with patch("cli.agent_cli.runtime.build_planner", return_value=_DelegatedPlanner()) as build_planner:
        result = runtime.spawn_agent_result(task="patchpoint delegation", role="subagent")

    build_planner.assert_called_once()
    delegated_config = build_planner.call_args.args[0]
    assert delegated_config.model == "glm-5"
    assert delegated_config.raw_model.get("model_timeout") == 17
    assert result.assistant_text == "delegated planner patched"


def test_headless_build_persistent_runtime_patchpoint_is_used_by_build_headless_runtime() -> None:
    class _StubRuntime:
        def __init__(self) -> None:
            self.thread_store = None
            self.cwd_set: Any = None

        def set_cwd(self, cwd: Any) -> None:
            self.cwd_set = cwd

    stub = _StubRuntime()
    with patch("cli.agent_cli.headless.build_persistent_runtime", return_value=stub) as build_runtime:
        runtime = headless.build_headless_runtime(
            runtime_policy=RuntimePolicy.normalized(),
            persistent=True,
            resume_thread_id=None,
        )

    assert runtime is stub
    _, kwargs = build_runtime.call_args
    assert kwargs["resume_active_thread"] is False
    assert kwargs["start_thread_if_unavailable"] is False
    assert stub.cwd_set is not None


def test_headless_build_runtime_new_session_uses_startup_cwd() -> None:
    class _StubRuntime:
        def __init__(self) -> None:
            self.thread_store = None
            self.cwd_set: Any = None

        def set_cwd(self, cwd: Any) -> None:
            self.cwd_set = cwd

    stub = _StubRuntime()
    with patch.dict("os.environ", {"AGENTHUB_STARTUP_CWD": "/tmp/gemini-cli"}, clear=False):
        with patch("cli.agent_cli.headless.build_persistent_runtime", return_value=stub):
            runtime = headless.build_headless_runtime(
                runtime_policy=RuntimePolicy.normalized(),
                persistent=True,
                resume_thread_id=None,
            )

    assert runtime is stub
    assert str(stub.cwd_set) == str(Path("/tmp/gemini-cli").resolve())


def test_headless_build_runtime_resume_keeps_existing_thread_cwd() -> None:
    class _StubRuntime:
        def __init__(self) -> None:
            self.thread_store = None
            self.cwd_set: Any = None

        def set_cwd(self, cwd: Any) -> None:
            self.cwd_set = cwd

    stub = _StubRuntime()
    with patch.dict("os.environ", {"AGENTHUB_STARTUP_CWD": "/tmp/gemini-cli"}, clear=False):
        with patch("cli.agent_cli.headless.build_persistent_runtime", return_value=stub):
            runtime = headless.build_headless_runtime(
                runtime_policy=RuntimePolicy.normalized(),
                persistent=True,
                resume_thread_id="thread_123",
            )

    assert runtime is stub
    assert stub.cwd_set is None


def test_headless_jsonl_stream_keeps_turn_completed_as_terminal_event() -> None:
    class _Runner:
        def __init__(self) -> None:
            self.thread_id = "thread_patchpoint"
            self.turn_event_callback = None
            self.activity_callback = None

        def handle_prompt(self, prompt: str) -> PromptResponse:
            assert prompt == "stream patchpoint"
            if callable(self.turn_event_callback):
                # A regression once leaked this event into the tail position.
                self.turn_event_callback({"type": "thread.completed", "thread_id": self.thread_id})
            return PromptResponse(
                user_text=prompt,
                assistant_text="ok",
                turn_events=[
                    {"type": "turn.started"},
                    {
                        "type": "item.completed",
                        "item": {"id": "item_1", "type": "agent_message", "text": "ok"},
                    },
                    {"type": "turn.completed"},
                ],
            )

    output = io.StringIO()
    response = headless._execute_prompt(  # noqa: SLF001 - explicit patchpoint contract check
        _Runner(),
        "stream patchpoint",
        output_stream=output,
        jsonl=True,
    )
    assert response.assistant_text == "ok"

    lines = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
    event_types = [str(item.get("type") or "") for item in lines]
    assert event_types
    assert event_types[-1] == "turn.completed"
    assert "thread.completed" in event_types
    assert event_types.index("thread.completed") < len(event_types) - 1
