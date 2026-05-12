from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    ResponseInputItem,
    ToolEvent,
    latest_open_todo_list_item,
    response_message_item,
    todo_list_turn_event_from_plan_payload,
)
from cli.agent_cli.providers import (
    openai_planner_followup_runtime,
    openai_planner_runtime_helpers_runtime,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_planner import OpenAIPlanner
from cli.agent_cli.providers.openai_planner_turn_events import (
    _rebase_item_events as planner_rebase_item_events,
)
from cli.agent_cli.providers.planner_postprocessing import structured_tool_fallback_text
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    handle_update_plan_command,
)
from cli.agent_cli.runtime_core.tool_call_context_runtime import active_provider_tool_call_id


def _simple_config() -> ProviderConfig:
    return ProviderConfig(model="gpt-5.4", api_key="sk-test")


def test_openai_planner_native_tool_prompt_includes_concise_no_heading_rule() -> None:
    planner = OpenAIPlanner(_simple_config())

    assert (
        "Do not use markdown headings, horizontal rules, or tables unless the user explicitly asks for them."
        in planner.native_tool_system_prompt
    )


class _FollowupTurnEngine:
    instances: list[_FollowupTurnEngine] = []

    def __init__(
        self,
        adapter,
        *,
        tool_executor,
        command_builder,
        followup_handler,
        **kwargs,
    ) -> None:
        self.followup_handler = followup_handler
        self.executed_events = [
            ToolEvent(
                name="list_dir",
                ok=True,
                summary="fallback list",
                payload={
                    "dir_path": ".",
                    "entries": [{"index": 1, "kind": "file", "path": "README.md"}],
                },
            ),
        ]
        self.tool_events = list(self.executed_events)
        self.__class__.instances.append(self)

    def run(self, *, user_text: str, initial_input: list[dict], **kwargs) -> AgentIntent:
        del initial_input, kwargs
        fallback_intent = self.followup_handler(user_text, list(self.executed_events))
        return AgentIntent(
            assistant_text=fallback_intent.assistant_text,
            status_hint="tool",
            tool_events=list(self.tool_events),
        )


class _ContinuationFollowupTurnEngine:
    def __init__(
        self,
        adapter,
        *,
        tool_executor,
        command_builder,
        followup_handler,
        **kwargs,
    ) -> None:
        self.followup_handler = followup_handler
        self.executed_events = [
            ToolEvent(
                name="read_file",
                ok=True,
                summary="file loaded",
                payload={"file_path": "README.md", "text": "L1: hello"},
            ),
        ]

    def run(self, *, user_text: str, initial_input: list[dict], **kwargs) -> AgentIntent:
        del initial_input, kwargs
        return self.followup_handler(
            user_text,
            list(self.executed_events),
            [],
            "resp_prev",
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "L1: hello",
                    "success": True,
                }
            ],
        )


def _build_config() -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        wire_api="responses",
        raw_provider={
            "reference_parity": True,
            "codex_installation_id": "install-test",
        },
    )


def _build_non_reference_config() -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        wire_api="responses",
        raw_provider={"reference_parity": False},
    )


def _build_explicit_codex_profile_config(
    *, legacy_reference_parity: bool = False
) -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
        wire_api="responses",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
        raw_provider={
            "reference_parity": legacy_reference_parity,
            "codex_installation_id": "install-test",
        },
    )


def _dummy_tool_executor(command_text: str):
    return "ok", [
        ToolEvent(name="shell", ok=True, summary="ran", payload={"command": command_text})
    ]


class _SequentialResponses:
    def __init__(self, scripted: list[object]) -> None:
        self.scripted = list(scripted)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(dict(kwargs))
        if not self.scripted:
            raise AssertionError("unexpected responses.create call")
        return self.scripted.pop(0)


class _SequentialClient:
    def __init__(self, scripted: list[object]) -> None:
        self.responses = _SequentialResponses(scripted)


class _TrackingResponsesClient:
    def __init__(self, scripted: list[object]) -> None:
        self.responses = _SequentialResponses(scripted)
        self.timeouts: list[int] = []

    def with_options(self, *, timeout=None):
        if timeout is not None:
            self.timeouts.append(int(timeout))
        return self


class _TrackingChatClient:
    def __init__(self, response: object) -> None:
        self.timeouts: list[int] = []
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._response = response

    def with_options(self, *, timeout=None):
        if timeout is not None:
            self.timeouts.append(int(timeout))
        return self

    def _create(self, **kwargs):
        self.requests.append(dict(kwargs))
        return self._response


class _TrackingChatSequenceClient:
    def __init__(self, scripted: list[object]) -> None:
        self.timeouts: list[int] = []
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._scripted = list(scripted)

    def with_options(self, *, timeout=None):
        if timeout is not None:
            self.timeouts.append(int(timeout))
        return self

    def _create(self, **kwargs):
        self.requests.append(dict(kwargs))
        if not self._scripted:
            raise AssertionError("unexpected chat.completions.create call")
        return self._scripted.pop(0)


def _responses_function_call(call_id: str, name: str, arguments: str):
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


def _responses_message(text: str):
    return SimpleNamespace(
        type="message",
        role="assistant",
        phase="final_answer",
        content=[SimpleNamespace(type="output_text", text=text)],
    )


def _response(*items, response_id: str = "resp_1"):
    return SimpleNamespace(
        id=response_id,
        output=list(items),
        output_text="final text",
    )


def test_openai_planner_delegates_to_turn_engine_and_uses_native_output_text():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="final",
        response_items=[response_message_item("assistant", "final", phase="final_answer")],
        turn_events=[
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "final"},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
            },
        ],
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ) as session_cls,
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=turn_engine_instance
        ) as turn_engine_cls,
        patch.object(
            OpenAIPlanner, "_intent_from_raw_text", wraps=OpenAIPlanner._intent_from_raw_text
        ) as parse_intent,
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan("list files", history=[], tool_executor=_dummy_tool_executor)

    turn_engine_cls.assert_called_once()
    session_cls.assert_called_once()
    assert session_cls.call_args.kwargs["instructions"] == planner.native_tool_system_prompt
    assert session_cls.call_args.kwargs["provider_name"] == "openai"
    assert [
        (item.get("type"), item.get("name")) for item in session_cls.call_args.kwargs["tool_specs"]
    ] == [
        ("function", "exec_command"),
        ("function", "write_stdin"),
        ("function", "update_plan"),
        ("function", "request_user_input"),
        ("custom", "apply_patch"),
        ("web_search", None),
        ("function", "view_image"),
        ("function", "spawn_agent"),
        ("function", "send_input"),
        ("function", "resume_agent"),
        ("function", "wait_agent"),
        ("function", "close_agent"),
    ]
    turn_engine_instance.run.assert_called_once()
    parse_intent.assert_not_called()
    assert result.assistant_text == "final"
    assert result.status_hint == "llm"
    assert result.response_items[0].extra["phase"] == "final_answer"
    assert result.turn_events[-1]["type"] == "turn.completed"


def test_openai_planner_passes_plain_responses_messages_to_turn_engine():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="final",
        response_items=[response_message_item("assistant", "final", phase="final_answer")],
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=turn_engine_instance
        ),
    ):
        planner = OpenAIPlanner(config)
        planner.plan(
            "list files",
            history=[{"role": "assistant", "content": "previous"}],
            tool_executor=_dummy_tool_executor,
            input_items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "<environment_context>ctx</environment_context>",
                        }
                    ],
                }
            ],
        )

    initial_input = turn_engine_instance.run.call_args.kwargs["initial_input"]
    assert initial_input[0] == {
        "role": "user",
        "content": "<environment_context>ctx</environment_context>",
    }
    assert initial_input[1] == {"role": "assistant", "content": "previous"}
    assert initial_input[-1] == {"role": "user", "content": "list files"}
    assert all(item.get("type") != "message" for item in initial_input)


def test_openai_planner_followup_prefers_tool_followup_route() -> None:
    config = _build_non_reference_config()
    config.raw_model = {
        "routes": {
            "tool_followup": {
                "model": "gpt_54_mini",
                "reasoning_effort": "low",
                "timeout": 13,
            }
        }
    }
    route_config = ProviderConfig(
        model="gpt-5.4-mini",
        api_key="sk-route",
        provider_name="openai",
        model_key="gpt_54_mini",
        planner_kind="openai_responses",
        wire_api="responses",
        base_url="https://relay.example/v1",
        reasoning_effort="low",
    )
    main_client = _TrackingResponsesClient([])
    route_client = _TrackingResponsesClient([_response(_responses_message("route followup"))])

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client",
            side_effect=[main_client, route_client],
        ),
        patch("cli.agent_cli.provider.load_provider_config", return_value=route_config),
    ):
        planner = OpenAIPlanner(config)
        result = planner._fresh_followup_after_tool_loop(
            user_text="继续",
            executed_events=[],
            tool_executor=_dummy_tool_executor,
        )

    assert result.assistant_text == "final text"
    assert route_client.timeouts == [13]
    assert route_client.responses.requests[0]["model"] == "gpt-5.4-mini"
    assert route_client.responses.requests[0]["stream"] is True
    assert route_client.responses.requests[0]["reasoning"] == {"effort": "low", "summary": "auto"}
    assert main_client.responses.requests == []


def test_openai_planner_synthesis_prefers_final_synthesis_route() -> None:
    config = _build_non_reference_config()
    config.raw_model = {
        "routes": {
            "final_synthesis": {
                "model": "gpt_54_high",
                "reasoning_effort": "medium",
                "timeout": 7,
            }
        }
    }
    route_config = ProviderConfig(
        model="gpt-5.4",
        api_key="sk-route",
        provider_name="openai",
        model_key="gpt_54_high",
        planner_kind="openai_responses",
        wire_api="responses",
        base_url="https://relay.example/v1",
        reasoning_effort="medium",
    )
    main_client = _TrackingResponsesClient([])
    route_client = _TrackingResponsesClient([_response(_responses_message("route synthesis"))])

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client",
            side_effect=[main_client, route_client],
        ),
        patch("cli.agent_cli.provider.load_provider_config", return_value=route_config),
    ):
        planner = OpenAIPlanner(config)
        result = planner._fresh_synthesis_after_tool_loop(
            user_text="总结",
            executed_events=[],
        )

    assert result.assistant_text == "final text"
    assert route_client.timeouts == [7]
    assert route_client.responses.requests[0]["model"] == "gpt-5.4"
    assert route_client.responses.requests[0]["stream"] is True
    assert route_client.responses.requests[0]["reasoning"] == {
        "effort": "medium",
        "summary": "auto",
    }
    assert main_client.responses.requests == []


def test_openai_planner_synthesis_supports_openai_chat_route() -> None:
    config = _build_non_reference_config()
    config.raw_model = {
        "routes": {
            "final_synthesis": {
                "model": "glm_5",
                "reasoning_effort": "high",
                "timeout": 11,
            }
        }
    }
    route_config = ProviderConfig(
        model="glm-5",
        api_key="sk-glm",
        provider_name="glm",
        model_key="glm_5",
        planner_kind="openai_chat",
        wire_api="openai_chat",
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        reasoning_effort="high",
        raw_model={"reasoning_mode": "thinking.type"},
    )
    main_client = _TrackingResponsesClient([])
    route_client = _TrackingChatClient(
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="cross-wire synthesis ok"))]
        )
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client",
            side_effect=[main_client, route_client],
        ),
        patch("cli.agent_cli.provider.load_provider_config", return_value=route_config),
    ):
        planner = OpenAIPlanner(config)
        result = planner._fresh_synthesis_after_tool_loop(
            user_text="总结",
            executed_events=[],
        )

    assert result.assistant_text == "cross-wire synthesis ok"
    assert route_client.timeouts == [11]
    assert route_client.requests[0]["model"] == "glm-5"
    assert route_client.requests[0]["extra_body"] == {
        "thinking": {"type": "enabled", "clear_thinking": False}
    }
    assert "messages" in route_client.requests[0]
    assert main_client.responses.requests == []


def test_openai_planner_followup_supports_openai_chat_route_with_tool_loop() -> None:
    config = _build_non_reference_config()
    config.raw_model = {
        "routes": {
            "tool_followup": {
                "model": "glm_5",
                "reasoning_effort": "high",
                "timeout": 12,
            }
        }
    }
    route_config = ProviderConfig(
        model="glm-5",
        api_key="sk-glm",
        provider_name="glm",
        model_key="glm_5",
        planner_kind="openai_chat",
        wire_api="openai_chat",
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        reasoning_effort="high",
        raw_model={
            "supports_tools": True,
            "supports_reasoning": True,
            "reasoning_mode": "thinking.type",
            "reasoning_output_field": "reasoning_content",
        },
    )
    main_client = _TrackingResponsesClient([])
    route_client = _TrackingChatSequenceClient(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="tool_calls",
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call_1",
                                    function=SimpleNamespace(
                                        name="exec_command", arguments='{"cmd":"pwd"}'
                                    ),
                                )
                            ],
                        ),
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(
                            content="/tmp/demo",
                            tool_calls=[],
                        ),
                    )
                ]
            ),
        ]
    )

    def _pwd_tool_executor(command_text: str):
        assert "pwd" in command_text
        return "/tmp/demo", [
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="pwd => /tmp/demo",
                payload={"stdout": "/tmp/demo\n", "aggregated_output": "/tmp/demo"},
            )
        ]

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client",
            side_effect=[main_client, route_client],
        ),
        patch("cli.agent_cli.provider.load_provider_config", return_value=route_config),
    ):
        planner = OpenAIPlanner(config)
        result = planner._fresh_followup_after_tool_loop(
            user_text="继续",
            executed_events=[],
            tool_executor=_pwd_tool_executor,
        )

    assert result.assistant_text == "/tmp/demo"
    assert route_client.timeouts == [12]
    assert len(route_client.requests) == 2
    assert route_client.requests[0]["model"] == "glm-5"
    assert route_client.requests[0]["extra_body"] == {
        "thinking": {"type": "enabled", "clear_thinking": False}
    }
    second_messages = route_client.requests[1]["messages"]
    assert any(
        str(item.get("role") or "") == "tool" for item in second_messages if isinstance(item, dict)
    )
    assert main_client.responses.requests == []


def test_openai_planner_command_builder_infers_spawn_agent_delegation_defaults() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_non_reference_config())

    command = planner._command_for_function_call(
        "spawn_agent",
        {
            "task": "运行 benchmark 收集 provider 延迟数据",
            "role": "subagent",
            "async": True,
        },
    )

    assert command is not None
    assert '"reason": "long_running_exec"' in command
    assert '"mode": "background"' in command
    assert '"wait_required": false' in command
    assert '"task_shape": "long_running"' in command


def test_openai_planner_command_builder_defaults_teammate_to_async_background() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_non_reference_config())

    command = planner._command_for_function_call(
        "spawn_agent",
        {
            "task": "收集 provider 差异并整理结论",
            "role": "teammate",
        },
    )

    assert command is not None
    assert '"async": true' in command
    assert '"mode": "background"' in command
    assert '"wait_required": false' in command
    assert '"task_shape": "read_only"' in command


def test_openai_planner_command_builder_defaults_context_sensitive_teammate_to_sync() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_non_reference_config())

    command = planner._command_for_function_call(
        "spawn_agent",
        {
            "task": "Continue current task using current context and above conversation",
            "role": "teammate",
        },
    )

    assert command is not None
    assert '"mode": "sync"' in command
    assert '"task_shape": "context_sensitive"' in command
    assert '"async": true' not in command


def test_openai_planner_command_builder_defaults_long_running_subagent_to_background() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_non_reference_config())

    command = planner._command_for_function_call(
        "spawn_agent",
        {
            "task": "运行 benchmark 收集 provider 延迟数据",
            "role": "subagent",
        },
    )

    assert command is not None
    assert '"async": true' in command
    assert '"mode": "background"' in command
    assert '"task_shape": "long_running"' in command


def test_openai_planner_command_builder_infers_wait_agent_defaults() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_non_reference_config())

    command = planner._command_for_function_call(
        "wait_agent",
        {"target": "agent_1"},
    )

    assert command == "/wait_agent agent_1 --reason wait_for_child_result --wait-required true"


def test_openai_planner_command_builder_rewrites_non_blocking_wait_to_agent_workflow() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_non_reference_config())

    command = planner._command_for_function_call(
        "wait_agent",
        {"target": "agent_1", "wait_required": False, "timeout_ms": 250},
    )

    assert command == "/agent_workflow agent_1"


def test_openai_planner_command_builder_infers_recover_agent_defaults() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_non_reference_config())

    command = planner._command_for_function_call(
        "recover_agent",
        {"target": "agent_1"},
    )

    assert command == "/recover_agent agent_1 --action retry_step"


def test_openai_planner_prefers_structured_input_items_over_legacy_history():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="final",
        response_items=[response_message_item("assistant", "final", phase="final_answer")],
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=turn_engine_instance
        ),
    ):
        planner = OpenAIPlanner(config)
        planner.plan(
            "summarize",
            history=[{"role": "assistant", "content": "legacy assistant from history"}],
            tool_executor=_dummy_tool_executor,
            input_items=[
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "input_text", "text": "structured assistant"}],
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "structured user"}],
                },
            ],
        )

    initial_input = turn_engine_instance.run.call_args.kwargs["initial_input"]
    contents = [str(item.get("content") or "") for item in initial_input]
    assert "legacy assistant from history" not in contents
    assert "structured assistant" in contents
    assert "structured user" in contents


def test_openai_planner_history_skips_when_function_call_output_items_present():
    config = _build_config()
    planner = OpenAIPlanner(config)
    history = [{"role": "assistant", "content": "legacy assistant"}]
    input_items = [{"type": "function_call_output", "call_id": "call_1", "output": "{}"}]

    assert planner._history_for_conversation(history, input_items=input_items) == []


def test_openai_planner_history_skips_when_response_items_carry_assistant():
    config = _build_config()
    planner = OpenAIPlanner(config)
    history = [{"role": "assistant", "content": "legacy assistant"}]
    input_items = [
        {
            "type": "response_item",
            "role": "assistant",
            "item": {"role": "assistant", "content": "tool-aware assistant"},
        }
    ]

    assert planner._history_for_conversation(history, input_items=input_items) == []


def test_openai_planner_tool_item_events_include_function_call_output_type():
    config = _build_config()
    planner = OpenAIPlanner(config)
    turn_events = [
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "item_0",
                "type": "function_call_output",
                "call_id": "call_1",
                "output": '{"ok": true}',
            },
        },
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
        },
    ]

    extracted = planner._tool_item_events_from_turn_events(turn_events)

    assert len(extracted) == 1
    assert extracted[0]["item"]["type"] == "function_call_output"
    assert extracted[0]["item"]["call_id"] == "call_1"


def test_openai_planner_resume_native_tool_followup_reuses_continuation_input_items():
    config = _build_config()
    session = MagicMock()
    callback = MagicMock()
    rescue_intent = AgentIntent(
        assistant_text="native followup",
        response_items=[
            response_message_item("assistant", "native followup", phase="final_answer")
        ],
    )
    rescue_engine = MagicMock()
    rescue_engine.run.return_value = rescue_intent

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=rescue_engine
        ) as turn_engine_cls,
    ):
        planner = OpenAIPlanner(config)
        result = planner._resume_native_tool_followup(
            session=session,
            user_text="继续分析",
            tool_executor=_dummy_tool_executor,
            executed_events=[
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"file_path": "README.md"},
                )
            ],
            executed_item_events=[
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "mcp_tool_call",
                        "tool": "read_file",
                        "status": "completed",
                    },
                }
            ],
            previous_response_id="resp_prev",
            continuation_input_items=[
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "L1: hello",
                    "success": True,
                }
            ],
            terminal_handler=MagicMock(),
            turn_event_callback=callback,
        )

    turn_engine_cls.assert_called_once_with(
        session,
        tool_executor=_dummy_tool_executor,
        command_builder=planner._command_for_function_call,
        followup_handler=None,
        terminal_handler=ANY,
        turn_event_callback=callback,
    )
    rescue_engine.run.assert_called_once_with(
        user_text="继续分析",
        initial_input=[
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "L1: hello",
                "success": True,
            }
        ],
        initial_previous_response_id="resp_prev",
        initial_executed_events=[
            ToolEvent(
                name="read_file", ok=True, summary="file loaded", payload={"file_path": "README.md"}
            )
        ],
        initial_executed_item_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "read_file",
                    "status": "completed",
                },
            }
        ],
    )
    assert result is rescue_intent


def test_openai_planner_resume_native_tool_followup_retries_full_replay_when_cursor_is_unsupported():
    config = _build_config()
    session = MagicMock()
    callback = MagicMock()
    rescue_intent = AgentIntent(
        assistant_text="native followup",
        response_items=[
            response_message_item("assistant", "native followup", phase="final_answer")
        ],
    )

    class _UnsupportedCursorError(Exception):
        status_code = 400

        def __str__(self) -> str:
            return "Error code: 400 - {'detail': 'Unsupported parameter: previous_response_id'}"

    rescue_engine = MagicMock()
    rescue_engine.run.side_effect = [_UnsupportedCursorError(), rescue_intent]

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch("cli.agent_cli.providers.openai_planner.TurnEngine", return_value=rescue_engine),
    ):
        planner = OpenAIPlanner(config)
        result = planner._resume_native_tool_followup(
            session=session,
            user_text="继续分析",
            tool_executor=_dummy_tool_executor,
            executed_events=[
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"file_path": "README.md"},
                )
            ],
            executed_item_events=[
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "mcp_tool_call",
                        "tool": "read_file",
                        "status": "completed",
                    },
                }
            ],
            previous_response_id="resp_prev",
            continuation_input_items=[
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "L1: hello",
                    "success": True,
                }
            ],
            terminal_handler=MagicMock(),
            turn_event_callback=callback,
        )

    assert rescue_engine.run.call_count == 2
    assert rescue_engine.run.call_args_list[0].kwargs["initial_previous_response_id"] == "resp_prev"
    assert rescue_engine.run.call_args_list[1].kwargs["initial_previous_response_id"] is None
    assert rescue_engine.run.call_args_list[1].kwargs["initial_input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "L1: hello",
            "success": True,
        }
    ]
    session.disable_incremental_continuation.assert_called_once_with(
        reason="previous_response_id_unsupported"
    )
    assert result is rescue_intent


def test_openai_planner_resume_native_tool_followup_skips_cursor_retry_when_initial_send_error_already_rejected_cursor():
    config = _build_config()
    session = MagicMock()
    callback = MagicMock()
    rescue_intent = AgentIntent(
        assistant_text="native followup",
        response_items=[
            response_message_item("assistant", "native followup", phase="final_answer")
        ],
    )

    class _UnsupportedCursorError(Exception):
        status_code = 400

        def __str__(self) -> str:
            return "Error code: 400 - {'detail': 'Unsupported parameter: previous_response_id'}"

    rescue_engine = MagicMock()
    rescue_engine.run.return_value = rescue_intent

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch("cli.agent_cli.providers.openai_planner.TurnEngine", return_value=rescue_engine),
    ):
        planner = OpenAIPlanner(config)
        result = planner._resume_native_tool_followup(
            session=session,
            user_text="继续分析",
            tool_executor=_dummy_tool_executor,
            executed_events=[
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"file_path": "README.md"},
                )
            ],
            executed_item_events=[
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "mcp_tool_call",
                        "tool": "read_file",
                        "status": "completed",
                    },
                }
            ],
            previous_response_id="resp_prev",
            continuation_input_items=[
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "L1: hello",
                    "success": True,
                }
            ],
            initial_send_error=_UnsupportedCursorError(),
            terminal_handler=MagicMock(),
            turn_event_callback=callback,
        )

    rescue_engine.run.assert_called_once()
    assert rescue_engine.run.call_args.kwargs["initial_previous_response_id"] is None
    assert rescue_engine.run.call_args.kwargs["initial_input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "L1: hello",
            "success": True,
        }
    ]
    session.disable_incremental_continuation.assert_called_once_with(
        reason="previous_response_id_unsupported"
    )
    assert result is rescue_intent


def test_openai_planner_followup_prefers_native_continuation_before_synthetic_followup():
    config = _build_config()
    native_intent = AgentIntent(
        assistant_text="native followup",
        response_items=[
            response_message_item("assistant", "native followup", phase="final_answer")
        ],
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", new=_ContinuationFollowupTurnEngine
        ),
        patch.object(
            OpenAIPlanner, "_resume_native_tool_followup", return_value=native_intent
        ) as native_followup,
        patch.object(OpenAIPlanner, "_fresh_followup_after_tool_loop") as synthetic_followup,
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan("read file", history=[], tool_executor=_dummy_tool_executor)

    native_followup.assert_called_once()
    synthetic_followup.assert_not_called()
    assert result.assistant_text == "native followup"


def test_openai_planner_native_continuation_failure_falls_back_to_synthesis_without_repeating_tools():
    config = _build_config()
    synthesized = AgentIntent(
        assistant_text="synthesized from verified tool results",
        response_items=[
            response_message_item(
                "assistant",
                "synthesized from verified tool results",
                phase="final_answer",
            )
        ],
        status_hint="tool",
        tool_events=[
            ToolEvent(
                name="read_file",
                ok=True,
                summary="file loaded",
                payload={"file_path": "README.md", "text": "L1: hello"},
            )
        ],
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", new=_ContinuationFollowupTurnEngine
        ),
        patch.object(
            OpenAIPlanner,
            "_resume_native_tool_followup",
            side_effect=RuntimeError("proxy_unavailable"),
        ) as native_followup,
        patch.object(OpenAIPlanner, "_fresh_followup_after_tool_loop") as synthetic_followup,
        patch.object(
            OpenAIPlanner, "_fresh_synthesis_after_tool_loop", return_value=synthesized
        ) as synthesis_mock,
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan("read file", history=[], tool_executor=_dummy_tool_executor)

    native_followup.assert_called_once()
    synthetic_followup.assert_not_called()
    synthesis_mock.assert_not_called()
    expected_fallback_text = structured_tool_fallback_text(
        [
            ToolEvent(
                name="read_file",
                ok=True,
                summary="file loaded",
                payload={"file_path": "README.md", "text": "L1: hello"},
            )
        ]
    )
    assert (
        result.assistant_text
        == f"{expected_fallback_text}\n回答阶段错误：RuntimeError: proxy_unavailable"
    )
    assert [event.name for event in result.tool_events] == ["read_file"]


def test_openai_planner_native_continuation_initial_send_error_is_preserved_in_fallback():
    config = _build_config()

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", new=_ContinuationFollowupTurnEngine
        ),
        patch.object(
            OpenAIPlanner,
            "_resume_native_tool_followup",
            side_effect=RuntimeError("proxy_unavailable"),
        ),
    ):
        planner = OpenAIPlanner(config)
        followup_handler = openai_planner_runtime_helpers_runtime.build_followup_handler(
            planner=planner,
            session=MagicMock(),
            tool_executor=_dummy_tool_executor,
            terminal_handler=openai_planner_runtime_helpers_runtime.build_terminal_handler(
                planner=planner,
                attachments=None,
            ),
            attachments=None,
            turn_event_callback=None,
        )
        result = followup_handler(
            "read file",
            [
                ToolEvent(
                    name="exec_command",
                    ok=True,
                    summary="exec_command exited",
                    payload={"command": "cat helloworld.py", "stdout": "Hello, world!\n"},
                )
            ],
            [],
            "resp_prev",
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "Hello, world!",
                    "success": True,
                }
            ],
            RuntimeError("provider 503"),
        )

    assert "工具输出：\nHello, world!" in result.assistant_text
    assert "回答阶段错误：RuntimeError: provider 503" in result.assistant_text


def test_openai_planner_response_items_generate_messages():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="final",
        response_items=[response_message_item("assistant", "final", phase="final_answer")],
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=turn_engine_instance
        ),
    ):
        planner = OpenAIPlanner(config)
        planner.plan(
            "check status",
            history=[{"role": "assistant", "content": "legacy assistant"}],
            tool_executor=_dummy_tool_executor,
            input_items=[
                {
                    "type": "response_item",
                    "role": "assistant",
                    "item": {
                        "role": "assistant",
                        "content": [{"type": "input_text", "text": "structured assistant"}],
                    },
                }
            ],
        )

    initial_input = turn_engine_instance.run.call_args.kwargs["initial_input"]
    response_items = [item for item in initial_input if item.get("type") == "response_item"]
    assert len(response_items) == 1
    nested = response_items[0].get("item") or {}
    assert nested.get("role") == "assistant"
    content_blocks = nested.get("content") or []
    assert content_blocks and content_blocks[0].get("text") == "structured assistant"
    assert all(
        item.get("role") != "assistant" or item.get("type") == "response_item"
        for item in initial_input
    )


def test_openai_planner_skips_synthesis_when_turn_events_contain_tool_items():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="",
        tool_events=[
            ToolEvent(name="list_dir", ok=True, summary="entries=1", payload={"dir_path": "."})
        ],
        response_items=[response_message_item("assistant", "done", phase="final_answer")],
        turn_events=[
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "command_execution",
                    "command": "/list_dir .",
                },
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
            },
        ],
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=turn_engine_instance
        ),
        patch.object(OpenAIPlanner, "_fresh_synthesis_after_tool_loop", autospec=True) as synth,
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan("list files", history=[], tool_executor=_dummy_tool_executor)

    synth.assert_not_called()
    assert result.assistant_text == "done"
    assert result.status_hint == "tool"


def test_openai_planner_merges_synthesis_timings_after_native_tool_loop() -> None:
    config = _build_non_reference_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="",
        response_items=[],
        status_hint="tool",
        tool_events=[
            ToolEvent(name="read_file", ok=True, summary="loaded", payload={"path": "README.md"})
        ],
        turn_events=[],
        timings={
            "initial_model_ms": 40,
            "tool_execution_ms": 60,
            "synthesis_model_ms": 0,
            "total_ms": 120,
            "planning_rounds": 1,
            "synthesis_rounds": 0,
            "planning_trace": [{"round": 1}],
            "synthesis_trace": [],
            "tool_call_count": 1,
        },
    )
    synthesized = AgentIntent(
        assistant_text="synthesized final",
        response_items=[
            response_message_item("assistant", "synthesized final", phase="final_answer")
        ],
        status_hint="tool",
        tool_events=[
            ToolEvent(name="read_file", ok=True, summary="loaded", payload={"path": "README.md"})
        ],
        timings={
            "initial_model_ms": 7,
            "tool_execution_ms": 5,
            "synthesis_model_ms": 30,
            "synthesis_rounds": 1,
            "planning_trace": [{"stage": "synth"}],
            "synthesis_trace": [{"stage": "synth"}],
        },
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=turn_engine_instance
        ),
        patch.object(OpenAIPlanner, "_fresh_synthesis_after_tool_loop", return_value=synthesized),
        patch(
            "cli.agent_cli.providers.openai_planner_runtime.time.perf_counter",
            side_effect=[10.0, 11.0],
        ),
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan("read file", history=[], tool_executor=_dummy_tool_executor)

    assert result.assistant_text == "synthesized final"
    assert result.timings["initial_model_ms"] == 47
    assert result.timings["tool_execution_ms"] == 65
    assert result.timings["synthesis_model_ms"] == 30
    assert result.timings["planning_rounds"] == 1
    assert result.timings["synthesis_rounds"] == 1
    assert result.timings["planning_trace"] == [{"round": 1}, {"stage": "synth"}]
    assert result.timings["synthesis_trace"] == [{"stage": "synth"}]
    assert result.timings["tool_call_count"] == 1
    assert result.timings["total_ms"] == 1000


def test_openai_planner_conversation_items_skip_history_when_structured_items_present():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="final",
        response_items=[response_message_item("assistant", "final", phase="final_answer")],
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=turn_engine_instance
        ),
    ):
        planner = OpenAIPlanner(config)
        planner.plan(
            "summarize",
            history=[{"role": "assistant", "content": "legacy assistant"}],
            tool_executor=_dummy_tool_executor,
            input_items=[
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "input_text", "text": "structured assistant"}],
                }
            ],
        )

    initial_input = turn_engine_instance.run.call_args.kwargs["initial_input"]
    assert not any(item.get("content") == "legacy assistant" for item in initial_input)


def test_openai_planner_conversation_items_include_history_when_no_structured_items():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="final",
        response_items=[response_message_item("assistant", "final", phase="final_answer")],
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=turn_engine_instance
        ),
    ):
        planner = OpenAIPlanner(config)
        planner.plan(
            "summarize",
            history=[{"role": "assistant", "content": "legacy assistant"}],
            tool_executor=_dummy_tool_executor,
            input_items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "struct user"}],
                }
            ],
        )

    initial_input = turn_engine_instance.run.call_args.kwargs["initial_input"]
    assert any(item.get("content") == "legacy assistant" for item in initial_input)


def test_openai_planner_continuation_failure_triggers_fresh_followup():
    config = _build_config()
    _FollowupTurnEngine.instances.clear()
    followup_intent = AgentIntent(assistant_text="fresh followup text", status_hint="tool")

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ),
        patch.object(
            OpenAIPlanner, "_fresh_followup_after_tool_loop", return_value=followup_intent
        ) as followup_mock,
        patch.object(
            OpenAIPlanner, "_fresh_synthesis_after_tool_loop", return_value=AgentIntent()
        ) as synthesis_mock,
        patch("cli.agent_cli.providers.openai_planner.TurnEngine", new=_FollowupTurnEngine),
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan("read file", history=[], tool_executor=_dummy_tool_executor)

    followup_mock.assert_not_called()
    synthesis_mock.assert_not_called()
    engine_instance = _FollowupTurnEngine.instances[-1]
    assert result.assistant_text == structured_tool_fallback_text(engine_instance.executed_events)
    assert result.tool_events == engine_instance.tool_events


def test_openai_planner_followup_exhaustion_falls_back_to_fresh_synthesis_instead_of_tool_summary():
    config = _build_non_reference_config()
    client = _SequentialClient(
        [
            SimpleNamespace(
                id=f"resp_{idx}",
                output=[
                    _responses_function_call(
                        f"call_{idx}",
                        "read_file",
                        '{"file_path": "docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md"}',
                    )
                ],
                output_text="",
            )
            for idx in range(1, 7)
        ]
    )

    def tool_executor(_command_text: str):
        return "read ok", [
            ToolEvent(
                name="read_file",
                ok=True,
                summary="file loaded",
                payload={
                    "file_path": "docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md",
                    "path": "docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md",
                },
            )
        ]

    class _StructuredToolExecutor:
        def __call__(self, command_text: str):
            return tool_executor(command_text)

        def run_structured(self, command_text: str):
            assistant_text, events = tool_executor(command_text)
            return CommandExecutionResult(
                assistant_text=assistant_text,
                tool_events=list(events),
                item_events=[
                    {
                        "type": "item.started",
                        "item": {
                            "id": "item_0",
                            "type": "command_execution",
                            "command": command_text,
                            "aggregated_output": "",
                            "exit_code": None,
                            "status": "in_progress",
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_0",
                            "type": "command_execution",
                            "command": command_text,
                            "aggregated_output": "alignment status",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    },
                ],
            )

    synthesized = AgentIntent(
        assistant_text="剩余差距：1）unified exec；2）tool registry；3）turn context。",
        response_items=[
            response_message_item(
                "assistant",
                "剩余差距：1）unified exec；2）tool registry；3）turn context。",
                phase="final_answer",
            )
        ],
        status_hint="tool",
        timings={"synthesis_model_ms": 12, "synthesis_rounds": 1},
    )

    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client):
        planner = OpenAIPlanner(config)
        with patch.object(
            OpenAIPlanner, "_fresh_synthesis_after_tool_loop", return_value=synthesized
        ) as synthesis_mock:
            result = planner._fresh_followup_after_tool_loop(
                user_text="请给出当前贴近 Reference 的 3 个剩余差距。",
                executed_events=[],
                tool_executor=_StructuredToolExecutor(),
            )

    synthesis_mock.assert_called_once()
    assert result.assistant_text.startswith("剩余差距：")
    assert "已读取文件：" not in result.assistant_text
    assert result.response_items[0].extra["phase"] == "final_answer"
    assert result.timings["synthesis_rounds"] == 7
    assert len(result.tool_events) == 6
    command_items = [
        event
        for event in result.turn_events
        if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
    ]
    assert len(command_items) == 6
    assert command_items[-1]["item"]["aggregated_output"] == "alignment status"


def test_openai_planner_reference_parity_http_second_round_uses_full_item_replay() -> None:
    config = _build_config()
    client = _SequentialClient(
        [
            SimpleNamespace(
                id="resp_1",
                output=[
                    _responses_function_call(
                        "call_1",
                        "read_file",
                        '{"file_path": "README.md"}',
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_2",
                output=[_responses_message("README.md 已读取。")],
                output_text="",
            ),
        ]
    )

    def tool_executor(command_text: str):
        assert command_text == "/read_file README.md"
        return "read ok", [
            ToolEvent(
                name="read_file",
                ok=True,
                summary="file loaded",
                payload={"file_path": "README.md", "text": "L1: hello"},
            )
        ]

    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client):
        planner = OpenAIPlanner(config)
        result = planner.plan("读取 README.md", history=[], tool_executor=tool_executor)

    assert result.assistant_text == "README.md 已读取。"
    assert len(client.responses.requests) == 2

    second_request = client.responses.requests[1]
    second_input = second_request["input"]
    assert "previous_response_id" not in second_request
    assert [item.get("type") for item in second_input] == [
        "message",
        "function_call",
        "function_call_output",
    ]
    assert second_input[-2]["call_id"] == "call_1"
    assert second_input[-1]["call_id"] == "call_1"
    assert "VERIFIED_TOOL_RESULT_SUMMARY:" not in json.dumps(second_input, ensure_ascii=False)
    assert (
        "Continue solving the original request from these verified tool results"
        not in json.dumps(second_input, ensure_ascii=False)
    )


def test_openai_planner_visible_child_tab_tool_returns_matching_function_call_output() -> None:
    config = _build_config()
    client = _SequentialClient(
        [
            SimpleNamespace(
                id="resp_1",
                output=[
                    _responses_function_call(
                        "call_visible_child_1",
                        "spawn_child_tab",
                        '{"task":"Inspect README","task_name":"README"}',
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_2",
                output=[_responses_message("child queued")],
                output_text="",
            ),
        ]
    )
    observed_commands: list[str] = []

    def tool_executor(command_text: str):
        observed_commands.append(command_text)
        assert command_text.startswith("/__spawn_child_tab ")
        return "visible child tab spawned", [
            ToolEvent(
                name="spawn_child_tab",
                ok=True,
                summary="visible child tab spawned",
                payload={
                    "tab_id": "tab-2",
                    "task_id": "visible_run:README:0",
                    "parent_tab_id": "tab-1",
                },
            )
        ]

    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client):
        planner = OpenAIPlanner(config)
        result = planner.plan(
            "请用 visible child tabs 拆一个任务看 README",
            history=[],
            tool_executor=tool_executor,
        )

    assert result.assistant_text == "child queued"
    assert len(observed_commands) == 1
    assert len(client.responses.requests) == 2
    second_input = client.responses.requests[1]["input"]
    assert [item.get("type") for item in second_input] == [
        "message",
        "function_call",
        "function_call_output",
    ]
    assert second_input[-2]["call_id"] == "call_visible_child_1"
    assert second_input[-2]["name"] == "spawn_child_tab"
    assert second_input[-1]["call_id"] == "call_visible_child_1"


def test_openai_planner_reference_parity_websocket_second_round_uses_incremental_output() -> None:
    config = _build_config()
    client = _SequentialClient(
        [
            SimpleNamespace(
                id="resp_1",
                output=[
                    _responses_function_call(
                        "call_1",
                        "read_file",
                        '{"file_path": "README.md"}',
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_2",
                output=[_responses_message("README.md 已读取。")],
                output_text="",
            ),
        ]
    )
    client.transport_kind = "websocket"

    def tool_executor(command_text: str):
        assert command_text == "/read_file README.md"
        return "read ok", [
            ToolEvent(
                name="read_file",
                ok=True,
                summary="file loaded",
                payload={"file_path": "README.md", "text": "L1: hello"},
            )
        ]

    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client):
        planner = OpenAIPlanner(config)
        result = planner.plan("读取 README.md", history=[], tool_executor=tool_executor)

    assert result.assistant_text == "README.md 已读取。"
    assert len(client.responses.requests) == 2

    second_request = client.responses.requests[1]
    second_input = second_request["input"]
    assert second_request["previous_response_id"] == "resp_1"
    assert [item.get("type") for item in second_input] == ["function_call_output"]
    assert second_input[0]["call_id"] == "call_1"


def test_update_plan_followup_rebase_preserves_explicit_function_call_output() -> None:
    runtime = SimpleNamespace(collaboration_mode="default")
    with active_provider_tool_call_id("call_update_plan_1"):
        result = handle_update_plan_command(
            runtime,
            arg_text='{"plan":[{"step":"inspect","status":"in_progress"}]}',
        )

    rebased = openai_planner_followup_runtime.rebase_followup_result_item_events(
        call={
            "name": "update_plan",
            "arguments": {"plan": [{"step": "inspect", "status": "in_progress"}]},
        },
        result=result,
        aggregated_item_events=[],
        next_item_index=0,
        latest_open_todo_list_item_fn=latest_open_todo_list_item,
        todo_list_turn_event_from_plan_payload_fn=todo_list_turn_event_from_plan_payload,
        rebase_item_events_fn=planner_rebase_item_events,
    )

    assert [event["item"]["type"] for event in rebased] == ["todo_list", "function_call_output"]
    assert rebased[0]["item"]["id"] == "item_0"
    assert rebased[1]["item"]["call_id"] == "call_update_plan_1"
    assert rebased[1]["item"]["output"] == "Plan updated"
    assert rebased[1]["item"]["success"] is True


def test_openai_planner_reference_parity_http_exec_write_stdin_followup_uses_full_item_replay() -> (
    None
):
    config = _build_config()
    client = _SequentialClient(
        [
            SimpleNamespace(
                id="resp_1",
                output=[
                    _responses_function_call(
                        "call_exec_1",
                        "exec_command",
                        '{"cmd":"sleep 30"}',
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_2",
                output=[
                    _responses_function_call(
                        "call_poll_1",
                        "write_stdin",
                        '{"session_id":"255"}',
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_3",
                output=[_responses_message("命令已完成。")],
                output_text="",
            ),
        ]
    )
    executed_commands: list[str] = []

    def tool_executor(command_text: str):
        executed_commands.append(command_text)
        if command_text == "/exec_command 'sleep 30'":
            return "command started", [
                ToolEvent(
                    name="exec_command",
                    ok=True,
                    summary="exec_command running",
                    payload={
                        "stdout": "tick 1\n",
                        "session_id": "255",
                        "task_id": "255",
                        "status": "written",
                        "duration_ms": 700,
                        "function_call_output": (
                            "Process running with session ID 255\n"
                            "Background task ID 255\n"
                            "Use write_stdin 255 to poll for completion or send input\n"
                            "Output:\n"
                            "tick 1\n"
                        ),
                    },
                )
            ]
        if command_text == "/write_stdin 255":
            return "command finished", [
                ToolEvent(
                    name="write_stdin",
                    ok=True,
                    summary="command finished",
                    payload={
                        "stdout": "done\n",
                        "aggregated_output": "done\n",
                        "exit_code": 0,
                        "status": "completed",
                        "duration_ms": 200,
                        "function_call_output": "done\n",
                    },
                )
            ]
        raise AssertionError(f"unexpected command: {command_text}")

    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client):
        planner = OpenAIPlanner(config)
        result = planner.plan("运行命令并等待结束", history=[], tool_executor=tool_executor)

    assert result.assistant_text == "命令已完成。"
    assert executed_commands == ["/exec_command 'sleep 30'", "/write_stdin 255"]
    assert len(client.responses.requests) == 3

    second_request = client.responses.requests[1]
    assert "previous_response_id" not in second_request
    assert [item.get("type") for item in second_request["input"]] == [
        "message",
        "function_call",
        "function_call_output",
    ]
    assert second_request["input"][-2]["call_id"] == "call_exec_1"
    assert second_request["input"][-1]["call_id"] == "call_exec_1"

    third_request = client.responses.requests[2]
    assert "previous_response_id" not in third_request
    assert [item.get("type") for item in third_request["input"]] == [
        "message",
        "function_call",
        "function_call_output",
        "function_call",
        "function_call_output",
    ]
    assert third_request["input"][-2]["call_id"] == "call_poll_1"
    assert third_request["input"][-1]["call_id"] == "call_poll_1"
    serialized_third_input = json.dumps(third_request["input"], ensure_ascii=False)
    assert '"name": "write_stdin"' in serialized_third_input


def test_openai_planner_reference_parity_websocket_exec_write_stdin_followup_stays_incremental() -> (
    None
):
    config = _build_config()
    client = _SequentialClient(
        [
            SimpleNamespace(
                id="resp_1",
                output=[
                    _responses_function_call(
                        "call_exec_1",
                        "exec_command",
                        '{"cmd":"sleep 30"}',
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_2",
                output=[
                    _responses_function_call(
                        "call_poll_1",
                        "write_stdin",
                        '{"session_id":"255"}',
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_3",
                output=[_responses_message("命令已完成。")],
                output_text="",
            ),
        ]
    )
    client.transport_kind = "websocket"

    def tool_executor(command_text: str):
        if command_text == "/exec_command 'sleep 30'":
            return "command started", [
                ToolEvent(
                    name="exec_command",
                    ok=True,
                    summary="exec_command running",
                    payload={
                        "stdout": "tick 1\n",
                        "session_id": "255",
                        "status": "written",
                        "duration_ms": 700,
                        "function_call_output": "Process running with session ID 255\nOutput:\ntick 1\n",
                    },
                )
            ]
        if command_text == "/write_stdin 255":
            return "command finished", [
                ToolEvent(
                    name="write_stdin",
                    ok=True,
                    summary="command finished",
                    payload={
                        "stdout": "done\n",
                        "exit_code": 0,
                        "status": "completed",
                        "duration_ms": 200,
                        "function_call_output": "done\n",
                    },
                )
            ]
        raise AssertionError(f"unexpected command: {command_text}")

    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client):
        planner = OpenAIPlanner(config)
        result = planner.plan("运行命令并等待结束", history=[], tool_executor=tool_executor)

    assert result.assistant_text == "命令已完成。"
    assert len(client.responses.requests) == 3

    second_request = client.responses.requests[1]
    assert second_request["previous_response_id"] == "resp_1"
    assert [item.get("type") for item in second_request["input"]] == ["function_call_output"]
    assert second_request["input"][0]["call_id"] == "call_exec_1"

    third_request = client.responses.requests[2]
    assert third_request["previous_response_id"] == "resp_2"
    assert [item.get("type") for item in third_request["input"]] == ["function_call_output"]
    assert third_request["input"][0]["call_id"] == "call_poll_1"
    assert "/write_stdin" not in json.dumps(third_request["input"], ensure_ascii=False)


def test_openai_planner_reference_parity_disables_direct_synthetic_followup_path() -> None:
    config = _build_config()
    client = _SequentialClient([])

    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client):
        planner = OpenAIPlanner(config)

    try:
        planner._fresh_followup_after_tool_loop(
            user_text="继续",
            executed_events=[],
            tool_executor=_dummy_tool_executor,
        )
    except RuntimeError as exc:
        assert "disabled when reference parity is enabled" in str(exc)
    else:
        raise AssertionError("expected reference parity synthetic followup path to be disabled")


def test_openai_planner_reference_parity_without_tool_executor_uses_native_responses_path() -> None:
    config = _build_config()
    client = _SequentialClient(
        [
            SimpleNamespace(
                id="resp_native_no_tools",
                output=[_responses_message("native answer")],
                output_text="",
            )
        ]
    )

    with (
        patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client),
        patch.object(
            OpenAIPlanner, "_plan_without_native_tools", autospec=True
        ) as legacy_json_path,
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan(
            "今天几号？",
            history=[{"role": "assistant", "content": "上一轮回答"}],
            tool_executor=None,
            input_items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "<environment_context>ctx</environment_context>",
                        }
                    ],
                }
            ],
        )

    legacy_json_path.assert_not_called()
    assert result.assistant_text == "native answer"
    assert len(client.responses.requests) == 1
    request = client.responses.requests[0]
    assert "tools" not in request
    assert request["stream"] is False
    assert [item.get("type") for item in request["input"]] == ["message", "message", "message"]
    assert request["input"][0]["role"] == "user"
    assert request["input"][1]["role"] == "assistant"
    assert request["input"][2]["role"] == "user"


def test_openai_planner_explicit_codex_profile_without_legacy_flag_uses_native_responses_path() -> (
    None
):
    config = _build_explicit_codex_profile_config(legacy_reference_parity=False)
    client = _SequentialClient(
        [
            SimpleNamespace(
                id="resp_explicit_codex_native",
                output=[_responses_message("explicit codex answer")],
                output_text="",
            )
        ]
    )

    with (
        patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client),
        patch.object(
            OpenAIPlanner, "_plan_without_native_tools", autospec=True
        ) as legacy_json_path,
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan("今天几号？", history=[], tool_executor=None)

    legacy_json_path.assert_not_called()
    assert planner.reference_parity_enabled is True
    assert planner.resolved_interaction_contract.profile == "codex_openai"
    assert result.assistant_text == "explicit codex answer"
    assert len(client.responses.requests) == 1
    request = client.responses.requests[0]
    assert request["stream"] is False
    assert "tools" not in request
    assert request["text"] == {"verbosity": "low"}
    assert request["extra_body"]["client_metadata"] == {"x-codex-installation-id": "install-test"}


def test_openai_planner_codex_profile_preserves_multiblock_developer_input_items() -> None:
    config = _build_explicit_codex_profile_config(legacy_reference_parity=False)
    client = _SequentialClient(
        [
            SimpleNamespace(
                id="resp_multiblock_developer",
                output=[_responses_message("OK")],
                output_text="",
            )
        ]
    )

    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client):
        planner = OpenAIPlanner(config)
        planner.plan(
            "请只回答 OK",
            history=[],
            tool_executor=None,
            input_items=[
                {
                    "type": "message",
                    "role": "developer",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "<permissions instructions>p</permissions instructions>",
                        },
                        {
                            "type": "input_text",
                            "text": "<skills_instructions>\n## Skills\n- live: smoke\n</skills_instructions>",
                        },
                    ],
                }
            ],
        )

    request = client.responses.requests[0]
    developer = request["input"][0]
    assert developer["role"] == "developer"
    assert developer["content"] == [
        {"type": "input_text", "text": "<permissions instructions>p</permissions instructions>"},
        {
            "type": "input_text",
            "text": "<skills_instructions>\n## Skills\n- live: smoke\n</skills_instructions>",
        },
    ]
    assert request["input"][1]["role"] == "user"


def test_openai_planner_non_reference_without_tool_executor_keeps_legacy_json_path() -> None:
    config = _build_non_reference_config()

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch.object(
            OpenAIPlanner,
            "_plan_without_native_tools",
            autospec=True,
            return_value=AgentIntent(assistant_text="legacy"),
        ) as legacy_json_path,
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan("继续", history=[], tool_executor=None)

    legacy_json_path.assert_called_once()
    assert result.assistant_text == "legacy"


def test_openai_planner_plan_without_native_tools_is_blocked_in_reference_parity() -> None:
    config = _build_config()

    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(config)

    try:
        planner._plan_without_native_tools("继续", [])
    except RuntimeError as exc:
        assert "disabled when reference parity is enabled" in str(exc)
    else:
        raise AssertionError(
            "expected legacy json planner path to be blocked in reference parity mode"
        )


def test_openai_planner_keeps_final_answer_when_responses_returns_message_items_after_tool_loop():
    config = _build_config()
    client = _SequentialClient(
        [
            SimpleNamespace(
                id="resp_1",
                output=[
                    _responses_function_call(
                        "call_1",
                        "read_file",
                        '{"file_path": "docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md"}',
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_2",
                output=[
                    _responses_message(
                        "剩余 3 个差距：1）原生 tool-call loop；2）结构化 thread history；3）unified exec。"
                    )
                ],
                output_text="",
            ),
        ]
    )

    def tool_executor(command_text: str):
        assert command_text == "/read_file docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md"
        return "read ok", [
            ToolEvent(
                name="read_file",
                ok=True,
                summary="file loaded",
                payload={
                    "file_path": "docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md",
                    "path": "docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md",
                    "text": "alignment status",
                    "line_count": 32,
                },
            )
        ]

    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=client):
        planner = OpenAIPlanner(config)
        result = planner.plan(
            "请查看项目并给出当前贴近 Reference 的 3 个剩余差距，每个差距附一个相关文件路径。",
            history=[],
            tool_executor=tool_executor,
        )

    assert result.assistant_text.startswith("剩余 3 个差距：")
    assert "已读取文件：" not in result.assistant_text
    assert [event.name for event in result.tool_events] == ["read_file"]
    assert result.response_items[0].extra["phase"] == "final_answer"


def test_openai_planner_can_disable_slash_command_pattern_fallback() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_config())

    intent = planner._intent_from_raw_text(
        "先做检索\n/file_search reference --path cli",
        allow_command_pattern_fallback=False,
    )

    assert intent.command_text is None
    assert intent.status_hint == "llm"
    assert "/file_search reference --path cli" in intent.assistant_text


def test_openai_planner_runs_fresh_synthesis_when_turn_engine_returns_only_non_text_items_after_tools() -> (
    None
):
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="",
        response_items=[
            ResponseInputItem.from_dict(
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": '{"ok": true}',
                }
            )
        ],
        status_hint="tool",
        tool_events=[
            ToolEvent(
                name="read_file",
                ok=True,
                summary="file loaded",
                payload={
                    "file_path": "docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md",
                    "path": "docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md",
                },
            )
        ],
        turn_events=[
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "command_execution",
                    "command": "/read_file docs/REFERENCE_EXEC_ALIGNMENT_STATUS.md",
                    "aggregated_output": "alignment status",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
            },
        ],
    )
    synthesized = AgentIntent(
        assistant_text="剩余 3 个差距：1）tool loop；2）thread items；3）unified exec。",
        response_items=[
            response_message_item(
                "assistant",
                "剩余 3 个差距：1）tool loop；2）thread items；3）unified exec。",
                phase="final_answer",
            )
        ],
        status_hint="tool",
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.OpenAIResponsesSession",
            return_value=MagicMock(),
        ),
        patch(
            "cli.agent_cli.providers.openai_planner.TurnEngine", return_value=turn_engine_instance
        ),
        patch.object(
            OpenAIPlanner, "_fresh_synthesis_after_tool_loop", return_value=synthesized
        ) as synthesis_mock,
    ):
        planner = OpenAIPlanner(config)
        result = planner.plan("请给出剩余差距", history=[], tool_executor=_dummy_tool_executor)

    synthesis_mock.assert_not_called()
    assert result.assistant_text == "file loaded"


def test_openai_planner_normalizes_legacy_file_alias_tool_calls_to_canonical_commands() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_config())

    assert (
        planner._command_for_function_call("file_search", {"query": "provider", "path": "cli"})
        == "/grep_files provider --path cli"
    )
    assert (
        planner._command_for_function_call("file_list", {"path": "cli", "limit": 5})
        == "/list_dir cli --limit 5"
    )
    assert (
        planner._command_for_function_call(
            "file_read", {"path": "README.md", "offset": 3, "limit": 5}
        )
        == "/read_file README.md --offset 3 --limit 5"
    )


def test_openai_planner_keeps_one_layer_list_dir_native() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_config())

    command = planner._command_for_function_call(
        "list_dir", {"dir_path": ".", "limit": 5, "depth": 1}
    )

    assert command == "/list_dir . --limit 5 --depth 1"


def test_openai_planner_synthesis_messages_include_executed_item_events_context() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_config())

    messages = planner._synthesis_messages(
        user_text="请分析 provider 实现",
        executed_events=[
            ToolEvent(
                name="grep_files",
                ok=True,
                summary="paths=1",
                payload={"pattern": "provider", "paths": ["cli/agent_cli/provider.py"]},
            )
        ],
        executed_item_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "grep_files",
                    "arguments": {"pattern": "provider"},
                    "result": {"content": [{"type": "text", "text": "cli/agent_cli/provider.py"}]},
                    "status": "completed",
                },
            }
        ],
    )

    content = messages[0]["content"]
    assert "EXECUTED_ITEM_EVENTS_JSON:" in content
    assert '"item_type": "mcp_tool_call"' in content
    assert '"tool": "grep_files"' in content


def test_openai_planner_followup_messages_include_executed_item_events_context() -> None:
    with patch(
        "cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()
    ):
        planner = OpenAIPlanner(_build_config())

    messages = planner._tool_followup_messages(
        user_text="继续分析",
        executed_events=[
            ToolEvent(
                name="read_file", ok=True, summary="file loaded", payload={"path": "README.md"}
            )
        ],
        executed_item_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "/read_file README.md --offset 3 --limit 5",
                    "aggregated_output": "L3: hello",
                    "exit_code": 0,
                    "status": "completed",
                },
            }
        ],
    )

    content = messages[0]["content"]
    assert "EXECUTED_ITEM_EVENTS_JSON:" in content
    assert '"item_type": "command_execution"' in content
    assert '"/read_file README.md --offset 3 --limit 5"' in content
