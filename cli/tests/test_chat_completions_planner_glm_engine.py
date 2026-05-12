from __future__ import annotations

import copy
from types import SimpleNamespace

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.providers.chat_completions_planner import ChatCompletionsPlanner
from cli.agent_cli.providers.config_catalog import ProviderConfig

class _FakeChatCompletions:
    def __init__(self, scripted_items: list[object]) -> None:
        self.scripted_items = list(scripted_items)
        self.requests: list[dict] = []
        self.calls = 0

    def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        item = self.scripted_items[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(choices=[SimpleNamespace(message=item)])

def _tool_call(call_id: str, name: str, arguments: str):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )

def _planner() -> ChatCompletionsPlanner:
    return ChatCompletionsPlanner(
        ProviderConfig(
            model="glm-5",
            api_key="sk-test",
            provider_name="glm",
            planner_kind="openai_chat",
            base_url="https://open.bigmodel.cn/api/paas/v4",
        ),
        host_platform=detect_host_platform(system_name="Linux", sys_platform="linux"),
    )

def test_glm_chat_completions_planner_uses_turn_engine_for_tool_loop():
    planner = _planner()
    completions = _FakeChatCompletions(
        [
            SimpleNamespace(content="", tool_calls=[_tool_call("call_1", "read_file", '{"file_path":"README.md"}')]),
            SimpleNamespace(content="README 已读取。", tool_calls=[]),
        ]
    )
    planner.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    def _executor(command_text: str):
        assert command_text == "/read_file README.md"
        return "执行完成", [ToolEvent(name="read_file", ok=True, summary="file read ok", payload={"file_path": "README.md", "path": "README.md"})]

    intent = planner.plan("读取 README", [], tool_executor=_executor)

    assert intent.assistant_text == "README 已读取。"
    assert intent.status_hint == "tool"
    assert len(intent.tool_events) == 1
    assert intent.timings["planning_rounds"] == 2
    assert intent.timings["synthesis_rounds"] == 0
    assert completions.requests[1]["messages"][2]["role"] == "assistant"
    assert completions.requests[1]["messages"][3]["role"] == "tool"

def test_glm_chat_completions_planner_synthesizes_after_continuation_failure():
    planner = _planner()
    completions = _FakeChatCompletions(
        [
            SimpleNamespace(content="", tool_calls=[_tool_call("call_1", "list_dir", '{"dir_path":".","limit":5}')]),
            RuntimeError("proxy_unavailable"),
            RuntimeError("proxy_unavailable"),
            RuntimeError("proxy_unavailable"),
            RuntimeError("proxy_unavailable"),
            RuntimeError("proxy_unavailable"),
            SimpleNamespace(content="这是一个 AgentHub 项目。", tool_calls=[]),
        ]
    )
    planner.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    def _executor(command_text: str):
        assert command_text
        return "执行完成", [ToolEvent(name="list_dir", ok=True, summary="entries=1", payload={"dir_path": ".", "entries": []})]

    intent = planner.plan("你看看当前项目是干什么的", [], tool_executor=_executor)

    assert intent.assistant_text == "这是一个 AgentHub 项目。"
    assert intent.status_hint == "tool"
    assert len(intent.tool_events) == 1
    assert intent.timings["planning_rounds"] == 1
    assert intent.timings["synthesis_rounds"] == 1
    assert len(completions.requests) == 7
    assert "tools" not in completions.requests[6]
    assert "TOOL_RESULT_SUMMARY" in completions.requests[6]["messages"][1]["content"]
