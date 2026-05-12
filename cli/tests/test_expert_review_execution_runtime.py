from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import parse_args, run_command_text_result
from cli.agent_cli.runtime_services.expert_review_execution_runtime import (
    run_expert_review,
)


class _NullTools:
    _plugin_manager = None

    @staticmethod
    def run_plugin_command_result(name, arg_text, runtime):
        del name, arg_text, runtime
        return None

    @staticmethod
    def run_plugin_command(name, arg_text, runtime):
        del name, arg_text, runtime
        return None


class _ExpertReviewRuntime:
    def __init__(
        self,
        *,
        provider_status: dict[str, object] | None = None,
        provider_review_gate: dict[str, object] | None = None,
        available_providers: list[dict[str, object]] | None = None,
        reviewer_output: str = "",
    ) -> None:
        self.tools = _NullTools()
        self.history = []
        self.history_turns = [
            {
                "turn_id": "turn_1",
                "user_text": "请检查最新答案是否有证据问题。",
                "assistant_text": "我已经完成实现，并补了基本测试。",
                "turn_events": [],
            }
        ]
        self._provider_status = dict(
            provider_status
            or {
                "provider_name": "openai",
                "provider_model": "gpt-5.4",
                "provider_reasoning_effort": "high",
                "provider_label": "openai | gpt-5.4 | tool-calls",
            }
        )
        self._provider_review_gate = dict(
            provider_review_gate
            or {
                "expert_review_available": True,
                "expert_review_unavailable_reason": "-",
                "primary_provider_name": "openai",
            }
        )
        self._available_providers = list(
            available_providers
            or [
                {
                    "provider_name": "openai",
                    "config_provider_name": "openai",
                    "default_model": "gpt_54",
                    "provider_default_model_id": "gpt-5.4",
                    "provider_base_eligible": True,
                    "availability_status": "available",
                    "provider_status_state": "ready",
                },
                {
                    "provider_name": "anthropic",
                    "config_provider_name": "anthropic",
                    "default_model": "claude_opus",
                    "provider_default_model_id": "claude-opus-4.1",
                    "provider_base_eligible": True,
                    "availability_status": "available",
                    "provider_status_state": "ready",
                },
            ]
        )
        self._reviewer_output = reviewer_output or (
            '{"verdict":"revise","confidence":"high","summary":"Need one supporting citation.",'
            '"recommended_action":"revise_and_recheck","findings":[{"severity":"high","category":"evidence",'
            '"title":"Missing citation","detail":"No supporting source."}]}'
        )
        self.spawn_calls: list[dict[str, object]] = []
        self.wait_calls: list[dict[str, object]] = []
        self.agent = SimpleNamespace(
            provider_status=self.provider_status,
            provider_review_gate=self.provider_review_gate,
            available_providers=self.available_providers,
            resolve_delegate_execution=self.resolve_delegate_execution,
        )

    def provider_status(self) -> dict[str, object]:
        return dict(self._provider_status)

    def provider_review_gate(self) -> dict[str, object]:
        return dict(self._provider_review_gate)

    def available_providers(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._available_providers]

    @staticmethod
    def resolve_delegate_execution(role, *, model=None, provider=None, reasoning_effort=None, timeout=None):
        del timeout
        assert role == "subagent"
        return SimpleNamespace(
            config=SimpleNamespace(
                provider_name=provider or "anthropic",
                model="claude-opus-4.1" if provider == "anthropic" else (model or "claude-opus-4.1"),
                reasoning_effort=reasoning_effort or "high",
            ),
            timeout=45,
            source="call_override",
        )

    def spawn_agent_result(self, **kwargs) -> CommandExecutionResult:
        self.spawn_calls.append(dict(kwargs))
        return CommandExecutionResult(
            assistant_text="delegated agent reviewer_1 started",
            tool_events=[
                ToolEvent(
                    name="spawn_agent",
                    ok=True,
                    summary="spawn_agent started",
                    payload={"agent_id": "reviewer_1", "status": "queued"},
                )
            ],
        )

    def wait_agent_result(self, agent_id, **kwargs) -> CommandExecutionResult:
        self.wait_calls.append({"agent_id": agent_id, **dict(kwargs)})
        return CommandExecutionResult(
            assistant_text=self._reviewer_output,
            tool_events=[
                ToolEvent(
                    name="wait_agent",
                    ok=True,
                    summary="wait_agent completed",
                    payload={
                        "status": "completed",
                        "text": self._reviewer_output,
                        "wait_timed_out": False,
                    },
                )
            ],
        )

    @staticmethod
    def _snapshot_thread_state() -> dict[str, object]:
        return {
            "approval_policy": "never",
            "sandbox_mode": "danger-full-access",
            "changed_files": ["agent_cli/runtime_core/command_handlers.py"],
            "diff_summary": "Wired expert_review runtime execution.",
        }

    @staticmethod
    def _is_interrupt_requested():
        return False

    @staticmethod
    def _interrupt_tuple():
        return ("interrupted", [])

    @staticmethod
    def _parse_args(arg_text):
        return parse_args(arg_text)


def test_run_expert_review_success_path_uses_delegate_spawn_wait_and_emits_turn_events() -> None:
    runtime = _ExpertReviewRuntime()

    result = run_expert_review(
        runtime,
        task="Review the latest answer for evidence gaps.",
        focus=["evidence", "correctness"],
        strictness="high",
    )

    assert runtime.spawn_calls
    assert runtime.spawn_calls[0]["provider"] == "anthropic"
    assert runtime.spawn_calls[0]["model"] == "claude_opus"
    assert runtime.spawn_calls[0]["reasoning_effort"] == "high"
    assert runtime.spawn_calls[0]["async_mode"] is True
    assert runtime.spawn_calls[0]["reason"] == "expert_review"
    assert runtime.spawn_calls[0]["task_shape"] == "read_only"
    assert runtime.wait_calls == [
        {
            "agent_id": "reviewer_1",
            "timeout_ms": 45000,
            "reason": "wait_for_child_result",
        }
    ]
    assert result.tool_events[0].name == "expert_review"
    assert result.tool_events[0].ok is True
    assert result.tool_events[0].payload["status"] == "ok"
    assert result.tool_events[0].payload["structured_payload"]["verdict"] == "revise"
    assert result.tool_events[0].payload["structured_payload"]["reviewer"]["provider"] == "anthropic"
    assert result.tool_events[0].payload["structured_payload"]["reviewer"]["model"] == "claude-opus-4.1"
    assert "reviewer_provider" not in result.tool_events[0].payload["structured_payload"]
    assert "reviewer_model" not in result.tool_events[0].payload["structured_payload"]
    assert result.tool_events[0].payload["reviewer_selection"]["provider"] == "anthropic"
    assert result.tool_events[0].payload["reviewer_selection"]["reviewer_reasoning_strategy"] == "anthropic_reasoning_effort"
    assert result.tool_events[0].payload["reviewer_selection"]["reviewer_reasoning_effort"] == "high"
    assert result.tool_events[0].payload["reviewer_selection"]["reasoning_capability_validation"] == "static_matrix"
    assert result.tool_events[0].payload["reviewer_selection"]["reasoning_capability_warning_present"] is False
    assert [event["type"] for event in result.item_events] == [
        "item.started",
        "item.updated",
        "item.completed",
    ]
    assert result.item_events[-1]["item"]["type"] == "expert_review"
    assert result.item_events[-1]["item"]["outcome"]["verdict"] == "revise"
    assert "verdict=revise" in result.assistant_text
    assert "findings=1" in result.assistant_text


def test_run_expert_review_gate_failure_returns_failed_item_event_without_delegate_calls() -> None:
    runtime = _ExpertReviewRuntime(
        provider_review_gate={
            "expert_review_available": False,
            "expert_review_unavailable_reason": "insufficient_eligible_providers",
            "primary_provider_name": "openai",
        },
        available_providers=[
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "default_model": "gpt_54",
                "provider_default_model_id": "gpt-5.4",
                "provider_base_eligible": True,
                "availability_status": "available",
                "provider_status_state": "ready",
            }
        ],
    )

    result = run_expert_review(runtime, task="Review the latest answer.")

    assert runtime.spawn_calls == []
    assert runtime.wait_calls == []
    assert result.tool_events[0].ok is False
    assert result.tool_events[0].payload["structured_payload"]["error_code"] == "expert_review_no_eligible_provider"
    assert [event["type"] for event in result.item_events] == ["item.started", "item.completed"]
    assert result.item_events[-1]["item"]["status"] == "failed"
    assert result.item_events[-1]["item"]["outcome"]["error_code"] == "expert_review_no_eligible_provider"


def test_run_expert_review_parse_failure_returns_canonical_parse_error() -> None:
    runtime = _ExpertReviewRuntime(reviewer_output="review complete but no structured verdict")

    result = run_expert_review(runtime, task="Review the latest answer.")

    assert result.tool_events[0].ok is False
    assert result.tool_events[0].payload["structured_payload"]["error_code"] == "expert_review_parse_failed"
    assert result.item_events[-1]["item"]["status"] == "failed"
    assert result.item_events[-1]["item"]["outcome"]["error_code"] == "expert_review_parse_failed"
    assert "error_code=expert_review_parse_failed" in result.assistant_text


def test_run_expert_review_delegate_runtime_error_returns_canonical_delegate_failure() -> None:
    runtime = _ExpertReviewRuntime()

    def _raise_delegate_failure(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("delegated agent unavailable for role: subagent")

    runtime.agent.resolve_delegate_execution = _raise_delegate_failure

    result = run_expert_review(runtime, task="Review the latest answer.")

    assert result.tool_events[0].ok is False
    assert result.tool_events[0].payload["structured_payload"]["error_code"] == "expert_review_delegate_failed"
    assert result.item_events[-1]["item"]["status"] == "failed"


def test_run_expert_review_does_not_swallow_programming_errors() -> None:
    runtime = _ExpertReviewRuntime()

    with patch(
        "cli.agent_cli.runtime_services.expert_review_execution_runtime.build_expert_review_packet",
        side_effect=TypeError("packet contract bug"),
    ):
        with pytest.raises(TypeError, match="packet contract bug"):
            run_expert_review(runtime, task="Review the latest answer.")


def test_run_command_text_result_supports_expert_review_slash_command() -> None:
    runtime = _ExpertReviewRuntime()

    result = run_command_text_result(
        runtime,
        '/expert_review \'{"task":"Review latest answer","focus":["correctness"],"strictness":"high"}\'',
    )

    assert result.tool_events[0].name == "expert_review"
    assert result.tool_events[0].payload["request"]["task"] == "Review latest answer"
    assert result.tool_events[0].payload["request"]["focus"] == ["correctness"]
    assert result.tool_events[0].payload["request"]["strictness"] == "high"
    assert [event["type"] for event in result.item_events] == [
        "item.started",
        "item.updated",
        "item.completed",
    ]
