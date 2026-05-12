from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from cli.agent_cli.core.provider_session import ProviderSessionResult
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers.adapters.openai_responses_request_runtime import execute_streaming_request


class _BlockingStream:
    def __init__(self) -> None:
        self.closed = threading.Event()
        self.close_calls = 0

    def __iter__(self):
        while not self.closed.wait(timeout=0.01):
            continue
        raise RuntimeError("stream closed")

    def close(self) -> None:
        self.close_calls += 1
        self.closed.set()

    def get_final_response(self):
        raise RuntimeError("stream closed")


class _SlowHeartbeatStream:
    def __init__(self, delays: list[float]) -> None:
        self.delays = list(delays)
        self.close_calls = 0

    def __iter__(self):
        for delay in self.delays:
            time.sleep(delay)
            yield object()

    def close(self) -> None:
        self.close_calls += 1


class _ManagedStreamingApiResponse:
    def __init__(self, stream) -> None:
        self._stream = stream
        self.headers = {}
        self.close_calls = 0

    def parse(self):
        return self._stream

    def close(self) -> None:
        self.close_calls += 1


class _ManagedStreamingCreate:
    def __init__(self, api_response) -> None:
        self._api_response = api_response

    def create(self, **kwargs):
        del kwargs
        api_response = self._api_response

        class _ContextManager:
            def __enter__(self_inner):
                return api_response

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _ContextManager()


class _ManagedStreamingClient:
    def __init__(self, api_response) -> None:
        self.responses = SimpleNamespace(with_streaming_response=_ManagedStreamingCreate(api_response))


def _wait_until(predicate, *, timeout_seconds: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_execute_streaming_request_raises_idle_timeout_for_hung_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTHUB_OPENAI_STREAM_IDLE_TIMEOUT_SECONDS", "0.05")
    stream = _BlockingStream()
    api_response = _ManagedStreamingApiResponse(stream)
    client = _ManagedStreamingClient(api_response)
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    with pytest.raises(RuntimeError, match="stream idle timeout before response.completed") as exc_info:
        execute_streaming_request(
            session,
            kwargs={"input": [{"role": "user", "content": "hi"}], "stream": True},
            turn_event_callback=lambda event: None,
            consume_stream=session._consume_stream,
        )

    diagnostics = dict(getattr(exc_info.value, "agenthub_provider_diagnostics", {}) or {})
    assert diagnostics["classification"] == "stream_idle_timeout"
    assert diagnostics["retryable"] is True
    assert diagnostics["source"] == "responses.send.streaming"
    assert stream.close_calls >= 1
    assert api_response.close_calls >= 1


def test_execute_streaming_request_cleans_up_watchdog_after_idle_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTHUB_OPENAI_STREAM_IDLE_TIMEOUT_SECONDS", "0.05")
    stream = _BlockingStream()
    api_response = _ManagedStreamingApiResponse(stream)
    client = _ManagedStreamingClient(api_response)
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    with pytest.raises(RuntimeError, match="stream idle timeout before response.completed"):
        execute_streaming_request(
            session,
            kwargs={"input": [{"role": "user", "content": "hi"}], "stream": True},
            turn_event_callback=lambda event: None,
            consume_stream=session._consume_stream,
        )

    assert _wait_until(
        lambda: not any(
            thread.name == "openai-stream-watchdog" and thread.is_alive()
            for thread in threading.enumerate()
        )
    )


def test_execute_streaming_request_does_not_time_out_when_stream_activity_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTHUB_OPENAI_STREAM_IDLE_TIMEOUT_SECONDS", "0.20")
    stream = _SlowHeartbeatStream([0.03, 0.03, 0.03])
    api_response = _ManagedStreamingApiResponse(stream)
    client = _ManagedStreamingClient(api_response)
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    def _consume_stream(session_obj, stream_obj, **kwargs):
        del kwargs
        mark_activity = getattr(session_obj, "mark_active_stream_activity", None)
        for _ in stream_obj:
            if callable(mark_activity):
                mark_activity()
        return ProviderSessionResult(output_text="done")

    result = execute_streaming_request(
        session,
        kwargs={"input": [{"role": "user", "content": "hi"}], "stream": True},
        turn_event_callback=lambda event: None,
        consume_stream=_consume_stream,
    )

    assert result.output_text == "done"


def test_execute_streaming_request_preserves_user_interrupt_without_idle_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTHUB_OPENAI_STREAM_IDLE_TIMEOUT_SECONDS", "0.20")
    stream = _BlockingStream()
    api_response = _ManagedStreamingApiResponse(stream)
    client = _ManagedStreamingClient(api_response)
    interrupted = threading.Event()
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        interrupt_requested=lambda: interrupted.is_set(),
    )

    timer = threading.Timer(0.03, interrupted.set)
    timer.start()
    try:
        result = execute_streaming_request(
            session,
            kwargs={"input": [{"role": "user", "content": "hi"}], "stream": True},
            turn_event_callback=lambda event: None,
            consume_stream=session._consume_stream,
        )
    finally:
        timer.cancel()

    assert result.output_text == ""
    assert result.trace["streamed"] is True
    assert result.trace["provider_native_retryable"] is False
