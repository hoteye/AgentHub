from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from cli.agent_cli.memory_store import MemoryStore


def _project_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "project-memory")


def test_project_store_rejects_scope_user_write(tmp_path: Path) -> None:
    store = _project_store(tmp_path)
    with pytest.raises(PermissionError):
        store.upsert_memory(
            {
                "memory_id": "mem_user_forbidden",
                "scope": "user",
                "memory_type": "user",
                "title": "forbidden",
                "summary": "forbidden write",
                "body": "should fail",
            }
        )


def test_user_store_accepts_scope_user_write_with_opt_in(tmp_path: Path) -> None:
    home = tmp_path / "home" / ".agent_cli"
    with patch.dict("os.environ", {"AGENT_CLI_HOME": str(home)}, clear=False):
        store = MemoryStore.user_default(allow_user_scope=True)
        saved = store.upsert_memory(
            {
                "memory_id": "mem_user_ok",
                "scope": "user",
                "memory_type": "user",
                "title": "owner prefs",
                "summary": "prefers terse",
                "body": "keep concise",
            }
        )
    assert saved["scope"] == "user"
    assert [item["memory_id"] for item in store.list_memories()] == ["mem_user_ok"]


def test_user_store_rejects_project_scope_write(tmp_path: Path) -> None:
    home = tmp_path / "home" / ".agent_cli"
    with patch.dict("os.environ", {"AGENT_CLI_HOME": str(home)}, clear=False):
        store = MemoryStore.user_default(allow_user_scope=True)
        with pytest.raises(ValueError):
            store.upsert_memory(
                {
                    "memory_id": "mem_project_in_user_store",
                    "scope": "project",
                    "memory_type": "project",
                    "title": "bad scope",
                    "summary": "should fail",
                    "body": "wrong scope",
                }
            )


def test_project_and_user_storage_are_isolated(tmp_path: Path) -> None:
    project_store = _project_store(tmp_path)
    project_store.upsert_memory(
        {
            "memory_id": "mem_project_only",
            "scope": "project",
            "memory_type": "project",
            "title": "project rule",
            "summary": "project summary",
            "body": "project body",
        }
    )

    home = tmp_path / "home" / ".agent_cli"
    with patch.dict("os.environ", {"AGENT_CLI_HOME": str(home)}, clear=False):
        user_store = MemoryStore.user_default(allow_user_scope=True)
        user_store.upsert_memory(
            {
                "memory_id": "mem_user_only",
                "scope": "user",
                "memory_type": "user",
                "title": "user prefs",
                "summary": "user summary",
                "body": "user body",
            }
        )

    assert [item["memory_id"] for item in project_store.list_memories()] == ["mem_project_only"]
    assert [item["memory_id"] for item in user_store.list_memories()] == ["mem_user_only"]
