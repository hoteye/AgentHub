from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any


def run_prompt(
    server: Any,
    prompt: str,
    *,
    request_id: Any,
    stream: bool,
    activity_event_to_dict_fn: Callable[[Any], dict[str, Any]],
    prompt_response_turn_events_fn: Callable[[Any], list[dict[str, Any]]],
    activity_dedupe_key_fn: Callable[[Any], tuple[str, str, str, str, str]],
) -> Any:
    if not stream:
        with _temporary_request_user_input_handler(
            server.runtime,
            server._make_request_user_input_handler(request_id=request_id),
            replace_only_when_missing=True,
        ):
            return server.runtime.handle_prompt(prompt)

    emitted: set[tuple[str, str, str, str, str]] = set()
    emitted_turn_event_signatures: set[str] = set()
    emitted_turn_event_backfill_counts: dict[str, int] = {}

    def on_activity(event: Any) -> None:
        key = activity_dedupe_key_fn(event)
        emitted.add(key)
        server._emit_notification(
            "session/activity",
            {
                "requestId": request_id,
                "event": activity_event_to_dict_fn(event),
            },
        )

    def on_turn_event(event: dict[str, Any]) -> None:
        signature = _turn_event_signature(event)
        if signature in emitted_turn_event_signatures:
            return
        emitted_turn_event_signatures.add(signature)
        backfill_signature = _turn_event_backfill_signature(event)
        emitted_turn_event_backfill_counts[backfill_signature] = (
            int(emitted_turn_event_backfill_counts.get(backfill_signature) or 0) + 1
        )
        server._emit_notification(
            "session/turn_event",
            {
                "requestId": request_id,
                "event": dict(event),
            },
        )

    with _temporary_activity_callback(server.runtime, on_activity):
        with _temporary_turn_event_callback(server.runtime, on_turn_event):
            with _temporary_request_user_input_handler(
                server.runtime,
                server._make_request_user_input_handler(request_id=request_id),
                replace_only_when_missing=True,
            ):
                response = server.runtime.handle_prompt(prompt)

    for event in response.activity_events:
        key = activity_dedupe_key_fn(event)
        if key in emitted:
            continue
        server._emit_notification(
            "session/activity",
            {
                "requestId": request_id,
                "event": activity_event_to_dict_fn(event),
            },
        )
    for turn_event in list(response.turn_events or prompt_response_turn_events_fn(response)):
        if not isinstance(turn_event, dict):
            continue
        signature = _turn_event_backfill_signature(turn_event)
        remaining = int(emitted_turn_event_backfill_counts.get(signature) or 0)
        if remaining > 0:
            emitted_turn_event_backfill_counts[signature] = remaining - 1
            continue
        server._emit_notification(
            "session/turn_event",
            {
                "requestId": request_id,
                "event": dict(turn_event),
            },
        )
    return response


@contextmanager
def _temporary_activity_callback(
    runner: Any,
    callback: Any,
) -> Iterator[None]:
    previous = getattr(runner, "activity_callback", None)
    runner.activity_callback = callback
    try:
        yield
    finally:
        runner.activity_callback = previous


@contextmanager
def _temporary_turn_event_callback(
    runner: Any,
    callback: Any,
) -> Iterator[None]:
    previous = getattr(runner, "turn_event_callback", None)
    runner.turn_event_callback = callback
    try:
        yield
    finally:
        runner.turn_event_callback = previous


def _turn_event_signature(event: dict[str, Any]) -> str:
    try:
        return json.dumps(event, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(event)


def _normalized_turn_event_value(value: Any) -> Any:
    if isinstance(value, dict):
        if str(value.get("type") or "").strip() == "agent_message":
            normalized_agent_message: dict[str, Any] = {}
            for key, item in dict(value or {}).items():
                if str(key) == "id":
                    continue
                normalized_agent_message[str(key)] = _normalized_turn_event_value(item)
            phase = str(normalized_agent_message.get("phase") or "").strip().lower()
            normalized_agent_message["phase"] = phase or "final_answer"
            return normalized_agent_message
        normalized: dict[str, Any] = {}
        for key, item in dict(value or {}).items():
            if str(key) == "id":
                continue
            normalized[str(key)] = _normalized_turn_event_value(item)
        return normalized
    if isinstance(value, list):
        return [_normalized_turn_event_value(item) for item in list(value or [])]
    return value


def _turn_event_backfill_signature(event: dict[str, Any]) -> str:
    normalized = _normalized_turn_event_value(dict(event or {}))
    try:
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(normalized)


@contextmanager
def _temporary_request_user_input_handler(
    runner: Any,
    handler: Any,
    *,
    replace_only_when_missing: bool = False,
) -> Iterator[None]:
    previous = getattr(runner, "request_user_input_handler", None)
    if replace_only_when_missing and previous is not None:
        yield
        return
    runner.request_user_input_handler = handler
    try:
        yield
    finally:
        runner.request_user_input_handler = previous


@contextmanager
def temporary_activity_callback(
    runner: Any,
    callback: Any,
) -> Iterator[None]:
    with _temporary_activity_callback(runner, callback):
        yield


@contextmanager
def temporary_turn_event_callback(
    runner: Any,
    callback: Any,
) -> Iterator[None]:
    with _temporary_turn_event_callback(runner, callback):
        yield


def turn_event_signature(event: dict[str, Any]) -> str:
    return _turn_event_signature(event)


def turn_event_backfill_signature(event: dict[str, Any]) -> str:
    return _turn_event_backfill_signature(event)


@contextmanager
def temporary_request_user_input_handler(
    runner: Any,
    handler: Any,
    *,
    replace_only_when_missing: bool = False,
) -> Iterator[None]:
    with _temporary_request_user_input_handler(
        runner,
        handler,
        replace_only_when_missing=replace_only_when_missing,
    ):
        yield
