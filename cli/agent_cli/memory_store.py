from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from cli.agent_cli import memory_store_hygiene_runtime as hygiene_helpers
from cli.agent_cli import memory_store_runtime as runtime_helpers
from cli.agent_cli import memory_types
from cli.agent_cli.runtime_paths import project_local_data_dir


class MemoryStore:
    def __init__(
        self,
        base_dir: str | Path,
        *,
        scope: str = "project",
        allow_user_scope: bool | str | None = None,
    ) -> None:
        self.scope = memory_types.normalize_memory_scope(scope)
        self.allow_user_scope = runtime_helpers.user_scope_allowed(allow_user_scope=allow_user_scope)
        if self.scope == "user" and not self.allow_user_scope:
            raise PermissionError(
                "user scope memory store requires explicit opt-in; set AGENTHUB_MEMORY_USER_SCOPE_ENABLED=true "
                "or pass allow_user_scope=True"
            )
        self.base_dir = Path(base_dir).resolve()
        self.sqlite_path = self.base_dir / runtime_helpers.sqlite_basename_for_scope(self.scope)
        self._lock = threading.Lock()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @classmethod
    def default(
        cls,
        *,
        scope: str = "project",
        allow_user_scope: bool | str | None = None,
    ) -> "MemoryStore":
        normalized_scope = memory_types.normalize_memory_scope(scope)
        if normalized_scope == "user":
            return cls.user_default(allow_user_scope=allow_user_scope)
        return cls(
            project_local_data_dir() / runtime_helpers.PROJECT_SCOPE_STORAGE_DIRNAME,
            scope="project",
            allow_user_scope=allow_user_scope,
        )

    @classmethod
    def user_default(
        cls,
        *,
        allow_user_scope: bool | str | None = None,
    ) -> "MemoryStore":
        return cls(
            runtime_helpers.user_scope_storage_base_dir(),
            scope="user",
            allow_user_scope=allow_user_scope,
        )

    def _init_schema(self) -> None:
        with self._lock, self._connection() as conn:
            runtime_helpers.init_schema(conn)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _new_event_id(self) -> str:
        return f"memevt_{uuid.uuid4().hex}"

    def _append_event(
        self,
        conn: sqlite3.Connection,
        *,
        memory_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO memory_events(event_id, memory_id, event_type, payload_json, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                self._new_event_id(),
                memory_id,
                str(event_type or "").strip(),
                json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True),
                created_at,
            ),
        )

    def upsert_memory(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(payload or {})
        memory_id = str(row.get("memory_id") or "").strip() or f"mem_{uuid.uuid4().hex}"
        now = runtime_helpers.utc_now()
        existing = self.get_memory(memory_id)
        created_at = str((existing or {}).get("created_at") or row.get("created_at") or now).strip() or now
        updated_at = str(row.get("updated_at") or "").strip() or now
        normalized_scope = memory_types.normalize_memory_scope(str(row.get("scope") or ""))
        if self.scope == "user" and normalized_scope != "user":
            raise ValueError("user scope memory store only accepts scope=user records")
        if self.scope == "project" and normalized_scope == "user":
            raise PermissionError("scope=user writes require a user scope memory store with explicit opt-in")
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO memories(
                    memory_id, scope, memory_type, title, summary, body,
                    tags_json, paths_json, source_thread_id, source_turn_id,
                    status, salience, hit_count, last_used_at, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    scope=excluded.scope,
                    memory_type=excluded.memory_type,
                    title=excluded.title,
                    summary=excluded.summary,
                    body=excluded.body,
                    tags_json=excluded.tags_json,
                    paths_json=excluded.paths_json,
                    source_thread_id=excluded.source_thread_id,
                    source_turn_id=excluded.source_turn_id,
                    status=excluded.status,
                    salience=excluded.salience,
                    hit_count=excluded.hit_count,
                    last_used_at=excluded.last_used_at,
                    updated_at=excluded.updated_at
                """,
                (
                    memory_id,
                    normalized_scope,
                    memory_types.normalize_memory_type(str(row.get("memory_type") or "")),
                    str(row.get("title") or "").strip(),
                    str(row.get("summary") or "").strip(),
                    str(row.get("body") or "").strip(),
                    runtime_helpers.encode_json_list(list(row.get("tags") or [])),
                    runtime_helpers.encode_json_list(list(row.get("paths") or [])),
                    str(row.get("source_thread_id") or "").strip(),
                    str(row.get("source_turn_id") or "").strip(),
                    memory_types.normalize_memory_status(str(row.get("status") or "")),
                    float(row.get("salience") or 0.0),
                    int(row.get("hit_count") or 0),
                    str(row.get("last_used_at") or "").strip(),
                    created_at,
                    updated_at,
                ),
            )
            self._append_event(
                conn,
                memory_id=memory_id,
                event_type="memory_upserted",
                payload={"memory_id": memory_id},
                created_at=updated_at,
            )
            conn.commit()
        result = self.get_memory(memory_id)
        return dict(result or {"memory_id": memory_id})

    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        key = str(memory_id or "").strip()
        if not key:
            return None
        with self._lock, self._connection() as conn:
            row = conn.execute("SELECT * FROM memories WHERE memory_id = ?", (key,)).fetchone()
        if row is None:
            return None
        return runtime_helpers.memory_row_to_dict(row)

    def list_memories(
        self,
        *,
        limit: int = 50,
        status: str = "active",
        scope: str | None = None,
        memory_type: str | None = None,
    ) -> List[Dict[str, Any]]:
        filters: List[str] = []
        params: List[Any] = []
        normalized_status = str(status or "").strip().lower()
        if normalized_status and normalized_status != "any":
            filters.append("status = ?")
            params.append(memory_types.normalize_memory_status(normalized_status))
        if str(scope or "").strip():
            normalized_scope = memory_types.normalize_memory_scope(str(scope or ""))
            if self.scope == "project" and normalized_scope == "user":
                return []
            if self.scope == "user" and normalized_scope != "user":
                return []
            filters.append("scope = ?")
            params.append(normalized_scope)
        elif self.scope == "user":
            filters.append("scope = ?")
            params.append("user")
        if str(memory_type or "").strip():
            filters.append("memory_type = ?")
            params.append(memory_types.normalize_memory_type(str(memory_type or "")))
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        capped_limit = max(1, min(int(limit or 50), 500))
        query = f"SELECT * FROM memories {where_clause} ORDER BY updated_at DESC, memory_id ASC LIMIT ?"
        params.append(capped_limit)
        with self._lock, self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [runtime_helpers.memory_row_to_dict(row) for row in rows]

    def list_memory_events(self, memory_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        return hygiene_helpers.list_memory_events(self, memory_id, limit=limit)

    def find_similar_memories(
        self,
        memory_id: str,
        *,
        limit: int = 5,
        min_similarity: float = 0.55,
    ) -> List[Dict[str, Any]]:
        return hygiene_helpers.find_similar_memories(
            self,
            memory_id,
            limit=limit,
            min_similarity=min_similarity,
        )

    def merge_memories(
        self,
        *,
        source_memory_id: str,
        target_memory_id: str,
        archive_source: bool = True,
    ) -> bool:
        return hygiene_helpers.merge_memories(
            self,
            source_memory_id=source_memory_id,
            target_memory_id=target_memory_id,
            archive_source=archive_source,
        )

    def list_hygiene_candidates(
        self,
        *,
        limit: int = 20,
        stale_days: int = 30,
        low_signal_threshold: float = 0.75,
    ) -> List[Dict[str, Any]]:
        return hygiene_helpers.list_hygiene_candidates(
            self,
            limit=limit,
            stale_days=stale_days,
            low_signal_threshold=low_signal_threshold,
        )

    def archive_memory(self, memory_id: str) -> bool:
        key = str(memory_id or "").strip()
        if not key:
            return False
        now = runtime_helpers.utc_now()
        with self._lock, self._connection() as conn:
            result = conn.execute(
                "UPDATE memories SET status = ?, updated_at = ? WHERE memory_id = ?",
                ("archived", now, key),
            )
            if result.rowcount > 0:
                self._append_event(
                    conn,
                    memory_id=key,
                    event_type="memory_archived",
                    payload={"memory_id": key},
                    created_at=now,
                )
            conn.commit()
            return bool(result.rowcount > 0)

    def delete_memory(self, memory_id: str) -> bool:
        key = str(memory_id or "").strip()
        if not key:
            return False
        now = runtime_helpers.utc_now()
        with self._lock, self._connection() as conn:
            result = conn.execute(
                "UPDATE memories SET status = ?, updated_at = ? WHERE memory_id = ?",
                ("deleted", now, key),
            )
            if result.rowcount > 0:
                self._append_event(
                    conn,
                    memory_id=key,
                    event_type="memory_deleted",
                    payload={"memory_id": key},
                    created_at=now,
                )
            conn.commit()
            return bool(result.rowcount > 0)

    def record_memory_hit(self, memory_id: str, *, used_at: str | None = None) -> bool:
        key = str(memory_id or "").strip()
        if not key:
            return False
        timestamp = str(used_at or "").strip() or runtime_helpers.utc_now()
        with self._lock, self._connection() as conn:
            result = conn.execute(
                """
                UPDATE memories
                SET hit_count = hit_count + 1, last_used_at = ?, updated_at = ?
                WHERE memory_id = ? AND status != 'deleted'
                """,
                (timestamp, timestamp, key),
            )
            if result.rowcount > 0:
                self._append_event(
                    conn,
                    memory_id=key,
                    event_type="memory_hit",
                    payload={"memory_id": key},
                    created_at=timestamp,
                )
            conn.commit()
            return bool(result.rowcount > 0)
