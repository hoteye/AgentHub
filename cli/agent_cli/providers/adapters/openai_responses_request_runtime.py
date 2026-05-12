from __future__ import annotations

import inspect
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli.core.provider_session import ProviderSessionResult

_STREAM_IDLE_TIMEOUT_ERROR = "stream idle timeout before response.completed"
_EXTRA_BODY_REQUEST_KEYS = ("client_metadata",)


def sdk_request_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    request_kwargs = dict(kwargs)
    extra_body = dict(request_kwargs.get("extra_body") or {})
    for key in _EXTRA_BODY_REQUEST_KEYS:
        if key not in request_kwargs:
            continue
        extra_body[key] = request_kwargs.pop(key)
    if extra_body:
        request_kwargs["extra_body"] = extra_body
    return request_kwargs


def _stream_idle_timeout_seconds() -> float:
    raw = str(os.getenv("AGENTHUB_OPENAI_STREAM_IDLE_TIMEOUT_SECONDS", "") or "").strip()
    if not raw:
        return 30.0
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        return 30.0
    return max(0.0, parsed)


def _idle_timeout_exception(*, source: str, idle_timeout_seconds: float) -> RuntimeError:
    exc = RuntimeError(_STREAM_IDLE_TIMEOUT_ERROR)
    exc.agenthub_provider_diagnostics = {
        "source": source,
        "classification": "stream_idle_timeout",
        "retryable": True,
        "idle_timeout_seconds": idle_timeout_seconds,
    }
    return exc


def execute_non_streaming_request(
    session: Any,
    *,
    kwargs: dict[str, Any],
) -> Any:
    request_kwargs = sdk_request_kwargs(kwargs)
    raw_responses = getattr(getattr(session.client, "responses", None), "with_raw_response", None)
    if raw_responses is not None and callable(getattr(raw_responses, "create", None)):
        raw_response = raw_responses.create(**request_kwargs)
        session._capture_transport_state(raw_response)
        return raw_response.parse()
    response = session.client.responses.create(**request_kwargs)
    session._capture_transport_state(response)
    return response


def execute_streaming_request(
    session: Any,
    *,
    kwargs: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
    consume_stream: Callable[..., ProviderSessionResult],
) -> ProviderSessionResult:
    def _close_stream_resources(*resources: Any) -> None:
        for resource in resources:
            if resource is None:
                continue
            closer = getattr(resource, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    continue

    def _consume_with_idle_timeout(
        *,
        stream: Any,
        interrupter: Callable[[], None],
        source: str,
    ) -> ProviderSessionResult:
        def _invoke_consume_stream() -> ProviderSessionResult:
            callback_kwargs = {
                "turn_event_callback": turn_event_callback,
                "initial_input_items": initial_input_items,
            }
            bound_self = getattr(consume_stream, "__self__", None)
            if bound_self is session:
                return consume_stream(stream, **callback_kwargs)
            try:
                signature = inspect.signature(consume_stream)
            except (TypeError, ValueError):
                signature = None
            if signature is not None:
                positional_params = [
                    parameter
                    for parameter in signature.parameters.values()
                    if parameter.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                if len(positional_params) <= 1:
                    return consume_stream(stream, **callback_kwargs)
            return consume_stream(session, stream, **callback_kwargs)

        idle_timeout_seconds = _stream_idle_timeout_seconds()
        stop_watchdog = threading.Event()
        idle_timeout_triggered = threading.Event()
        last_activity_lock = threading.Lock()
        last_activity_monotonic = time.monotonic()

        def _mark_activity() -> None:
            nonlocal last_activity_monotonic
            with last_activity_lock:
                last_activity_monotonic = time.monotonic()

        def _trigger_stream_shutdown() -> None:
            try:
                interrupter()
            except Exception:
                return

        def _watchdog() -> None:
            while not stop_watchdog.wait(timeout=0.05):
                if session._is_interrupt_requested():
                    _trigger_stream_shutdown()
                    return
                if idle_timeout_seconds <= 0:
                    continue
                with last_activity_lock:
                    last_activity_age = time.monotonic() - last_activity_monotonic
                if last_activity_age >= idle_timeout_seconds:
                    idle_timeout_triggered.set()
                    _trigger_stream_shutdown()
                    return

        watchdog = threading.Thread(
            target=_watchdog,
            name="openai-stream-watchdog",
            daemon=True,
        )
        register_activity = getattr(session, "register_active_stream_activity_callback", None)
        clear_activity = getattr(session, "clear_active_stream_activity_callback", None)
        if callable(register_activity):
            register_activity(_mark_activity)
        watchdog.start()
        try:
            result = _invoke_consume_stream()
        except BaseException as exc:
            if idle_timeout_triggered.is_set():
                if isinstance(exc, RuntimeError) and str(exc) == _STREAM_IDLE_TIMEOUT_ERROR:
                    raise
                raise _idle_timeout_exception(
                    source=source, idle_timeout_seconds=idle_timeout_seconds
                ) from exc
            raise
        finally:
            stop_watchdog.set()
            if callable(clear_activity):
                clear_activity(_mark_activity)
            watchdog.join(timeout=1.0)
        if idle_timeout_triggered.is_set():
            raise _idle_timeout_exception(source=source, idle_timeout_seconds=idle_timeout_seconds)
        return result

    streaming_responses = getattr(
        getattr(session.client, "responses", None), "with_streaming_response", None
    )
    initial_input_items: list[dict[str, Any]] = list(kwargs.get("input") or [])
    request_kwargs = sdk_request_kwargs(kwargs)
    if streaming_responses is not None and callable(getattr(streaming_responses, "create", None)):
        with streaming_responses.create(**request_kwargs) as api_response:
            session._capture_transport_state(api_response)
            stream = api_response.parse()

            def interrupter() -> None:
                _close_stream_resources(stream, api_response)

            session.register_active_stream_interrupter(interrupter)
            try:
                if session._is_interrupt_requested():
                    interrupter()
                return _consume_with_idle_timeout(
                    stream=stream,
                    interrupter=interrupter,
                    source="responses.send.streaming",
                )
            finally:
                session.clear_active_stream_interrupter(interrupter)
    stream = session.client.responses.create(**request_kwargs)
    session._capture_transport_state(stream)

    def interrupter() -> None:
        _close_stream_resources(stream)

    session.register_active_stream_interrupter(interrupter)
    try:
        if session._is_interrupt_requested():
            interrupter()
        return _consume_with_idle_timeout(
            stream=stream,
            interrupter=interrupter,
            source="responses.send.streaming",
        )
    finally:
        session.clear_active_stream_interrupter(interrupter)
