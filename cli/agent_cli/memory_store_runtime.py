from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from cli.agent_cli import memory_types

AGENT_CLI_HOME_ENV = "AGENT_CLI_HOME"
DEFAULT_AGENT_CLI_HOME = Path.home() / ".agent_cli"
PROJECT_SCOPE_STORAGE_DIRNAME = "memory"
USER_SCOPE_STORAGE_DIRNAME = "memory_user"
PROJECT_SCOPE_SQLITE_BASENAME = "memory.sqlite3"
USER_SCOPE_SQLITE_BASENAME = "memory_user.sqlite3"
MEMORY_SYNC_OPT_IN_ENV = "AGENTHUB_MEMORY_SYNC_ENABLED"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode_json_list(values: List[str] | None) -> str:
    return json.dumps(memory_types.normalize_string_list(values), ensure_ascii=False)


def decode_json_list(value: str) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return memory_types.normalize_string_list(payload)


def safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def agent_cli_home() -> Path:
    configured = str(os.environ.get(AGENT_CLI_HOME_ENV) or "").strip()
    if configured:
        return safe_resolve(Path(configured))
    return safe_resolve(DEFAULT_AGENT_CLI_HOME)


def user_scope_storage_base_dir() -> Path:
    return agent_cli_home() / USER_SCOPE_STORAGE_DIRNAME


def sqlite_basename_for_scope(scope: str) -> str:
    normalized_scope = memory_types.normalize_memory_scope(scope)
    if normalized_scope == "user":
        return USER_SCOPE_SQLITE_BASENAME
    return PROJECT_SCOPE_SQLITE_BASENAME


def user_scope_allowed(*, allow_user_scope: bool | str | None = None) -> bool:
    return memory_types.user_scope_opt_in_enabled(allow_user_scope)


def memory_sync_allowed(*, enabled: bool | str | None = None) -> bool:
    if isinstance(enabled, bool):
        return enabled
    if enabled is None:
        enabled = os.environ.get(MEMORY_SYNC_OPT_IN_ENV)
    return _truthy_enabled(enabled)


def prefer_local_store_fallback(
    *,
    sync_enabled: bool | str | None = None,
    remote_available: bool | str | None = None,
) -> bool:
    if not memory_sync_allowed(enabled=sync_enabled):
        return True
    if isinstance(remote_available, bool):
        return not remote_available
    if remote_available is None:
        return False
    return not _truthy_enabled(remote_available)


def _truthy_enabled(value: bool | str | None) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on", "enabled"}


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            memory_id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]',
            paths_json TEXT NOT NULL DEFAULT '[]',
            source_thread_id TEXT NOT NULL DEFAULT '',
            source_turn_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            salience REAL NOT NULL DEFAULT 0,
            hit_count INTEGER NOT NULL DEFAULT 0,
            last_used_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_events (
            event_id TEXT PRIMARY KEY,
            memory_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_status_updated ON memories(status, updated_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_scope_type ON memories(scope, memory_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_events_memory_created ON memory_events(memory_id, created_at DESC)")


def memory_row_to_dict(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(row or {})
    return {
        "memory_id": str(payload.get("memory_id") or ""),
        "scope": memory_types.normalize_memory_scope(str(payload.get("scope") or "")),
        "memory_type": memory_types.normalize_memory_type(str(payload.get("memory_type") or "")),
        "title": str(payload.get("title") or ""),
        "summary": str(payload.get("summary") or ""),
        "body": str(payload.get("body") or ""),
        "tags": decode_json_list(str(payload.get("tags_json") or "")),
        "paths": decode_json_list(str(payload.get("paths_json") or "")),
        "source_thread_id": str(payload.get("source_thread_id") or ""),
        "source_turn_id": str(payload.get("source_turn_id") or ""),
        "status": memory_types.normalize_memory_status(str(payload.get("status") or "")),
        "salience": float(payload.get("salience") or 0.0),
        "hit_count": int(payload.get("hit_count") or 0),
        "last_used_at": str(payload.get("last_used_at") or ""),
        "created_at": str(payload.get("created_at") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
    }


def parse_iso_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def memory_signal_terms(record: Dict[str, Any]) -> Set[str]:
    tokens: Set[str] = set()
    for key in ("title", "summary", "body"):
        for raw in str(record.get(key) or "").lower().replace("/", " ").replace("_", " ").split():
            token = raw.strip(".,:;!?'\"()[]{}")
            if len(token) >= 3:
                tokens.add(token)
    for tag in list(record.get("tags") or []):
        normalized = str(tag or "").strip().lower()
        if len(normalized) >= 2:
            tokens.add(normalized)
    return tokens


def jaccard_similarity(a: Iterable[str], b: Iterable[str]) -> float:
    left = {str(item or "").strip().lower() for item in list(a or []) if str(item or "").strip()}
    right = {str(item or "").strip().lower() for item in list(b or []) if str(item or "").strip()}
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return float(len(left & right)) / float(len(union))


def memory_similarity_score(candidate: Dict[str, Any], baseline: Dict[str, Any]) -> float:
    candidate_terms = memory_signal_terms(candidate)
    baseline_terms = memory_signal_terms(baseline)
    tag_overlap = jaccard_similarity(list(candidate.get("tags") or []), list(baseline.get("tags") or []))
    path_overlap = jaccard_similarity(list(candidate.get("paths") or []), list(baseline.get("paths") or []))
    text_overlap = jaccard_similarity(candidate_terms, baseline_terms)
    return (0.45 * text_overlap) + (0.35 * tag_overlap) + (0.20 * path_overlap)


def staleness_days(record: Dict[str, Any], *, now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    last_used = parse_iso_datetime(str(record.get("last_used_at") or ""))
    updated_at = parse_iso_datetime(str(record.get("updated_at") or ""))
    anchor = last_used or updated_at
    if anchor is None:
        return 9999
    delta = current - anchor
    return max(0, int(delta.total_seconds() // 86400))


def low_signal_score(record: Dict[str, Any]) -> float:
    hit_count = int(record.get("hit_count") or 0)
    salience = float(record.get("salience") or 0.0)
    signal_terms = memory_signal_terms(record)
    content_size = len(signal_terms)
    score = 0.0
    if hit_count <= 1:
        score += 0.5
    if salience <= 0.2:
        score += 0.35
    if content_size <= 3:
        score += 0.25
    return min(1.0, score)
