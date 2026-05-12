from __future__ import annotations

import json
from typing import Any


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _flag_or_unknown(value: bool | None) -> str:
    if value is None:
        return "-"
    return _flag(value)


def _code_version_mismatch(payload: dict[str, Any]) -> bool | None:
    if "worker_code_version_match" in payload:
        return not bool(payload.get("worker_code_version_match"))
    worker_code_version = str(payload.get("worker_code_version") or "").strip()
    current_worker_code_version = str(payload.get("current_worker_code_version") or "").strip()
    if worker_code_version and current_worker_code_version:
        return worker_code_version != current_worker_code_version
    return None


def _restart_required(payload: dict[str, Any]) -> bool | None:
    if "restart_required" in payload:
        return bool(payload.get("restart_required"))
    mismatch = _code_version_mismatch(payload)
    if mismatch is not None:
        return mismatch
    return None


def _append_supervision_lines(lines: list[str], payload: dict[str, Any]) -> None:
    restart_required = _restart_required(payload)
    if restart_required is not None:
        lines.append(f"supervision_restart_required={_flag(restart_required)}")
    mismatch = _code_version_mismatch(payload)
    if mismatch is not None:
        lines.append(f"supervision_code_version_mismatch={_flag(mismatch)}")
    worker_code_version = str(payload.get("worker_code_version") or "").strip()
    current_worker_code_version = str(payload.get("current_worker_code_version") or "").strip()
    if worker_code_version or current_worker_code_version:
        lines.append(
            f"supervision_code_version={worker_code_version or '-'}->{current_worker_code_version or '-'}"
        )
    signature_source = str(payload.get("worker_code_signature_source") or "").strip()
    signature_algorithm = str(payload.get("worker_code_signature_algorithm") or "").strip()
    signature_file_count = payload.get("worker_code_signature_file_count")
    if signature_source:
        lines.append(f"supervision_signature_source={signature_source}")
    if signature_algorithm:
        lines.append(f"supervision_signature_algorithm={signature_algorithm}")
    if signature_file_count not in (None, ""):
        lines.append(f"supervision_signature_file_count={signature_file_count}")
    restart_reason = str(payload.get("restart_reason") or "").strip()
    if restart_required is True:
        if restart_reason:
            lines.append(f"supervision_restart_hint=restart_worker:{restart_reason}")
        else:
            lines.append("supervision_restart_hint=restart_worker")
    elif restart_required is False:
        lines.append("supervision_restart_hint=no_restart_needed")
    active_task_id = str(payload.get("active_task_id") or "").strip()
    active_task_type = str(payload.get("active_task_type") or "").strip()
    if active_task_id:
        active_task = active_task_id if not active_task_type else f"{active_task_id}:{active_task_type}"
        lines.append(f"supervision_active_task={active_task}")
    else:
        lines.append("supervision_active_task=none")
    cleanup_count = payload.get("last_cleanup_count")
    cleanup_task_ids = payload.get("last_cleanup_task_ids")
    has_cleanup_count = cleanup_count not in (None, "")
    has_cleanup_task_ids = cleanup_task_ids is not None
    if has_cleanup_count:
        lines.append(f"supervision_cleanup_count={cleanup_count}")
    if has_cleanup_task_ids:
        lines.append(f"supervision_cleanup_task_ids={json.dumps(cleanup_task_ids, ensure_ascii=False)}")
    if not has_cleanup_count and not has_cleanup_task_ids:
        lines.append("supervision_cleanup=none")


def background_worker_status_text(
    *,
    enabled: bool,
    provider: str,
    queue_provider_label: str,
    payload: dict[str, Any] | None,
) -> str:
    lines = ["background worker status"]
    lines.append(f"enabled={'true' if enabled else 'false'}")
    lines.append(f"provider={provider}")
    lines.append(f"queue={queue_provider_label}")
    if not isinstance(payload, dict):
        return "\n".join(lines)
    for key in ("health", "status", "mode", "state_path", "results_dir", "db_path", "cwd"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    started_at = str(payload.get("started_at") or "").strip()
    lines.append(f"started_at={started_at or '-'}")
    worker_code_version = str(payload.get("worker_code_version") or "").strip()
    current_worker_code_version = str(payload.get("current_worker_code_version") or "").strip()
    lines.append(f"worker_code_version={worker_code_version or '-'}")
    lines.append(f"current_worker_code_version={current_worker_code_version or '-'}")
    worker_code_version_match = payload.get("worker_code_version_match")
    if isinstance(worker_code_version_match, bool):
        lines.append(f"worker_code_version_match={_flag(worker_code_version_match)}")
    else:
        mismatch = _code_version_mismatch(payload)
        lines.append(f"worker_code_version_match={_flag_or_unknown(None if mismatch is None else (not mismatch))}")
    restart_required = _restart_required(payload)
    lines.append(f"restart_required={_flag_or_unknown(restart_required)}")
    restart_reason = str(payload.get("restart_reason") or "").strip()
    if restart_reason:
        lines.append(f"restart_reason={restart_reason}")
    for key in ("huey_available", "immediate", "state_present"):
        if key in payload:
            lines.append(f"{key}={'true' if payload.get(key) else 'false'}")
    for key in ("worker_count", "worker_pid", "max_jobs", "last_processed_count", "active_runner_pid"):
        if payload.get(key) not in (None, "", 0):
            lines.append(f"{key}={payload[key]}")
    for key in ("active_task_id", "active_task_type", "stop_reason"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    if payload.get("last_cleanup_count") not in (None, "", 0):
        lines.append(f"last_cleanup_count={payload['last_cleanup_count']}")
    cleanup_task_ids = payload.get("last_cleanup_task_ids")
    if cleanup_task_ids is not None:
        lines.append(f"last_cleanup_task_ids={json.dumps(cleanup_task_ids, ensure_ascii=False)}")
    for key in ("last_heartbeat_at", "last_poll_at", "last_processed_at", "last_cleanup_at", "stopped_at"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    for key in ("poll_interval", "heartbeat_age_seconds", "stale_after_seconds"):
        value = payload.get(key)
        if value not in (None, "", 0, 0.0):
            lines.append(f"{key}={value}")
    config_sources = payload.get("config_sources")
    if config_sources is not None:
        lines.append(f"config_sources={json.dumps(config_sources, ensure_ascii=False)}")
    _append_supervision_lines(lines, payload)
    return "\n".join(lines)


def background_worker_run_once_text(
    *,
    processed: int,
    max_jobs: int,
    stale_after_seconds: float,
    payload: dict[str, Any] | None,
) -> str:
    lines = ["background worker run once completed"]
    lines.append(f"processed={processed}")
    lines.append(f"max_jobs={max_jobs}")
    lines.append(f"stale_after_seconds={stale_after_seconds}")
    if isinstance(payload, dict):
        for key in ("health", "status", "state_path"):
            value = str(payload.get(key) or "").strip()
            if value:
                lines.append(f"{key}={value}")
        if payload.get("last_cleanup_count") not in (None, ""):
            lines.append(f"last_cleanup_count={payload.get('last_cleanup_count')}")
    return "\n".join(lines)


def background_worker_start_text(
    *,
    max_jobs: int,
    poll_interval: float,
    stale_after_seconds: float,
    payload: dict[str, Any],
) -> str:
    started = bool(payload.get("started"))
    title = "background worker started" if started else "background worker start noop"
    lines = [title]
    lines.append(f"max_jobs={max_jobs}")
    lines.append(f"poll_interval={poll_interval}")
    lines.append(f"stale_after_seconds={stale_after_seconds}")
    for key in ("reason", "state_path", "stdout_path", "stderr_path", "cwd"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    if payload.get("worker_pid") not in (None, "", 0):
        lines.append(f"worker_pid={payload['worker_pid']}")
    for key in ("worker_code_version", "current_worker_code_version"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    for key in ("worker_code_signature_source", "worker_code_signature_algorithm"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    if payload.get("worker_code_signature_file_count") not in (None, ""):
        lines.append(f"worker_code_signature_file_count={payload.get('worker_code_signature_file_count')}")
    if "restart_required" in payload:
        lines.append(f"restart_required={'true' if payload.get('restart_required') else 'false'}")
    restart_required = _restart_required(payload)
    if restart_required is not None:
        lines.append(f"supervision_restart_required={_flag(restart_required)}")
    mismatch = _code_version_mismatch(payload)
    if mismatch is not None:
        lines.append(f"supervision_code_version_mismatch={_flag(mismatch)}")
    command = payload.get("command")
    if command is not None:
        lines.append(f"command={json.dumps(command, ensure_ascii=False)}")
    return "\n".join(lines)


def background_worker_stop_text(*, force: bool, payload: dict[str, Any]) -> str:
    stopped = bool(payload.get("stopped"))
    title = "background worker stopped" if stopped else "background worker stop noop"
    lines = [title]
    lines.append(f"force={'true' if force else 'false'}")
    for key in ("reason", "state_path"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    if payload.get("worker_pid") not in (None, "", 0):
        lines.append(f"worker_pid={payload['worker_pid']}")
    if "forced" in payload:
        lines.append(f"forced={'true' if payload.get('forced') else 'false'}")
    return "\n".join(lines)
