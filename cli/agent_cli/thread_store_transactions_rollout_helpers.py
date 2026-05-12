from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from cli.agent_cli import (
    thread_store_transactions_mapping_runtime as thread_store_transactions_mapping_runtime_service,
)
from cli.agent_cli.models import RolloutItem


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_rollout_path(store: Any, thread_id: str, record: Dict[str, Any]) -> Path:
    stored = Path(str(record.get("rollout_path") or ""))
    canonical = store.rollouts_dir / f"{thread_id}.jsonl"
    if stored == canonical:
        return canonical
    if canonical.exists():
        return canonical
    if stored.exists():
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(stored.read_text(encoding="utf-8"), encoding="utf-8")
        return canonical
    return canonical


def normalize_record(store: Any, record: Any) -> Any:
    canonical = store._resolve_rollout_path(record.thread_id, record.to_dict())
    canonical_text = str(canonical)
    if record.rollout_path == canonical_text:
        return record
    normalized = type(record)(
        thread_id=record.thread_id,
        name=record.name,
        created_at=record.created_at,
        updated_at=record.updated_at,
        rollout_path=canonical_text,
        cwd=record.cwd,
        turn_count=record.turn_count,
        archived=record.archived,
        last_user_text=record.last_user_text,
        last_assistant_text=record.last_assistant_text,
    )
    with store._lock, store._connection() as conn:
        conn.execute(
            """
            UPDATE threads
            SET rollout_path = ?
            WHERE thread_id = ?
            """,
            (canonical_text, record.thread_id),
        )
        conn.commit()
    return normalized


def resolve_existing_rollout_path(path_text: str | Path) -> Path:
    candidate = Path(path_text).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate
    if not resolved.exists():
        raise FileNotFoundError(f"rollout path does not exist: {resolved}")
    return resolved


def path_mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def thread_meta_from_rollout_path(rollout_path: Path, *, record_cls: type[Any]) -> Any:
    with rollout_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            rollout_item = RolloutItem.from_dict(payload)
            if rollout_item.item_type != "thread_meta":
                raise ValueError(f"rollout path is missing thread_meta: {rollout_path}")
            return record_cls(
                **thread_store_transactions_mapping_runtime_service.thread_meta_record_kwargs(
                    rollout_item=rollout_item,
                    raw_payload=payload,
                    utc_now_fn=_utc_now,
                    cwd_default=str(Path.cwd()),
                    rollout_path=rollout_path,
                    path_mtime_iso_fn=path_mtime_iso,
                )
            )
    raise ValueError(f"rollout path is empty: {rollout_path}")


def thread_rollout_summary(store: Any, rollout_path: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    preview = ""
    if not rollout_path.exists():
        return {"meta": meta, "preview": preview}
    with rollout_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            rollout_item = RolloutItem.from_dict(payload)
            if not meta and rollout_item.item_type == "thread_meta":
                meta = dict(rollout_item.payload or {})
                preview = str(meta.get("preview") or "").strip()
                if meta and preview:
                    break
                continue
            if preview:
                continue
            preview = thread_store_transactions_mapping_runtime_service.rollout_summary_from_item(
                rollout_item=rollout_item,
                history_item_from_rollout_payload_fn=store._history_item_from_rollout_payload,
            )
            if meta and preview:
                break
    return {"meta": meta, "preview": preview}


def ensure_thread_record_for_rollout_path(store: Any, rollout_path: Path) -> Dict[str, Any]:
    rollout_path_text = str(rollout_path)
    with store._lock, store._connection() as conn:
        row = conn.execute(
            """
            SELECT thread_id, name, created_at, updated_at, rollout_path, cwd,
                   turn_count, archived, last_user_text, last_assistant_text
            FROM threads
            WHERE rollout_path = ?
            """,
            (rollout_path_text,),
        ).fetchone()
    if row is not None:
        return store._normalize_record(store._row_to_record(row)).to_dict()

    discovered = store._thread_meta_from_rollout_path(rollout_path)
    existing = store.get_thread(discovered.thread_id)
    if existing is not None:
        with store._lock, store._connection() as conn:
            conn.execute(
                """
                UPDATE threads
                SET rollout_path = ?, updated_at = ?, cwd = ?, name = ?
                WHERE thread_id = ?
                """,
                (
                    rollout_path_text,
                    discovered.updated_at,
                    discovered.cwd,
                    discovered.name,
                    discovered.thread_id,
                ),
            )
            conn.commit()
        refreshed = store.get_thread(discovered.thread_id)
        if refreshed is not None:
            return refreshed

    with store._lock, store._connection() as conn:
        conn.execute(
            """
            INSERT INTO threads (
                thread_id, name, created_at, updated_at, rollout_path, cwd,
                turn_count, archived, last_user_text, last_assistant_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', '')
            ON CONFLICT(thread_id) DO UPDATE SET
                name = excluded.name,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                rollout_path = excluded.rollout_path,
                cwd = excluded.cwd
            """,
            (
                discovered.thread_id,
                discovered.name,
                discovered.created_at,
                discovered.updated_at,
                discovered.rollout_path,
                discovered.cwd,
                discovered.turn_count,
            ),
        )
        conn.commit()
    persisted = store.get_thread(discovered.thread_id)
    if persisted is None:
        raise ValueError(f"failed to materialize thread record for rollout path: {rollout_path}")
    return persisted
