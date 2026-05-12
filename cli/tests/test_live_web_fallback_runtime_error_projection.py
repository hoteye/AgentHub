from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.agent_plan_runtime_helpers import plan_with_provider_and_fallback
from cli.agent_cli.agent_runtime import intent_with_protocol_path
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.models import AgentIntent


class _PlannerRaises503:
    def plan(self, user_text: str, history: List[Dict[str, str]], **kwargs: Any) -> AgentIntent:
        del user_text, history, kwargs
        raise RuntimeError("InternalServerError: Error code: 503 - proxy_unavailable")

    def public_summary(self) -> Dict[str, Any]:
        return {
            "provider_name": "openai",
            "model": "gpt-5.4",
        }


class _AgentStub:
    def __init__(self) -> None:
        self.host_platform = current_host_platform()
        self._planner = _PlannerRaises503()
        self._planner_error: Optional[str] = None
        self._planner_runtime_error: Optional[str] = None
        self._planner_runtime_error_diagnostics: Dict[str, Any] | None = None
        self._provider_availability_registry = None

    def _filter_callable_kwargs(self, handler: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        del handler
        return dict(kwargs)

    def _planner_is_replay_runtime(self) -> bool:
        return False

    def _intent_with_protocol_path(self, intent: AgentIntent, **kwargs: Any) -> AgentIntent:
        return intent_with_protocol_path(intent, **kwargs)

    def _live_web_fallback_intent(self, text: str, *, tool_executor: Any = None) -> AgentIntent | None:
        del text, tool_executor
        return AgentIntent(
            assistant_text="live-fallback-ok",
            commentary_text="这是实时信息查询，我先做网页搜索。",
        )

    def _match_shell_intent(self, text: str, normalized: str) -> AgentIntent | None:
        del text, normalized
        return None

    def _planner_runtime_error_diagnostic_lines(self) -> List[str]:
        return [
            "503 请求结构诊断:",
            "- input[5] previous_turn_function_call: call_id=item_1 是本地合成 id。",
        ]

    def _planner_fallback_text(self) -> str:
        return "planner-fallback"


def test_live_web_fallback_exposes_provider_runtime_error_diagnostics() -> None:
    agent = _AgentStub()

    intent = plan_with_provider_and_fallback(
        agent,
        "https://example.com/status",
        history=[],
        tool_executor=None,
    )

    assert intent.assistant_text == "live-fallback-ok"
    assert "主 provider 本轮失败，已切换到 live_web_fallback。" in intent.commentary_text
    assert "provider_error=RuntimeError: InternalServerError: Error code: 503 - proxy_unavailable" in intent.commentary_text
    assert "503 请求结构诊断:" in intent.commentary_text

    protocol_path = dict(intent.protocol_diagnostics.get("protocol_path") or {})
    assert protocol_path.get("kind") == "host_short_circuit_live_web_fallback"
    assert protocol_path.get("reason") == "live_web_fallback"
    assert (
        intent.protocol_diagnostics.get("provider_runtime_error")
        == "RuntimeError: InternalServerError: Error code: 503 - proxy_unavailable"
    )
    assert intent.protocol_diagnostics.get("provider_runtime_error_diagnostics") == [
        "503 请求结构诊断:",
        "- input[5] previous_turn_function_call: call_id=item_1 是本地合成 id。",
    ]
