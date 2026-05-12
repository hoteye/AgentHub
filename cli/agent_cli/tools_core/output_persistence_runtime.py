from __future__ import annotations

import os
import re
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


LARGE_OUTPUT_PERSIST_THRESHOLD_CHARS = 30_000
PERSISTED_OUTPUT_PREVIEW_CHARS = 4_096
PERSISTED_OUTPUT_STALE_TTL_SECONDS = 7 * 24 * 60 * 60
SHELL_BACKGROUND_ARTIFACT_DIRNAME = "background_shell"
_SAFE_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_FALLBACK_TRUNCATION_MARKER = "\n\n...[persist-to-disk unavailable; output truncated]..."
_pruned_cache_roots: set[str] = set()


@dataclass(frozen=True, slots=True)
class ToolOutputPersistenceContext:
    tool_result_projection_policy: str = ""
    workspace_root: str = ""
    thread_id: str = ""


@dataclass(frozen=True, slots=True)
class PersistedToolOutput:
    model_output: str
    persisted: bool = False
    storage_path: str = ""
    original_size: int = 0


@dataclass(frozen=True, slots=True)
class PersistedShellBackgroundArtifact:
    task_id: str
    persisted: bool = False
    artifact_path: str = ""
    storage_path: str = ""


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def _safe_component(value: object, *, fallback: str) -> str:
    text = _normalized_text(value)
    if not text:
        return fallback
    sanitized = _SAFE_COMPONENT_PATTERN.sub("_", text).strip("._")
    return sanitized or fallback


def _workspace_cache_root(workspace_root: object) -> Path | None:
    raw = _normalized_text(workspace_root)
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve(strict=False) / ".config" / "tool_output_cache"
    except OSError:
        return None


def _agent_cli_home_cache_root() -> Path | None:
    raw = _normalized_text(os.environ.get("AGENT_CLI_HOME"))
    try:
        home_root = (
            Path(raw).expanduser().resolve(strict=False)
            if raw
            else (Path.home() / ".agent_cli").resolve(strict=False)
        )
    except OSError:
        return None
    return home_root / "tool_output_cache"


def _model_visible_path(*, thread_key: str, call_key: str) -> str:
    return f".config/tool_output_cache/{thread_key}/{call_key}.txt"


def _shell_background_model_path(*, task_key: str) -> str:
    return f".config/tool_output_cache/{SHELL_BACKGROUND_ARTIFACT_DIRNAME}/{task_key}.json"


def _shell_background_storage_path(cache_root: Path, *, task_key: str) -> Path:
    return cache_root / SHELL_BACKGROUND_ARTIFACT_DIRNAME / f"{task_key}.json"


def _truncated_fallback(text: str, *, limit: int = LARGE_OUTPUT_PERSIST_THRESHOLD_CHARS) -> str:
    raw = str(text or "")
    if len(raw) <= limit:
        return raw
    clipped = raw[: max(0, limit - len(_FALLBACK_TRUNCATION_MARKER))].rstrip()
    return clipped + _FALLBACK_TRUNCATION_MARKER


def _persisted_output_wrapper(*, filepath: str, original_size: int, preview: str, has_more: bool) -> str:
    return (
        "<persisted-output>\n"
        f"filepath: {filepath}\n"
        f"originalSize: {int(original_size)}\n"
        "preview:\n"
        f"{preview}\n"
        f"hasMore: {'true' if has_more else 'false'}\n"
        "</persisted-output>"
    )


def _write_persisted_output(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_persisted_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


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


def _normalized_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _shell_background_status_projection(
    payload: Mapping[str, Any],
    *,
    foreground_adopted: bool = False,
) -> dict[str, object]:
    normalized = dict(payload or {})
    status = str(normalized.get("status") or "").strip().lower()
    phase = str(normalized.get("phase") or "").strip().lower()
    exit_code = _normalized_int(normalized.get("exit_code", normalized.get("returncode")))
    timed_out = bool(normalized.get("timed_out")) or status in {"timeout", "timed_out"}
    interrupted = bool(normalized.get("interrupted")) or status == "interrupted"
    terminal_statuses = {"ok", "error", "completed", "timeout", "timed_out", "interrupted", "pruned"}
    terminal = status in terminal_statuses or phase == "completed" or exit_code is not None
    failed = status == "error" or (
        exit_code not in (None, 0) and not timed_out and not interrupted
    )
    if timed_out:
        terminal_state = "timed_out"
    elif interrupted:
        terminal_state = "interrupted"
    elif failed:
        terminal_state = "failed"
    elif terminal:
        terminal_state = "completed"
    else:
        terminal_state = ""
    adopted = bool(terminal and foreground_adopted)
    if terminal:
        workflow_state = "completed"
        completion_state = "adopted" if adopted else "ready_to_adopt"
        result_state = "adopted" if adopted else "returned"
        notification_state = "foreground_adopted" if adopted else "ready"
        if timed_out:
            summary = "background shell timed out"
        elif interrupted:
            summary = "background shell interrupted"
        elif failed:
            summary = "background shell failed"
        else:
            summary = "background shell result adopted" if adopted else "background shell result ready"
    else:
        workflow_state = "running"
        completion_state = "pending"
        result_state = ""
        notification_state = "pending"
        summary = "background shell running"
    projected: dict[str, object] = {
        "workflow_state": workflow_state,
        "completion_state": completion_state,
        "notification_state": notification_state,
        "summary": summary,
        "adopted": adopted,
    }
    if result_state:
        projected["result_state"] = result_state
    if terminal_state:
        projected["terminal_state"] = terminal_state
    return projected


def _shell_background_artifact_payload(payload: Mapping[str, Any], *, task_id: str) -> dict[str, object]:
    normalized = dict(payload or {})
    stdout = str(normalized.get("stdout") or "")
    stderr = str(normalized.get("stderr") or "")
    aggregated_output = str(normalized.get("aggregated_output") or stdout or stderr or "")
    preview = aggregated_output[:PERSISTED_OUTPUT_PREVIEW_CHARS]
    session_id = str(normalized.get("session_id") or task_id).strip() or task_id
    process_id = str(normalized.get("process_id") or session_id).strip() or session_id
    status = str(normalized.get("status") or "").strip()
    terminal_statuses = {"ok", "error", "completed", "timeout", "timed_out", "interrupted", "pruned"}
    notification_status = "completed" if status.lower() in terminal_statuses else "pending"
    payload_out: dict[str, object] = {
        "schema_version": 1,
        "kind": "shell_background_session",
        "task_id": task_id,
        "session_id": session_id,
        "call_id": str(normalized.get("call_id") or "").strip(),
        "process_id": process_id,
        "command": str(normalized.get("command") or "").strip(),
        "cwd": str(normalized.get("cwd") or "").strip(),
        "login": bool(normalized.get("login")),
        "tty": bool(normalized.get("tty")),
        "shell": str(normalized.get("shell") or "").strip(),
        "status": status,
        "started_at_ms": _normalized_int(normalized.get("started_at_ms")),
        "finished_at_ms": _normalized_int(normalized.get("finished_at_ms")),
        "updated_at_ms": int(time.time() * 1000),
        "completion_notification_available": True,
        "completion_notification_status": notification_status,
        "completion_poll_tool": "write_stdin",
        "stdout_total_chars": _normalized_int(normalized.get("stdout_total_chars")) or len(stdout),
        "stderr_total_chars": _normalized_int(normalized.get("stderr_total_chars")) or len(stderr),
        "stdout_truncated": bool(normalized.get("stdout_truncated")),
        "stderr_truncated": bool(normalized.get("stderr_truncated")),
        "output_preview": preview,
        "has_more_output": len(aggregated_output) > len(preview),
    }
    payload_out.update(_shell_background_status_projection(normalized))
    exit_code = _normalized_int(normalized.get("exit_code", normalized.get("returncode")))
    if exit_code is not None:
        payload_out["exit_code"] = exit_code
    if normalized.get("interrupted") is not None:
        payload_out["interrupted"] = bool(normalized.get("interrupted"))
    if normalized.get("timed_out") is not None:
        payload_out["timed_out"] = bool(normalized.get("timed_out"))
    return payload_out


def persist_shell_background_artifact(
    payload: Mapping[str, Any] | None,
    *,
    workspace_root: str | None,
    task_id: str | None = None,
) -> PersistedShellBackgroundArtifact:
    normalized = dict(payload or {})
    resolved_task_id = str(task_id or normalized.get("task_id") or normalized.get("session_id") or "").strip()
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
    resolved_task_id = str(task_id or normalized.get("task_id") or normalized.get("session_id") or "").strip()
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
