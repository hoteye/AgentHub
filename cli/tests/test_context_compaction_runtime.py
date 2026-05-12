from __future__ import annotations

from cli.agent_cli.models import AgentIntent
from cli.agent_cli.runtime_services import (
    context_compaction_runtime,
    prompt_turn_history_state_runtime,
)


class _CompactionAgent:
    def __init__(
        self,
        *,
        summary: str = "",
        raise_error: bool = False,
        context_window: int = 100,
        auto_compact_token_limit: int = 0,
    ) -> None:
        self.summary = summary
        self.raise_error = raise_error
        self.calls: list[dict] = []
        self._planner = object()
        self.context_window = context_window
        self.auto_compact_token_limit = auto_compact_token_limit

    def provider_status(self) -> dict[str, str]:
        status = {
            "provider_ready": "true",
            "provider_name": "openai",
            "provider_model": "gpt-test",
            "model_context_window": str(self.context_window),
        }
        if self.auto_compact_token_limit > 0:
            status["model_auto_compact_token_limit"] = str(self.auto_compact_token_limit)
        return status

    def plan(self, text: str, history=None, **kwargs) -> AgentIntent:
        self.calls.append(
            {"text": text, "history": list(history or []), "kwargs": dict(kwargs or {})}
        )
        if self.raise_error:
            raise RuntimeError("summary provider unavailable")
        return AgentIntent(assistant_text=self.summary)


class _Runtime:
    _PLANNER_HISTORY_LIMIT_MESSAGES = 24
    _AUTO_COMPACT_TRIGGER_ITEMS = 999
    _AUTO_COMPACT_TRIGGER_TOKENS = 20
    _AUTO_COMPACT_TOKEN_THRESHOLD_PERCENT = 90
    _MODEL_COMPACT_SOURCE_MAX_CHARS = 12_000

    def __init__(self, *, agent: _CompactionAgent) -> None:
        self.agent = agent
        self.thread_store = None
        self.thread_id = "thread-test"
        self.rollout_items: list[dict] = []
        self.history_turns = [
            {
                "user_text": "用户要求修复 provider 配置漂移",
                "assistant_text": "已经修改 provider helper 并补充测试",
                "protocol_diagnostics": {"protocol_path": {"provider_used": True}},
            }
        ]
        self.reference_context_items = [{"label": "old"}]
        self._environment_context_snapshot = {"cwd": "/tmp/demo"}
        self._environment_context_history = [{"role": "user", "content": "env"}]
        self._workspace_context_snapshot = {"workspace": "old"}
        self._memory_context_snapshot = {"memory": "old"}
        self._context_update_history = [{"role": "user", "content": "ctx"}]
        self._base_history: list[dict[str, str]] = []
        self.history: list[dict[str, str]] = []
        self._planner_input_items: list[dict] = []

    @staticmethod
    def _filter_handler_kwargs(handler, kwargs):
        del handler
        return dict(kwargs or {})

    @staticmethod
    def _turn_used_provider(turn):
        return bool(
            ((turn or {}).get("protocol_diagnostics") or {})
            .get("protocol_path", {})
            .get("provider_used", True)
        )

    @staticmethod
    def _normalized_history_item(item):
        role = str((item or {}).get("role") or "").strip()
        content = str((item or {}).get("content") or "").strip()
        if not role or not content:
            return None
        return {"role": role, "content": content}

    @staticmethod
    def _planner_message_input_item(role, content):
        return {
            "type": "message",
            "role": role,
            "content": [{"type": "input_text", "text": content}],
        }

    def _planner_message_history_input_items(self, history):
        return [
            self._planner_message_input_item(item["role"], item["content"])
            for item in list(history or [])
        ]

    def _planner_base_history_input_items(self):
        return self._planner_message_history_input_items(self._base_history)

    def _planner_history(self):
        return list(self._base_history)

    def _planner_conversation_item_count(self):
        return len(self.history_turns) * 2

    def _planner_conversation_input_items(self):
        return [
            self._planner_message_input_item("user", str(turn.get("user_text") or ""))
            for turn in self.history_turns
        ]

    def _build_auto_compaction_replacement_history(
        self, *, instructions="", prefer_model_summary=False
    ):
        return context_compaction_runtime.build_compaction_replacement_history(
            self,
            instructions=instructions,
            prefer_model_summary=prefer_model_summary,
        )

    def _apply_compaction_state(self, replacement_history):
        prompt_turn_history_state_runtime.apply_compaction_state(self, replacement_history)


def test_model_summary_compaction_uses_provider_summary_and_records_metadata() -> None:
    runtime = _Runtime(
        agent=_CompactionAgent(summary="目标：修复 provider 配置漂移。下一步：跑 AB 测试。")
    )

    result = prompt_turn_history_state_runtime.compact_history(
        runtime,
        reason="manual_compact",
        trigger="manual",
        instructions="保留下一步",
        prefer_model_summary=True,
    )

    assert result["ok"] is True
    compacted = runtime.rollout_items[-1]
    assert compacted["summary_strategy"] == "model"
    assert compacted["instructions"] == "保留下一步"
    assert compacted["replacement_history"] == [
        {
            "role": "assistant",
            "content": "Previous conversation summary:\n目标：修复 provider 配置漂移。下一步：跑 AB 测试。",
        }
    ]
    assert runtime.history_turns == []
    assert runtime.agent.calls


def test_model_summary_failure_falls_back_to_deterministic_summary() -> None:
    runtime = _Runtime(agent=_CompactionAgent(raise_error=True))

    result = prompt_turn_history_state_runtime.compact_history(
        runtime,
        reason="manual_compact",
        trigger="manual",
        prefer_model_summary=True,
    )

    assert result["ok"] is True
    compacted = runtime.rollout_items[-1]
    assert compacted["summary_strategy"] == "deterministic"
    assert "summary provider unavailable" in compacted["model_summary_error"]
    assert (
        "1. user: 用户要求修复 provider 配置漂移" in compacted["replacement_history"][0]["content"]
    )


def test_auto_compaction_prefers_token_threshold_and_records_token_metadata() -> None:
    runtime = _Runtime(agent=_CompactionAgent(summary="压缩摘要", context_window=10_000))
    runtime._AUTO_COMPACT_TRIGGER_TOKENS = 1
    runtime._AUTO_COMPACT_TRIGGER_ITEMS = 999

    prompt_turn_history_state_runtime.maybe_auto_compact_history(runtime)

    compacted = runtime.rollout_items[-1]
    assert compacted["reason"] == "auto_pre_turn_token_limit"
    assert compacted["summary_strategy"] == "model"
    assert compacted["estimated_tokens"] >= 1
    assert compacted["trigger_tokens"] == 1
    assert compacted["context_window"] == 10_000
    assert (
        compacted["replacement_history"][0]["content"] == "Previous conversation summary:\n压缩摘要"
    )


def test_auto_compaction_uses_provider_auto_compact_limit_before_percent_window() -> None:
    runtime = _Runtime(
        agent=_CompactionAgent(
            summary="压缩摘要",
            context_window=258_400,
            auto_compact_token_limit=244_800,
        )
    )
    runtime._AUTO_COMPACT_TRIGGER_TOKENS = 0
    runtime._AUTO_COMPACT_TRIGGER_ITEMS = 999

    decision = context_compaction_runtime.auto_compaction_decision(runtime)

    assert decision["trigger_tokens"] == 244_800
    assert decision["context_window"] == 258_400


def test_auto_compaction_without_model_context_window_keeps_item_count_fallback() -> None:
    runtime = _Runtime(agent=_CompactionAgent(summary="压缩摘要", context_window=0))
    runtime._AUTO_COMPACT_TRIGGER_TOKENS = 0
    runtime._AUTO_COMPACT_TRIGGER_ITEMS = 1

    decision = context_compaction_runtime.auto_compaction_decision(runtime)

    assert decision["trigger_tokens"] == 0
    assert decision["context_window"] == 0
    assert decision["will_run"] is True
    assert decision["trigger_reason"] == "auto_pre_turn_history_limit"
