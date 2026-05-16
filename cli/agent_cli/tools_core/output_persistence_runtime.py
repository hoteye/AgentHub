from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cli.agent_cli.tools_core.output_persistence_helpers import (
    LARGE_OUTPUT_PERSIST_THRESHOLD_CHARS,
    PERSISTED_OUTPUT_PREVIEW_CHARS,
    PERSISTED_OUTPUT_STALE_TTL_SECONDS,
    PersistedShellBackgroundArtifact,
    PersistedToolOutput,
    ToolOutputPersistenceContext,
    _agent_cli_home_cache_root,
    _model_visible_path,
    _normalized_text,
    _persisted_output_wrapper,
    _safe_component,
    _shell_background_artifact_payload,
    _shell_background_status_projection,
    _shell_background_storage_path,
    _truncated_fallback,
    _workspace_cache_root,
)

_pruned_cache_roots: set[str] = set()


def _write_persisted_output(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_persisted_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _remove_empty_dirs(root: Path) -> None:
    try:
        directories = sorted((path for path in root.rglob("*") if path.is_dir()), reverse=True)
    except OSError:
        return
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            continue


def prune_stale_persisted_outputs(
    cache_root: Path,
    *,
    now: float | None = None,
    stale_ttl_seconds: int = PERSISTED_OUTPUT_STALE_TTL_SECONDS,
) -> None:
    try:
        if not cache_root.exists():
            return
    except OSError:
        return
    current_time = float(now if now is not None else time.time())
    cutoff = current_time - max(0, int(stale_ttl_seconds))
    try:
        candidates = [path for path in cache_root.rglob("*") if path.is_file()]
    except OSError:
        return
    for path in candidates:
        try:
            modified_at = path.stat().st_mtime
        except OSError:
            continue
        if modified_at >= cutoff:
            continue
        _remove_file(path)
    _remove_empty_dirs(cache_root)


def persist_shell_background_artifact(
    payload: Mapping[str, Any] | None,
    *,
    workspace_root: str | None,
    task_id: str | None = None,
) -> PersistedShellBackgroundArtifact:
    normalized = dict(payload or {})
    resolved_task_id = str(
        task_id or normalized.get("task_id") or normalized.get("session_id") or ""
    ).strip()
    if not resolved_task_id:
        return PersistedShellBackgroundArtifact(task_id="")
    cache_root = _agent_cli_home_cache_root() or _workspace_cache_root(workspace_root)
    task_key = _safe_component(resolved_task_id, fallback="shell_task")
    if cache_root is None:
        return PersistedShellBackgroundArtifact(task_id=resolved_task_id)
    storage_path = _shell_background_storage_path(cache_root, task_key=task_key)
    try:
        cache_root_key = str(cache_root)
        if cache_root_key not in _pruned_cache_roots:
            _pruned_cache_roots.add(cache_root_key)
            prune_stale_persisted_outputs(cache_root)
        _write_persisted_json(
            storage_path,
            _shell_background_artifact_payload(normalized, task_id=resolved_task_id),
        )
    except OSError:
        return PersistedShellBackgroundArtifact(task_id=resolved_task_id)
    return PersistedShellBackgroundArtifact(
        task_id=resolved_task_id,
        persisted=True,
        storage_path=str(storage_path).replace(os.sep, "/"),
    )


def shell_background_contract_fields(
    payload: Mapping[str, Any] | None,
    *,
    workspace_root: str | None,
    task_id: str | None = None,
    persist: bool = True,
    foreground_adopted: bool = False,
) -> dict[str, object]:
    normalized = dict(payload or {})
    resolved_task_id = str(
        task_id or normalized.get("task_id") or normalized.get("session_id") or ""
    ).strip()
    if not resolved_task_id:
        return {}
    if persist:
        artifact = persist_shell_background_artifact(
            normalized,
            workspace_root=workspace_root,
            task_id=resolved_task_id,
        )
    else:
        artifact = PersistedShellBackgroundArtifact(
            task_id=resolved_task_id,
        )
    fields: dict[str, object] = {
        "task_id": resolved_task_id,
        "completion_notification_available": True,
        "completion_poll_tool": "write_stdin",
    }
    fields.update(
        _shell_background_status_projection(
            normalized,
            foreground_adopted=foreground_adopted,
        )
    )
    notification_state = str(fields.get("notification_state") or "").strip().lower()
    fields["completion_notification_status"] = (
        "completed" if notification_state in {"ready", "foreground_adopted"} else "pending"
    )
    if artifact.artifact_path:
        fields["background_artifact_path"] = artifact.artifact_path
    return fields


def persist_large_tool_output(
    text: str,
    *,
    call_id: str,
    context: ToolOutputPersistenceContext | None,
) -> PersistedToolOutput:
    raw = str(text or "")
    if not raw:
        return PersistedToolOutput(model_output=raw, original_size=0)
    normalized_context = context or ToolOutputPersistenceContext()
    if _normalized_text(normalized_context.tool_result_projection_policy).lower() != "claude_like":
        return PersistedToolOutput(model_output=raw, original_size=len(raw))
    if len(raw) <= LARGE_OUTPUT_PERSIST_THRESHOLD_CHARS:
        return PersistedToolOutput(model_output=raw, original_size=len(raw))
    cache_root = _workspace_cache_root(normalized_context.workspace_root)
    if cache_root is None:
        return PersistedToolOutput(
            model_output=_truncated_fallback(raw),
            original_size=len(raw),
        )

    thread_key = _safe_component(normalized_context.thread_id, fallback="adhoc")
    call_key = _safe_component(call_id, fallback="tool_output")
    storage_path = cache_root / thread_key / f"{call_key}.txt"
    model_path = _model_visible_path(thread_key=thread_key, call_key=call_key)
    try:
        cache_root_key = str(cache_root)
        if cache_root_key not in _pruned_cache_roots:
            _pruned_cache_roots.add(cache_root_key)
            prune_stale_persisted_outputs(cache_root)
        _write_persisted_output(storage_path, raw)
    except OSError:
        return PersistedToolOutput(
            model_output=_truncated_fallback(raw),
            original_size=len(raw),
        )

    preview = raw[:PERSISTED_OUTPUT_PREVIEW_CHARS]
    return PersistedToolOutput(
        model_output=_persisted_output_wrapper(
            filepath=model_path.replace(os.sep, "/"),
            original_size=len(raw),
            preview=preview,
            has_more=len(raw) > len(preview),
        ),
        persisted=True,
        storage_path=str(storage_path).replace(os.sep, "/"),
        original_size=len(raw),
    )
