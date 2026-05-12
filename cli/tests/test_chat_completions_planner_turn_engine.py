from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cli.agent_cli.core.provider_session import ProviderSessionResult, ProviderToolCall
from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.models import (
    AgentIntent,
    REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
    CommandExecutionResult,
    ToolEvent,
    response_message_item,
)
from cli.agent_cli.providers.chat_completions_planner import ChatCompletionsPlanner
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_profile_resolution import InteractionProfileCompatibilityError

def _build_config() -> ProviderConfig:
    return ProviderConfig(
        model="glm-5",
        api_key="test-key",
        provider_name="glm",
        planner_kind="openai_chat",
        base_url="https://open.bigmodel.cn/api/paas/v4",
    )

def _dummy_tool_executor(command_text: str):
    return "ok", [ToolEvent(name="list_dir", ok=True, summary="entries=1", payload={"command": command_text})]

class _InterruptAwareStructuredExecutor:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self._interrupted = False

    def __call__(self, command_text: str):
        return self.run_structured(command_text)

    def run_structured(self, command_text: str) -> CommandExecutionResult:
        self.commands.append(command_text)
        self._interrupted = True
        return CommandExecutionResult(
            assistant_text="Run shell command.",
            tool_events=[
                ToolEvent(
                    name="shell",
                    ok=False,
                    summary="shell interrupted",
                    payload={
                        "command": command_text,
                        "interrupted": True,
                        "status": "interrupted",
                    },
                )
            ],
            item_events=[
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "command_execution",
                        "command": command_text,
                        "status": "failed",
                        "exit_code": None,
                    },
                }
            ],
        )

    def interrupt_requested(self) -> bool:
        return self._interrupted

    def interrupt_result(self):
        return (
            REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
            [
                ToolEvent(
                    name="interrupted",
                    ok=False,
                    summary="execution interrupted",
                    payload={"interrupted": True, "reason": "user_interrupt"},
                )
            ],
        )

class _SingleToolSession:
    def __init__(self) -> None:
        self.send_calls = 0

    def send(self, **kwargs) -> ProviderSessionResult:
        del kwargs
        self.send_calls += 1
        if self.send_calls > 1:
            raise AssertionError("turn engine should stop after interrupted tool execution")
        return ProviderSessionResult(
            response_id="resp_1",
            tool_calls=[
                ProviderToolCall(
                    call_id="call_1",
                    name="exec_command",
                    arguments={"cmd": "sleep 5"},
                )
            ],
            output_text="",
            response_items=[],
            continuation_input_items=[],
            trace={"tool_calls": ["exec_command"], "tool_call_count": 1},
        )

class _FakeChatClient:
    def __init__(self, response) -> None:
        self._response = response
        self.requests: list[dict] = []
        self.timeouts: list[int] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def with_options(self, *, timeout=None):
        if timeout is not None:
            self.timeouts.append(int(timeout))
        return self

    def _create(self, **kwargs):
        self.requests.append(dict(kwargs))
        return self._response

def test_chat_completions_planner_non_deepseek_delegates_to_turn_engine():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="planner final",
        response_items=[response_message_item("assistant", "planner final", phase="final_answer")],
        status_hint="tool",
        tool_events=[ToolEvent(name="list_dir", ok=True, summary="entries=1", payload={})],
        timings={"initial_model_ms": 12, "planning_rounds": 1, "planning_trace": [], "synthesis_trace": []},
    )

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.ChatCompletionsSession", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.TurnEngine", return_value=turn_engine_instance) as turn_engine_cls:
        planner = ChatCompletionsPlanner(config)
        result = planner.plan("list files", history=[], tool_executor=_dummy_tool_executor)

    turn_engine_cls.assert_called_once()
    turn_engine_instance.run.assert_called_once()
    assert result.assistant_text == "planner final"
    assert result.status_hint == "tool"
    assert len(result.tool_events) == 1
    assert result.response_items[0].extra["phase"] == "final_answer"


def test_chat_completions_planner_turn_engine_session_receives_resolved_contract_fields() -> None:
    config = _build_config()
    config.interaction_profile = "generic_chat"
    config.interaction_profile_source = "model.interaction_profile"
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="planner final",
        response_items=[response_message_item("assistant", "planner final", phase="final_answer")],
        status_hint="tool",
        tool_events=[ToolEvent(name="list_dir", ok=True, summary="entries=1", payload={})],
        timings={"initial_model_ms": 1, "planning_rounds": 1, "planning_trace": [], "synthesis_trace": []},
    )

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.ChatCompletionsSession", return_value=MagicMock()) as session_cls, \
        patch("cli.agent_cli.providers.chat_completions_planner.TurnEngine", return_value=turn_engine_instance):
        planner = ChatCompletionsPlanner(config)
        planner.plan("list files", history=[], tool_executor=_dummy_tool_executor)

    assert planner.interaction_profile == "generic_chat"
    assert planner.turn_protocol_policy == "generic_chat_turn"
    session_kwargs = session_cls.call_args.kwargs
    assert session_kwargs["interaction_profile"] == "generic_chat"
    assert session_kwargs["turn_protocol_policy"] == "generic_chat_turn"


def test_chat_completions_planner_explicit_incompatible_profile_raises_hard_error() -> None:
    config = _build_config()
    config.interaction_profile = "codex_openai"
    config.interaction_profile_source = "model.interaction_profile"

    with pytest.raises(InteractionProfileCompatibilityError):
        ChatCompletionsPlanner(config)


def test_chat_completions_turn_engine_exception_fallback_reports_elapsed_total_ms() -> None:
    config = _build_config()

    class _SessionStub:
        def __init__(self, **kwargs):
            del kwargs

    class _RaisingTurnEngine:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def run(self, **kwargs):
            del kwargs
            raise RuntimeError("planner failure")

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()):
        planner = ChatCompletionsPlanner(config)

    planner._turn_engine_session_cls = _SessionStub
    planner._turn_engine_cls = _RaisingTurnEngine
    perf_values = iter([1.0, 1.5])
    planner._turn_engine_perf_counter_fn = lambda: next(perf_values)

    intent = planner._planning_intent_with_turn_engine(
        user_text="list files",
        messages=[],
        tool_executor=_dummy_tool_executor,
    )

    assert intent.timings["total_ms"] == 500
    assert intent.timings["initial_model_ms"] == 0
    assert intent.timings["tool_execution_ms"] == 0
    assert intent.timings["synthesis_model_ms"] == 0


def test_chat_completions_policy_helper_prefers_route_config() -> None:
    config = _build_config()
    config.raw_model = {
        "policy_llm_assist": True,
        "routes": {
            "policy_helper": {
                "model": "deepseek_chat",
                "reasoning_effort": "low",
                "timeout": 9,
            }
        },
    }
    route_config = ProviderConfig(
        model="deepseek-chat",
        api_key="sk-deepseek",
        provider_name="deepseek",
        model_key="deepseek_chat",
        planner_kind="deepseek_chat",
        wire_api="openai_chat",
        base_url="https://api.deepseek.com",
        reasoning_effort="low",
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"queries":["权限管理"]}'))]
    )
    main_client = _FakeChatClient(response)
    route_client = _FakeChatClient(response)

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", side_effect=[main_client, route_client]), \
        patch("cli.agent_cli.provider.load_provider_config", return_value=route_config):
        planner = ChatCompletionsPlanner(config)
        payload = planner._chat_json_payload(system_prompt="sys", user_prompt="usr")

    assert payload == {"queries": ["权限管理"]}
    assert main_client.requests == []
    assert route_client.timeouts == [9]
    assert route_client.requests[0]["model"] == "deepseek-chat"

def test_chat_completions_policy_helper_logs_route_specific_trace() -> None:
    config = _build_config()
    config.raw_model = {
        "policy_llm_assist": True,
        "routes": {
            "policy_helper": {
                "provider": "deepseek",
                "model": "deepseek_chat",
                "reasoning_effort": "low",
                "timeout": 9,
            }
        },
    }
    route_config = ProviderConfig(
        model="deepseek-chat",
        api_key="sk-deepseek",
        provider_name="deepseek",
        model_key="deepseek_chat",
        planner_kind="deepseek_chat",
        wire_api="openai_chat",
        base_url="https://api.deepseek.com",
        reasoning_effort="low",
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"queries":["权限管理"]}'))]
    )
    main_client = _FakeChatClient(response)
    route_client = _FakeChatClient(response)

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", side_effect=[main_client, route_client]), \
        patch("cli.agent_cli.provider.load_provider_config", return_value=route_config), \
        patch("cli.agent_cli.providers.chat_completions_planner.timeline_debug_enabled", return_value=True), \
        patch("cli.agent_cli.providers.chat_completions_planner.log_timeline") as log_timeline_mock:
        planner = ChatCompletionsPlanner(config)
        payload = planner._chat_json_payload(system_prompt="sys", user_prompt="usr")

    assert payload == {"queries": ["权限管理"]}
    stages = [call.args[0] for call in log_timeline_mock.call_args_list]
    assert "chat_completions.route_policy_helper.request_raw" in stages
    assert "chat_completions.route_policy_helper.response_raw" in stages
    request_call = next(
        call for call in log_timeline_mock.call_args_list
        if call.args[0] == "chat_completions.route_policy_helper.request_raw"
    )
    assert request_call.kwargs["provider_name"] == "deepseek"
    assert request_call.kwargs["base_url"] == "https://api.deepseek.com"

def test_chat_completions_default_trace_includes_provider_metadata() -> None:
    config = _build_config()
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    client = _FakeChatClient(response)

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=client), \
        patch("cli.agent_cli.providers.chat_completions_planner.timeline_debug_enabled", return_value=True), \
        patch("cli.agent_cli.providers.chat_completions_planner.log_timeline") as log_timeline_mock:
        planner = ChatCompletionsPlanner(config)
        planner._chat_completion_create(
            model=config.model,
            messages=[{"role": "user", "content": "hello"}],
            stream=False,
        )

    request_call = next(
        call for call in log_timeline_mock.call_args_list
        if call.args[0] == "chat_completions.request_raw"
    )
    assert request_call.kwargs["provider_name"] == "glm"
    assert request_call.kwargs["base_url"] == "https://open.bigmodel.cn/api/paas/v4"

def test_turn_engine_stops_after_interrupted_tool_execution():
    session = _SingleToolSession()
    executor = _InterruptAwareStructuredExecutor()
    engine = TurnEngine(
        session,
        tool_executor=executor,
        command_builder=lambda name, arguments: f"/exec_command --cmd \"{arguments['cmd']}\"",
    )

    result = engine.run(
        user_text="sleep",
        initial_input=[{"role": "user", "content": "sleep"}],
    )

    assert session.send_calls == 1
    assert executor.commands == ['/exec_command --cmd "sleep 5"']
    assert result.assistant_text == REFERENCE_CONVERSATION_INTERRUPTED_TEXT
    assert result.tool_events[-1].name == "interrupted"
    assert any(event.name == "shell" for event in result.tool_events)

def test_chat_completions_turn_engine_command_builder_infers_spawn_agent_defaults():
    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()):
        planner = ChatCompletionsPlanner(_build_config())

    command = planner._turn_engine_command_builder(
        "spawn_agent",
        {
            "task": "并行验证 provider 响应差异",
            "role": "subagent",
            "async": True,
        },
        planner.host_platform,
        plugin_manager_factory=planner.plugin_manager_factory,
    )

    assert command is not None
    assert '"reason": "verify_side_task"' in command
    assert '"mode": "background"' in command
    assert '"wait_required": false' in command
    assert '"task_shape": "read_only"' in command

def test_chat_completions_turn_engine_command_builder_defaults_teammate_to_async_background():
    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()):
        planner = ChatCompletionsPlanner(_build_config())

    command = planner._turn_engine_command_builder(
        "spawn_agent",
        {
            "task": "收集 provider 差异并整理结论",
            "role": "teammate",
        },
        planner.host_platform,
        plugin_manager_factory=planner.plugin_manager_factory,
    )

    assert command is not None
    assert '"async": true' in command
    assert '"mode": "background"' in command
    assert '"wait_required": false' in command
    assert '"task_shape": "read_only"' in command

def test_chat_completions_turn_engine_command_builder_defaults_context_sensitive_teammate_to_sync():
    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()):
        planner = ChatCompletionsPlanner(_build_config())

    command = planner._turn_engine_command_builder(
        "spawn_agent",
        {
            "task": "Continue current task using current context and above conversation",
            "role": "teammate",
        },
        planner.host_platform,
        plugin_manager_factory=planner.plugin_manager_factory,
    )

    assert command is not None
    assert '"mode": "sync"' in command
    assert '"task_shape": "context_sensitive"' in command
    assert '"async": true' not in command

def test_chat_completions_turn_engine_command_builder_defaults_long_running_subagent_to_background():
    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()):
        planner = ChatCompletionsPlanner(_build_config())

    command = planner._turn_engine_command_builder(
        "spawn_agent",
        {
            "task": "运行 benchmark 收集 provider 延迟数据",
            "role": "subagent",
        },
        planner.host_platform,
        plugin_manager_factory=planner.plugin_manager_factory,
    )

    assert command is not None
    assert '"async": true' in command
    assert '"mode": "background"' in command
    assert '"task_shape": "long_running"' in command

def test_chat_completions_turn_engine_command_builder_infers_recover_agent_defaults():
    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()):
        planner = ChatCompletionsPlanner(_build_config())

    command = planner._turn_engine_command_builder(
        "recover_agent",
        {"target": "agent_1"},
        planner.host_platform,
        plugin_manager_factory=planner.plugin_manager_factory,
    )

    assert command == "/recover_agent agent_1 --action retry_step"

def test_chat_completions_turn_engine_command_builder_rewrites_non_blocking_wait_to_agent_workflow():
    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()):
        planner = ChatCompletionsPlanner(_build_config())

    command = planner._turn_engine_command_builder(
        "wait_agent",
        {"target": "agent_1", "wait_required": False, "timeout_ms": 250},
        planner.host_platform,
        plugin_manager_factory=planner.plugin_manager_factory,
    )

    assert command == "/agent_workflow agent_1"

def test_chat_completions_planner_prefers_structured_input_items_over_history():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(assistant_text="planner final")

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.ChatCompletionsSession", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.TurnEngine", return_value=turn_engine_instance):
        planner = ChatCompletionsPlanner(config)
        planner.plan(
            "list files",
            history=[{"role": "assistant", "content": "legacy assistant from history"}],
            tool_executor=_dummy_tool_executor,
            input_items=[
                {"type": "message", "role": "assistant", "content": [{"type": "input_text", "text": "structured assistant"}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "structured user"}]},
            ],
        )

    initial_input = turn_engine_instance.run.call_args.kwargs["initial_input"]
    joined = "\n".join(str(item.get("content") or "") for item in initial_input)
    assert "legacy assistant from history" not in joined
    assert "structured assistant" in joined

def test_chat_completions_planner_history_skips_when_function_call_output_items_present():
    config = _build_config()
    planner = ChatCompletionsPlanner(config)
    history = [{"role": "assistant", "content": "legacy assistant"}]
    input_items = [{"type": "function_call_output", "call_id": "call_1", "output": "{}"}]

    assert planner._history_for_conversation(history, input_items=input_items) == []

def test_chat_completions_planner_history_skips_when_response_items_carry_assistant():
    config = _build_config()
    planner = ChatCompletionsPlanner(config)
    history = [{"role": "assistant", "content": "legacy assistant"}]
    input_items = [
        {
            "type": "response_item",
            "role": "assistant",
            "item": {"role": "assistant", "content": "tool-aware assistant"},
        }
    ]

    assert planner._history_for_conversation(history, input_items=input_items) == []

def test_chat_completions_planner_tool_item_events_include_function_call_output_type():
    config = _build_config()
    planner = ChatCompletionsPlanner(config)
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
        {"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}},
    ]

    extracted = planner._tool_item_events_from_turn_events(turn_events)

    assert len(extracted) == 1
    assert extracted[0]["item"]["type"] == "function_call_output"
    assert extracted[0]["item"]["call_id"] == "call_1"

def test_chat_completions_planner_response_items_emit_messages():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(assistant_text="planner final")

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.ChatCompletionsSession", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.TurnEngine", return_value=turn_engine_instance):
        planner = ChatCompletionsPlanner(config)
        planner.plan(
            "compare results",
            history=[],
            tool_executor=_dummy_tool_executor,
            input_items=[
                {
                    "type": "response_item",
                    "role": "assistant",
                    "item": {
                        "role": "assistant",
                        "content": [{"type": "input_text", "text": "response payload"}],
                    },
                }
            ],
        )

    initial_input = turn_engine_instance.run.call_args.kwargs["initial_input"]
    assert {"role": "assistant", "content": "response payload"} in initial_input

def test_chat_completions_planner_conversation_items_skip_history_when_structured_items_present():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(assistant_text="planner final")

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.ChatCompletionsSession", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.TurnEngine", return_value=turn_engine_instance):
        planner = ChatCompletionsPlanner(config)
        planner.plan(
            "check status",
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

def test_chat_completions_planner_conversation_items_include_history_when_no_structured_items():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(assistant_text="planner final")

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.ChatCompletionsSession", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.TurnEngine", return_value=turn_engine_instance):
        planner = ChatCompletionsPlanner(config)
        planner.plan(
            "check status",
            history=[{"role": "assistant", "content": "legacy assistant"}],
            tool_executor=_dummy_tool_executor,
            input_items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "user turn"}],
                }
            ],
        )

    initial_input = turn_engine_instance.run.call_args.kwargs["initial_input"]
    assert any(item.get("content") == "legacy assistant" for item in initial_input)

def test_chat_completions_planner_uses_response_items_when_turn_engine_text_empty():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="",
        response_items=[response_message_item("assistant", "provider native answer", phase="final_answer")],
        status_hint="llm",
        tool_events=[],
        timings={"initial_model_ms": 8, "planning_rounds": 1, "planning_trace": [], "synthesis_trace": []},
    )

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.ChatCompletionsSession", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.TurnEngine", return_value=turn_engine_instance):
        planner = ChatCompletionsPlanner(config)
        result = planner.plan("hello", history=[], tool_executor=_dummy_tool_executor)

    assert result.assistant_text == "provider native answer"
    assert result.response_items[0].extra["phase"] == "final_answer"

def test_chat_completions_planner_emits_canonical_turn_events_from_turn_engine_items():
    config = _build_config()
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(
        assistant_text="planner final",
        response_items=[response_message_item("assistant", "planner final", phase="final_answer")],
        status_hint="tool",
        tool_events=[ToolEvent(name="list_dir", ok=True, summary="entries=1", payload={"dir_path": "."})],
        turn_events=[
            {"type": "turn.started"},
            {
                "type": "item.started",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "server": "local",
                    "tool": "list_dir",
                    "arguments": {"dir_path": "."},
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "server": "local",
                    "tool": "list_dir",
                    "arguments": {"dir_path": "."},
                    "result": {"content": [{"type": "text", "text": "entries=1"}]},
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "agent_message",
                    "text": "planner final",
                },
            },
            {"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}},
        ],
        timings={"initial_model_ms": 12, "planning_rounds": 1, "planning_trace": [], "synthesis_trace": []},
    )

    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.ChatCompletionsSession", return_value=MagicMock()), \
        patch("cli.agent_cli.providers.chat_completions_planner.TurnEngine", return_value=turn_engine_instance):
        planner = ChatCompletionsPlanner(config)
        result = planner.plan("list files", history=[], tool_executor=_dummy_tool_executor)

    assert result.turn_events[0]["type"] == "turn.started"
    assert result.turn_events[-1]["type"] == "turn.completed"
    assert any(
        event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "mcp_tool_call"
        and event["item"].get("tool") == "list_dir"
        for event in result.turn_events
    )
    assert any(
        event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "agent_message"
        and "planner final" in str(event["item"].get("text") or "")
        for event in result.turn_events
    )

def test_chat_completions_planner_structured_executor_rebases_batch_item_ids():
    config = _build_config()
    planner = ChatCompletionsPlanner(config)

    class _StructuredExecutor:
        def __call__(self, command_text: str):
            return "compat", [ToolEvent(name="list_dir", ok=True, summary=command_text, payload={"command": command_text})]

        def run_structured(self, command_text: str) -> CommandExecutionResult:
            return CommandExecutionResult(
                assistant_text=f"ran: {command_text}",
                tool_events=[ToolEvent(name="list_dir", ok=True, summary=f"ok: {command_text}", payload={"command": command_text})],
                item_events=[
                    {
                        "type": "item.started",
                        "item": {
                            "id": "item_0",
                            "type": "mcp_tool_call",
                            "server": "local",
                            "tool": "list_dir",
                            "arguments": {"command": command_text},
                            "status": "in_progress",
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_0",
                            "type": "mcp_tool_call",
                            "server": "local",
                            "tool": "list_dir",
                            "arguments": {"command": command_text},
                            "status": "completed",
                        },
                    },
                ],
            )

    tool_calls = [
        SimpleNamespace(id="call_1", function=SimpleNamespace(name="list_dir", arguments='{"dir_path":"."}')),
        SimpleNamespace(id="call_2", function=SimpleNamespace(name="list_dir", arguments='{"dir_path":"src"}')),
    ]
    results, _ = planner._execute_tool_call_batch(tool_calls, tool_executor=_StructuredExecutor())

    assert len(results) == 2
    first_ids = [
        str((event.get("item") or {}).get("id") or "")
        for event in list(results[0].get("item_events") or [])
        if isinstance(event, dict)
    ]
    second_ids = [
        str((event.get("item") or {}).get("id") or "")
        for event in list(results[1].get("item_events") or [])
        if isinstance(event, dict)
    ]
    assert first_ids == ["item_0", "item_0"]
    assert second_ids == ["item_1", "item_1"]

def test_chat_completions_planner_item_events_from_turn_events_when_missing():
    config = _build_config()
    planner = ChatCompletionsPlanner(config)

    class _StructuredExecutor:
        def __call__(self, command_text: str):
            return "compat", [ToolEvent(name="list_dir", ok=True, summary="entries", payload={"command": command_text})]

        def run_structured(self, command_text: str) -> CommandExecutionResult:
            return CommandExecutionResult(
                assistant_text="compat",
                tool_events=[ToolEvent(name="list_dir", ok=True, summary="entries", payload={"command": command_text})],
                item_events=[],
                turn_events=[
                    {"type": "turn.started"},
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_0",
                            "type": "mcp_tool_call",
                            "tool": "list_dir",
                            "arguments": {"dir_path": "src"},
                        },
                    },
                    {"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}},
                ],
            )

    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="list_dir", arguments='{"dir_path":"src"}'),
    )
    results, _ = planner._execute_tool_call_batch([tool_call], tool_executor=_StructuredExecutor())
    item_events = [event for event in results[0].get("item_events") or [] if event.get("type") == "item.completed"]
    assert any(event["item"]["tool"] == "list_dir" for event in item_events)

def test_chat_completions_planner_normalizes_legacy_file_alias_batch_commands() -> None:
    config = _build_config()
    planner = ChatCompletionsPlanner(config)
    observed_commands = []

    class _StructuredExecutor:
        def __call__(self, command_text: str):
            observed_commands.append(command_text)
            return "compat", [ToolEvent(name="read_file", ok=True, summary="file loaded", payload={"path": "README.md"})]

        def run_structured(self, command_text: str) -> CommandExecutionResult:
            observed_commands.append(command_text)
            return CommandExecutionResult(
                assistant_text="compat",
                tool_events=[ToolEvent(name="read_file", ok=True, summary="file loaded", payload={"path": "README.md"})],
                item_events=[],
            )

    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="file_read", arguments='{"path":"README.md","offset":3,"limit":5}'),
    )
    results, _ = planner._execute_tool_call_batch([tool_call], tool_executor=_StructuredExecutor())

    assert len(results) == 1
    assert observed_commands == ["/read_file README.md --offset 3 --limit 5"]

def test_chat_completions_planner_synthesis_messages_include_executed_item_events_context() -> None:
    planner = ChatCompletionsPlanner(_build_config())
    messages = planner._synthesis_messages(
        user_text="总结当前 provider 链路",
        executed_events=[
            ToolEvent(
                name="list_dir",
                ok=True,
                summary="entries=1",
                payload={"dir_path": "cli", "entries": [{"index": 1, "kind": "file", "path": "provider.py"}]},
            )
        ],
        executed_item_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "list_dir",
                    "arguments": {"dir_path": "cli"},
                    "result": {"content": [{"type": "text", "text": "E1: [file] provider.py"}]},
                    "status": "completed",
                },
            }
        ],
    )

    content = messages[1]["content"]
    assert "EXECUTED_ITEM_EVENTS_JSON:" in content
    assert '"item_type": "mcp_tool_call"' in content
    assert '"tool": "list_dir"' in content
