from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest
from unittest.mock import patch

from cli.agent_cli.memory_events import (
    MEMORY_AUDIT_EVENT_TAXONOMY,
    aggregate_memory_audit_metrics,
    build_memory_audit_event,
    normalize_audit_event_fields,
)
from cli.agent_cli.memory_store import MemoryStore
from cli.agent_cli.runtime_paths import PROJECT_ROOT_ENV


def _store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory")


def test_memory_store_schema_init(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with sqlite3.connect(store.sqlite_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}

    assert "memories" in tables
    assert "memory_events" in tables
    assert "idx_memories_status_updated" in indexes
    assert "idx_memories_scope_type" in indexes
    assert "idx_memory_events_memory_created" in indexes


def test_memory_store_upsert_get_and_list_contract(tmp_path: Path) -> None:
    store = _store(tmp_path)
    saved = store.upsert_memory(
        {
            "memory_id": "mem_alpha",
            "scope": "project",
            "memory_type": "reference",
            "title": "docs entry",
            "summary": "where docs live",
            "body": "use internal docs index",
            "tags": ["docs", "index", "docs"],
            "paths": ["docs/index.md", "docs/index.md"],
            "source_thread_id": "thread_1",
            "source_turn_id": "turn_1",
            "salience": 1.25,
        }
    )

    assert saved["memory_id"] == "mem_alpha"
    assert saved["memory_type"] == "reference"
    assert saved["tags"] == ["docs", "index"]
    assert saved["paths"] == ["docs/index.md"]
    assert saved["status"] == "active"
    assert saved["hit_count"] == 0
    assert saved["created_at"]
    assert saved["updated_at"]

    fetched = store.get_memory("mem_alpha")
    assert fetched is not None
    assert fetched["summary"] == "where docs live"
    assert fetched["source_thread_id"] == "thread_1"

    listed = store.list_memories()
    assert [item["memory_id"] for item in listed] == ["mem_alpha"]

    updated = store.upsert_memory(
        {
            "memory_id": "mem_alpha",
            "scope": "project",
            "memory_type": "project",
            "title": "docs entry updated",
            "summary": "updated summary",
            "body": "updated body",
            "tags": ["docs", "project"],
            "paths": ["docs/index.md", "docs/README.md"],
            "status": "active",
            "salience": 3.0,
        }
    )
    assert updated["memory_type"] == "project"
    assert updated["summary"] == "updated summary"
    assert updated["tags"] == ["docs", "project"]
    assert updated["paths"] == ["docs/index.md", "docs/README.md"]
    assert updated["salience"] == 3.0
    assert updated["created_at"] == saved["created_at"]


def test_memory_store_archive_delete_and_hit_counter(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_memory(
        {
            "memory_id": "mem_beta",
            "scope": "project",
            "memory_type": "user",
            "title": "owner preference",
            "summary": "prefers short replies",
            "body": "keep answers concise",
        }
    )

    assert store.record_memory_hit("mem_beta", used_at="2026-04-09T10:00:00+00:00")
    after_hit = store.get_memory("mem_beta")
    assert after_hit is not None
    assert after_hit["hit_count"] == 1
    assert after_hit["last_used_at"] == "2026-04-09T10:00:00+00:00"

    assert store.archive_memory("mem_beta")
    archived = store.get_memory("mem_beta")
    assert archived is not None
    assert archived["status"] == "archived"
    assert [item["memory_id"] for item in store.list_memories(status="archived")] == ["mem_beta"]

    assert store.delete_memory("mem_beta")
    deleted = store.get_memory("mem_beta")
    assert deleted is not None
    assert deleted["status"] == "deleted"
    assert store.list_memories(status="active") == []


def test_memory_store_default_uses_project_local_data_dir(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    with patch.dict("os.environ", {PROJECT_ROOT_ENV: str(root)}, clear=False):
        store = MemoryStore.default()
        assert store.base_dir == (root / ".config" / "memory").resolve()
        assert store.sqlite_path == (root / ".config" / "memory" / "memory.sqlite3").resolve()


def test_memory_store_user_default_requires_explicit_opt_in(tmp_path: Path) -> None:
    home = tmp_path / "home" / ".agent_cli"
    with patch.dict("os.environ", {"AGENT_CLI_HOME": str(home)}, clear=False):
        with pytest.raises(PermissionError):
            MemoryStore.default(scope="user")
        store = MemoryStore.default(scope="user", allow_user_scope=True)
    assert store.scope == "user"
    assert store.base_dir == (home / "memory_user").resolve()
    assert store.sqlite_path == (home / "memory_user" / "memory_user.sqlite3").resolve()


def test_memory_audit_taxonomy_and_field_normalization_contract() -> None:
    assert "memory_upserted" in MEMORY_AUDIT_EVENT_TAXONOMY
    assert "memory_recall_evaluated" in MEMORY_AUDIT_EVENT_TAXONOMY
    normalized = normalize_audit_event_fields(
        {
            "event_type": "unknown_event",
            "query_tokens": [" api  ", "", None],
            "query_paths": [" src/api.py ", ""],
            "recalled_ids": [" mem_1 ", ""],
            "blocked": True,
            "latency_ms": "23",
        }
    )
    assert normalized["event_type"] == "memory_recall_evaluated"
    assert normalized["query_tokens"] == ["api"]
    assert normalized["query_paths"] == ["src/api.py"]
    assert normalized["recalled_ids"] == ["mem_1"]
    assert normalized["blocked"] is True
    assert normalized["outcome"] == "blocked"
    assert normalized["latency_ms"] == 23
    assert normalized["event_schema_version"] == "v1"


def test_memory_audit_metrics_aggregate_proxies_and_rates() -> None:
    events = [
        build_memory_audit_event(
            event_type="memory_recall_evaluated",
            candidate_count=4,
            recalled_count=2,
            latency_ms=12,
        ),
        build_memory_audit_event(
            event_type="memory_recall_blocked",
            blocked=True,
            blocked_reason="empty_query",
            latency_ms=5,
        ),
        build_memory_audit_event(
            event_type="memory_save_accepted",
            outcome="accepted",
            latency_ms=8,
        ),
        build_memory_audit_event(
            event_type="memory_save_blocked",
            blocked=True,
            blocked_reason="contains_sensitive_content",
            outcome="blocked",
            latency_ms=7,
        ),
        build_memory_audit_event(
            event_type="memory_save_rejected",
            outcome="rejected",
            latency_ms=3,
        ),
    ]
    metrics = aggregate_memory_audit_metrics(events)

    assert metrics["event_count"] == 5
    assert metrics["recall_attempts"] == 2
    assert metrics["save_attempts"] == 3
    assert metrics["counts"]["recall_candidates"] == 4
    assert metrics["counts"]["recall_selected"] == 2
    assert metrics["counts"]["save_accepted"] == 1
    assert metrics["counts"]["save_blocked"] == 1
    assert metrics["counts"]["save_rejected"] == 1
    assert metrics["recall_precision_proxy"] == 0.5
    assert metrics["save_acceptance"] == pytest.approx(1 / 3, rel=1e-4)
    assert metrics["pollution_proxy"] == pytest.approx(2 / 3, rel=1e-4)
    assert metrics["recall_block_rate"] == 0.5
    assert metrics["save_block_rate"] == pytest.approx(1 / 3, rel=1e-4)
    assert metrics["overall_block_rate"] == 0.4
    assert metrics["latency_ms_avg"] == 7.0
    assert metrics["latency_ms_p95"] == 12.0
