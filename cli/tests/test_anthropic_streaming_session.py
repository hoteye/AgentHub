from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.providers.anthropic_claude import AnthropicMessagesSession


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(call_id: str, name: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=payload)


class _FakeStreamContext:
    def __init__(self, *, events: list[object], final_response: object) -> None:
        self._events = list(events)
        self._final_response = final_response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._final_response


class _StreamingMessagesApi:
    def __init__(self, *, events: list[object], final_response: object) -> None:
        self.stream_requests: list[dict] = []
        self.requests = self.stream_requests
        self.with_streaming_response_requests: list[dict] = []
        self.create_requests: list[dict] = []
        self.with_streaming_response = SimpleNamespace(create=self._stream_create)
        self._events = list(events)
        self._final_response = final_response

    def stream(self, **kwargs):
        self.stream_requests.append(dict(kwargs))
        return _FakeStreamContext(events=self._events, final_response=self._final_response)

    def _stream_create(self, **kwargs):
        self.with_streaming_response_requests.append(dict(kwargs))
        raise AssertionError("with_streaming_response.create is not an event stream")

    def create(self, **kwargs):
        self.create_requests.append(dict(kwargs))
        return self._final_response


class _CreateStreamMessagesApi:
    def __init__(self, *, events: list[object], final_response: object) -> None:
        self.create_requests: list[dict] = []
        self._events = list(events)
        self._final_response = final_response

    def create(self, **kwargs):
        self.create_requests.append(dict(kwargs))
        if kwargs.get("stream") is True:
            return _FakeStreamContext(events=self._events, final_response=self._final_response)
        return self._final_response


class _FailingStreamingMessagesApi:
    def __init__(self, *, fallback_response: object) -> None:
        self.stream_requests: list[dict] = []
        self.requests = self.stream_requests
        self.with_streaming_response_requests: list[dict] = []
        self.create_requests: list[dict] = []
        self.with_streaming_response = SimpleNamespace(create=self._stream_create)
        self._fallback_response = fallback_response

    def stream(self, **kwargs):
        self.stream_requests.append(dict(kwargs))
        raise RuntimeError("stream failed")

    def _stream_create(self, **kwargs):
        self.with_streaming_response_requests.append(dict(kwargs))
        raise AssertionError("with_streaming_response.create is not an event stream")

    def create(self, **kwargs):
        self.create_requests.append(dict(kwargs))
        return self._fallback_response


class _PartialFailureStreamContext:
    def __init__(self, *, events: list[object], error: Exception) -> None:
        self._events = list(events)
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def __iter__(self):
        yield from self._events
        raise self._error

    def get_final_message(self):
        return None


class _PartialFailureStreamingMessagesApi:
    def __init__(self, *, events: list[object], error: Exception) -> None:
        self.stream_requests: list[dict] = []
        self.requests = self.stream_requests
        self.with_streaming_response_requests: list[dict] = []
        self.create_requests: list[dict] = []
        self.with_streaming_response = SimpleNamespace(create=self._stream_create)
        self._events = list(events)
        self._error = error

    def stream(self, **kwargs):
        self.stream_requests.append(dict(kwargs))
        return _PartialFailureStreamContext(events=self._events, error=self._error)

    def _stream_create(self, **kwargs):
        self.with_streaming_response_requests.append(dict(kwargs))
        raise AssertionError("with_streaming_response.create is not an event stream")

    def create(self, **kwargs):
        self.create_requests.append(dict(kwargs))
        raise AssertionError("partial stream recovery should not call non-streaming fallback")


def test_anthropic_messages_session_streaming_emits_early_events_and_tool_start() -> None:
    final_response = SimpleNamespace(
        id="msg_stream_1",
        content=[
            _text_block("先读取文件"),
            _tool_use_block("toolu_1", "file_read", {"path": "README.md"}),
        ],
    )
    stream_events = [
        {"type": "message_start", "message": {"id": "msg_stream_1"}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"text": "先读取"}},
        {"type": "content_block_delta", "index": 0, "delta": {"text": "文件"}},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "file_read",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"partial_json": '{"path":"README.md"}'},
        },
        {"type": "content_block_stop", "index": 1},
    ]
    messages_api = _StreamingMessagesApi(events=stream_events, final_response=final_response)
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[
            {"name": "file_read", "description": "Read file", "input_schema": {"type": "object"}}
        ],
        supports_tools=True,
        max_tokens=2048,
    )

    turn_events: list[dict] = []
    result = session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "read README"}],
            }
        ],
        allow_tools=True,
        prompt_cache_key="thread_123",
        turn_event_callback=lambda event: turn_events.append(dict(event)),
    )

    assert len(messages_api.requests) == 1
    assert messages_api.with_streaming_response_requests == []
    assert messages_api.create_requests == []
    assert result.output_text == "先读取文件"
    assert result.response_items[0].extra["phase"] == "commentary"
    assert [call.name for call in result.tool_calls] == ["file_read"]
    assert result.tool_calls[0].arguments == {"path": "README.md"}
    assert any(
        event.get("type") == "item.updated"
        and (event.get("item") or {}).get("type") == "agent_message"
        for event in turn_events
    )
    assert any(
        event.get("type") == "item.started"
        and (event.get("item") or {}).get("type") == "function_call"
        for event in turn_events
    )
    assert result.trace["anthropic_streaming_enabled"] is True
    assert result.trace["anthropic_streaming_fallback_reason"] == ""
    assert result.trace["streamed"] is True
    assert int(result.trace["time_to_first_event_ms"]) >= 0
    assert int(result.trace["time_to_first_tool_ms"]) >= 0
    assert result.trace["streamed_message_count"] >= 1
    assert (
        result.trace["anthropic_prompt_cache_key_skipped_reason"]
        == "anthropic_messages_no_prompt_cache_api"
    )


def test_anthropic_messages_session_uses_create_stream_true_when_stream_api_missing() -> None:
    final_response = SimpleNamespace(
        id="msg_create_stream_1",
        content=[_text_block("hello via create stream")],
    )
    messages_api = _CreateStreamMessagesApi(
        events=[
            {"type": "message_start", "message": {"id": "msg_create_stream_1"}},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            {"type": "content_block_delta", "index": 0, "delta": {"text": "hello"}},
            {"type": "content_block_delta", "index": 0, "delta": {"text": " via create stream"}},
            {"type": "content_block_stop", "index": 0},
        ],
        final_response=final_response,
    )
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[],
        supports_tools=False,
        max_tokens=2048,
    )

    result = session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ],
        allow_tools=False,
        turn_event_callback=lambda _event: None,
    )

    assert len(messages_api.create_requests) == 1
    assert messages_api.create_requests[0]["stream"] is True
    assert result.output_text == "hello via create stream"
    assert result.trace["anthropic_streaming_enabled"] is True
    assert result.trace["anthropic_streaming_fallback_reason"] == ""
    assert result.trace["streamed"] is True


def test_anthropic_messages_session_stream_failure_falls_back_to_non_streaming() -> None:
    fallback_response = SimpleNamespace(
        id="msg_fallback_1", content=[_text_block("fallback answer")]
    )
    messages_api = _FailingStreamingMessagesApi(fallback_response=fallback_response)
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[],
        supports_tools=False,
        max_tokens=2048,
    )

    streamed_events: list[dict] = []
    result = session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ],
        allow_tools=False,
        turn_event_callback=lambda event: streamed_events.append(dict(event)),
    )

    assert len(messages_api.requests) == 1
    assert messages_api.with_streaming_response_requests == []
    assert len(messages_api.create_requests) == 1
    assert streamed_events == []
    assert result.output_text == "fallback answer"
    assert result.trace["anthropic_streaming_enabled"] is False
    assert str(result.trace["anthropic_streaming_fallback_reason"]).startswith(
        "stream_request_failed"
    )
    assert result.trace["streamed"] is False
    assert result.trace["time_to_first_event_ms"] is None
    assert result.trace["time_to_first_tool_ms"] is None


def test_anthropic_messages_session_recovers_partial_stream_content_after_stream_error() -> None:
    messages_api = _PartialFailureStreamingMessagesApi(
        events=[
            {"type": "message_start", "message": {"id": "msg_partial_1"}},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            {"type": "content_block_delta", "index": 0, "delta": {"text": "先读取"}},
            {"type": "content_block_delta", "index": 0, "delta": {"text": "README"}},
            {"type": "content_block_stop", "index": 0},
        ],
        error=RuntimeError("stream interrupted"),
    )
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[],
        supports_tools=False,
        max_tokens=2048,
    )

    streamed_events: list[dict] = []
    result = session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "read README"}],
            }
        ],
        allow_tools=False,
        turn_event_callback=lambda event: streamed_events.append(dict(event)),
    )

    assert len(messages_api.requests) == 1
    assert messages_api.with_streaming_response_requests == []
    assert messages_api.create_requests == []
    assert result.output_text == "先读取README"
    assert result.trace["anthropic_streaming_enabled"] is True
    assert result.trace["anthropic_streaming_fallback_reason"] == ""
    assert (
        result.trace["anthropic_streaming_termination_reason"]
        == "stream_interrupted_partial_response:RuntimeError"
    )
    assert result.trace["streamed"] is True
    assert result.trace["streamed_message_count"] == 1
    assert streamed_events == [
        {
            "type": "item.updated",
            "item": {"id": "msg_partial_1:0", "type": "agent_message", "text": "先读取"},
        },
        {
            "type": "item.updated",
            "item": {"id": "msg_partial_1:0", "type": "agent_message", "text": "先读取README"},
        },
        {
            "type": "item.completed",
            "item": {"id": "msg_partial_1:0", "type": "agent_message", "text": "先读取README"},
        },
    ]


def test_anthropic_messages_session_recovers_partial_tool_use_after_stream_error() -> None:
    messages_api = _PartialFailureStreamingMessagesApi(
        events=[
            {"type": "message_start", "message": {"id": "msg_partial_tool_1"}},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_partial_1",
                    "name": "file_read",
                    "input": {},
                },
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"partial_json": '{"path":"README.md"}'},
            },
        ],
        error=RuntimeError("stream interrupted"),
    )
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[
            {"name": "file_read", "description": "Read file", "input_schema": {"type": "object"}}
        ],
        supports_tools=True,
        max_tokens=2048,
    )

    streamed_events: list[dict] = []
    result = session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "read README"}],
            }
        ],
        allow_tools=True,
        turn_event_callback=lambda event: streamed_events.append(dict(event)),
    )

    assert len(messages_api.requests) == 1
    assert messages_api.with_streaming_response_requests == []
    assert messages_api.create_requests == []
    assert [call.name for call in result.tool_calls] == ["file_read"]
    assert result.tool_calls[0].arguments == {"path": "README.md"}
    assert result.trace["anthropic_streaming_enabled"] is True
    assert result.trace["anthropic_streaming_fallback_reason"] == ""
    assert (
        result.trace["anthropic_streaming_termination_reason"]
        == "stream_interrupted_partial_response:RuntimeError"
    )
    assert streamed_events == [
        {
            "type": "item.started",
            "item": {
                "id": "toolu_partial_1",
                "type": "function_call",
                "call_id": "toolu_partial_1",
                "name": "file_read",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "toolu_partial_1",
                "type": "function_call",
                "call_id": "toolu_partial_1",
                "name": "file_read",
                "arguments": '{"path": "README.md"}',
            },
        },
    ]


def test_anthropic_messages_session_recovers_text_and_partial_tool_use_after_stream_error() -> None:
    messages_api = _PartialFailureStreamingMessagesApi(
        events=[
            {"type": "message_start", "message": {"id": "msg_partial_mix_1"}},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            {"type": "content_block_delta", "index": 0, "delta": {"text": "先读取"}},
            {"type": "content_block_stop", "index": 0},
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_partial_1",
                    "name": "file_read",
                    "input": {},
                },
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"partial_json": '{"path":"README.md"}'},
            },
        ],
        error=RuntimeError("stream interrupted"),
    )
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[
            {"name": "file_read", "description": "Read file", "input_schema": {"type": "object"}}
        ],
        supports_tools=True,
        max_tokens=2048,
    )

    streamed_events: list[dict] = []
    result = session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "read README"}],
            }
        ],
        allow_tools=True,
        turn_event_callback=lambda event: streamed_events.append(dict(event)),
    )

    assert len(messages_api.requests) == 1
    assert messages_api.with_streaming_response_requests == []
    assert messages_api.create_requests == []
    assert result.output_text == "先读取"
    assert [call.name for call in result.tool_calls] == ["file_read"]
    assert result.tool_calls[0].arguments == {"path": "README.md"}
    assert result.trace["anthropic_streaming_enabled"] is True
    assert result.trace["anthropic_streaming_fallback_reason"] == ""
    assert (
        result.trace["anthropic_streaming_termination_reason"]
        == "stream_interrupted_partial_response:RuntimeError"
    )
    assert result.trace["streamed"] is True
    assert result.trace["streamed_message_count"] == 1
    assert streamed_events == [
        {
            "type": "item.updated",
            "item": {"id": "msg_partial_mix_1:0", "type": "agent_message", "text": "先读取"},
        },
        {
            "type": "item.completed",
            "item": {"id": "msg_partial_mix_1:0", "type": "agent_message", "text": "先读取"},
        },
        {
            "type": "item.started",
            "item": {
                "id": "toolu_partial_1",
                "type": "function_call",
                "call_id": "toolu_partial_1",
                "name": "file_read",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "toolu_partial_1",
                "type": "function_call",
                "call_id": "toolu_partial_1",
                "name": "file_read",
                "arguments": '{"path": "README.md"}',
            },
        },
    ]
