from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from cli.agent_cli import memory_store_runtime as runtime_helpers
from cli.agent_cli import memory_types


def list_memory_events(store: Any, memory_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    key = str(memory_id or "").strip()
    if not key:
        return []
    capped_limit = max(1, min(int(limit or 50), 500))
    with store._lock, store._connection() as conn:
        rows = conn.execute(
            """
            SELECT event_id, memory_id, event_type, payload_json, created_at
            FROM memory_events
            WHERE memory_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (key, capped_limit),
        ).fetchall()
    results: List[Dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        try:
            payload_json = json.loads(str(payload.get("payload_json") or "{}"))
        except json.JSONDecodeError:
            payload_json = {}
        results.append(
            {
                "event_id": str(payload.get("event_id") or ""),
                "memory_id": str(payload.get("memory_id") or ""),
                "event_type": str(payload.get("event_type") or ""),
                "payload": dict(payload_json or {}),
                "created_at": str(payload.get("created_at") or ""),
            }
        )
    return results


def find_similar_memories(
    store: Any,
    memory_id: str,
    *,
    limit: int = 5,
    min_similarity: float = 0.55,
) -> List[Dict[str, Any]]:
    key = str(memory_id or "").strip()
    baseline = store.get_memory(key)
    if baseline is None:
        return []
    candidates = store.list_memories(limit=500, status="active")
    ranked: List[Dict[str, Any]] = []
    for item in candidates:
        candidate_id = str(item.get("memory_id") or "").strip()
        if not candidate_id or candidate_id == key:
            continue
        if store.scope == "user" and str(item.get("scope") or "") != "user":
            continue
        similarity = runtime_helpers.memory_similarity_score(item, baseline)
        if similarity < float(min_similarity):
            continue
        ranked.append({"memory": dict(item), "similarity": float(similarity)})
    ranked.sort(
        key=lambda item: (
            float(item.get("similarity") or 0.0),
            float(dict(item.get("memory") or {}).get("salience") or 0.0),
            int(dict(item.get("memory") or {}).get("hit_count") or 0),
            str(dict(item.get("memory") or {}).get("updated_at") or ""),
        ),
        reverse=True,
    )
    capped_limit = max(1, min(int(limit or 5), 50))
    return ranked[:capped_limit]


def merge_memories(
    store: Any,
    *,
    source_memory_id: str,
    target_memory_id: str,
    archive_source: bool = True,
) -> bool:
    source_key = str(source_memory_id or "").strip()
    target_key = str(target_memory_id or "").strip()
    if not source_key or not target_key or source_key == target_key:
        return False
    now = runtime_helpers.utc_now()
    with store._lock, store._connection() as conn:
        source_row = conn.execute("SELECT * FROM memories WHERE memory_id = ?", (source_key,)).fetchone()
        target_row = conn.execute("SELECT * FROM memories WHERE memory_id = ?", (target_key,)).fetchone()
        if source_row is None or target_row is None:
            return False
        source = runtime_helpers.memory_row_to_dict(source_row)
        target = runtime_helpers.memory_row_to_dict(target_row)
        if source.get("status") == "deleted" or target.get("status") == "deleted":
            return False
        if source.get("scope") != target.get("scope"):
            return False

        merged_tags = memory_types.normalize_string_list(list(target.get("tags") or []) + list(source.get("tags") or []))
        merged_paths = memory_types.normalize_string_list(
            list(target.get("paths") or []) + list(source.get("paths") or [])
        )
        merged_hit_count = int(target.get("hit_count") or 0) + int(source.get("hit_count") or 0)
        merged_salience = max(float(target.get("salience") or 0.0), float(source.get("salience") or 0.0))
        merged_title = str(target.get("title") or "").strip() or str(source.get("title") or "").strip()
        merged_summary = str(target.get("summary") or "").strip() or str(source.get("summary") or "").strip()
        merged_body = str(target.get("body") or "").strip() or str(source.get("body") or "").strip()
        merged_last_used_at = (
            str(target.get("last_used_at") or "").strip()
            or str(source.get("last_used_at") or "").strip()
        )

        conn.execute(
            """
            UPDATE memories
            SET title = ?, summary = ?, body = ?,
                tags_json = ?, paths_json = ?,
                hit_count = ?, salience = ?, last_used_at = ?, updated_at = ?
            WHERE memory_id = ?
            """,
            (
                merged_title,
                merged_summary,
                merged_body,
                runtime_helpers.encode_json_list(merged_tags),
                runtime_helpers.encode_json_list(merged_paths),
                merged_hit_count,
                merged_salience,
                merged_last_used_at,
                now,
                target_key,
            ),
        )
        store._append_event(
            conn,
            memory_id=target_key,
            event_type="memory_merged",
            payload={
                "source_memory_id": source_key,
                "target_memory_id": target_key,
                "archive_source": bool(archive_source),
            },
            created_at=now,
        )
        if archive_source:
            conn.execute(
                "UPDATE memories SET status = ?, updated_at = ? WHERE memory_id = ?",
                ("archived", now, source_key),
            )
            store._append_event(
                conn,
                memory_id=source_key,
                event_type="memory_archived",
                payload={"memory_id": source_key, "archived_reason": "merged_into", "target_memory_id": target_key},
                created_at=now,
            )
        conn.commit()
        return True


def list_hygiene_candidates(
    store: Any,
    *,
    limit: int = 20,
    stale_days: int = 30,
    low_signal_threshold: float = 0.75,
) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    candidates: List[Dict[str, Any]] = []
    for memory in store.list_memories(limit=500, status="active"):
        reasons: List[str] = []
        staleness = runtime_helpers.staleness_days(memory, now=now)
        low_signal = runtime_helpers.low_signal_score(memory)
        if staleness >= int(stale_days):
            reasons.append(f"stale:{staleness}d")
        if low_signal >= float(low_signal_threshold):
            reasons.append(f"low_signal:{low_signal:.2f}")
        if not reasons:
            continue
        candidates.append(
            {
                "memory": dict(memory),
                "reasons": reasons,
                "staleness_days": staleness,
                "low_signal_score": low_signal,
            }
        )
    candidates.sort(
        key=lambda item: (
            int(item.get("staleness_days") or 0),
            float(item.get("low_signal_score") or 0.0),
            int(dict(item.get("memory") or {}).get("hit_count") or 0) * -1,
        ),
        reverse=True,
    )
    capped_limit = max(1, min(int(limit or 20), 100))
    return candidates[:capped_limit]
