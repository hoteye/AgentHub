from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BackgroundTasksConfig
from .queue import huey_available

_WORKER_CODE_VERSION_FILES = (
    "worker_entry.py",
    "worker_state.py",
    "adapter.py",
    "storage.py",
    "queue.py",
    "tasks.py",
    "subprocess_runtime.py",
    "tasks_stream_runtime.py",
    "tasks_execution_runtime.py",
    "tasks_teammate_runtime.py",
)
_WORKER_CODE_SIGNATURE_ALGORITHM = "sha256"
_WORKER_CODE_SIGNATURE_SOURCE = "worker_code_version_files"


def worker_state_path(config: BackgroundTasksConfig) -> Path:
    return config.huey.results_dir / "worker_state.json"


def read_worker_state(config: BackgroundTasksConfig) -> dict[str, Any]:
    path = worker_state_path(config)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_worker_state(config: BackgroundTasksConfig, payload: dict[str, Any]) -> Path:
    path = worker_state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def touch_worker_state_results_dir(
    results_dir: str | Path,
    *,
    status: str | None = None,
    active_task_id: str | None = None,
    active_task_type: str | None = None,
    runner_pid: int | None = None,
) -> Path:
    path = Path(results_dir).expanduser() / "worker_state.json"
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            payload.update(loaded)
    normalized_runner_pid = _safe_int(runner_pid, 0) if runner_pid is not None else 0
    existing_status = str(payload.get("status") or "").strip().lower()
    existing_mode = str(payload.get("mode") or "").strip().lower()
    existing_worker_pid = _safe_int(payload.get("worker_pid"), 0)
    if (
        normalized_runner_pid > 0
        and existing_mode == "loop"
        and existing_status not in {"", "stopped", "exited"}
        and existing_worker_pid > 0
        and existing_worker_pid != normalized_runner_pid
        and _pid_is_running(existing_worker_pid)
    ):
        return path
    now = datetime.now(timezone.utc).isoformat()
    payload["last_heartbeat_at"] = now
    payload["last_poll_at"] = now
    if str(status or "").strip():
        payload["status"] = str(status or "").strip()
    if str(active_task_id or "").strip():
        payload["active_task_id"] = str(active_task_id or "").strip()
    if str(active_task_type or "").strip():
        payload["active_task_type"] = str(active_task_type or "").strip()
    if runner_pid is not None:
        try:
            normalized_pid = max(0, int(runner_pid))
        except (TypeError, ValueError):
            normalized_pid = 0
        if normalized_pid > 0:
            payload["active_runner_pid"] = normalized_pid
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def background_worker_status(config: BackgroundTasksConfig, *, queue_provider: str = "") -> dict[str, Any]:
    state_path = worker_state_path(config)
    state = read_worker_state(config)
    current_version = current_worker_code_version()
    worker_code_version = str(state.get("worker_code_version") or "").strip() if state else ""
    worker_code_version_match = bool(worker_code_version) and worker_code_version == current_version
    signature_meta = current_worker_code_signature_metadata()
    restart_required, restart_reason = _restart_requirement(
        state=state,
        worker_code_version=worker_code_version,
        current_worker_code_version=current_version,
    )
    payload: dict[str, Any] = {
        "enabled": bool(config.enabled),
        "provider": str(config.provider or ""),
        "queue": str(queue_provider or ""),
        "huey_available": bool(huey_available()),
        "immediate": bool(config.huey.immediate),
        "worker_count": int(config.huey.worker_count or 1),
        "state_path": str(state_path),
        "results_dir": str(config.huey.results_dir),
        "db_path": str(config.huey.path),
        "state_present": bool(state),
        "current_worker_code_version": current_version,
        "worker_code_version": worker_code_version,
        "worker_code_version_match": worker_code_version_match,
        "worker_code_signature_algorithm": str(signature_meta["algorithm"]),
        "worker_code_signature_source": str(signature_meta["source"]),
        "worker_code_signature_file_count": int(signature_meta["file_count"]),
        "restart_required": restart_required,
    }
    if restart_reason:
        payload["restart_reason"] = restart_reason
    if config.source_paths:
        payload["config_sources"] = [str(path) for path in config.source_paths]
    if state:
        payload.update(
            {
                "status": str(state.get("status") or "").strip(),
                "mode": str(state.get("mode") or "").strip(),
                "cwd": str(state.get("cwd") or "").strip(),
                "started_at": str(state.get("started_at") or "").strip(),
                "last_heartbeat_at": str(state.get("last_heartbeat_at") or "").strip(),
                "last_poll_at": str(state.get("last_poll_at") or "").strip(),
                "last_processed_at": str(state.get("last_processed_at") or "").strip(),
                "last_cleanup_at": str(state.get("last_cleanup_at") or "").strip(),
                "stopped_at": str(state.get("stopped_at") or "").strip(),
                "worker_pid": int(state.get("worker_pid") or 0),
                "last_processed_count": int(state.get("last_processed_count") or 0),
                "last_cleanup_count": int(state.get("last_cleanup_count") or 0),
                "max_jobs": int(state.get("max_jobs") or 1),
                "poll_interval": _safe_float(state.get("poll_interval"), 0.0),
                "active_task_id": str(state.get("active_task_id") or "").strip(),
                "active_task_type": str(state.get("active_task_type") or "").strip(),
                "active_runner_pid": int(state.get("active_runner_pid") or 0),
                "stop_reason": str(state.get("stop_reason") or "").strip(),
            }
        )
        cleanup_task_ids = state.get("last_cleanup_task_ids")
        if isinstance(cleanup_task_ids, list):
            payload["last_cleanup_task_ids"] = [str(item) for item in cleanup_task_ids if str(item)]
    stale_after_seconds = _stale_after_seconds(state)
    payload["stale_after_seconds"] = stale_after_seconds
    heartbeat_age_seconds = _heartbeat_age_seconds(state)
    if heartbeat_age_seconds is not None:
        payload["heartbeat_age_seconds"] = heartbeat_age_seconds
    payload["health"] = _health_value(
        config,
        queue_provider=queue_provider,
        state=state,
        heartbeat_age_seconds=heartbeat_age_seconds,
        stale_after_seconds=stale_after_seconds,
    )
    return payload


def current_worker_code_version() -> str:
    digest = _worker_code_digest()
    return f"sig:{digest.hexdigest()[:16]}"


def current_worker_code_signature_metadata() -> dict[str, Any]:
    return {
        "algorithm": _WORKER_CODE_SIGNATURE_ALGORITHM,
        "source": _WORKER_CODE_SIGNATURE_SOURCE,
        "file_count": len(_WORKER_CODE_VERSION_FILES),
        "files": list(_WORKER_CODE_VERSION_FILES),
    }


def _worker_code_digest() -> "hashlib._Hash":
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for filename in _WORKER_CODE_VERSION_FILES:
        digest.update(filename.encode("utf-8", errors="ignore"))
        path = root / filename
        try:
            raw = path.read_bytes()
        except OSError:
            raw = b"<missing>"
        digest.update(raw)
    return digest


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _pid_is_running(pid: int) -> bool:
    normalized_pid = max(0, int(pid or 0))
    if normalized_pid <= 0:
        return False
    try:
        os.kill(normalized_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _stale_after_seconds(state: dict[str, Any]) -> float:
    explicit = _safe_float(state.get("stale_after_seconds"), 0.0)
    if explicit > 0:
        return explicit
    poll_interval = max(0.0, _safe_float(state.get("poll_interval"), 0.0))
    if poll_interval > 0:
        return max(5.0, round(poll_interval * 4, 3))
    return 15.0


def _heartbeat_age_seconds(state: dict[str, Any]) -> float | None:
    raw = str(state.get("last_heartbeat_at") or "").strip()
    if not raw:
        return None
    try:
        heartbeat = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    age_seconds = max(0.0, (datetime.now(timezone.utc) - heartbeat.astimezone(timezone.utc)).total_seconds())
    return round(age_seconds, 3)


def _health_value(
    config: BackgroundTasksConfig,
    *,
    queue_provider: str,
    state: dict[str, Any],
    heartbeat_age_seconds: float | None,
    stale_after_seconds: float,
) -> str:
    if not config.enabled:
        return "disabled"
    if "unavailable" in str(queue_provider or "").strip():
        return "unavailable"
    if not state:
        return "unknown"
    status = str(state.get("status") or "").strip().lower()
    if status in {"stopped", "exited"}:
        return "stopped"
    if heartbeat_age_seconds is not None and heartbeat_age_seconds > stale_after_seconds:
        return "stale"
    if status in {"starting", "running", "busy", "idle"}:
        return "healthy"
    return "unknown"


def _restart_requirement(
    *,
    state: dict[str, Any],
    worker_code_version: str,
    current_worker_code_version: str,
) -> tuple[bool, str]:
    if not state:
        return (False, "")
    status = str(state.get("status") or "").strip().lower()
    worker_pid = _safe_int(state.get("worker_pid"), 0)
    if worker_code_version and current_worker_code_version and worker_code_version != current_worker_code_version:
        return (True, "code_version_mismatch")
    if worker_pid > 0 and status in {"starting", "running", "busy", "idle"} and not _pid_is_running(worker_pid):
        return (True, "worker_pid_stale")
    if worker_pid > 0 and status in {"starting", "running", "busy", "idle"} and not worker_code_version:
        return (True, "worker_code_version_missing")
    return (False, "")
