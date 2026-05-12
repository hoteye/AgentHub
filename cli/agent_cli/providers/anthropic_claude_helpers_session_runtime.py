from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.models import FunctionCallOutputPayload


def tool_result_block(
    *,
    call_id: str,
    output: Any,
    success: bool | None,
) -> dict[str, Any]:
    payload = FunctionCallOutputPayload.from_output(output, success=success)
    text = (payload.to_text() or "Tool completed.").strip()
    if success is False and ("<error>" not in text or "</error>" not in text):
        text = f"<error>{text}</error>"
    block: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": call_id,
        "content": [{"type": "text", "text": text}],
    }
    if success is False:
        block["is_error"] = True
    return block


def request_tool_specs_payload(
    *,
    tool_specs: list[dict[str, Any]],
    cached_payload: list[dict[str, Any]] | None,
    cached_fingerprint: str,
    stable_tool_specs_payload_fn: Callable[
        [list[dict[str, Any]]], tuple[list[dict[str, Any]], str]
    ],
) -> tuple[list[dict[str, Any]], str, bool]:
    cached = list(cached_payload or [])
    normalized_cached_fingerprint = str(cached_fingerprint or "").strip()
    prepared_tool_specs, fingerprint = stable_tool_specs_payload_fn(tool_specs)
    if cached and fingerprint and fingerprint == normalized_cached_fingerprint:
        return cached, normalized_cached_fingerprint, True
    return list(prepared_tool_specs), fingerprint, False


def _log_stream_resolution(*, selected: str, callable_value: Any = None) -> None:
    if not timeline_debug_enabled():
        return
    payload: dict[str, Any] = {"selected_api": selected}
    if callable_value is not None:
        payload["callable_name"] = str(
            getattr(callable_value, "__qualname__", "")
            or getattr(callable_value, "__name__", "")
            or ""
        )
        owner = getattr(callable_value, "__self__", None)
        if owner is not None:
            payload["callable_owner_type"] = type(owner).__name__
    log_timeline("anthropic_messages.stream.resolved", **payload)


def _streaming_create_wrapper(create_fn: Callable[..., Any]) -> Callable[..., Any]:
    def _create_streaming(**kwargs: Any) -> Any:
        return create_fn(**{**kwargs, "stream": True})

    return _create_streaming


def resolve_stream_fn(
    *,
    client: Any,
    stream_fn: Callable[..., Any] | None,
) -> Callable[..., Any] | None:
    if callable(stream_fn):
        _log_stream_resolution(selected="explicit", callable_value=stream_fn)
        return stream_fn
    messages_api = getattr(client, "messages", None)
    candidate = getattr(messages_api, "stream", None)
    if callable(candidate):
        _log_stream_resolution(selected="messages.stream", callable_value=candidate)
        return candidate
    create = getattr(messages_api, "create", None)
    if callable(create):
        wrapped = _streaming_create_wrapper(create)
        _log_stream_resolution(selected="messages.create(stream=True)", callable_value=create)
        return wrapped
    _log_stream_resolution(selected="unavailable")
    return None
