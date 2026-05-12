from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.memory_context_runtime import memory_context_turn_update
from cli.agent_cli.memory_events import MEMORY_AUDIT_EVENT_TAXONOMY
from cli.agent_cli.runtime_services import runtime_response_runtime


class _RuntimeStub:
    def __init__(self) -> None:
        self.thread_id = "thread_1"
        self.thread_name = "Memory Test"
        self.cwd = "/tmp/work"
        self.selected_conversation = None
        self.pending_send_text = ""
        self.send_ready = False
        self.runtime_policy = SimpleNamespace(
            approval_policy="never",
            sandbox_mode="danger-full-access",
            web_search_mode="auto",
            network_access_enabled=True,
        )
        self.agent = SimpleNamespace(
            provider_status=lambda: {"provider_name": "openai", "provider_model": "gpt-test"},
            session_route_overrides=lambda: {},
            session_delegate_overrides=lambda: {},
        )
        self._workspace_context_snapshot = {"instructions_digest": "abc"}
        self._environment_context_snapshot = {"shell": "bash"}
        self._memory_context_snapshot = {"recalled_count": 1, "recalled_ids": ["mem_1"]}
        self._environment_context_history = []
        self._context_update_history = []
        self._delegated_agent_state_snapshot = lambda: {}
        self.runtime_policy_status = lambda: {
            "approval_policy": "never",
            "sandbox_mode": "danger-full-access",
            "web_search_mode": "auto",
            "network_access_enabled": True,
        }
        self.approval_status = lambda: {}


def test_snapshot_thread_state_includes_memory_context_snapshot() -> None:
    runtime = _RuntimeStub()
    payload = runtime_response_runtime.snapshot_thread_state(runtime)
    assert payload["memory_context_snapshot"] == {"recalled_count": 1, "recalled_ids": ["mem_1"]}


class _StoreStub:
    def __init__(self, memories):
        self._memories = list(memories)
        self.hit_ids = []

    def list_memories(self, *, limit: int = 200, status: str = "active"):
        del status
        return list(self._memories)[:limit]

    def record_memory_hit(self, memory_id: str) -> bool:
        self.hit_ids.append(memory_id)
        return True


class _RuntimeMemoryStub:
    def __init__(self, memories):
        self.cwd = "/tmp/work/repo"
        self._memory_store = _StoreStub(memories)
        self._memory_context_limit = 3
        self._base_history = [{"role": "user", "content": "remember deployment constraints in service/api.py"}]
        self.history_turns = []


def test_memory_context_turn_update_exposes_ranking_and_recalled_ids() -> None:
    runtime = _RuntimeMemoryStub([{"memory_id": "mem_alpha", "memory_type": "project", "status": "active"}])
    recalled_payload = {
        "memory": {"memory_id": "mem_alpha", "memory_type": "project"},
        "score": 5.5,
        "reasons": ["path_overlap:service/api.py", "keyword_overlap:deployment"],
        "excerpt": "Use canary rollout for api deploys",
        "query_terms": ["deployment", "service/api.py"],
        "query_paths": ["service/api.py"],
        "reference_context_item": {
            "item_type": "memory",
            "source": "runtime:memory_store",
            "label": "project_memory",
            "path": "memory://mem_alpha",
            "description": "recalled by relevance",
            "metadata": {
                "memory_id": "mem_alpha",
                "memory_type": "project",
                "score": 5.5,
                "reasons": ["path_overlap:service/api.py", "keyword_overlap:deployment"],
            },
        },
    }
    with patch("cli.agent_cli.memory_context_runtime.recall_memories_for_turn", return_value=[recalled_payload]):
        _messages, context_items, snapshot = memory_context_turn_update(runtime)

    assert len(context_items) == 1
    assert snapshot["recalled_ids"] == ["mem_alpha"]
    assert snapshot["blocked"] is False
    assert snapshot["blocked_reason"] == ""
    assert snapshot["query_paths"] == ["service/api.py"]
    assert snapshot["recalled_types"] == ["project"]
    assert snapshot["ranking_explainability"][0]["memory_id"] == "mem_alpha"
    assert snapshot["ranking_explainability"][0]["rank"] == 1
    assert snapshot["ranking_explainability"][0]["score"] == 5.5
    assert snapshot["ranking_explainability"][0]["selected"] is True
    assert snapshot["recall_latency_ms"] >= 0
    assert snapshot["audit_events"][0]["event_type"] == "memory_recall_evaluated"
    assert snapshot["audit_events"][0]["event_type"] in MEMORY_AUDIT_EVENT_TAXONOMY
    assert snapshot["audit_events"][0]["recalled_ids"] == ["mem_alpha"]
    assert snapshot["metrics_baseline"]["recall_precision_proxy"] == 1.0
    assert snapshot["metrics_baseline"]["recall_block_rate"] == 0.0
    assert runtime._memory_store.hit_ids == ["mem_alpha"]


def test_memory_context_turn_update_blocked_reason_when_no_active_memories() -> None:
    runtime = _RuntimeMemoryStub([])
    _messages, context_items, snapshot = memory_context_turn_update(runtime)

    assert context_items == []
    assert snapshot["recalled_count"] == 0
    assert snapshot["blocked"] is True
    assert snapshot["blocked_reason"] == "no_active_memories"
    assert snapshot["ranking_explainability"] == []
    assert snapshot["audit_events"][0]["event_type"] == "memory_recall_blocked"
    assert snapshot["audit_events"][0]["blocked"] is True
    assert snapshot["metrics_baseline"]["overall_block_rate"] == 1.0
