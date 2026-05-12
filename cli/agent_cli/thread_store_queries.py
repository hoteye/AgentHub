from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli import __version__


def _normalize_cwd_filter(cwd: str | None) -> str | None:
    text = str(cwd or "").strip()
    if not text:
        return None
    return str(Path(text).expanduser().resolve())


def list_threads(
    store: Any,
    *,
    limit: int = 50,
    archived: bool = False,
    cwd: str | None = None,
) -> list[dict[str, Any]]:
    normalized_cwd = _normalize_cwd_filter(cwd)
    where = "archived = ?"
    params: list[Any] = [1 if archived else 0]
    if normalized_cwd:
        where += " AND cwd = ?"
        params.append(normalized_cwd)
    params.append(max(1, int(limit)))
    with store._lock, store._connection() as conn:
        rows = conn.execute(
            f"""
            SELECT thread_id, name, created_at, updated_at, rollout_path, cwd,
                   turn_count, archived, last_user_text, last_assistant_text
            FROM threads
            WHERE {where}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    return [store._normalize_record(store._row_to_record(row)).to_dict() for row in rows]


def get_thread(store: Any, thread_id: str) -> dict[str, Any] | None:
    with store._lock, store._connection() as conn:
        row = conn.execute(
            """
            SELECT thread_id, name, created_at, updated_at, rollout_path, cwd,
                   turn_count, archived, last_user_text, last_assistant_text
            FROM threads
            WHERE thread_id = ?
            """,
            (thread_id,),
        ).fetchone()
    return store._normalize_record(store._row_to_record(row)).to_dict() if row else None


def get_active_thread_id(store: Any) -> str | None:
    with store._lock, store._connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'active_thread_id'").fetchone()
    if not row:
        return None
    value = str(row[0] or "").strip()
    return value or None


def describe_thread_record(
    store: Any,
    record: dict[str, Any] | Any,
    *,
    status: str = "not_loaded",
    turns: list[dict[str, Any]] | None = None,
    metadata_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if hasattr(record, "to_dict") and callable(record.to_dict):
        raw_record = record.to_dict()
    else:
        raw_record = dict(record or {})
    thread_id = str(raw_record.get("thread_id") or "").strip()
    if not thread_id:
        raise ValueError("thread record missing thread_id")
    normalized = store.get_thread(thread_id) or raw_record
    rollout_path = store._resolve_rollout_path(thread_id, normalized)
    rollout_summary = store._thread_rollout_summary(rollout_path)
    meta = dict(rollout_summary.get("meta") or {})
    provider_status = dict(meta.get("provider_status") or {})
    runtime_policy = dict(meta.get("runtime_policy") or {})
    cli_version = str(meta.get("cli_version") or __version__).strip() or __version__
    source = str(meta.get("source") or "agenthub_cli").strip() or "agenthub_cli"
    model_provider = (
        str(meta.get("model_provider") or "").strip()
        or str(provider_status.get("provider_name") or "").strip()
    )
    path_text = None if bool(meta.get("ephemeral")) else str(rollout_path.resolve())
    preview = str(
        rollout_summary.get("preview")
        or meta.get("preview")
        or normalized.get("last_user_text")
        or ""
    ).strip()
    metadata = {
        "provider_status": provider_status,
        "runtime_policy": runtime_policy,
    }
    if metadata_overrides:
        metadata.update(dict(metadata_overrides or {}))
    return {
        **normalized,
        "id": thread_id,
        "thread_id": thread_id,
        "preview": preview,
        "ephemeral": bool(meta.get("ephemeral")),
        "model_provider": model_provider,
        "status": str(status or "not_loaded").strip() or "not_loaded",
        "path": path_text,
        "cwd": str(normalized.get("cwd") or meta.get("cwd") or ""),
        "cli_version": cli_version,
        "source": source,
        "created_at_unix": store._iso_to_unix_seconds(str(normalized.get("created_at") or "")),
        "updated_at_unix": store._iso_to_unix_seconds(str(normalized.get("updated_at") or "")),
        "turns": [dict(item) for item in list(turns or []) if isinstance(item, dict)],
        "metadata": metadata,
    }


def describe_thread(
    store: Any,
    thread_id: str,
    *,
    status: str = "not_loaded",
    turns: list[dict[str, Any]] | None = None,
    metadata_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = store.get_thread(thread_id)
    if record is None:
        raise ValueError(f"unknown thread: {thread_id}")
    return describe_thread_record(
        store,
        record,
        status=status,
        turns=turns,
        metadata_overrides=metadata_overrides,
    )
