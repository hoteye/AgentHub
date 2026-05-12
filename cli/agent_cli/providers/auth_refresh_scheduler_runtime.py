from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from cli.agent_cli.providers.auth_session_runtime import AuthSession
from cli.agent_cli.providers.auth_token_store_runtime import AuthTokenStore
from cli.agent_cli.providers.oauth_device_flow_runtime import refresh_oauth_token


@dataclass(frozen=True)
class RefreshProviderContext:
    provider_name: str
    token_ref: str
    token_endpoint: str
    client_id: str
    client_secret: str = ""
    scope: str = ""


@dataclass
class RefreshDaemonHandle:
    thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    running: bool = False
    interval_seconds: int = 60
    refresh_window_seconds: int = 300
    started_at: float | None = None
    last_run_at: float | None = None
    loop_count: int = 0
    last_summary: dict[str, Any] = field(default_factory=dict)
    last_error: str = ""


def session_refresh_due(
    session: AuthSession | None,
    *,
    now_ts: float | None = None,
    refresh_window_seconds: int = 300,
) -> bool:
    if session is None:
        return False
    if not str(session.refresh_token or "").strip():
        return False
    expires_at = float(session.expires_at or 0.0)
    if expires_at <= 0:
        return True
    now_value = float(now_ts if now_ts is not None else time.time())
    return expires_at <= (now_value + max(0, int(refresh_window_seconds)))


def refresh_one_due_session(
    *,
    store: AuthTokenStore,
    context: RefreshProviderContext,
    now_ts: float | None = None,
    refresh_window_seconds: int = 300,
    refresh_fn: Callable[..., Mapping[str, Any]] = refresh_oauth_token,
) -> dict[str, Any]:
    session = store.get(context.provider_name, context.token_ref)
    if not session_refresh_due(session, now_ts=now_ts, refresh_window_seconds=refresh_window_seconds):
        return {"status": "skipped", "reason": "not_due_or_missing", "provider_name": context.provider_name}
    assert session is not None
    result = dict(
        refresh_fn(
            token_endpoint=context.token_endpoint,
            client_id=context.client_id,
            client_secret=context.client_secret or None,
            scope=context.scope or None,
            refresh_token=str(session.refresh_token or "").strip(),
        )
        or {}
    )
    if str(result.get("status") or "").strip() != "ok":
        return {
            "status": "error",
            "provider_name": context.provider_name,
            "token_ref": context.token_ref,
            "error_code": str(result.get("error_code") or "refresh_failed"),
        }
    now_value = float(now_ts if now_ts is not None else time.time())
    expires_in = int(result.get("expires_in") or 0)
    refreshed = AuthSession(
        provider_name=context.provider_name,
        token_ref=context.token_ref,
        access_token=str(result.get("access_token") or "").strip(),
        refresh_token=str(result.get("refresh_token") or "").strip() or str(session.refresh_token or "").strip(),
        token_type=str(result.get("token_type") or "").strip(),
        scope=str(result.get("scope") or "").strip() or str(session.scope or "").strip(),
        expires_at=(now_value + expires_in) if expires_in > 0 else None,
        issued_at=now_value,
        metadata=dict(session.metadata or {}),
    )
    store.put(refreshed)
    return {
        "status": "ok",
        "provider_name": context.provider_name,
        "token_ref": context.token_ref,
        "expires_in": expires_in,
    }


def refresh_due_sessions(
    *,
    store: AuthTokenStore,
    contexts: list[RefreshProviderContext],
    now_ts: float | None = None,
    refresh_window_seconds: int = 300,
    refresh_fn: Callable[..., Mapping[str, Any]] = refresh_oauth_token,
) -> dict[str, Any]:
    refreshed = 0
    skipped = 0
    failed = 0
    details: list[dict[str, Any]] = []
    for context in contexts:
        result = refresh_one_due_session(
            store=store,
            context=context,
            now_ts=now_ts,
            refresh_window_seconds=refresh_window_seconds,
            refresh_fn=refresh_fn,
        )
        status = str(result.get("status") or "").strip()
        if status == "ok":
            refreshed += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1
        details.append(result)
    return {
        "status": "ok" if failed == 0 else "partial",
        "contexts": len(contexts),
        "refreshed": refreshed,
        "skipped": skipped,
        "failed": failed,
        "results": details,
    }


def refresh_daemon_status(
    *,
    handle: RefreshDaemonHandle,
) -> dict[str, Any]:
    with handle.lock:
        summary = dict(handle.last_summary or {})
        return {
            "daemon_status": "running" if bool(handle.running) else "stopped",
            "running": bool(handle.running),
            "interval_seconds": int(handle.interval_seconds),
            "refresh_window_seconds": int(handle.refresh_window_seconds),
            "started_at": float(handle.started_at) if handle.started_at is not None else None,
            "last_run_at": float(handle.last_run_at) if handle.last_run_at is not None else None,
            "loop_count": int(handle.loop_count),
            "last_error": str(handle.last_error or "").strip(),
            "summary_status": str(summary.get("status") or "").strip(),
            "contexts": int(summary.get("contexts") or 0),
            "refreshed": int(summary.get("refreshed") or 0),
            "skipped": int(summary.get("skipped") or 0),
            "failed": int(summary.get("failed") or 0),
        }


def _daemon_loop(
    *,
    handle: RefreshDaemonHandle,
    store: AuthTokenStore,
    contexts_provider: Callable[[], list[RefreshProviderContext]],
    refresh_window_seconds: int,
    refresh_fn: Callable[..., Mapping[str, Any]],
) -> None:
    interval_seconds = max(1, int(handle.interval_seconds or 60))
    while not handle.stop_event.is_set():
        now_value = time.time()
        summary: dict[str, Any]
        error_text = ""
        try:
            contexts = list(contexts_provider() or [])
            summary = refresh_due_sessions(
                store=store,
                contexts=contexts,
                now_ts=now_value,
                refresh_window_seconds=refresh_window_seconds,
                refresh_fn=refresh_fn,
            )
        except Exception as exc:
            error_text = str(exc)
            summary = {
                "status": "error",
                "contexts": 0,
                "refreshed": 0,
                "skipped": 0,
                "failed": 0,
                "results": [],
                "error_code": "refresh_daemon_iteration_failed",
            }
        with handle.lock:
            handle.last_run_at = now_value
            handle.loop_count += 1
            handle.last_summary = dict(summary or {})
            handle.last_error = error_text
        if handle.stop_event.wait(interval_seconds):
            break
    with handle.lock:
        handle.running = False
        if handle.thread is not None and not handle.thread.is_alive():
            handle.thread = None


def start_refresh_daemon(
    *,
    handle: RefreshDaemonHandle,
    store: AuthTokenStore,
    contexts_provider: Callable[[], list[RefreshProviderContext]],
    interval_seconds: int = 60,
    refresh_window_seconds: int = 300,
    refresh_fn: Callable[..., Mapping[str, Any]] = refresh_oauth_token,
) -> dict[str, Any]:
    with handle.lock:
        active = bool(handle.running and handle.thread is not None and handle.thread.is_alive())
    if active:
        snapshot = refresh_daemon_status(handle=handle)
        return {"status": "already_running", **snapshot}
    with handle.lock:
        handle.stop_event = threading.Event()
        handle.interval_seconds = max(1, int(interval_seconds or 60))
        handle.refresh_window_seconds = max(0, int(refresh_window_seconds or 300))
        handle.started_at = time.time()
        handle.last_run_at = None
        handle.loop_count = 0
        handle.last_summary = {}
        handle.last_error = ""
        handle.running = True
        thread = threading.Thread(
            target=_daemon_loop,
            kwargs={
                "handle": handle,
                "store": store,
                "contexts_provider": contexts_provider,
                "refresh_window_seconds": handle.refresh_window_seconds,
                "refresh_fn": refresh_fn,
            },
            name="auth-refresh-daemon",
            daemon=True,
        )
        handle.thread = thread
    try:
        thread.start()
    except Exception as exc:
        with handle.lock:
            handle.running = False
            handle.last_error = str(exc)
            handle.thread = None
        snapshot = refresh_daemon_status(handle=handle)
        return {
            "status": "error",
            "error_code": "refresh_daemon_start_failed",
            "error_hint": str(exc),
            **snapshot,
        }
    snapshot = refresh_daemon_status(handle=handle)
    return {"status": "started", **snapshot}


def stop_refresh_daemon(
    *,
    handle: RefreshDaemonHandle,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    with handle.lock:
        thread = handle.thread
        was_running = bool(handle.running)
        stop_event = handle.stop_event
    stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(max(0.1, float(timeout_seconds or 2.0)))
    with handle.lock:
        if handle.thread is not None and not handle.thread.is_alive():
            handle.thread = None
        handle.running = bool(handle.thread is not None and handle.thread.is_alive())
    snapshot = refresh_daemon_status(handle=handle)
    if snapshot.get("running"):
        return {"status": "stop_timeout", **snapshot}
    return {"status": "stopped" if was_running else "already_stopped", **snapshot}
