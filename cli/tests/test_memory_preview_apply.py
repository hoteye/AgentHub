from __future__ import annotations

from pathlib import Path

from cli.agent_cli.memory_extraction_runtime import (
    extract_memory_candidates_from_last_turn,
    preview_payload_from_candidate,
)
from cli.agent_cli.memory_store import MemoryStore
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.runtime_core.memory_commands import handle_memory_command


class _RuntimeStub:
    def __init__(self, store: MemoryStore) -> None:
        self.memory_store = store
        self.history_turns = []
        self.reference_context_items = []
        self.thread_id = "thread_preview_apply"
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


def test_preview_payload_contract_exposes_apply_fields() -> None:
    candidates = extract_memory_candidates_from_last_turn(
        turn={
            "user_text": "Remember deployments stay canary-first",
            "assistant_text": "Will keep that rule",
        },
        memory_type="project",
        paths=["/repo/service/api.py"],
    )
    assert len(candidates) == 1
    preview = preview_payload_from_candidate(candidates[0])
    assert preview == {
        "memory_type": "project",
        "title": "Remember deployments stay canary-first",
        "summary": "Will keep that rule",
        "paths": ["/repo/service/api.py"],
        "tags": ["preview", "last_turn"],
        "reasons": ["from_last_turn", "non_derivable_candidate"],
        "blocked_sensitive": False,
        "blocked_reason": "",
        "source": "last_turn",
    }


def test_preview_then_save_from_last_turn_creates_memory_record(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_apply",
            "user_text": "Remember deployments stay canary-first",
            "assistant_text": "Will keep that rule",
        }
    ]
    runtime.reference_context_items = [{"item_type": "workspace_context", "path": "/repo/service/api.py"}]

    preview_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="preview --from-last-turn --type project",
    ) or ("", [])
    assert "memory preview" in preview_text
    assert "blocked_reason=-" in preview_text

    save_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="save --from-last-turn --type project",
    ) or ("", [])
    assert "memory saved" in save_text
    stored = runtime.memory_store.list_memories()
    assert len(stored) == 1
    assert stored[0]["title"] == "Remember deployments stay canary-first"
    assert stored[0]["paths"] == ["/repo/service/api.py"]


def test_preview_and_save_surface_blocked_reason_for_sensitive_candidate(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.history_turns = [
        {
            "turn_id": "turn_blocked",
            "user_text": "token is sk-abc1234567890",
            "assistant_text": "记住了",
        }
    ]

    preview_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="preview --from-last-turn --type reference",
    ) or ("", [])
    assert "blocked_sensitive=true" in preview_text
    assert "blocked_reason=contains_sensitive_content" in preview_text

    save_text, _events = handle_memory_command(
        runtime,
        name="memory",
        arg_text="save --from-last-turn --type reference",
    ) or ("", [])
    assert "memory save blocked: contains_sensitive_content" in save_text
    assert runtime.memory_store.list_memories() == []
