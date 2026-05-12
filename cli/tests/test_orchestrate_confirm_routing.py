from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.models import AgentIntent
from cli.agent_cli.orchestration import taskbook_runtime as taskbook_runtime_service
from cli.agent_cli.runtime_core import run_command_text_result
from cli.agent_cli.runtime_core.local_routing import looks_like_orchestrate_confirm_request


class _PlannerStub:
    def __init__(self, assistant_text: str = "planner handled") -> None:
        self.assistant_text = assistant_text
        self.calls: list[str] = []

    def plan(self, text, history, *, tool_executor=None, attachments=None, input_items=None, prompt_cache_key=None, turn_event_callback=None):
        del history, tool_executor, attachments, input_items, prompt_cache_key, turn_event_callback
        self.calls.append(text)
        return AgentIntent(assistant_text=self.assistant_text)


class _RoutingAgent(RuleBasedAgent):
    def __init__(self, *, planner=None) -> None:
        self.host_platform = current_host_platform()
        self.cwd = Path("/tmp")
        self._plugin_manager_factory = None
        self._planner = planner
        self._planner_managed = False
        self._planner_error = None
        self._planner_runtime_error = None
        self._planner_runtime_error_diagnostics = None
        self._runtime_policy_overrides = {}
        self._session_provider_env_overrides = {}
        self._session_route_overrides = {}
        self._session_delegation_overrides = {}
        self._provider_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

    def set_cwd(self, cwd):
        self.cwd = Path(cwd).resolve()
        return self.cwd

    def provider_status(self) -> dict[str, str]:
        return {
            "provider_name": "openai",
            "provider_model": "gpt-5.4",
            "provider_reasoning_effort": "high",
        }


class _PromptRuntimeStub:
    def __init__(self, root: Path, agent: RuleBasedAgent) -> None:
        self.cwd = Path(root)
        self.thread_id = "thread_taskbook_routing"
        self.agent = agent
        self.request_payloads: list[dict] = []
        self._request_responses: list[dict | None] = []
        self.request_user_input_handler = self._request_user_input_handler
        self._orchestration_runtime_services_cache = None
        self._orchestration_runtime_services_cwd = ""

    def queue_request_response(self, response: dict | None) -> None:
        self._request_responses.append(response)

    def _request_user_input_handler(self, payload: dict) -> dict | None:
        self.request_payloads.append(dict(payload or {}))
        if not self._request_responses:
            return None
        return self._request_responses.pop(0)

    def _run_command_text_result(self, text: str):
        return run_command_text_result(self, text)


def _line_value(text: str, key: str) -> str:
    prefix = f"{key}="
    for raw_line in str(text or "").splitlines():
        line = str(raw_line or "").strip()
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def test_looks_like_orchestrate_confirm_request_detects_explicit_mode_requests() -> None:
    assert looks_like_orchestrate_confirm_request("我想用任务书模式执行当前大文件拆解任务，请帮我用任务书模式完成。")
    assert looks_like_orchestrate_confirm_request("Use taskbook mode for this refactor and let me confirm before starting.")
    assert not looks_like_orchestrate_confirm_request("任务书模式和普通模式有什么区别？")


def test_rule_based_agent_does_not_short_circuit_taskbook_mode_natural_language_request() -> None:
    planner = _PlannerStub()
    agent = _RoutingAgent(planner=planner)

    intent = agent.plan(
        "请用任务书模式执行这个任务，先给我确认。",
        history=[{"role": "user", "content": "拆分 cli/agent_cli/runtime_core/orchestration_commands.py 并补测试"}],
    )

    assert planner.calls == ["请用任务书模式执行这个任务，先给我确认。"]
    assert intent.command_text is None
    assert intent.assistant_text == "planner handled"
    assert intent.protocol_diagnostics["protocol_path"]["source"] == "provider"


def test_rule_based_agent_does_not_hijack_taskbook_discussion() -> None:
    planner = _PlannerStub("planner kept control")
    agent = _RoutingAgent(planner=planner)

    intent = agent.plan("任务书模式和普通模式有什么区别？", history=[])

    assert planner.calls == ["任务书模式和普通模式有什么区别？"]
    assert intent.command_text is None
    assert intent.assistant_text == "planner kept control"
    assert intent.protocol_diagnostics["protocol_path"]["source"] == "provider"


def test_explicit_orchestrate_confirm_command_runs_confirm_flow_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = _RoutingAgent(planner=_PlannerStub())
        agent.set_cwd(tmpdir)
        runtime = _PromptRuntimeStub(Path(tmpdir), agent)
        runtime.queue_request_response(
            {"answers": {"taskbook_action": {"answers": ["Confirm and start"]}}}
        )
        result = run_command_text_result(
            runtime,
            "/orchestrate_confirm 拆分 policy_grounding.py 并补最小回归测试",
        )

        assert "orchestration confirmation accepted" in result.assistant_text
        run_id = _line_value(result.assistant_text, "run_id")
        services = taskbook_runtime_service.runtime_services(runtime)
        run = services.storage.read_run(run_id)

        assert run is not None
        assert run.objective == "拆分 policy_grounding.py 并补最小回归测试"
        assert len(runtime.request_payloads) == 1
