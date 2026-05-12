from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any


def reasoning_request(
    reasoning_effort: str | None,
    *,
    reasoning_summary: str | None = "auto",
) -> dict[str, Any] | None:
    effort = str(reasoning_effort or "").strip()
    if not effort:
        return None
    request: dict[str, Any] = {"effort": effort}
    summary = str(reasoning_summary or "").strip()
    if summary:
        request["summary"] = summary
    return request


def responses_include(
    reasoning_effort: str | None,
    *,
    reasoning_include: str,
    reasoning_summary: str | None = "auto",
) -> list[str]:
    if reasoning_request(reasoning_effort, reasoning_summary=reasoning_summary) is None:
        return []
    return [reasoning_include]


def text_request(text_verbosity: str | None) -> dict[str, Any] | None:
    verbosity = str(text_verbosity or "").strip().lower()
    if verbosity not in {"low", "medium", "high"}:
        return None
    return {"verbosity": verbosity}


def resolve_conversation_id(
    *,
    prompt_cache_key: str | None,
    session_prompt_cache_key: str | None,
    session_id: str | None = None,
    include_session_id_fallback: bool = True,
) -> str:
    candidates = [
        prompt_cache_key,
        session_prompt_cache_key,
    ]
    if include_session_id_fallback:
        candidates.append(session_id)
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if normalized:
            return normalized
    return ""


def request_extra_headers(
    *,
    prompt_cache_key: str | None,
    session_prompt_cache_key: str | None,
    turn_state: str | None,
    session_id_header: str,
    turn_state_header: str,
    session_id: str | None = None,
    reference_parity: bool = False,
    turn_id: str | None = None,
    sandbox_mode: str | None = None,
    stream: bool = False,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    conversation_id = resolve_conversation_id(
        prompt_cache_key=prompt_cache_key,
        session_prompt_cache_key=session_prompt_cache_key,
        session_id=session_id,
        include_session_id_fallback=True,
    )
    if conversation_id:
        headers[session_id_header] = conversation_id
    normalized_turn_state = str(turn_state or "").strip()
    if normalized_turn_state:
        headers[turn_state_header] = normalized_turn_state
    if reference_parity:
        if stream:
            headers["Accept"] = "text/event-stream"
        metadata = codex_turn_metadata_header(turn_id=turn_id, sandbox_mode=sandbox_mode)
        if metadata:
            headers["x-codex-turn-metadata"] = metadata
    return headers


def codex_sandbox_tag(sandbox_mode: str | None) -> str | None:
    normalized = str(sandbox_mode or "").strip().lower().replace("_", "-")
    if not normalized:
        return None
    if normalized in {"danger-full-access", "none", "bypass", "bypass-permissions"}:
        return "none"
    if normalized == "external":
        return "external"
    if sys.platform.startswith("linux") and normalized in {"read-only", "workspace-write"}:
        return "seccomp"
    if sys.platform.startswith("win") and normalized in {"read-only", "workspace-write"}:
        return "windows"
    return normalized


def codex_turn_metadata_header(*, turn_id: str | None, sandbox_mode: str | None) -> str | None:
    payload: dict[str, str] = {}
    normalized_turn_id = str(turn_id or "").strip()
    if normalized_turn_id:
        payload["turn_id"] = normalized_turn_id
    sandbox = codex_sandbox_tag(sandbox_mode)
    if sandbox:
        payload["sandbox"] = sandbox
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def capture_transport_state(
    response: Any,
    *,
    turn_state_header: str,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., Any],
) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        http_response = getattr(response, "http_response", None)
        headers = getattr(http_response, "headers", None)
    if headers is None:
        return None
    turn_state = None
    getter = getattr(headers, "get", None)
    if callable(getter):
        turn_state = getter(turn_state_header)
    elif isinstance(headers, dict):
        turn_state = headers.get(turn_state_header)
    normalized = str(turn_state or "").strip() or None
    if timeline_debug_enabled_fn():
        log_timeline_fn(
            "responses.transport.state",
            turn_state=normalized,
        )
    return normalized


def response_function_calls(
    response: Any,
    *,
    stream_item_to_dict_fn: Callable[[Any], dict[str, Any]],
    provider_tool_call_from_payload_fn: Callable[[dict[str, Any]], Any],
) -> list[Any]:
    calls: list[Any] = []
    for item in list(getattr(response, "output", []) or []):
        provider_call = provider_tool_call_from_payload_fn(stream_item_to_dict_fn(item))
        if provider_call is not None:
            calls.append(provider_call)
    return calls


def sync_runtime_debug_hooks(
    runtime_service: Any,
    *,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., Any],
) -> None:
    runtime_service.timeline_debug_enabled = timeline_debug_enabled_fn
    runtime_service.log_timeline = log_timeline_fn
