from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.memory_store import MemoryStore
from cli.agent_cli.runtime_core import memory_commands as memory_commands_module
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.runtime_core.memory_commands import handle_memory_command
from cli.agent_cli.slash_commands import slash_command_help_text


class _RuntimeStub:
    def __init__(self, store: MemoryStore) -> None:
        self.memory_store = store
        self.history_turns = []
        self.reference_context_items = []
        self.thread_id = "thread_test"
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


def test_memory_command_is_listed_in_help() -> None:
    assert "/memory <list|show|preview|save|delete|debug> [args]" in slash_command_help_text()


def test_slash_help_text_uses_chinese_locale_for_builtin_commands() -> None:
    help_text = slash_command_help_text(locale="zh-CN")

    assert help_text.splitlines()[0] == "可用命令："
    assert "/help - 显示可用斜杠命令" in help_text
    assert "使用 /help all 显示高级命令和插件命令。" in help_text


def test_memory_list_and_show(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    saved = runtime.memory_store.upsert_memory(
        {
            "memory_id": "mem_1",
            "scope": "project",
            "memory_type": "project",
            "title": "Build constraints",
            "summary": "Use x86 runner first",
            "body": "Body",
        }
    )
    list_text, _events = handle_memory_command(runtime, name="memory", arg_text="list") or ("", [])
    assert "memory_count=1" in list_text
    assert saved["memory_id"] in list_text

    show_text, _events = handle_memory_command(
        runtime, name="memory", arg_text=f"show {saved['memory_id']}"
    ) or ("", [])
    assert f"memory_id={saved['memory_id']}" in show_text
    assert "type=project" in show_text


def test_memory_save_from_last_turn_and_delete(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_1",
            "user_text": "Remember that deployment needs canary first",
            "assistant_text": "Will keep canary-first deployment as project memory",
        }
    ]
    runtime.reference_context_items = [
        {"item_type": "workspace_context", "path": "/repo/service/api.py"}
    ]

    save_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="save --from-last-turn --type project",
    ) or ("", [])
    assert "memory saved" in save_text
    listed = runtime.memory_store.list_memories()
    assert len(listed) == 1
    memory_id = listed[0]["memory_id"]

    delete_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text=f"delete {memory_id}",
    ) or ("", [])
    assert f"memory deleted: {memory_id}" in delete_text
    deleted = runtime.memory_store.get_memory(memory_id)
    assert deleted is not None
    assert deleted["status"] == "deleted"


def test_memory_preview_from_last_turn(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_preview",
            "user_text": "Remember the build should stay canary-first",
            "assistant_text": "Will keep that as project memory",
        }
    ]
    runtime.reference_context_items = [
        {"item_type": "workspace_context", "path": "/repo/service/api.py"}
    ]

    preview_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="preview --from-last-turn --type project",
    ) or ("", [])
    assert "memory preview" in preview_text
    assert "type=project" in preview_text
    assert "blocked_sensitive=false" in preview_text
    assert runtime.memory_store.list_memories() == []


def test_memory_save_from_last_turn_blocks_sensitive_candidate(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_2",
            "user_text": "token is sk-abc1234567890",
            "assistant_text": "记住了",
        }
    ]

    save_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="save --from-last-turn --type reference",
    ) or ("", [])
    assert "memory save blocked" in save_text
    assert runtime.memory_store.list_memories() == []


def test_memory_debug_renders_recalled_items(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime._memory_context_snapshot = {
        "recalled_count": 1,
        "recalled_ids": ["mem_alpha"],
        "blocked_reason": "no_recall_match",
        "query_paths": ["service/api.py"],
        "recalled_types": ["reference"],
        "ranking_explainability": [
            {
                "rank": 1,
                "memory_id": "mem_alpha",
                "memory_type": "reference",
                "score": 3.8,
                "selected": True,
                "reasons": ["path_overlap", "tag_overlap"],
            }
        ],
    }
    runtime.reference_context_items = [
        {
            "item_type": "memory",
            "path": "memory://mem_alpha",
            "metadata": {
                "memory_id": "mem_alpha",
                "memory_type": "reference",
                "score": 3.8,
                "reasons": ["path_overlap", "tag_overlap"],
            },
        }
    ]
    debug_text, _events = handle_memory_command(
        runtime, name="memory", arg_text="debug --limit 5"
    ) or ("", [])
    assert "recalled_memory_count=1" in debug_text
    assert "snapshot_recalled_count=1" in debug_text
    assert "snapshot_recalled_ids=mem_alpha" in debug_text
    assert "snapshot_blocked_reason=no_recall_match" in debug_text
    assert "snapshot_query_paths=service/api.py" in debug_text
    assert "snapshot_recalled_types=reference" in debug_text
    assert "snapshot_ranking_explainability_count=1" in debug_text
    assert (
        "# rank=1 | memory_id=mem_alpha | type=reference | score=3.8 | selected=true" in debug_text
    )
    assert "mem_alpha" in debug_text
    assert "score=3.8" in debug_text


def test_memory_usage_for_unknown_action(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    text, events = handle_memory_command(runtime, name="memory", arg_text="unknown") or ("", [])
    assert "Usage: /memory" in text
    assert events == []


def test_memory_list_scope_user_requires_opt_in(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    text, events = handle_memory_command(runtime, name="memory", arg_text="list --scope user") or (
        "",
        [],
    )
    assert "requires explicit opt-in" in text
    assert events == []


def test_memory_list_scope_user_uses_user_store_with_opt_in(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with patch.dict(
        "os.environ",
        {
            "AGENTHUB_MEMORY_USER_SCOPE_ENABLED": "true",
            "AGENT_CLI_HOME": str(tmp_path / "agent_cli_home"),
        },
        clear=False,
    ):
        user_store = MemoryStore.default(scope="user")
        saved = user_store.upsert_memory(
            {
                "memory_id": "mem_user_1",
                "scope": "user",
                "memory_type": "user",
                "title": "User preference",
                "summary": "Prefer concise answers",
                "body": "Keep responses concise and direct.",
            }
        )
        text, _events = handle_memory_command(
            runtime, name="memory", arg_text="list --scope user --type user"
        ) or ("", [])
    assert "memory_count=" in text
    assert saved["memory_id"] in text


def test_memory_save_scope_user_from_last_turn_requires_opt_in(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_user_save_1",
            "user_text": "Remember I prefer short outputs.",
            "assistant_text": "Will remember your preference for concise output.",
        }
    ]
    text, events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="save --from-last-turn --scope user --type user",
    ) or ("", [])
    assert "requires explicit opt-in" in text
    assert events == []


def test_memory_save_scope_user_from_last_turn_uses_user_store(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_user_save_2",
            "user_text": "Remember I always want terse status updates.",
            "assistant_text": "I will keep terse status update preference.",
        }
    ]
    with patch.dict(
        "os.environ",
        {
            "AGENTHUB_MEMORY_USER_SCOPE_ENABLED": "true",
            "AGENT_CLI_HOME": str(tmp_path / "agent_cli_home"),
        },
        clear=False,
    ):
        text, _events = handle_memory_command(
            runtime,
            name="memory",
            arg_text="save --from-last-turn --scope user --type user",
        ) or ("", [])
        user_store = MemoryStore.default(scope="user")
        listed_user = user_store.list_memories(scope="user", memory_type="user")
    assert "memory saved" in text
    saved_memory_id = ""
    for line in text.splitlines():
        if line.startswith("memory_id="):
            saved_memory_id = line.split("=", 1)[1].strip()
            break
    assert saved_memory_id
    assert any(str(item.get("memory_id") or "") == saved_memory_id for item in listed_user)
    assert all(
        str(item.get("scope") or "") == "user"
        for item in listed_user
        if str(item.get("memory_id") or "") == saved_memory_id
    )
    assert all(
        str(item.get("memory_id") or "") != saved_memory_id
        for item in runtime.memory_store.list_memories()
    )


def test_memory_auto_writeback_policy_defaults_to_disabled(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_auto_disabled",
            "user_text": "Remember deployment stays canary-first",
            "assistant_text": "Will keep that rule",
        }
    ]
    text, events = memory_commands_module._save_from_last_turn(
        runtime,
        memory_type="project",
        scope="project",
        store=runtime.memory_store,
        auto_writeback=True,
    )
    assert text == "memory save blocked: auto_writeback_policy_disabled"
    assert events == []
    assert runtime.memory_store.list_memories() == []


def test_memory_auto_writeback_blocks_candidate_with_block_decision(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime._memory_auto_writeback_policy = {
        "scope_types": {"project:reference": True},
    }
    runtime.history_turns = [
        {
            "turn_id": "turn_auto_blocked",
            "user_text": "token is sk-abc1234567890",
            "assistant_text": "记住了",
        }
    ]
    text, events = memory_commands_module._save_from_last_turn(
        runtime,
        memory_type="reference",
        scope="project",
        store=runtime.memory_store,
        auto_writeback=True,
    )
    assert text == "memory save blocked: contains_sensitive_content"
    assert events == []
    assert runtime.memory_store.list_memories() == []
