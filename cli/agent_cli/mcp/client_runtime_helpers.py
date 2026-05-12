from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from .client_helpers import _RetryState


def respond_permission_request(
    *,
    server_name: str,
    request_id: str,
    approved: bool,
    reason: str,
    get_cached_connection_by_name: Callable[[str], Any],
) -> dict[str, Any]:
    normalized_name = str(server_name or "").strip()
    if not normalized_name:
        raise ValueError("server name is required")
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise ValueError("request_id is required")
    handle = get_cached_connection_by_name(normalized_name)
    session = getattr(handle, "session", None) if handle is not None else None
    request_fn = getattr(session, "request", None)
    if not callable(request_fn):
        return {
            "ok": False,
            "status": "unavailable",
            "server": normalized_name,
            "request_id": normalized_request_id,
            "approved": bool(approved),
            "error": "session unavailable",
        }
    params: dict[str, Any] = {"request_id": normalized_request_id, "approved": bool(approved)}
    if str(reason or "").strip():
        params["reason"] = str(reason)
    for method in ("permission/respond", "permissions/respond"):
        try:
            response = request_fn(method, dict(params))
            payload = dict(response) if isinstance(response, Mapping) else {"ok": bool(response)}
            payload.setdefault("server", normalized_name)
            payload.setdefault("request_id", normalized_request_id)
            payload.setdefault("approved", bool(approved))
            payload.setdefault("status", "ok" if bool(payload.get("ok", True)) else "failed")
            return payload
        except Exception:
            continue
    return {
        "ok": False,
        "status": "failed",
        "server": normalized_name,
        "request_id": normalized_request_id,
        "approved": bool(approved),
        "error": "permission respond request failed",
    }


def retry_waiting(retry_state: dict[str, _RetryState], *, server_name: str) -> float | None:
    state = retry_state.get(server_name)
    if state is None:
        return None
    now = time.time()
    if now >= state.next_retry_at:
        return None
    return max(state.next_retry_at - now, 0.0)


def record_connect_failure(
    retry_state: dict[str, _RetryState],
    *,
    server_name: str,
    max_retry_attempts: int,
    base_backoff_sec: float,
    max_backoff_sec: float,
) -> tuple[int, float]:
    state = retry_state.get(server_name) or _RetryState()
    if state.attempt < max_retry_attempts:
        state.attempt += 1
    exponent = max(state.attempt - 1, 0)
    delay = min(base_backoff_sec * (2**exponent), max_backoff_sec)
    state.next_retry_at = time.time() + delay
    retry_state[server_name] = state
    return state.attempt, delay


def prune_stale_servers(
    *,
    active_names: set[str],
    cache: dict[str, Any],
    close_handle: Callable[[Any], None],
    retry_state: dict[str, _RetryState],
    descriptor_cache: dict[str, Any],
    channel_message_cache: dict[str, list[dict[str, Any]]],
    permission_request_cache: dict[str, list[dict[str, Any]]],
) -> None:
    normalized = {str(name or "").strip() for name in active_names if str(name or "").strip()}
    for cache_key, handle in list(cache.items()):
        if handle.name in normalized:
            continue
        stale = cache.pop(cache_key, None)
        if stale is not None:
            close_handle(stale)
    for server_name in list(retry_state):
        if server_name not in normalized:
            retry_state.pop(server_name, None)
    for server_name in list(descriptor_cache):
        if server_name not in normalized:
            descriptor_cache.pop(server_name, None)
    for server_name in list(channel_message_cache):
        if server_name not in normalized:
            channel_message_cache.pop(server_name, None)
    for server_name in list(permission_request_cache):
        if server_name not in normalized:
            permission_request_cache.pop(server_name, None)
