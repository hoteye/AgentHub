from __future__ import annotations

from pathlib import Path

from cli.agent_cli.memory_store import MemoryStore


def _store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory")


def test_similar_detection_merge_and_audit_events(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_memory(
        {
            "memory_id": "mem_target",
            "scope": "project",
            "memory_type": "project",
            "title": "deployment policy",
            "summary": "use canary deploys for service api",
            "body": "canary first, monitor error budget",
            "tags": ["deploy", "canary"],
            "paths": ["service/api/deploy.md"],
            "hit_count": 2,
            "salience": 0.4,
        }
    )
    store.upsert_memory(
        {
            "memory_id": "mem_source",
            "scope": "project",
            "memory_type": "project",
            "title": "api deployment guidance",
            "summary": "service api should use canary rollout",
            "body": "monitor latency after rollout",
            "tags": ["deploy", "rollout"],
            "paths": ["service/api/deploy.md", "service/api/runbook.md"],
            "hit_count": 1,
            "salience": 0.8,
        }
    )

    similar = store.find_similar_memories("mem_target", limit=3, min_similarity=0.30)
    assert similar
    assert similar[0]["memory"]["memory_id"] == "mem_source"
    assert similar[0]["similarity"] >= 0.30

    merged = store.merge_memories(source_memory_id="mem_source", target_memory_id="mem_target")
    assert merged is True

    source = store.get_memory("mem_source")
    target = store.get_memory("mem_target")
    assert source is not None and source["status"] == "archived"
    assert target is not None
    assert target["hit_count"] == 3
    assert sorted(target["tags"]) == ["canary", "deploy", "rollout"]
    assert "service/api/runbook.md" in target["paths"]
    assert [item["memory_id"] for item in store.list_memories(status="active")] == ["mem_target"]

    target_events = store.list_memory_events("mem_target")
    source_events = store.list_memory_events("mem_source")
    assert any(event["event_type"] == "memory_merged" for event in target_events)
    assert any(
        event["event_type"] == "memory_archived"
        and event["payload"].get("archived_reason") == "merged_into"
        for event in source_events
    )


def test_hygiene_candidates_identify_stale_and_low_signal(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_memory(
        {
            "memory_id": "mem_old_low_signal",
            "scope": "project",
            "memory_type": "reference",
            "title": "tmp",
            "summary": "",
            "body": "",
            "tags": [],
            "paths": [],
            "hit_count": 0,
            "salience": 0.0,
            "last_used_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
    )
    store.upsert_memory(
        {
            "memory_id": "mem_fresh_strong",
            "scope": "project",
            "memory_type": "project",
            "title": "important policy",
            "summary": "critical production policy",
            "body": "do not rotate keys during deploy window",
            "tags": ["prod", "policy"],
            "paths": ["infra/policy.md"],
            "hit_count": 20,
            "salience": 2.0,
            "last_used_at": "2030-01-01T00:00:00+00:00",
            "updated_at": "2030-01-01T00:00:00+00:00",
            "created_at": "2030-01-01T00:00:00+00:00",
        }
    )

    candidates = store.list_hygiene_candidates(limit=10, stale_days=30, low_signal_threshold=0.75)
    candidate_ids = [item["memory"]["memory_id"] for item in candidates]
    assert "mem_old_low_signal" in candidate_ids
    assert "mem_fresh_strong" not in candidate_ids
    old_candidate = next(item for item in candidates if item["memory"]["memory_id"] == "mem_old_low_signal")
    assert old_candidate["staleness_days"] >= 30
    assert old_candidate["low_signal_score"] >= 0.75
    assert any(reason.startswith("stale:") for reason in old_candidate["reasons"])

