from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cli.agent_cli import __version__
from cli.agent_cli import (
    thread_store_transactions_mapping_runtime as thread_store_transactions_mapping_runtime_service,
)
from cli.agent_cli import (
    thread_store_transactions_rollout_helpers as thread_store_transactions_rollout_helpers_service,
)
from cli.agent_cli.models import PromptResponse, RolloutItem


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def start_thread(
    store: Any,
    *,
    record_cls: type[Any],
    name: str | None = None,
    cwd: str | None = None,
    provider_status: dict[str, Any] | None = None,
    runtime_policy_status: dict[str, Any] | None = None,
) -> Any:
    thread_id = uuid.uuid4().hex
    created_at = _utc_now()
    rollout_path = store.rollouts_dir / f"{thread_id}.jsonl"
    record = record_cls(
        thread_id=thread_id,
        name=(name or f"Thread {created_at[:19].replace('T', ' ')}").strip(),
        created_at=created_at,
        updated_at=created_at,
        rollout_path=str(rollout_path),
        cwd=str(cwd or Path.cwd()),
        turn_count=0,
    )
    with store._lock:
        store._write_rollout_line(
            rollout_path,
            RolloutItem(
                item_type="thread_meta",
                thread_id=thread_id,
                timestamp=created_at,
                payload={
                    "name": record.name,
                    "created_at": created_at,
                    "cwd": record.cwd,
                    "path": str(rollout_path),
                    "ephemeral": False,
                    "source": "agenthub_cli",
                    "cli_version": __version__,
                    "model_provider": str((provider_status or {}).get("provider_name") or ""),
                    "provider_status": dict(provider_status or {}),
                    "runtime_policy": dict(runtime_policy_status or {}),
                },
            ).to_dict(),
        )
        with store._connection() as conn:
            conn.execute(
                """
                INSERT INTO threads (
                    thread_id, name, created_at, updated_at, rollout_path, cwd,
                    turn_count, archived, last_user_text, last_assistant_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', '')
                """,
                (
                    record.thread_id,
                    record.name,
                    record.created_at,
                    record.updated_at,
                    record.rollout_path,
                    record.cwd,
                    record.turn_count,
                ),
            )
            conn.execute(
                """
                INSERT INTO settings(key, value)
                VALUES('active_thread_id', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (record.thread_id,),
            )
            conn.commit()
    return record


def append_turn(
    store: Any,
    thread_id: str,
    response: PromptResponse,
    *,
    runtime_state: dict[str, Any] | None = None,
    update_active: bool = True,
) -> dict[str, Any]:
    record = store.get_thread(thread_id)
    if record is None:
        raise ValueError(f"unknown thread: {thread_id}")
    updated_at = _utc_now()
    last_user_text = str(response.user_text or "")
    last_assistant_text = str(response.assistant_text or "")
    assistant_history_text = store._assistant_history_text(response)
    rollout_path = store._resolve_rollout_path(thread_id, record)
    turn = store._history_turn_from_response(
        response,
        timestamp=updated_at,
        assistant_history_text=assistant_history_text,
        runtime_state=runtime_state,
    )
    line = RolloutItem(
        item_type="turn",
        thread_id=thread_id,
        timestamp=updated_at,
        payload=store._rollout_causality_payload(response, runtime_state=runtime_state),
        turn=turn,
    ).to_dict()
    with store._lock:
        store._write_rollout_line(rollout_path, line)
        with store._connection() as conn:
            conn.execute(
                """
                UPDATE threads
                SET updated_at = ?,
                    turn_count = turn_count + 1,
                    last_user_text = ?,
                    last_assistant_text = ?,
                    name = CASE
                        WHEN name LIKE 'Thread %' AND ? <> '' THEN ?
                        ELSE name
                    END
                WHERE thread_id = ?
                """,
                (
                    updated_at,
                    last_user_text[:400],
                    last_assistant_text[:400],
                    last_user_text,
                    store._derive_name(last_user_text),
                    thread_id,
                ),
            )
            if update_active:
                conn.execute(
                    """
                    INSERT INTO settings(key, value)
                    VALUES('active_thread_id', ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (thread_id,),
                )
            conn.commit()
    return line


def append_rollout_items(
    store: Any,
    thread_id: str,
    items: list[dict[str, Any]],
    *,
    update_active: bool = True,
) -> list[dict[str, Any]]:
    record = store.get_thread(thread_id)
    if record is None:
        raise ValueError(f"unknown thread: {thread_id}")
    rollout_path = store._resolve_rollout_path(thread_id, record)
    normalized: list[dict[str, Any]] = []
    with store._lock:
        for raw in list(items or []):
            payload = dict(raw or {})
            if not payload:
                continue
            payload.setdefault("thread_id", thread_id)
            payload.setdefault("timestamp", _utc_now())
            normalized.append(payload)
            store._write_rollout_line(rollout_path, payload)
        if normalized and update_active:
            with store._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO settings(key, value)
                    VALUES('active_thread_id', ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (thread_id,),
                )
                conn.commit()
    return normalized


def append_compacted(
    store: Any,
    thread_id: str,
    *,
    replacement_history: list[dict[str, Any]] | None = None,
    message: str = "",
    metadata: dict[str, Any] | None = None,
    update_active: bool = True,
) -> dict[str, Any]:
    record = store.get_thread(thread_id)
    if record is None:
        raise ValueError(f"unknown thread: {thread_id}")
    updated_at = _utc_now()
    rollout_path = store._resolve_rollout_path(thread_id, record)
    payload = thread_store_transactions_mapping_runtime_service.compacted_payload(
        thread_id=thread_id,
        timestamp=updated_at,
        replacement_history=replacement_history,
        message=message,
        metadata=metadata,
        history_item_from_rollout_payload_fn=store._history_item_from_rollout_payload,
    )
    with store._lock:
        store._write_rollout_line(rollout_path, payload)
        with store._connection() as conn:
            conn.execute(
                """
                UPDATE threads
                SET updated_at = ?
                WHERE thread_id = ?
                """,
                (
                    updated_at,
                    thread_id,
                ),
            )
            if update_active:
                conn.execute(
                    """
                    INSERT INTO settings(key, value)
                    VALUES('active_thread_id', ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (thread_id,),
                )
            conn.commit()
    return payload


def resolve_rollout_path(store: Any, thread_id: str, record: dict[str, Any]) -> Path:
    return thread_store_transactions_rollout_helpers_service.resolve_rollout_path(
        store, thread_id, record
    )


def normalize_record(store: Any, record: Any) -> Any:
    return thread_store_transactions_rollout_helpers_service.normalize_record(store, record)


def resolve_existing_rollout_path(path_text: str | Path) -> Path:
    return thread_store_transactions_rollout_helpers_service.resolve_existing_rollout_path(
        path_text
    )


def path_mtime_iso(path: Path) -> str:
    return thread_store_transactions_rollout_helpers_service.path_mtime_iso(path)


def thread_meta_from_rollout_path(rollout_path: Path, *, record_cls: type[Any]) -> Any:
    return thread_store_transactions_rollout_helpers_service.thread_meta_from_rollout_path(
        rollout_path, record_cls=record_cls
    )


def thread_rollout_summary(store: Any, rollout_path: Path) -> dict[str, Any]:
    return thread_store_transactions_rollout_helpers_service.thread_rollout_summary(
        store, rollout_path
    )


def ensure_thread_record_for_rollout_path(store: Any, rollout_path: Path) -> dict[str, Any]:
    return thread_store_transactions_rollout_helpers_service.ensure_thread_record_for_rollout_path(
        store, rollout_path
    )
