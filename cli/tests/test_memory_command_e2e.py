from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.memory_store import MemoryStore
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.runtime_core.memory_commands import handle_memory_command


class _RuntimeStub:
    def __init__(self, store: MemoryStore) -> None:
        self.memory_store = store
        self.history_turns = []
        self.reference_context_items = []
        self.thread_id = "thread_memory_e2e"
        self.tools = type("Tools", (), {"_plugin_manager": None})()

    @staticmethod
    def _parse_args(arg_text: str):
        return parse_args(arg_text)

    @staticmethod
    def _is_interrupt_requested() -> bool:
        return False

    @staticmethod
    def _interrupt_tuple():
        return ("interrupted", [])


def _runtime(tmp_path: Path) -> _RuntimeStub:
    return _RuntimeStub(MemoryStore(tmp_path / "memory"))


def _kv(text: str, key: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def test_memory_cli_e2e_preview_save_list_show_debug_project_scope(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_project_e2e",
            "user_text": "Remember deployment must stay canary-first and include smoke checks.",
            "assistant_text": "Will keep canary-first + smoke checks as project memory.",
        }
    ]
    runtime.reference_context_items = [
        {"item_type": "workspace_context", "path": "/repo/service/deploy.py"},
        {"item_type": "workspace_context", "path": "/repo/service/smoke_test.py"},
    ]

    preview_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="preview --from-last-turn --type project",
    ) or ("", [])
    assert "memory preview" in preview_text
    assert "type=project" in preview_text
    assert "blocked_sensitive=false" in preview_text
    assert "blocked_reason=-" in preview_text

    save_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="save --from-last-turn --scope project --type project",
    ) or ("", [])
    assert "memory saved" in save_text
    memory_id = _kv(save_text, "memory_id")
    assert memory_id

    list_text, _events = handle_memory_command(runtime, name="memory", arg_text="list --scope project --type project") or ("", [])
    assert "memory_count=1" in list_text
    assert memory_id in list_text

    show_text, _events = handle_memory_command(runtime, name="memory", arg_text=f"show {memory_id} --scope project") or ("", [])
    assert f"memory_id={memory_id}" in show_text
    assert "scope=project" in show_text
    assert "type=project" in show_text
    assert "paths=/repo/service/deploy.py,/repo/service/smoke_test.py" in show_text

    runtime._memory_context_snapshot = {
        "recalled_count": 1,
        "recalled_ids": [memory_id],
        "blocked_reason": "no_recall_match",
        "query_paths": ["service/deploy.py"],
        "recalled_types": ["project"],
        "ranking_explainability": [
            {
                "rank": 1,
                "memory_id": memory_id,
                "memory_type": "project",
                "score": 6.1,
                "selected": True,
                "reasons": ["path_overlap", "tag_overlap"],
            }
        ],
    }
    runtime.reference_context_items = [
        {
            "item_type": "memory",
            "path": f"memory://{memory_id}",
            "metadata": {
                "memory_id": memory_id,
                "memory_type": "project",
                "score": 6.1,
                "reasons": ["path_overlap", "tag_overlap"],
            },
        }
    ]
    debug_text, _events = handle_memory_command(runtime, name="memory", arg_text="debug --limit 5") or ("", [])
    assert "recalled_memory_count=1" in debug_text
    assert f"snapshot_recalled_ids={memory_id}" in debug_text
    assert "snapshot_blocked_reason=no_recall_match" in debug_text
    assert "snapshot_ranking_explainability_count=1" in debug_text
    assert f"# rank=1 | memory_id={memory_id} | type=project | score=6.1 | selected=true" in debug_text


def test_memory_cli_e2e_sensitive_preview_blocked_and_cannot_save(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_sensitive_e2e",
            "user_text": "token is sk-abc1234567890",
            "assistant_text": "记住了",
        }
    ]

    preview_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="preview --from-last-turn --type reference",
    ) or ("", [])
    assert "memory preview" in preview_text
    assert "blocked_sensitive=true" in preview_text
    assert "blocked_reason=contains_sensitive_content" in preview_text

    save_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="save --from-last-turn --scope project --type reference",
    ) or ("", [])
    assert "memory save blocked: contains_sensitive_content" in save_text
    assert runtime.memory_store.list_memories() == []


def test_memory_cli_e2e_user_scope_requires_opt_in_and_succeeds_with_opt_in(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_user_e2e",
            "user_text": "Remember I prefer concise status updates.",
            "assistant_text": "Will remember concise status updates preference.",
        }
    ]

    blocked_text, blocked_events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="save --from-last-turn --scope user --type user",
    ) or ("", [])
    assert "requires explicit opt-in" in blocked_text
    assert blocked_events == []

    with patch.dict(
        "os.environ",
        {"AGENTHUB_MEMORY_USER_SCOPE_ENABLED": "true", "AGENT_CLI_HOME": str(tmp_path / "agent_cli_home")},
        clear=False,
    ):
        save_text, _events = handle_memory_command(
            runtime,
            name="memory",
            arg_text="save --from-last-turn --scope user --type user",
        ) or ("", [])
        assert "memory saved" in save_text
        saved_memory_id = _kv(save_text, "memory_id")
        assert saved_memory_id

        list_text, _events = handle_memory_command(
            runtime,
            name="memory",
            arg_text="list --scope user --type user",
        ) or ("", [])
        assert "memory_count=1" in list_text
        assert saved_memory_id in list_text

        show_text, _events = handle_memory_command(
            runtime,
            name="memory",
            arg_text=f"show {saved_memory_id} --scope user",
        ) or ("", [])
        assert f"memory_id={saved_memory_id}" in show_text
        assert "scope=user" in show_text
        assert "type=user" in show_text
