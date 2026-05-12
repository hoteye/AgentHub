from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.models import ReferenceContextItem
from cli.agent_cli.runtime_services import prompt_turn_context_runtime
from cli.agent_cli.runtime_services import runtime_context_runtime


class _RuntimeStub:
    def __init__(self) -> None:
        self.cwd = "/tmp/work"
        self.tools = SimpleNamespace(_plugin_manager=None)
        self.agent = SimpleNamespace(provider_status=lambda: {"provider_model": "gpt-test"})
        self.runtime_policy = SimpleNamespace(
            approval_policy="never",
            sandbox_mode="danger-full-access",
            network_access_enabled=True,
        )
        self._workspace_context_snapshot = {}
        self._forced_workspace_context_snapshot = {
            "cwd": "/tmp/work",
            "trust_level": "trusted",
            "instructions_text": "workspace rules",
            "instructions_digest": "digest-workspace",
            "docs": [{"path": "/tmp/work/AENGTHUB.md", "size": 10, "mtime_ns": 1}],
            "skills": [],
        }
        self._memory_context_snapshot = {}
        self._base_history = [{"role": "user", "content": "remember api endpoint"}]
        self.history_turns = []
        self._current_dt_provider = None
        self._forced_environment_context_snapshot = {
            "cwd": "/tmp/work",
            "shell": "bash",
            "current_date": "2026-04-09",
            "timezone": "Asia/Shanghai",
        }
        self._planner_input_items: list[dict] = []

    @staticmethod
    def _normalized_history_item(item):
        if not isinstance(item, dict):
            return None
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"system", "developer", "user", "assistant"} or not content:
            return None
        return {"role": role, "content": content}

    @staticmethod
    def _planner_conversation_input_items() -> list[dict]:
        return []

    @staticmethod
    def _planner_message_history_input_items(history):
        items = []
        for entry in list(history or []):
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "system").strip().lower() or "system"
            content = str(entry.get("content") or "").strip()
            if not content:
                continue
            items.append(
                {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text", "text": content}],
                }
            )
        return items

    def _planner_context_input_items(self, **kwargs):
        self._planner_context_kwargs = dict(kwargs)
        return [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "dev"}]}]

    @staticmethod
    def web_access_allowed() -> bool:
        return True


def test_workspace_context_turn_update_includes_memory_items_additively() -> None:
    runtime = _RuntimeStub()
    memory_item = ReferenceContextItem(
        item_type="memory",
        source="runtime:memory_store",
        label="project_memory",
        path="memory://mem_1",
        description="recalled by relevance",
        metadata={"memory_id": "mem_1", "score": 2.5},
    )
    with patch(
        "cli.agent_cli.runtime_services.runtime_context_runtime.memory_context_turn_update",
        return_value=([], [memory_item], {"recalled_count": 1, "recalled_ids": ["mem_1"]}),
    ):
        _, context_items, workspace_snapshot = runtime_context_runtime.workspace_context_turn_update(runtime)
    assert workspace_snapshot["instructions_digest"] == "digest-workspace"
    assert runtime._memory_context_snapshot["recalled_ids"] == ["mem_1"]
    item_types = [item.item_type for item in context_items]
    assert "workspace_context" in item_types
    assert "memory" in item_types


def test_delegated_planner_input_items_passes_memory_context_items() -> None:
    runtime = _RuntimeStub()
    memory_item = ReferenceContextItem(
        item_type="memory",
        source="runtime:memory_store",
        label="project_memory",
        path="memory://mem_2",
        description="recalled by relevance",
        metadata={"memory_id": "mem_2", "score": 3.0},
    )
    with patch(
        "cli.agent_cli.runtime_services.runtime_context_runtime.environment_context_turn_update",
        return_value=([], runtime._forced_environment_context_snapshot),
    ), patch(
        "cli.agent_cli.runtime_services.runtime_context_runtime.workspace_context_turn_update",
        return_value=([], [memory_item], runtime._forced_workspace_context_snapshot),
    ):
        planner_items = runtime_context_runtime.delegated_planner_input_items(runtime)
    assert planner_items
    pending = list(runtime._planner_context_kwargs.get("pending_context_items") or [])
    assert len(pending) == 1
    assert pending[0].item_type == "memory"


def test_turn_context_rollout_state_includes_memory_context_snapshot() -> None:
    runtime = _RuntimeStub()
    runtime._memory_context_snapshot = {"recalled_count": 1, "recalled_ids": ["mem_9"]}
    items = prompt_turn_context_runtime.turn_context_rollout_items(
        runtime,
        pending_environment_messages=[{"role": "system", "content": "env"}],
        pending_context_messages=[],
        pending_context_items=[],
        next_environment_snapshot={"shell": "bash"},
        next_workspace_snapshot={"instructions_digest": "abc"},
    )
    assert len(items) == 1
    state = dict(items[0]).get("state") or {}
    assert state.get("memory_context_snapshot") == {"recalled_count": 1, "recalled_ids": ["mem_9"]}


def test_workspace_context_turn_update_keeps_phase2_memory_snapshot_contract() -> None:
    runtime = _RuntimeStub()
    memory_item = ReferenceContextItem(
        item_type="memory",
        source="runtime:memory_store",
        label="project_memory",
        path="memory://mem_phase2",
        description="phase2 memory item",
        metadata={"memory_id": "mem_phase2", "score": 4.2},
    )
    phase2_snapshot = {
        "recalled_count": 1,
        "recalled_ids": ["mem_phase2"],
        "query_paths": ["src/service/api.py"],
        "recalled_types": ["project"],
        "blocked": False,
        "blocked_reason": "",
        "ranking_explainability": [
            {
                "rank": 1,
                "memory_id": "mem_phase2",
                "memory_type": "project",
                "score": 4.2,
                "reasons": ["path_overlap:src/service/api.py"],
                "excerpt_chars": 42,
                "selected": True,
            }
        ],
        "preview_apply_path": {"preview": "/memory preview --from-last-turn", "apply": "/memory save --from-last-turn"},
        "user_scope_opt_in": {"enabled": False, "env": "AGENTHUB_MEMORY_USER_SCOPE_ENABLED"},
    }
    with patch(
        "cli.agent_cli.runtime_services.runtime_context_runtime.memory_context_turn_update",
        return_value=([], [memory_item], phase2_snapshot),
    ):
        _messages, _context_items, _workspace_snapshot = runtime_context_runtime.workspace_context_turn_update(runtime)
    assert runtime._memory_context_snapshot["query_paths"] == ["src/service/api.py"]
    assert runtime._memory_context_snapshot["recalled_types"] == ["project"]
    assert runtime._memory_context_snapshot["blocked_reason"] == ""
    assert runtime._memory_context_snapshot["ranking_explainability"][0]["memory_id"] == "mem_phase2"
    assert runtime._memory_context_snapshot["preview_apply_path"]["preview"] == "/memory preview --from-last-turn"
    assert runtime._memory_context_snapshot["user_scope_opt_in"]["enabled"] is False


def test_turn_context_rollout_state_preserves_phase2_memory_snapshot_fields() -> None:
    runtime = _RuntimeStub()
    runtime._memory_context_snapshot = {
        "recalled_count": 1,
        "recalled_ids": ["mem_rollout"],
        "query_paths": ["src/runtime.py"],
        "recalled_types": ["reference"],
        "blocked": False,
        "blocked_reason": "",
        "ranking_explainability": [{"rank": 1, "memory_id": "mem_rollout", "selected": True}],
        "preview_apply_path": {"preview": "/memory preview --from-last-turn", "apply": "/memory save --from-last-turn"},
        "user_scope_opt_in": {"enabled": True, "env": "AGENTHUB_MEMORY_USER_SCOPE_ENABLED"},
    }
    items = prompt_turn_context_runtime.turn_context_rollout_items(
        runtime,
        pending_environment_messages=[{"role": "system", "content": "env"}],
        pending_context_messages=[],
        pending_context_items=[],
        next_environment_snapshot={"shell": "bash"},
        next_workspace_snapshot={"instructions_digest": "abc"},
    )
    state = dict(items[0]).get("state") or {}
    snapshot = dict(state.get("memory_context_snapshot") or {})
    assert snapshot["recalled_ids"] == ["mem_rollout"]
    assert snapshot["query_paths"] == ["src/runtime.py"]
    assert snapshot["recalled_types"] == ["reference"]
    assert snapshot["ranking_explainability"][0]["memory_id"] == "mem_rollout"
    assert snapshot["preview_apply_path"]["apply"] == "/memory save --from-last-turn"
    assert snapshot["user_scope_opt_in"]["enabled"] is True


def test_workspace_context_turn_update_includes_agent_cli_home_skill_roots_without_plugin_manager() -> None:
    runtime = _RuntimeStub()
    runtime._forced_workspace_context_snapshot = {}
    captured: dict[str, object] = {}

    def _fake_snapshot(cwd: str, *, extra_skill_roots=None):
        captured["cwd"] = cwd
        captured["extra_skill_roots"] = list(extra_skill_roots or [])
        return {
            "cwd": cwd,
            "trust_level": "trusted",
            "instructions_text": "workspace rules",
            "instructions_digest": "digest-home-skills",
            "docs": [],
            "skills": [{"path": "/tmp/agent_cli_home/skills/.system/demo/SKILL.md", "name": "demo"}],
        }

    with patch(
        "cli.agent_cli.runtime_services.runtime_context_runtime.agent_cli_home_skill_roots",
        return_value=["/tmp/agent_cli_home/skills"],
    ), patch(
        "cli.agent_cli.runtime_services.runtime_context_runtime.build_workspace_reference_snapshot",
        side_effect=_fake_snapshot,
    ), patch(
        "cli.agent_cli.runtime_services.runtime_context_runtime.memory_context_turn_update",
        return_value=([], [], {}),
    ):
        _messages, context_items, workspace_snapshot = runtime_context_runtime.workspace_context_turn_update(runtime)

    assert captured["cwd"] == "/tmp/work"
    assert captured["extra_skill_roots"] == ["/tmp/agent_cli_home/skills"]
    assert workspace_snapshot["instructions_digest"] == "digest-home-skills"
    assert any(item.item_type == "workspace_context" for item in context_items)
