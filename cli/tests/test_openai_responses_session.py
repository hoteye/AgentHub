from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cli.agent_cli.core.provider_session import ProviderSessionResult
from cli.agent_cli.models import ResponseInputItem, ToolEvent
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers.adapters.openai_responses_error_runtime import (
    call_with_responses_503_diagnostics,
)
from cli.agent_cli.providers.adapters.openai_responses_input import (
    normalize_input_items,
    reference_environment_context_text,
    workspace_context_message_text,
)
from cli.agent_cli.providers.adapters.openai_responses_payload_runtime import (
    build_send_request,
)
from cli.agent_cli.providers.adapters.openai_responses_request_runtime import (
    execute_streaming_request,
)
from cli.agent_cli.providers.adapters.openai_responses_result_runtime import (
    build_response_result,
)
from cli.agent_cli.providers.adapters.openai_responses_stream_runtime import (
    response_item_turn_event,
)


class _FakeResponses:
    def __init__(self, response) -> None:
        self.response = response
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(dict(kwargs))
        return self.response


class _FakeRawResponse:
    def __init__(self, response, headers: dict[str, str] | None = None) -> None:
        self._response = response
        self.headers = headers or {}

    def parse(self):
        return self._response


class _FakeRawResponses:
    def __init__(self, response, headers: dict[str, str] | None = None) -> None:
        self.response = response
        self.headers = headers or {}
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(dict(kwargs))
        return _FakeRawResponse(self.response, headers=self.headers)


class _FakeClient:
    def __init__(self, response) -> None:
        self.responses = _FakeResponses(response)


class _FakeRawClient:
    def __init__(self, response, headers: dict[str, str] | None = None) -> None:
        self.responses = _FakeResponses(response)
        self.responses.with_raw_response = _FakeRawResponses(response, headers=headers)


class _FakeStreamClient:
    def __init__(self, events) -> None:
        self.responses = _FakeResponses(events)


class _FlakyResponses:
    def __init__(self, scripted) -> None:
        self.scripted = list(scripted)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(dict(kwargs))
        if not self.scripted:
            raise AssertionError("unexpected responses.create call")
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FlakyClient:
    def __init__(self, scripted) -> None:
        self.responses = _FlakyResponses(scripted)


class _FakeWebsocketClient(_FakeClient):
    transport_kind = "websocket"


class _FakeHttpClient(_FakeClient):
    transport_kind = "http"


class _FakeStream:
    def __init__(self, events, final_response=None) -> None:
        self._events = list(events)
        self._final_response = final_response

    def __iter__(self):
        return iter(self._events)

    def get_final_response(self):
        return self._final_response


class _ClosableParsedStream:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _ManagedStreamingApiResponse:
    def __init__(self, stream) -> None:
        self._stream = stream
        self.headers: dict[str, str] = {}
        self.close_calls = 0

    def parse(self):
        return self._stream

    def close(self) -> None:
        self.close_calls += 1


class _ManagedStreamingCreate:
    def __init__(self, api_response) -> None:
        self._api_response = api_response
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(dict(kwargs))
        api_response = self._api_response

        class _ContextManager:
            def __enter__(self_inner):
                return api_response

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _ContextManager()


class _ManagedStreamingClient:
    def __init__(self, api_response) -> None:
        self.responses = _FakeResponses(None)
        self.responses.with_streaming_response = _ManagedStreamingCreate(api_response)


class _InterruptedBrokenStream:
    def __iter__(self):
        raise RuntimeError("stream closed")

    def get_final_response(self):
        raise RuntimeError("stream closed")


class _InterruptedAfterEventsStream:
    def __init__(self, events) -> None:
        self._events = list(events)

    def __iter__(self):
        yield from self._events
        raise RuntimeError("stream closed")

    def get_final_response(self):
        raise RuntimeError("stream closed")


def _response(
    *items, response_id: str = "resp_1", status: str = "completed", output_text: str = "final text"
):
    return SimpleNamespace(
        id=response_id,
        status=status,
        output=list(items),
        output_text=output_text,
    )


def _function_call(call_id: str, name: str, arguments: str):
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


def _function_call_stream_item(
    call_id: str,
    name: str,
    *,
    item_id: str = "fc_1",
    arguments: str | None = None,
    status: str | None = "in_progress",
):
    payload = {
        "type": "function_call",
        "id": item_id,
        "call_id": call_id,
        "name": name,
    }
    if arguments is not None:
        payload["arguments"] = arguments
    if status is not None:
        payload["status"] = status
    return payload


def _custom_tool_call(call_id: str, name: str, tool_input: str):
    return SimpleNamespace(
        type="custom_tool_call",
        call_id=call_id,
        name=name,
        input=tool_input,
    )


def _message_item(text: str, *, phase: str | None = None):
    return SimpleNamespace(
        type="message",
        role="assistant",
        phase=phase,
        content=[SimpleNamespace(type="output_text", text=text)],
    )


def _reasoning_item(summary_text: str, *, encrypted_content: str = "enc-1"):
    return SimpleNamespace(
        type="reasoning",
        content=None,
        encrypted_content=encrypted_content,
        summary=[SimpleNamespace(type="summary_text", text=summary_text)],
    )


def _web_search_call(query: str):
    return SimpleNamespace(
        type="web_search_call",
        status="completed",
        action={
            "type": "search",
            "query": query,
            "queries": [query],
        },
    )


def _stream_event(event_type: str, **payload):
    return SimpleNamespace(type=event_type, **payload)


def _resume_request_snapshot(request: dict) -> dict:
    return {
        "resume_items": list(request.get("input") or []),
        "resume_strategy": (
            "previous_response_id" if "previous_response_id" in request else "full_input_replay"
        ),
        "resume_cursor": request.get("previous_response_id"),
    }


def test_openai_responses_session_send_with_tools_and_reasoning():
    client = _FakeClient(
        _response(
            _function_call("call_1", "file_list", '{"path": ".", "limit": 5}'),
        )
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_list"}],
        reasoning_effort="medium",
    )

    result = session.send(
        input_items=[{"role": "user", "content": "list files"}],
        allow_tools=True,
        previous_response_id="resp_prev",
    )

    assert result.output_text == "final text"
    assert result.response_id == "resp_1"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].call_id == "call_1"
    assert result.tool_calls[0].name == "file_list"
    assert result.tool_calls[0].arguments == {"path": ".", "limit": 5}
    assert result.trace["tool_calls"] == ["file_list"]
    assert result.trace["tool_call_count"] == 1
    assert result.trace["answered"] is False

    request = client.responses.requests[0]
    assert request["model"] == "gpt-5.4"
    assert request["instructions"] == "system"
    assert request["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "list files"}],
        }
    ]
    assert request["store"] is False
    assert request["stream"] is False
    assert request["previous_response_id"] == "resp_prev"
    assert request["reasoning"] == {"effort": "medium", "summary": "auto"}
    assert request["include"] == ["reasoning.encrypted_content"]
    assert request["tools"] == [{"type": "function", "name": "file_list"}]
    assert request["tool_choice"] == "auto"
    assert request["parallel_tool_calls"] is False
    assert result.continuation_input_items == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "list files"}],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "file_list",
            "arguments": '{"path": ".", "limit": 5}',
        },
    ]


def test_openai_responses_session_disabling_incremental_continuation_omits_previous_response_id():
    client = _FakeClient(_response(response_id="resp_no_cursor"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    assert session.uses_incremental_continuation() is True
    session.disable_incremental_continuation(reason="previous_response_id_unsupported")
    assert session.uses_incremental_continuation() is False

    session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
        previous_response_id="resp_prev",
    )

    request = client.responses.requests[0]
    assert "previous_response_id" not in request


def test_build_response_result_marks_tool_call_turn_as_unanswered() -> None:
    response = _response(_function_call("call_1", "file_list", '{"path": ".", "limit": 5}'))
    session = OpenAIResponsesSession(
        client=_FakeClient(response),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_list"}],
    )

    result = build_response_result(
        session,
        response=response,
        normalized_input=[
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "ls"}]}
        ],
    )

    assert result.trace["answered"] is False
    assert result.trace["answer_preview"] == ""
    assert result.trace["tool_calls"] == ["file_list"]


def test_build_response_result_uses_projected_output_text_for_answer_preview() -> None:
    response = SimpleNamespace(
        id="resp_projected",
        output=[_message_item("最终分析：还剩 3 个差距。")],
        output_text="",
    )
    session = OpenAIResponsesSession(
        client=_FakeClient(response),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    result = build_response_result(
        session,
        response=response,
        normalized_input=[{"type": "function_call_output", "call_id": "call_1", "output": "{}"}],
    )

    assert result.output_text == "最终分析：还剩 3 个差距。"
    assert result.trace["answered"] is True
    assert result.trace["answer_preview"] == "最终分析：还剩 3 个差距。"


def test_openai_responses_session_logs_provider_metadata_in_request_raw() -> None:
    client = _FakeClient(_response(response_id="resp_trace"))
    client.base_url = "https://client.example/v1"
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        provider_name="openai",
        base_url="https://relay.example/v1",
    )

    with (
        patch(
            "cli.agent_cli.providers.adapters.openai_responses.timeline_debug_enabled",
            return_value=True,
        ),
        patch(
            "cli.agent_cli.providers.adapters.openai_responses.log_timeline"
        ) as log_timeline_mock,
    ):
        session.send(
            input_items=[{"role": "user", "content": "hello"}],
            allow_tools=False,
        )

    request_call = next(
        call
        for call in log_timeline_mock.call_args_list
        if call.args[0] == "responses.send.request_raw"
    )
    assert request_call.kwargs["provider_name"] == "openai"
    assert request_call.kwargs["base_url"] == "https://relay.example/v1"


def test_openai_responses_session_send_includes_prompt_cache_key_when_configured():
    client = _FakeClient(_response(response_id="resp_cache"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        prompt_cache_key="thread_123",
    )

    session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["prompt_cache_key"] == "thread_123"
    assert request["extra_headers"] == {"session_id": "thread_123"}


def test_openai_responses_session_codex_profile_includes_codex_headers_for_streaming_requests():
    client = _FakeClient(_response(response_id="resp_codex"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        prompt_cache_key="thread_123",
        reference_parity=True,
        session_id="thread_123",
        turn_id="turn_abc",
        sandbox_mode="workspace-write",
    )

    normalized_input, kwargs, effective_prompt_cache_key = build_send_request(
        session,
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
        previous_response_id=None,
        prompt_cache_key=None,
        turn_event_callback=lambda event: None,
    )

    assert effective_prompt_cache_key == "thread_123"
    assert normalized_input == kwargs["input"]
    assert kwargs["extra_headers"]["session_id"] == "thread_123"
    assert kwargs["extra_headers"]["Accept"] == "text/event-stream"
    assert kwargs["extra_headers"]["x-codex-turn-metadata"] == json.dumps(
        {"turn_id": "turn_abc", "sandbox": "seccomp"},
        ensure_ascii=True,
        separators=(",", ":"),
    )


def test_build_send_request_codex_profile_falls_back_to_session_id_for_prompt_cache_key() -> None:
    session = OpenAIResponsesSession(
        client=_FakeClient(_response(response_id="resp_codex_fallback")),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reference_parity=True,
        session_id="thread_from_session",
    )

    normalized_input, kwargs, effective_prompt_cache_key = build_send_request(
        session,
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
        previous_response_id=None,
        prompt_cache_key=None,
        turn_event_callback=None,
    )

    assert normalized_input == kwargs["input"]
    assert effective_prompt_cache_key == "thread_from_session"
    assert kwargs["prompt_cache_key"] == "thread_from_session"
    assert kwargs["extra_headers"]["session_id"] == "thread_from_session"


def test_build_send_request_extracts_payload_assembly_seam() -> None:
    session = OpenAIResponsesSession(
        client=_FakeClient(_response(response_id="resp_payload")),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_list"}],
        reasoning_effort="medium",
        prompt_cache_key="thread_123",
    )

    normalized_input, kwargs, effective_prompt_cache_key = build_send_request(
        session,
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=True,
        previous_response_id="resp_prev",
        prompt_cache_key=None,
        turn_event_callback=lambda event: None,
    )

    assert effective_prompt_cache_key == "thread_123"
    assert normalized_input == kwargs["input"]
    assert kwargs["stream"] is True
    assert kwargs["previous_response_id"] == "resp_prev"
    assert kwargs["prompt_cache_key"] == "thread_123"
    assert kwargs["reasoning"] == {"effort": "medium", "summary": "auto"}
    assert kwargs["include"] == ["reasoning.encrypted_content"]
    assert kwargs["tools"] == [{"type": "function", "name": "file_list"}]
    assert kwargs["parallel_tool_calls"] is False


def test_build_send_request_reference_parity_enables_parallel_tool_calls() -> None:
    session = OpenAIResponsesSession(
        client=_FakeClient(_response(response_id="resp_payload")),
        model="gpt-5.5",
        instructions="system",
        tool_specs=[{"type": "function", "name": "exec_command"}],
        reference_parity=True,
    )

    _normalized_input, kwargs, _effective_prompt_cache_key = build_send_request(
        session,
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=True,
        previous_response_id=None,
        prompt_cache_key=None,
        turn_event_callback=lambda event: None,
    )

    assert kwargs["parallel_tool_calls"] is True


def test_build_send_request_reference_parity_aligns_codex_request_controls() -> None:
    session = OpenAIResponsesSession(
        client=_FakeHttpClient(_response(response_id="resp_payload")),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "exec_command"}],
        reasoning_effort="xhigh",
        reference_parity=True,
        client_metadata={"x-codex-installation-id": "install-test"},
    )

    _normalized_input, kwargs, _effective_prompt_cache_key = build_send_request(
        session,
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=True,
        previous_response_id="resp_prev",
        prompt_cache_key=None,
        turn_event_callback=lambda event: None,
    )

    assert "previous_response_id" not in kwargs
    assert kwargs["reasoning"] == {"effort": "xhigh"}
    assert kwargs["include"] == ["reasoning.encrypted_content"]
    assert kwargs["text"] == {"verbosity": "low"}
    assert kwargs["client_metadata"] == {"x-codex-installation-id": "install-test"}
    assert kwargs["parallel_tool_calls"] is True


def test_openai_responses_session_logs_request_body_and_transport_separately_for_codex_profile() -> (
    None
):
    client = _FakeClient(_response(response_id="resp_trace_codex"))
    client.base_url = "https://client.example/v1"
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        provider_name="openai",
        base_url="https://relay.example/v1",
        reference_parity=True,
        session_id="thread_123",
        turn_id="turn_abc",
        sandbox_mode="workspace-write",
    )

    with (
        patch(
            "cli.agent_cli.providers.adapters.openai_responses.timeline_debug_enabled",
            return_value=True,
        ),
        patch(
            "cli.agent_cli.providers.adapters.openai_responses.log_timeline"
        ) as log_timeline_mock,
    ):
        session.send(
            input_items=[{"role": "user", "content": "hello"}],
            allow_tools=False,
        )

    request_call = next(
        call
        for call in log_timeline_mock.call_args_list
        if call.args[0] == "responses.send.request_raw"
    )
    transport_call = next(
        call
        for call in log_timeline_mock.call_args_list
        if call.args[0] == "responses.send.transport.request_raw"
    )

    assert request_call.kwargs["request"]["prompt_cache_key"] == "thread_123"
    assert "extra_headers" not in request_call.kwargs["request"]
    assert transport_call.kwargs["transport"]["extra_headers"] == {
        "session_id": "thread_123",
        "x-codex-turn-metadata": json.dumps(
            {"turn_id": "turn_abc", "sandbox": "seccomp"},
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    }


def test_normalize_input_items_backfills_reasoning_summary_for_openai_replay() -> None:
    normalized = normalize_input_items(
        [
            {
                "type": "reasoning",
                "encrypted_content": "enc-1",
                "content": None,
            }
        ],
        reference_parity=False,
    )

    assert normalized == [
        {
            "type": "reasoning",
            "encrypted_content": "enc-1",
            "summary": [],
            "content": None,
        }
    ]


def test_response_item_turn_event_keeps_reasoning_metadata() -> None:
    item = ResponseInputItem(
        item_type="reasoning",
        content=[{"type": "reasoning", "text": "先查北京时间"}],
        content_present=True,
        extra={
            "summary": [{"type": "summary_text", "text": "先查北京时间"}],
            "encrypted_content": "enc-1",
            "id": "rs_1",
            "status": "completed",
        },
    )
    turn_event = response_item_turn_event(item, item_id="stream_item_1")

    assert turn_event == {
        "type": "item.completed",
        "item": {
            "id": "stream_item_1",
            "type": "reasoning",
            "text": "先查北京时间",
            "status": "completed",
            "summary": [{"type": "summary_text", "text": "先查北京时间"}],
            "encrypted_content": "enc-1",
            "provider_item_id": "rs_1",
        },
    }


def test_response_item_turn_event_projects_provider_native_web_search_call() -> None:
    item = ResponseInputItem(
        item_type="web_search_call",
        content="",
        extra={
            "id": "ws_1",
            "status": "completed",
            "action": {"type": "search", "query": "北京 今天天气", "queries": ["北京 今天天气"]},
        },
    )

    assert response_item_turn_event(item, item_id="stream_item_1") == {
        "type": "item.completed",
        "item": {
            "id": "ws_1",
            "type": "web_search_call",
            "status": "completed",
            "search_phase": "search_results_received",
            "action": {"type": "search", "query": "北京 今天天气", "queries": ["北京 今天天气"]},
            "query": "北京 今天天气",
        },
    }


def test_openai_responses_session_consume_stream_emits_native_web_search_two_phase_events() -> None:
    query = "北京 今天天气"
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )
    final_response = _response(
        _web_search_call(query),
        _message_item("北京今天多云。", phase="final_answer"),
        response_id="resp_stream_native",
        output_text="北京今天多云。",
    )
    stream = _FakeStream(
        [
            _stream_event(
                "response.output_item.added",
                item={
                    "type": "web_search_call",
                    "id": "ws_1",
                    "action": {"type": "search", "query": query, "queries": [query]},
                },
                output_index=0,
            ),
            _stream_event(
                "response.output_item.done", item=_web_search_call(query), output_index=0
            ),
            _stream_event(
                "response.output_item.added",
                item={"type": "message", "id": "msg_1", "phase": "final_answer"},
                output_index=1,
            ),
            _stream_event("response.output_text.delta", delta="北京今天", output_index=1),
            _stream_event("response.output_text.done", text="北京今天多云。", output_index=1),
            _stream_event(
                "response.output_item.done",
                item=_message_item("北京今天多云。", phase="final_answer"),
                output_index=1,
            ),
            _stream_event("response.completed", response=final_response),
        ],
        final_response=final_response,
    )
    turn_events: list[dict] = []

    result = session._consume_stream(
        stream,
        turn_event_callback=turn_events.append,
        initial_input_items=[
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
        ],
    )

    assert result.trace["provider_native_search_phase"] == "search_results_received"
    assert turn_events[0] == {
        "type": "item.started",
        "item": {
            "id": "ws_1",
            "type": "web_search_call",
            "status": "in_progress",
            "search_phase": "search_dispatched",
            "action": {"type": "search", "query": query, "queries": [query]},
            "query": query,
        },
    }
    assert turn_events[1] == {
        "type": "item.completed",
        "item": {
            "id": "ws_1",
            "type": "web_search_call",
            "status": "completed",
            "search_phase": "search_results_received",
            "action": {"type": "search", "query": query, "queries": [query]},
            "query": query,
        },
    }


def test_openai_responses_session_consume_stream_tracks_native_web_search_ids_by_composite_key() -> (
    None
):
    query_a = "北京 今天天气"
    query_b = "上海 今天天气"
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )
    final_response = _response(
        _web_search_call(query_a),
        _web_search_call(query_b),
        _message_item("已完成。", phase="final_answer"),
        response_id="resp_stream_native_dual",
        output_text="已完成。",
    )
    stream = _FakeStream(
        [
            _stream_event(
                "response.output_item.added",
                item={
                    "type": "web_search_call",
                    "id": "ws_a",
                    "action": {"type": "search", "query": query_a, "queries": [query_a]},
                },
                output_index=0,
            ),
            _stream_event(
                "response.output_item.added",
                item={
                    "type": "web_search_call",
                    "id": "ws_b",
                    "action": {"type": "search", "query": query_b, "queries": [query_b]},
                },
                output_index=0,
            ),
            _stream_event(
                "response.output_item.done", item=_web_search_call(query_a), output_index=0
            ),
            _stream_event(
                "response.output_item.done", item=_web_search_call(query_b), output_index=0
            ),
            _stream_event(
                "response.output_item.added",
                item={"type": "message", "id": "msg_done", "phase": "final_answer"},
                output_index=1,
            ),
            _stream_event("response.output_text.done", text="已完成。", output_index=1),
            _stream_event(
                "response.output_item.done",
                item=_message_item("已完成。", phase="final_answer"),
                output_index=1,
            ),
            _stream_event("response.completed", response=final_response),
        ],
        final_response=final_response,
    )
    turn_events: list[dict] = []

    session._consume_stream(
        stream,
        turn_event_callback=turn_events.append,
        initial_input_items=[
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
        ],
    )

    completed_searches = [
        event["item"]
        for event in turn_events
        if event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "web_search_call"
    ]
    assert completed_searches == [
        {
            "id": "ws_a",
            "type": "web_search_call",
            "status": "completed",
            "search_phase": "search_results_received",
            "action": {"type": "search", "query": query_a, "queries": [query_a]},
            "query": query_a,
        },
        {
            "id": "ws_b",
            "type": "web_search_call",
            "status": "completed",
            "search_phase": "search_results_received",
            "action": {"type": "search", "query": query_b, "queries": [query_b]},
            "query": query_b,
        },
    ]


def test_openai_responses_session_consume_stream_normalizes_message_events() -> None:
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )
    final_response = _response(
        _message_item("hello", phase="final_answer"), response_id="resp_stream"
    )
    stream = _FakeStream(
        [
            _stream_event(
                "response.output_item.added",
                item={"type": "message", "id": "msg_1", "phase": "final_answer"},
                output_index=0,
            ),
            _stream_event("response.output_text.delta", delta="hel", output_index=0),
            _stream_event("response.output_text.done", text="hello", output_index=0),
            _stream_event(
                "response.output_item.done",
                item=_message_item("hello", phase="final_answer"),
                output_index=0,
            ),
            _stream_event("response.completed", response=final_response),
        ],
        final_response=final_response,
    )
    turn_events: list[dict] = []

    result = session._consume_stream(
        stream,
        turn_event_callback=turn_events.append,
        initial_input_items=[
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
        ],
    )

    assert result.output_text == "final text"
    assert result.response_id == "resp_stream"
    assert turn_events == [
        {
            "type": "item.updated",
            "item": {
                "id": "msg_1",
                "type": "agent_message",
                "text": "hel",
                "phase": "final_answer",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "msg_1",
                "type": "agent_message",
                "text": "hello",
                "phase": "final_answer",
            },
        },
    ]


def test_execute_streaming_request_registers_active_stream_interrupter() -> None:
    stream = _ClosableParsedStream()
    api_response = _ManagedStreamingApiResponse(stream)
    client = _ManagedStreamingClient(api_response)
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    def _consume_stream(*args, **kwargs):
        del args, kwargs
        assert session.interrupt_active_stream() is True
        assert stream.close_calls == 1
        assert api_response.close_calls == 1
        return ProviderSessionResult(output_text="stopped")

    result = execute_streaming_request(
        session,
        kwargs={"input": [{"role": "user", "content": "hi"}], "stream": True},
        turn_event_callback=lambda event: None,
        consume_stream=_consume_stream,
    )

    assert result.output_text == "stopped"
    assert session.interrupt_active_stream() is False


def test_openai_responses_session_consume_stream_treats_interrupted_close_as_terminal() -> None:
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        interrupt_requested=lambda: True,
    )

    result = session._consume_stream(
        _InterruptedBrokenStream(),
        turn_event_callback=lambda event: None,
    )

    assert result.output_text == ""
    assert result.tool_calls == []
    assert result.response_items == []
    assert result.trace["streamed"] is True
    assert result.trace["provider_native_interrupted"] is False
    assert result.trace["provider_native_outcome"] == ""
    assert result.trace["provider_native_retryable"] is False


def test_openai_responses_session_consume_stream_marks_interrupted_native_web_search_as_pending_continuation() -> (
    None
):
    query = "北京 今天天气"
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        interrupt_requested=lambda: True,
    )

    turn_events: list[dict] = []
    result = session._consume_stream(
        _InterruptedAfterEventsStream(
            [
                _stream_event(
                    "response.output_item.added",
                    item={
                        "type": "web_search_call",
                        "id": "ws_1",
                        "action": {"type": "search", "query": query, "queries": [query]},
                    },
                    output_index=0,
                ),
                _stream_event(
                    "response.output_item.done", item=_web_search_call(query), output_index=0
                ),
            ]
        ),
        turn_event_callback=turn_events.append,
        initial_input_items=[{"role": "user", "content": "北京今天天气怎么样"}],
    )

    assert result.output_text == ""
    assert result.tool_calls == []
    assert [item.item_type for item in result.response_items] == ["web_search_call"]
    assert result.continuation_input_items == [
        {"role": "user", "content": "北京今天天气怎么样"},
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "completed",
            "action": {"type": "search", "query": query, "queries": [query]},
        },
    ]
    assert result.response_id is None
    assert result.trace["provider_native_item_types"] == ["web_search_call"]
    assert result.trace["provider_native_continuation_pending"] is True
    assert result.trace["provider_native_continuation_reason"] == "native_item_incomplete"
    assert result.trace["provider_native_search_dispatched"] is True
    assert result.trace["provider_native_search_results_received"] is False
    assert result.trace["provider_native_search_phase"] == "search_dispatched"
    assert result.trace["provider_native_interrupted"] is True
    assert result.trace["provider_native_outcome"] == "native_interrupted"
    assert result.trace["provider_native_retryable"] is True
    assert result.trace["response_status"] == "interrupted"
    assert turn_events == [
        {
            "type": "item.started",
            "item": {
                "id": "ws_1",
                "type": "web_search_call",
                "status": "in_progress",
                "search_phase": "search_dispatched",
                "action": {"type": "search", "query": query, "queries": [query]},
                "query": query,
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "ws_1",
                "type": "web_search_call",
                "status": "completed",
                "search_phase": "search_results_received",
                "action": {"type": "search", "query": query, "queries": [query]},
                "query": query,
            },
        },
    ]


def test_openai_responses_session_consume_stream_recovers_added_only_native_web_search_after_interrupt() -> (
    None
):
    query = "北京 今天天气"
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        interrupt_requested=lambda: True,
    )

    turn_events: list[dict] = []
    result = session._consume_stream(
        _InterruptedAfterEventsStream(
            [
                _stream_event(
                    "response.output_item.added",
                    item={
                        "type": "web_search_call",
                        "id": "ws_1",
                        "action": {"type": "search", "query": query, "queries": [query]},
                    },
                    output_index=0,
                ),
            ]
        ),
        turn_event_callback=turn_events.append,
        initial_input_items=[{"role": "user", "content": "北京今天天气怎么样"}],
    )

    assert result.output_text == ""
    assert result.tool_calls == []
    assert [item.item_type for item in result.response_items] == ["web_search_call"]
    assert result.response_items[0].extra == {
        "id": "ws_1",
        "status": "in_progress",
        "action": {"type": "search", "query": query, "queries": [query]},
    }
    assert result.continuation_input_items == [
        {"role": "user", "content": "北京今天天气怎么样"},
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "in_progress",
            "action": {"type": "search", "query": query, "queries": [query]},
        },
    ]
    assert result.response_id is None
    assert result.trace["provider_native_item_types"] == ["web_search_call"]
    assert result.trace["provider_native_continuation_pending"] is True
    assert result.trace["provider_native_continuation_reason"] == "native_item_incomplete"
    assert result.trace["provider_native_search_dispatched"] is True
    assert result.trace["provider_native_search_results_received"] is False
    assert result.trace["provider_native_search_phase"] == "search_dispatched"
    assert result.trace["provider_native_interrupted"] is True
    assert result.trace["provider_native_outcome"] == "native_interrupted"
    assert result.trace["provider_native_retryable"] is True
    assert result.trace["response_status"] == "interrupted"
    assert turn_events == [
        {
            "type": "item.started",
            "item": {
                "id": "ws_1",
                "type": "web_search_call",
                "status": "in_progress",
                "search_phase": "search_dispatched",
                "action": {"type": "search", "query": query, "queries": [query]},
                "query": query,
            },
        }
    ]


def test_openai_responses_session_consume_stream_recovers_partial_mixed_resume_items_after_interrupt() -> (
    None
):
    query = "北京 今天天气"
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        interrupt_requested=lambda: True,
    )

    result = session._consume_stream(
        _InterruptedAfterEventsStream(
            [
                _stream_event(
                    "response.output_item.added",
                    item={
                        "type": "message",
                        "id": "msg_1",
                        "role": "assistant",
                        "phase": "commentary",
                    },
                    output_index=0,
                ),
                _stream_event("response.output_text.delta", delta="我先查一下。", output_index=0),
                _stream_event(
                    "response.output_item.added",
                    item={
                        "type": "web_search_call",
                        "id": "ws_1",
                        "action": {"type": "search", "query": query, "queries": [query]},
                    },
                    output_index=1,
                ),
            ]
        ),
        turn_event_callback=lambda event: None,
        initial_input_items=[{"role": "user", "content": "北京今天天气怎么样？"}],
    )

    assert result.output_text == "我先查一下。"
    assert [item.item_type for item in result.response_items] == ["message", "web_search_call"]
    assert result.continuation_input_items == [
        {"role": "user", "content": "北京今天天气怎么样？"},
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "我先查一下。"}],
        },
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "in_progress",
            "action": {"type": "search", "query": query, "queries": [query]},
        },
    ]
    assert result.trace["provider_native_continuation_pending"] is True
    assert result.trace["provider_native_outcome"] == "native_interrupted"


def test_openai_responses_session_consume_stream_recovers_partial_function_call_after_interrupt() -> (
    None
):
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_search"}],
        interrupt_requested=lambda: True,
    )

    result = session._consume_stream(
        _InterruptedAfterEventsStream(
            [
                _stream_event(
                    "response.output_item.added",
                    item=_function_call_stream_item("call_1", "file_search", item_id="fc_1"),
                    output_index=0,
                ),
                _stream_event(
                    "response.function_call_arguments.delta",
                    item_id="fc_1",
                    output_index=0,
                    delta='{"query":"provider"',
                ),
            ]
        ),
        turn_event_callback=lambda event: None,
        initial_input_items=[{"role": "user", "content": "search provider"}],
    )

    assert result.output_text == ""
    assert result.tool_calls == []
    assert [item.item_type for item in result.response_items] == ["function_call"]
    assert result.response_items[0].extra == {
        "id": "fc_1",
        "call_id": "call_1",
        "name": "file_search",
        "arguments": '{"query":"provider"',
        "status": "in_progress",
    }
    assert result.continuation_input_items == [
        {"role": "user", "content": "search provider"},
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_1",
            "name": "file_search",
            "arguments": '{"query":"provider"',
            "status": "in_progress",
        },
    ]
    assert result.response_id is None
    assert result.trace["answered"] is False


def test_openai_responses_session_consume_stream_recovers_added_only_shell_call_after_interrupt() -> (
    None
):
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        interrupt_requested=lambda: True,
    )

    result = session._consume_stream(
        _InterruptedAfterEventsStream(
            [
                _stream_event(
                    "response.output_item.added",
                    item={
                        "type": "shell_call",
                        "id": "sh_1",
                        "call_id": "call_shell_1",
                        "status": "in_progress",
                        "action": {
                            "type": "exec",
                            "command": ["pwd"],
                            "timeout_ms": 1000,
                        },
                    },
                    output_index=0,
                ),
            ]
        ),
        turn_event_callback=lambda event: None,
        initial_input_items=[{"role": "user", "content": "pwd"}],
    )

    assert result.output_text == ""
    assert result.tool_calls == []
    assert [item.item_type for item in result.response_items] == ["shell_call"]
    assert result.response_items[0].extra == {
        "id": "sh_1",
        "call_id": "call_shell_1",
        "status": "in_progress",
        "action": {
            "type": "exec",
            "command": ["pwd"],
            "timeout_ms": 1000,
        },
    }
    assert result.continuation_input_items == [
        {"role": "user", "content": "pwd"},
        {
            "type": "shell_call",
            "id": "sh_1",
            "call_id": "call_shell_1",
            "status": "in_progress",
            "action": {
                "type": "exec",
                "command": ["pwd"],
                "timeout_ms": 1000,
            },
        },
    ]


def test_openai_responses_session_consume_stream_preserves_completed_items_when_interrupted() -> (
    None
):
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_search"}],
        interrupt_requested=lambda: True,
    )

    result = session._consume_stream(
        _InterruptedAfterEventsStream(
            [
                _stream_event(
                    "response.output_item.done",
                    item=SimpleNamespace(
                        type="message",
                        id="msg_partial",
                        role="assistant",
                        phase="commentary",
                        content=[SimpleNamespace(type="output_text", text="先搜索仓库")],
                    ),
                    output_index=0,
                ),
                _stream_event(
                    "response.output_item.done",
                    item=SimpleNamespace(
                        type="function_call",
                        call_id="call_1",
                        name="file_search",
                        arguments='{"query":"provider","path":"cli"}',
                    ),
                    output_index=1,
                ),
            ]
        ),
        turn_event_callback=lambda event: None,
        initial_input_items=[{"role": "user", "content": "search provider"}],
    )

    assert result.output_text == "先搜索仓库"
    assert [call.name for call in result.tool_calls] == ["file_search"]
    assert [item.item_type for item in result.response_items] == ["message"]
    assert result.continuation_input_items == [
        {"role": "user", "content": "search provider"},
        {
            "type": "message",
            "id": "msg_partial",
            "role": "assistant",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "先搜索仓库"}],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "file_search",
            "arguments": '{"query":"provider","path":"cli"}',
        },
    ]
    assert result.response_id is None
    assert result.trace["streamed"] is True
    assert result.trace["answered"] is False


def test_openai_responses_session_consume_stream_recovers_function_call_when_completed_event_is_missing() -> (
    None
):
    session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_search"}],
    )

    result = session._consume_stream(
        _FakeStream(
            [
                _stream_event(
                    "response.output_item.added",
                    item=_function_call_stream_item("call_1", "file_search", item_id="fc_1"),
                    output_index=0,
                ),
                _stream_event(
                    "response.function_call_arguments.done",
                    item_id="fc_1",
                    output_index=0,
                    name="file_search",
                    arguments='{"query":"provider","path":"cli"}',
                ),
            ],
            final_response=SimpleNamespace(
                id="resp_incomplete",
                status="incomplete",
                output=[],
                output_text="",
            ),
        ),
        turn_event_callback=lambda event: None,
        initial_input_items=[{"role": "user", "content": "search provider"}],
    )

    assert [call.name for call in result.tool_calls] == ["file_search"]
    assert result.tool_calls[0].arguments == {"query": "provider", "path": "cli"}
    assert result.response_items == []
    assert result.continuation_input_items == [
        {"role": "user", "content": "search provider"},
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_1",
            "name": "file_search",
            "arguments": '{"query":"provider","path":"cli"}',
            "status": "in_progress",
        },
    ]
    assert result.response_id == "resp_incomplete"
    assert result.trace["response_status"] == "incomplete"
    assert result.trace["answered"] is False


def test_openai_responses_session_errors_when_stream_closes_before_response_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTHUB_OPENAI_STREAM_MAX_RETRIES", "0")
    client = _FakeStreamClient(
        [
            _stream_event(
                "response.output_item.done",
                item=SimpleNamespace(
                    type="message",
                    id="msg_partial",
                    role="assistant",
                    content=[
                        SimpleNamespace(type="output_text", text="我来查一下北京明天的天气。")
                    ],
                ),
            ),
        ]
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    with pytest.raises(RuntimeError, match=r"stream closed before response\.completed"):
        session.send(
            input_items=[{"role": "user", "content": "北京明天天气怎么样？"}],
            allow_tools=False,
            turn_event_callback=lambda event: None,
        )


def test_openai_responses_stream_retries_disconnect_and_emits_reconnect_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTHUB_OPENAI_STREAM_MAX_RETRIES", "1")
    monkeypatch.setenv("AGENTHUB_PROVIDER_RETRY_BASE_DELAY_SECONDS", "0")
    monkeypatch.setenv("AGENTHUB_PROVIDER_RETRY_MAX_DELAY_SECONDS", "0")
    client = _FlakyClient(
        [
            [
                _stream_event(
                    "response.output_item.done",
                    item=SimpleNamespace(
                        type="message",
                        id="msg_partial",
                        role="assistant",
                        content=[SimpleNamespace(type="output_text", text="partial")],
                    ),
                ),
            ],
            [
                _stream_event(
                    "response.completed",
                    response=_response(response_id="resp_ok", output_text="final text"),
                ),
            ],
        ]
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )
    turn_events: list[dict] = []

    with patch(
        "cli.agent_cli.providers.adapters.openai_responses_runtime.time.sleep", return_value=None
    ):
        result = session.send(
            input_items=[{"role": "user", "content": "北京明天天气怎么样？"}],
            allow_tools=False,
            turn_event_callback=turn_events.append,
        )

    assert result.output_text == "final text"
    assert len(client.responses.requests) == 2
    assert any(
        event.get("type") == "provider.retry"
        and event.get("message") == "Reconnecting... 1/1"
        and event.get("retry_attempt") == 1
        for event in turn_events
    )
    assert result.trace["stream_retry_attempts"] == 1
    assert result.trace["stream_max_retries"] == 1


def test_call_with_responses_503_diagnostics_attaches_context() -> None:
    error = RuntimeError("provider unavailable")
    with (
        patch(
            "cli.agent_cli.providers.adapters.openai_responses_error_runtime.call_with_provider_retries",
            side_effect=error,
        ),
        patch(
            "cli.agent_cli.providers.adapters.openai_responses_error_runtime.attach_responses_503_risks"
        ) as attach_mock,
    ):
        try:
            call_with_responses_503_diagnostics(
                lambda: None,
                payload={"input": [{"role": "user", "content": "hello"}]},
                source="responses.send",
            )
        except RuntimeError as exc:
            assert exc is error
        else:
            raise AssertionError("expected RuntimeError")

    attach_mock.assert_called_once_with(
        error,
        {"input": [{"role": "user", "content": "hello"}]},
        source="responses.send",
    )


def test_openai_responses_session_preserves_provider_native_output_items() -> None:
    query = 'time: {"utc_offset":"+08:00"}'
    client = _FakeClient(
        _response(
            _reasoning_item("先查北京时间"),
            _web_search_call(query),
            _message_item("现在北京时间是 `2026年3月31日 22:27:38`。", phase="final_answer"),
            response_id="resp_native",
        )
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    result = session.send(
        input_items=[{"role": "user", "content": "现在北京时间几点"}],
        allow_tools=False,
    )

    response_item_types = [item.item_type for item in result.response_items]
    assert response_item_types == ["reasoning", "web_search_call", "message"]
    assert result.response_items[0].to_dict() == {
        "type": "reasoning",
        "content": None,
        "encrypted_content": "enc-1",
        "summary": [{"type": "summary_text", "text": "先查北京时间"}],
    }
    assert result.response_items[1].extra["action"]["query"] == query
    assert result.continuation_input_items[-3] == {
        "type": "reasoning",
        "content": None,
        "encrypted_content": "enc-1",
        "summary": [{"type": "summary_text", "text": "先查北京时间"}],
    }
    assert result.continuation_input_items[-2]["type"] == "web_search_call"
    assert result.continuation_input_items[-2]["action"]["query"] == query
    assert result.continuation_input_items[-1]["type"] == "message"
    assert result.trace["provider_native_item_types"] == ["web_search_call"]
    assert result.trace["provider_native_continuation_pending"] is False
    assert result.trace["provider_native_search_dispatched"] is True
    assert result.trace["provider_native_search_results_received"] is True
    assert result.trace["provider_native_search_phase"] == "search_results_received"
    assert result.trace["provider_native_interrupted"] is False
    assert result.trace["provider_native_outcome"] == "search_results_received"
    assert result.trace["provider_native_retryable"] is False
    assert result.trace["provider_native_error_code"] == ""


def test_openai_responses_session_marks_incomplete_native_web_search_for_continuation() -> None:
    query = "北京 今天天气"
    client = _FakeClient(
        _response(
            _web_search_call(query),
            response_id="resp_native_partial",
            status="incomplete",
        )
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    result = session.send(
        input_items=[{"role": "user", "content": "北京今天天气怎么样"}],
        allow_tools=False,
    )

    assert result.trace["provider_native_item_types"] == ["web_search_call"]
    assert result.trace["response_status"] == "incomplete"
    assert result.trace["provider_native_continuation_pending"] is True
    assert result.trace["provider_native_search_dispatched"] is True
    assert result.trace["provider_native_search_results_received"] is False
    assert result.trace["provider_native_search_phase"] == "search_dispatched"
    assert result.trace["provider_native_interrupted"] is True
    assert result.trace["provider_native_outcome"] == "native_interrupted"
    assert result.trace["provider_native_retryable"] is True
    assert result.trace["provider_native_error_code"] == "native_item_incomplete"
    assert result.trace["answered"] is False
    assert result.trace["answer_preview"] == ""


def test_openai_responses_session_does_not_infer_continuation_from_assistant_text() -> None:
    preamble = "我来查一下华盛顿的面积有多大。"
    client = _FakeClient(
        _response(
            _message_item(preamble),
            response_id="resp_native_text_only",
            output_text=preamble,
        )
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "web_search"}],
    )

    result = session.send(
        input_items=[{"role": "user", "content": "查一查华盛顿的面积多大呢？"}],
        allow_tools=True,
    )

    assert result.trace["provider_native_item_types"] == []
    assert result.trace["provider_native_continuation_pending"] is False
    assert result.trace["provider_native_continuation_reason"] == ""
    assert result.trace["provider_native_search_phase"] == ""
    assert result.trace["answered"] is True


def test_openai_responses_session_does_not_mark_preamble_when_native_web_search_not_available() -> (
    None
):
    preamble = "我先查一下北京在 2026年4月14日 的天气预报。"
    client = _FakeClient(
        _response(
            _message_item(preamble),
            response_id="resp_local_preamble",
            output_text=preamble,
        )
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "web_search"}],
    )

    result = session.send(
        input_items=[{"role": "user", "content": "北京明天天气怎么样？"}],
        allow_tools=True,
    )

    assert result.trace["provider_native_continuation_pending"] is False
    assert result.trace["provider_native_continuation_reason"] == ""
    assert result.trace["answered"] is True


def test_openai_responses_session_send_includes_previous_response_id_for_websocket_transport():
    client = _FakeWebsocketClient(_response(response_id="resp_ws"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reasoning_effort="medium",
    )

    session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
        previous_response_id="resp_prev",
    )

    request = client.responses.requests[0]
    assert request["previous_response_id"] == "resp_prev"


def test_openai_responses_session_websocket_transport_keeps_incremental_mixed_item_slice() -> None:
    client = _FakeWebsocketClient(_response(response_id="resp_ws_slice"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reference_parity=True,
        session_id="thread_123",
        turn_id="turn_123",
        sandbox_mode="workspace-write",
    )

    session.send(
        input_items=[
            {
                "type": "response_item",
                "item": {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": {"cwd": "/repo"},
                },
            },
            {"role": "user", "content": "now summarize"},
        ],
        allow_tools=False,
        previous_response_id="resp_prev",
    )

    request = client.responses.requests[0]
    assert request["previous_response_id"] == "resp_prev"
    assert request["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"cwd": "/repo"}',
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "now summarize"}],
        },
    ]


def test_openai_responses_session_websocket_transport_keeps_incremental_native_continuation_slice() -> (
    None
):
    client = _FakeWebsocketClient(_response(response_id="resp_ws_native_slice"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reference_parity=True,
        session_id="thread_123",
        turn_id="turn_123",
        sandbox_mode="workspace-write",
    )

    session.send(
        input_items=[
            {
                "type": "response_item",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "我先查一下"}],
                },
            },
            {
                "type": "response_item",
                "item": {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "query": "北京 今天天气",
                        "queries": ["北京 今天天气"],
                    },
                },
            },
            {"type": "message", "role": "user", "content": "继续"},
        ],
        allow_tools=False,
        previous_response_id="resp_prev",
    )

    request = client.responses.requests[0]
    assert request["previous_response_id"] == "resp_prev"
    assert request["input"] == [
        {
            "type": "message",
            "role": "assistant",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "我先查一下"}],
        },
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "completed",
            "action": {"type": "search", "query": "北京 今天天气", "queries": ["北京 今天天气"]},
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "继续"}],
        },
    ]


def test_openai_responses_session_send_includes_previous_response_id_for_http_transport() -> None:
    client = _FakeHttpClient(_response(response_id="resp_http"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
        previous_response_id="resp_prev",
    )

    request = client.responses.requests[0]
    assert request["previous_response_id"] == "resp_prev"


def test_openai_responses_session_codex_profile_http_transport_replays_native_continuation_items() -> (
    None
):
    client = _FakeHttpClient(_response(response_id="resp_http_native_slice"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reference_parity=True,
        session_id="thread_123",
        turn_id="turn_123",
        sandbox_mode="workspace-write",
    )

    session.send(
        input_items=[
            {
                "type": "response_item",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "我先查一下"}],
                },
            },
            {
                "type": "response_item",
                "item": {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "query": "北京 今天天气",
                        "queries": ["北京 今天天气"],
                    },
                },
            },
            {"type": "message", "role": "user", "content": "继续"},
        ],
        allow_tools=False,
        previous_response_id="resp_prev",
    )

    request = client.responses.requests[0]
    assert "previous_response_id" not in request
    assert request["input"] == [
        {
            "type": "message",
            "role": "assistant",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "我先查一下"}],
        },
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "completed",
            "action": {"type": "search", "query": "北京 今天天气", "queries": ["北京 今天天气"]},
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "继续"}],
        },
    ]


def test_openai_responses_session_send_includes_previous_response_id_for_default_http_client() -> (
    None
):
    client = _FakeClient(_response(response_id="resp_http_default"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
        previous_response_id="resp_prev",
    )

    request = client.responses.requests[0]
    assert request["previous_response_id"] == "resp_prev"


def test_openai_responses_session_codex_profile_http_transport_omits_previous_response_id_with_full_input_array() -> (
    None
):
    client = _FakeHttpClient(_response(response_id="resp_http_codex"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reference_parity=True,
        session_id="thread_123",
        turn_id="turn_123",
        sandbox_mode="workspace-write",
    )

    session.send(
        input_items=[
            {"type": "message", "role": "user", "content": "list files"},
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "exec_command",
                "arguments": '{"cmd":"pwd"}',
            },
            {"type": "function_call_output", "call_id": "call_1", "output": "/repo"},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Current dir captured."}],
            },
            {"type": "message", "role": "user", "content": "now summarize"},
        ],
        allow_tools=False,
        previous_response_id="resp_prev",
    )

    request = client.responses.requests[0]
    assert "previous_response_id" not in request
    assert request["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "list files"}],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "exec_command",
            "arguments": '{"cmd":"pwd"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "/repo",
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Current dir captured."}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "now summarize"}],
        },
    ]


def test_openai_responses_session_codex_profile_http_transport_omits_previous_response_id_with_mixed_followup_items() -> (
    None
):
    client = _FakeHttpClient(_response(response_id="resp_http_codex_mixed"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reference_parity=True,
        session_id="thread_123",
        turn_id="turn_123",
        sandbox_mode="workspace-write",
    )

    session.send(
        input_items=[
            {"role": "user", "content": "list files"},
            {
                "type": "response_item",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "Checking current directory."}],
                },
            },
            {
                "type": "response_item",
                "item": {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "exec_command",
                    "arguments": '{"cmd":"pwd"}',
                    "content": [],
                },
            },
            {
                "type": "response_item",
                "item": {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": {"cwd": "/repo"},
                },
            },
            {"type": "message", "role": "user", "content": "now summarize"},
        ],
        allow_tools=False,
        previous_response_id="resp_prev",
    )

    request = client.responses.requests[0]
    assert "previous_response_id" not in request
    assert request["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "list files"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "Checking current directory."}],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "exec_command",
            "arguments": '{"cmd":"pwd"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"cwd": "/repo"}',
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "now summarize"}],
        },
    ]


def test_openai_responses_session_mixed_resume_snapshot_aligns_http_and_websocket_resume() -> None:
    query = "北京 今天天气"
    recovery_session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        interrupt_requested=lambda: True,
    )
    recovered = recovery_session._consume_stream(
        _InterruptedAfterEventsStream(
            [
                _stream_event(
                    "response.output_item.added",
                    item={
                        "type": "message",
                        "id": "msg_1",
                        "role": "assistant",
                        "phase": "commentary",
                    },
                    output_index=0,
                ),
                _stream_event("response.output_text.delta", delta="我先查一下。", output_index=0),
                _stream_event(
                    "response.output_item.added",
                    item={
                        "type": "web_search_call",
                        "id": "ws_1",
                        "action": {"type": "search", "query": query, "queries": [query]},
                    },
                    output_index=1,
                ),
            ]
        ),
        turn_event_callback=lambda event: None,
        initial_input_items=[{"role": "user", "content": "北京今天天气怎么样？"}],
    )

    websocket_client = _FakeWebsocketClient(_response(response_id="resp_ws_resume"))
    websocket_session = OpenAIResponsesSession(
        client=websocket_client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )
    websocket_session.send(
        input_items=list(recovered.continuation_input_items),
        allow_tools=False,
        previous_response_id="resp_partial",
    )

    http_client = _FakeHttpClient(_response(response_id="resp_http_resume"))
    http_session = OpenAIResponsesSession(
        client=http_client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )
    http_session.send(
        input_items=list(recovered.continuation_input_items),
        allow_tools=False,
        previous_response_id="resp_partial",
    )

    websocket_snapshot = _resume_request_snapshot(websocket_client.responses.requests[0])
    http_snapshot = _resume_request_snapshot(http_client.responses.requests[0])

    assert (
        websocket_snapshot["resume_items"]
        == http_snapshot["resume_items"]
        == [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "北京今天天气怎么样？"}],
            },
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "phase": "commentary",
                "content": [{"type": "output_text", "text": "我先查一下。"}],
            },
            {
                "type": "web_search_call",
                "id": "ws_1",
                "status": "in_progress",
                "action": {"type": "search", "query": query, "queries": [query]},
            },
        ]
    )
    assert websocket_snapshot["resume_strategy"] == "previous_response_id"
    assert websocket_snapshot["resume_cursor"] == "resp_partial"
    assert http_snapshot["resume_strategy"] == "previous_response_id"
    assert http_snapshot["resume_cursor"] == "resp_partial"


def test_openai_responses_session_partial_function_call_resume_snapshot_aligns_http_and_websocket() -> (
    None
):
    recovery_session = OpenAIResponsesSession(
        client=_FakeStreamClient([]),
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_search"}],
        interrupt_requested=lambda: True,
    )
    recovered = recovery_session._consume_stream(
        _InterruptedAfterEventsStream(
            [
                _stream_event(
                    "response.output_item.added",
                    item={
                        "type": "message",
                        "id": "msg_1",
                        "role": "assistant",
                        "phase": "commentary",
                    },
                    output_index=0,
                ),
                _stream_event("response.output_text.delta", delta="我先搜索仓库。", output_index=0),
                _stream_event(
                    "response.output_item.added",
                    item=_function_call_stream_item("call_1", "file_search", item_id="fc_1"),
                    output_index=1,
                ),
                _stream_event(
                    "response.function_call_arguments.delta",
                    item_id="fc_1",
                    output_index=1,
                    delta='{"query":"provider"',
                ),
            ]
        ),
        turn_event_callback=lambda event: None,
        initial_input_items=[{"role": "user", "content": "search provider"}],
    )

    websocket_client = _FakeWebsocketClient(_response(response_id="resp_ws_partial_tool"))
    websocket_session = OpenAIResponsesSession(
        client=websocket_client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_search"}],
    )
    websocket_session.send(
        input_items=list(recovered.continuation_input_items),
        allow_tools=True,
        previous_response_id="resp_partial_tool",
    )

    http_client = _FakeHttpClient(_response(response_id="resp_http_partial_tool"))
    http_session = OpenAIResponsesSession(
        client=http_client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_search"}],
    )
    http_session.send(
        input_items=list(recovered.continuation_input_items),
        allow_tools=True,
        previous_response_id="resp_partial_tool",
    )

    websocket_snapshot = _resume_request_snapshot(websocket_client.responses.requests[0])
    http_snapshot = _resume_request_snapshot(http_client.responses.requests[0])

    assert (
        websocket_snapshot["resume_items"]
        == http_snapshot["resume_items"]
        == [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "search provider"}],
            },
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "phase": "commentary",
                "content": [{"type": "output_text", "text": "我先搜索仓库。"}],
            },
            {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "file_search",
                "arguments": '{"query":"provider"',
                "status": "in_progress",
            },
        ]
    )
    assert websocket_snapshot["resume_strategy"] == "previous_response_id"
    assert websocket_snapshot["resume_cursor"] == "resp_partial_tool"
    assert http_snapshot["resume_strategy"] == "previous_response_id"
    assert http_snapshot["resume_cursor"] == "resp_partial_tool"


def test_openai_responses_session_send_without_tools_omits_tool_fields():
    client = _FakeClient(_response(response_id="resp_2"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_list"}],
    )

    result = session.send(
        input_items=[{"type": "function_call_output", "call_id": "call_1", "output": "{}"}],
        allow_tools=False,
    )

    assert result.output_text == "final text"
    assert result.response_id == "resp_2"
    assert result.tool_calls == []
    assert result.trace["tool_calls"] == []
    assert result.trace["tool_call_count"] == 0
    assert result.trace["answered"] is True
    assert result.trace["answer_preview"] == "final text"

    request = client.responses.requests[0]
    assert "tools" not in request
    assert "tool_choice" not in request
    assert "parallel_tool_calls" not in request
    assert "reasoning" not in request
    assert "previous_response_id" not in request


def test_openai_responses_session_normalizes_structured_message_items():
    client = _FakeClient(_response(response_id="resp_3"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "你好"}],
            },
            {"type": "function_call_output", "call_id": "call_1", "output": "{}"},
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"][0] == {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": "你好"}],
    }
    assert request["input"][1] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "{}",
    }


def test_openai_responses_session_strips_content_from_replayed_function_calls() -> None:
    client = _FakeClient(_response(response_id="resp_replay_tool"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tooluse_1",
                "arguments": '{"cmd":"pwd"}',
                "content": [],
            },
            {
                "type": "function_call_output",
                "call_id": "tooluse_1",
                "output": "/repo",
            },
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"] == [
        {
            "type": "function_call",
            "name": "exec_command",
            "call_id": "tooluse_1",
            "arguments": '{"cmd":"pwd"}',
        },
        {
            "type": "function_call_output",
            "call_id": "tooluse_1",
            "output": "/repo",
        },
    ]


def test_openai_responses_session_normalizes_response_item_wrappers():
    client = _FakeClient(_response(response_id="resp_3b"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "response_item",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "structured assistant"}],
                },
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"] == [
        {
            "type": "message",
            "role": "assistant",
            "phase": "final_answer",
            "content": [{"type": "output_text", "text": "structured assistant"}],
        }
    ]


def test_openai_responses_session_normalizes_legacy_role_content_items_to_typed_messages() -> None:
    client = _FakeClient(_response(response_id="resp_legacy"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {"role": "developer", "content": "System message"},
            {"role": "assistant", "content": "Previous answer"},
            {"role": "user", "content": "Next question"},
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"] == [
        {
            "type": "message",
            "role": "developer",
            "content": [{"type": "input_text", "text": "System message"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Previous answer"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Next question"}],
        },
    ]


def test_openai_responses_session_replays_turn_state_header_on_followup() -> None:
    client = _FakeRawClient(
        _response(response_id="resp_1"),
        headers={"x-reference-turn-state": "ts-1"},
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reasoning_effort="medium",
        prompt_cache_key="thread_123",
    )

    session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
    )
    session.send(
        input_items=[{"type": "function_call_output", "call_id": "call_1", "output": "ok"}],
        allow_tools=False,
        previous_response_id="resp_1",
    )

    assert client.responses.with_raw_response.requests[0]["extra_headers"] == {
        "session_id": "thread_123"
    }
    assert client.responses.with_raw_response.requests[1]["previous_response_id"] == "resp_1"
    assert client.responses.with_raw_response.requests[1]["extra_headers"] == {
        "session_id": "thread_123",
        "x-reference-turn-state": "ts-1",
    }


def test_openai_responses_session_codex_profile_replays_codex_turn_state_header_on_followup() -> (
    None
):
    client = _FakeRawClient(
        _response(response_id="resp_1"),
        headers={"x-codex-turn-state": "ts-codex-1"},
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reasoning_effort="medium",
        prompt_cache_key="thread_123",
        reference_parity=True,
        session_id="thread_123",
        turn_id="turn_123",
        sandbox_mode="workspace-write",
    )

    session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
    )
    session.send(
        input_items=[{"type": "function_call_output", "call_id": "call_1", "output": "ok"}],
        allow_tools=False,
        previous_response_id="resp_1",
    )

    expected_turn_metadata = json.dumps(
        {"turn_id": "turn_123", "sandbox": "seccomp"},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    assert client.responses.with_raw_response.requests[0]["extra_headers"] == {
        "session_id": "thread_123",
        "x-codex-turn-metadata": expected_turn_metadata,
    }
    assert "previous_response_id" not in client.responses.with_raw_response.requests[1]
    assert client.responses.with_raw_response.requests[1]["extra_headers"] == {
        "session_id": "thread_123",
        "x-codex-turn-state": "ts-codex-1",
        "x-codex-turn-metadata": expected_turn_metadata,
    }


def test_openai_responses_session_retries_transient_provider_errors():
    transient_error = RuntimeError(
        "InternalServerError: Error code: 503 - {'error': {'type': 'proxy_unavailable', 'message': 'All accounts are currently unavailable.'}}"
    )
    client = _FlakyClient([transient_error, _response(response_id="resp_retry")])
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    with patch("cli.agent_cli.providers.openai_client.time.sleep", return_value=None):
        result = session.send(
            input_items=[{"role": "user", "content": "hello"}],
            allow_tools=False,
        )

    assert result.response_id == "resp_retry"
    assert len(client.responses.requests) == 2


def test_openai_responses_session_does_not_retry_authentication_failures():
    auth_error = RuntimeError(
        "AuthenticationError: Error code: 401 - {'error': {'type': 'authentication_failed', 'message': 'Unauthorized'}}"
    )
    client = _FlakyClient([auth_error])
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    with patch("cli.agent_cli.providers.openai_client.time.sleep", return_value=None):
        try:
            session.send(
                input_items=[{"role": "user", "content": "hello"}],
                allow_tools=False,
            )
        except RuntimeError as exc:
            assert "authentication_failed" in str(exc)
        else:
            raise AssertionError("expected authentication error to propagate")

    assert len(client.responses.requests) == 1


def test_openai_responses_session_normalizes_tool_role_items_to_function_outputs():
    client = _FakeClient(_response(response_id="resp_4"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {"role": "tool", "tool_call_id": "call_1", "content": {"ok": True}},
            {"type": "function_call_output", "call_id": "call_2", "output": {"result": "ok"}},
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"][0] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"ok": true}',
    }
    assert request["input"][1] == {
        "type": "function_call_output",
        "call_id": "call_2",
        "output": '{"result": "ok"}',
    }


def test_openai_responses_session_projects_workspace_reference_context_item_to_message() -> None:
    client = _FakeClient(_response(response_id="resp_ctx"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "reference_context_item",
                "item": {
                    "item_type": "workspace_context",
                    "label": "workspace_context_update",
                    "path": "/repo",
                    "metadata": {
                        "trust_level": "trusted",
                        "instructions_digest": "digest-v2",
                        "digest_before": "digest-v1",
                        "instructions_excerpt": "workspace updated",
                        "diff": {"docs_updated": ["AENGTHUB.md"]},
                    },
                },
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "REFERENCE_CONTEXT_UPDATE:\ncwd=/repo\ntrust=trusted\ndigest_before=digest-v1\ndigest_after=digest-v2\nrule_count=0\ndocs_updated=AENGTHUB.md\n\nUPDATED_INSTRUCTIONS_EXCERPT:\nworkspace updated",
                }
            ],
        }
    ]


def test_openai_responses_session_reference_parity_merges_workspace_and_environment_prelude() -> (
    None
):
    client = _FakeClient(_response(response_id="resp_reference_ctx"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reference_parity=True,
    )

    session.send(
        input_items=[
            {
                "type": "reference_context_item",
                "item": {
                    "item_type": "workspace_context",
                    "label": "workspace_context_baseline",
                    "path": "/repo",
                    "metadata": {
                        "trust_level": "trusted",
                        "instructions_digest": "digest-v1",
                        "instructions_excerpt": "Use pytest for Python changes.",
                        "is_initial": True,
                    },
                },
            },
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "<environment_context>\n  <cwd>/repo</cwd>\n  <shell>bash</shell>\n  <current_date>2026-03-31</current_date>\n  <timezone>Asia/Shanghai</timezone>\n</environment_context>",
                    }
                ],
            },
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "# AGENTS.md instructions for /repo\n\n<INSTRUCTIONS>\nUse pytest for Python changes.\n</INSTRUCTIONS>",
                },
                {
                    "type": "input_text",
                    "text": "<environment_context>\n  <cwd>/repo</cwd>\n  <shell>bash</shell>\n  <current_date>2026-03-31</current_date>\n  <timezone>Asia/Shanghai</timezone>\n</environment_context>",
                },
            ],
        }
    ]


def test_workspace_context_message_text_reference_parity_aliases_aengthub_header() -> None:
    payload = {
        "path": "/repo",
        "metadata": {
            "instructions_excerpt": "# AENGTHUB.md instructions for /repo\n\n<INSTRUCTIONS>\nUse pytest for Python changes.\n</INSTRUCTIONS>"
        },
    }

    assert workspace_context_message_text(payload, reference_parity=True) == (
        "# AGENTS.md instructions for /repo\n\n<INSTRUCTIONS>\nUse pytest for Python changes.\n</INSTRUCTIONS>"
    )


def test_workspace_context_message_text_reference_parity_strips_agenthub_workspace_sections() -> (
    None
):
    payload = {
        "path": "/repo",
        "metadata": {
            "instructions_excerpt": (
                "## Active Workspace\n"
                "- Current working directory for local file tools: `/repo`\n"
                "\n"
                "## Workspace Defaults\n"
                "- If the current working directory is empty and the user asks you to create or scaffold a project or app, treat the current directory as the project root.\n"
                "\n"
                "## Skills\n"
                "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file.\n"
                "- demo-skill: Example skill entry.\n"
            )
        },
    }

    assert workspace_context_message_text(payload, reference_parity=True) == ""


def test_workspace_context_message_text_reference_parity_strips_skills_but_keeps_repo_docs() -> (
    None
):
    payload = {
        "path": "/repo",
        "metadata": {
            "instructions_excerpt": (
                "Use pytest for Python changes.\n"
                "\n"
                "## Skills\n"
                "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file.\n"
                "- demo-skill: Example skill entry.\n"
            )
        },
    }

    assert workspace_context_message_text(payload, reference_parity=True) == (
        "# AGENTS.md instructions for /repo\n\n<INSTRUCTIONS>\nUse pytest for Python changes.\n</INSTRUCTIONS>"
    )


def test_reference_environment_context_text_strips_subagents_and_normalizes_shell_name() -> None:
    text = (
        "<environment_context>\n"
        "  <cwd>/repo</cwd>\n"
        "  <shell>/bin/bash</shell>\n"
        "  <current_date>2026-04-20</current_date>\n"
        "  <timezone>CST</timezone>\n"
        "  <subagents>\n"
        "    subagent: openai | gpt-5.4 | reasoning=xhigh | source=inherit_main\n"
        "  </subagents>\n"
        '  <network enabled="true">\n'
        "    <allowed_domains>relay03.gaccode.com</allowed_domains>\n"
        "  </network>\n"
        "</environment_context>"
    )

    assert reference_environment_context_text(text) == (
        "<environment_context>\n"
        "  <cwd>/repo</cwd>\n"
        "  <shell>bash</shell>\n"
        "  <current_date>2026-04-20</current_date>\n"
        "  <timezone>CST</timezone>\n"
        "</environment_context>"
    )


def test_openai_responses_session_preserves_content_item_outputs() -> None:
    client = _FakeClient(_response(response_id="resp_4b"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": [
                    {"type": "input_text", "text": "line 1"},
                    {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
                ],
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"][0] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": [
            {"type": "input_text", "text": "line 1"},
            {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
        ],
    }


def test_openai_responses_session_projects_image_artifacts_to_input_image_outputs() -> None:
    client = _FakeClient(_response(response_id="resp_4c"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": json.dumps(
                    {
                        "ok": True,
                        "requested_path": "diagram.png",
                        "path": "/tmp/diagram.png",
                        "detail": "Image ready for continuation.",
                        "image_artifacts": [
                            {
                                "path": "/tmp/diagram.png",
                                "mime_type": "image/png",
                                "size_bytes": 42,
                                "width": 10,
                                "height": 12,
                                "image_url": "data:image/png;base64,AAA",
                                "detail": "high",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"][0] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": [
            {"type": "input_image", "image_url": "data:image/png;base64,AAA", "detail": "high"},
        ],
    }


def test_openai_responses_session_projects_image_blocks_to_input_image_outputs() -> None:
    client = _FakeClient(_response(response_id="resp_4c_blocks"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": [
                    {"type": "input_text", "text": "image prepared"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "AAA",
                        },
                    },
                ],
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"][0]["output"] == [
        {"type": "input_text", "text": "image prepared"},
        {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
    ]


def test_openai_responses_session_preserves_original_detail_on_image_block_outputs() -> None:
    client = _FakeClient(_response(response_id="resp_4c_blocks_original"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": [
                    {
                        "type": "image",
                        "detail": "original",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "AAA",
                        },
                    },
                ],
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"][0]["output"] == [
        {"type": "input_image", "image_url": "data:image/png;base64,AAA", "detail": "original"},
    ]


def test_openai_responses_session_projects_nested_tool_result_image_blocks() -> None:
    client = _FakeClient(_response(response_id="resp_4c_nested_blocks"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": {
                    "type": "tool_result",
                    "content": [
                        {"type": "text", "text": "image prepared"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "mime_type": "image/jpeg",
                                "data": "BBB",
                            },
                        },
                    ],
                },
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"][0]["output"] == [
        {"type": "input_text", "text": "image prepared"},
        {"type": "input_image", "image_url": "data:image/jpeg;base64,BBB"},
    ]


def test_openai_responses_session_normalizes_message_image_blocks_to_input_image() -> None:
    client = _FakeClient(_response(response_id="resp_4c_message_blocks"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Please inspect this image."},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "CCC",
                        },
                    },
                ],
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"][0] == {
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": "Please inspect this image."},
            {"type": "input_image", "image_url": "data:image/png;base64,CCC"},
        ],
    }


def test_openai_responses_session_does_not_project_failed_media_ingest_payload() -> None:
    client = _FakeClient(_response(response_id="resp_4d"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": {
                    "ok": False,
                    "error_code": "file_not_found",
                    "display_message": "Image file does not exist: /tmp/missing.png",
                    "requested_path": "missing.png",
                    "path": "/tmp/missing.png",
                },
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert isinstance(request["input"][0]["output"], str)
    assert json.loads(request["input"][0]["output"]) == {
        "ok": False,
        "error_code": "file_not_found",
        "display_message": "Image file does not exist: /tmp/missing.png",
        "requested_path": "missing.png",
        "path": "/tmp/missing.png",
    }


def test_openai_responses_session_projects_view_document_text_slice_to_input_text() -> None:
    client = _FakeClient(_response(response_id="resp_view_document_1"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "function_call_output",
                "call_id": "call_view_document_1",
                "output": json.dumps(
                    {
                        "ok": True,
                        "requested_path": "notes.md",
                        "path": "/tmp/notes.md",
                        "source_mode": "tool_path",
                        "capability_baseline": "extraction_only",
                        "document_class": "text_like",
                        "extraction_state": "text_slice_ready",
                        "mode": "text_slice",
                        "media_mode": "text_slice",
                        "mime_type": "text/markdown",
                        "supported_modes": ["text_slice", "structured_content"],
                        "text_slice": {
                            "text": "beta",
                            "encoding": "utf-8",
                            "offset": 6,
                            "max_chars": 4,
                            "returned_chars": 4,
                            "total_chars": 16,
                            "truncated": True,
                            "line_count": 1,
                        },
                        "structured_content": None,
                        "error_code": "",
                        "display_message": "",
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"][0] == {
        "type": "function_call_output",
        "call_id": "call_view_document_1",
        "output": [
            {"type": "input_text", "text": "beta"},
        ],
    }


def test_openai_responses_session_does_not_project_failed_view_document_payload() -> None:
    client = _FakeClient(_response(response_id="resp_view_document_2"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "function_call_output",
                "call_id": "call_view_document_2",
                "output": {
                    "ok": False,
                    "requested_path": "missing.md",
                    "path": "/tmp/missing.md",
                    "source_mode": "tool_path",
                    "capability_baseline": "extraction_only",
                    "document_class": "unknown",
                    "extraction_state": "extraction_failed",
                    "mode": "text_slice",
                    "media_mode": "unsupported_media",
                    "mime_type": "text/markdown",
                    "supported_modes": ["text_slice", "structured_content"],
                    "text_slice": None,
                    "structured_content": None,
                    "error_code": "unreadable_document",
                    "display_message": "Document file is not readable.",
                },
            }
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert isinstance(request["input"][0]["output"], str)
    assert json.loads(request["input"][0]["output"])["error_code"] == "unreadable_document"
    assert json.loads(request["input"][0]["output"])["capability_baseline"] == "extraction_only"


def test_openai_responses_session_build_tool_result_items_project_view_document_structured_output() -> (
    None
):
    client = _FakeClient(_response(response_id="resp_view_document_3"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    items = session.build_tool_result_items(
        call_id="call_view_document_3",
        command_text="/view_document data.json",
        assistant_text="ignored summary",
        events=[
            ToolEvent(
                name="view_document",
                ok=True,
                summary="document structured content ready: data.json",
                payload={
                    "provider_call_id": "call_view_document_3",
                    "ok": True,
                    "requested_path": "data.json",
                    "path": "/tmp/data.json",
                    "source_mode": "tool_path",
                    "capability_baseline": "extraction_only",
                    "document_class": "structured_json",
                    "extraction_state": "structured_content_ready",
                    "mode": "auto",
                    "media_mode": "structured_content",
                    "mime_type": "application/json",
                    "supported_modes": ["text_slice", "structured_content"],
                    "text_slice": None,
                    "structured_content": {
                        "format": "json",
                        "encoding": "utf-8",
                        "char_count": 25,
                        "top_level_type": "dict",
                        "data": {"name": "demo", "count": 2},
                    },
                    "error_code": "",
                    "display_message": "",
                },
            )
        ],
    )

    assert items == [
        {
            "type": "function_call_output",
            "call_id": "call_view_document_3",
            "output": [
                {"type": "input_text", "text": '{"name": "demo", "count": 2}'},
            ],
            "document_projection_mode": "tool_result_content_block",
            "document_projection_state": "document_projected_structured",
            "document_projection_subject": "/tmp/data.json",
            "success": True,
        }
    ]


def test_openai_responses_session_extracts_answer_from_message_items_when_output_text_empty():
    response = SimpleNamespace(
        id="resp_5",
        output=[_message_item("最终分析：还剩 3 个差距。")],
        output_text="",
    )
    client = _FakeClient(response)
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    result = session.send(
        input_items=[{"type": "function_call_output", "call_id": "call_1", "output": "{}"}],
        allow_tools=False,
    )

    assert result.output_text == "最终分析：还剩 3 个差距。"
    assert result.trace["answered"] is True
    assert result.trace["answer_preview"] == "最终分析：还剩 3 个差距。"
    assert len(result.response_items) == 1
    assert result.response_items[0].role == "assistant"
    assert result.response_items[0].content == [
        {"type": "output_text", "text": "最终分析：还剩 3 个差距。"}
    ]


def test_openai_responses_session_preserves_native_message_phase_in_response_items():
    response = SimpleNamespace(
        id="resp_5b",
        output=[_message_item("最终答案", phase="final_answer")],
        output_text="",
    )
    client = _FakeClient(response)
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    result = session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
    )

    assert len(result.response_items) == 1
    assert result.response_items[0].to_dict() == {
        "type": "message",
        "phase": "final_answer",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "最终答案"}],
    }


def test_openai_responses_session_build_tool_result_items_returns_native_output_body() -> None:
    client = _FakeClient(_response(response_id="resp_6"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    items = session.build_tool_result_items(
        call_id="call_1",
        command_text="/file_read README.md",
        assistant_text="read ok",
        events=[],
    )

    assert items == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "read ok",
            "success": True,
        }
    ]


def test_openai_responses_session_build_tool_result_items_prefers_textual_event_output() -> None:
    client = _FakeClient(_response(response_id="resp_7"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    items = session.build_tool_result_items(
        call_id="call_2",
        command_text="/web_fetch https://example.com",
        assistant_text="ignored summary",
        events=[
            SimpleNamespace(
                name="web_fetch",
                ok=True,
                summary="web page loaded",
                payload={"url": "https://example.com", "title": "Example"},
            )
        ],
    )

    assert items == [
        {
            "type": "function_call_output",
            "call_id": "call_2",
            "output": "web page loaded",
            "success": True,
        }
    ]


def test_openai_responses_session_extracts_shell_call_as_provider_tool_call() -> None:
    response = SimpleNamespace(
        id="resp_shell_1",
        output=[
            SimpleNamespace(
                type="shell_call",
                call_id="call_shell_1",
                action={
                    "type": "exec",
                    "command": ["pwd"],
                    "timeout_ms": 1000,
                    "max_output_length": 12000,
                },
                status="completed",
            )
        ],
        output_text="",
    )
    client = _FakeClient(response)
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    result = session.send(
        input_items=[{"role": "user", "content": "where am i"}],
        allow_tools=True,
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].call_id == "call_shell_1"
    assert result.tool_calls[0].name == "shell"
    assert result.tool_calls[0].item_type == "shell_call"
    assert result.tool_calls[0].arguments["command"] == "pwd"
    assert result.continuation_input_items[-1] == {
        "type": "shell_call",
        "call_id": "call_shell_1",
        "action": {
            "type": "exec",
            "command": ["pwd"],
            "timeout_ms": 1000,
            "max_output_length": 12000,
        },
        "status": "completed",
    }


def test_openai_responses_session_build_tool_result_items_emits_shell_call_output_for_native_shell_calls() -> (
    None
):
    client = _FakeClient(_response(response_id="resp_shell_2"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    items = session.build_tool_result_items(
        call_id="call_shell_2",
        command_text="/shell pwd",
        assistant_text="ignored",
        events=[
            ToolEvent(
                name="shell",
                ok=True,
                summary="shell rc=0",
                payload={
                    "provider_tool_type": "shell_call",
                    "provider_raw_item": {
                        "type": "shell_call",
                        "call_id": "call_shell_2",
                        "action": {
                            "type": "exec",
                            "command": ["pwd"],
                            "timeout_ms": 1000,
                            "max_output_length": 12000,
                        },
                    },
                    "stdout": "/repo\n",
                    "stderr": "",
                    "exit_code": 0,
                    "status": "completed",
                },
            )
        ],
    )

    assert items == [
        {
            "type": "shell_call_output",
            "call_id": "call_shell_2",
            "output": [
                {
                    "stdout": "/repo\n",
                    "stderr": "",
                    "outcome": {"type": "exit", "exit_code": 0},
                }
            ],
            "max_output_length": 12000,
            "status": "completed",
        }
    ]


def test_openai_responses_session_reference_parity_build_tool_result_items_uses_codex_like_shell_projection() -> (
    None
):
    client = _FakeClient(_response(response_id="resp_shell_codex_1"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reference_parity=True,
    )

    items = session.build_tool_result_items(
        call_id="call_exec_1",
        command_text="/exec_command 'sleep 30'",
        assistant_text="ignored",
        events=[
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command running",
                payload={
                    "stdout": "tick 1\n",
                    "session_id": "255",
                    "task_id": "255",
                    "status": "written",
                    "duration_ms": 700,
                    "function_call_output": (
                        "Process running with session ID 255\n"
                        "Background task ID 255\n"
                        "Use write_stdin 255 to poll for completion or send input\n"
                        "Output:\n"
                        "tick 1\n"
                    ),
                },
            )
        ],
    )

    assert items == [
        {
            "type": "function_call_output",
            "call_id": "call_exec_1",
            "output": (
                "Wall time: 0.7000 seconds\n"
                "Process running with session ID 255\n"
                "Output:\n"
                "tick 1"
            ),
            "success": True,
        }
    ]
    serialized = json.dumps(items[0], ensure_ascii=False)
    assert "/exec_command" not in serialized
    assert "/write_stdin" not in serialized
    assert "task_id" not in serialized


def test_openai_responses_session_reference_parity_build_tool_result_items_injects_apply_patch_warning() -> (
    None
):
    client = _FakeClient(_response(response_id="resp_shell_codex_patch_1"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
        reference_parity=True,
    )

    items = session.build_tool_result_items(
        call_id="call_exec_patch_1",
        command_text=(
            "/exec_command \"apply_patch <<'PATCH'\n"
            "*** Begin Patch\n"
            "*** Add File: main.py\n"
            '+print(\\"hello world\\")\n'
            "*** End Patch\n"
            'PATCH"'
        ),
        assistant_text="ignored",
        events=[
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command exited",
                payload={
                    "status": "completed",
                    "exit_code": 0,
                    "command": (
                        "apply_patch <<'PATCH'\n"
                        "*** Begin Patch\n"
                        "*** Add File: main.py\n"
                        '+print("hello world")\n'
                        "*** End Patch\n"
                        "PATCH"
                    ),
                    "function_call_output": "Success. Updated the following files:\nA main.py\n",
                },
            )
        ],
    )

    assert items == [
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Warning: apply_patch was requested via exec_command. Use the apply_patch tool instead of exec_command.",
                }
            ],
        },
        {
            "type": "function_call_output",
            "call_id": "call_exec_patch_1",
            "output": "Exit code: 0\nWall time: 0 seconds\nOutput:\nSuccess. Updated the following files:\nA main.py",
            "success": True,
        },
    ]


def test_openai_responses_session_streams_reference_like_message_and_function_call_events() -> None:
    # Modeled after Reference Responses SSE handling/tests:
    # - reference_baseline/reference-rs/reference-api/src/sse/responses.rs
    # - reference_baseline/reference-rs/exec/tests/event_processor_with_json_output.rs
    client = _FakeStreamClient(
        [
            _stream_event("response.reasoning_summary_text.delta", summary_index=0, delta="先"),
            _stream_event("response.reasoning_summary_text.delta", summary_index=0, delta="搜索"),
            _stream_event(
                "response.output_item.done",
                item=SimpleNamespace(
                    type="message",
                    id="msg_1",
                    role="assistant",
                    phase="commentary",
                    content=[SimpleNamespace(type="output_text", text="先搜索仓库")],
                ),
            ),
            _stream_event(
                "response.output_item.done",
                item=SimpleNamespace(
                    type="function_call",
                    call_id="call_1",
                    name="file_search",
                    arguments='{"query":"provider","path":"cli"}',
                ),
            ),
            _stream_event("response.completed", response=SimpleNamespace(id="resp_stream")),
        ]
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "file_search"}],
    )

    emitted: list[dict] = []
    result = session.send(
        input_items=[{"role": "user", "content": "search provider"}],
        allow_tools=True,
        turn_event_callback=emitted.append,
    )

    request = client.responses.requests[0]
    assert request["stream"] is True
    assert result.response_id == "resp_stream"
    assert [call.name for call in result.tool_calls] == ["file_search"]
    assert emitted == [
        {
            "type": "item.updated",
            "item": {"id": "stream_item_0", "type": "reasoning", "text": "先"},
        },
        {
            "type": "item.updated",
            "item": {"id": "stream_item_0", "type": "reasoning", "text": "先搜索"},
        },
        {
            "type": "item.completed",
            "item": {"id": "stream_item_0", "type": "reasoning", "text": "先搜索"},
        },
        {
            "type": "item.completed",
            "item": {
                "id": "msg_1",
                "type": "agent_message",
                "text": "先搜索仓库",
                "phase": "commentary",
            },
        },
    ]
    assert result.continuation_input_items == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "search provider"}],
        },
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "先搜索仓库"}],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "file_search",
            "arguments": '{"query":"provider","path":"cli"}',
        },
    ]


def test_openai_responses_session_dedupes_reasoning_summary_against_reasoning_output_item() -> None:
    client = _FakeStreamClient(
        [
            _stream_event("response.reasoning_summary_text.delta", summary_index=0, delta="先"),
            _stream_event("response.reasoning_summary_text.delta", summary_index=0, delta="搜索"),
            _stream_event(
                "response.output_item.done",
                item=SimpleNamespace(
                    type="reasoning",
                    id="rs_1",
                    content=[SimpleNamespace(type="reasoning", text="先搜索")],
                    summary=[SimpleNamespace(type="summary_text", text="先搜索")],
                    encrypted_content="enc-1",
                ),
            ),
            _stream_event(
                "response.output_item.done",
                item=SimpleNamespace(
                    type="message",
                    id="msg_1",
                    role="assistant",
                    content=[SimpleNamespace(type="output_text", text="先搜索仓库")],
                ),
            ),
            _stream_event("response.completed", response=SimpleNamespace(id="resp_stream")),
        ]
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    emitted: list[dict] = []
    result = session.send(
        input_items=[{"role": "user", "content": "search provider"}],
        allow_tools=True,
        turn_event_callback=emitted.append,
    )

    assert emitted == [
        {
            "type": "item.updated",
            "item": {"id": "stream_item_0", "type": "reasoning", "text": "先"},
        },
        {
            "type": "item.updated",
            "item": {"id": "stream_item_0", "type": "reasoning", "text": "先搜索"},
        },
        {
            "type": "item.completed",
            "item": {
                "id": "rs_1",
                "type": "reasoning",
                "text": "先搜索",
                "summary": [{"type": "summary_text", "text": "先搜索"}],
                "encrypted_content": "enc-1",
                "provider_item_id": "rs_1",
            },
        },
        {
            "type": "item.completed",
            "item": {"id": "msg_1", "type": "agent_message", "text": "先搜索仓库"},
        },
    ]
    assert [item.item_type for item in result.response_items] == ["reasoning", "message"]


def test_openai_responses_session_streams_shell_call_items() -> None:
    client = _FakeStreamClient(
        [
            _stream_event(
                "response.output_item.done",
                item=SimpleNamespace(
                    type="shell_call",
                    call_id="call_shell_stream",
                    action={
                        "type": "exec",
                        "command": ["pwd"],
                        "timeout_ms": 1000,
                        "max_output_length": 12000,
                    },
                    status="completed",
                ),
            ),
            _stream_event("response.completed", response=SimpleNamespace(id="resp_shell_stream")),
        ]
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[{"type": "function", "name": "shell"}],
    )

    emitted: list[dict] = []
    result = session.send(
        input_items=[{"role": "user", "content": "pwd"}],
        allow_tools=True,
        turn_event_callback=emitted.append,
    )

    assert emitted == []
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].item_type == "shell_call"
    assert result.tool_calls[0].arguments["command"] == "pwd"
    assert result.continuation_input_items[-1] == {
        "type": "shell_call",
        "call_id": "call_shell_stream",
        "action": {
            "type": "exec",
            "command": ["pwd"],
            "timeout_ms": 1000,
            "max_output_length": 12000,
        },
        "status": "completed",
    }


def test_openai_responses_session_streams_output_text_as_updated_then_completed_message() -> None:
    client = _FakeStreamClient(
        [
            _stream_event("response.output_text.delta", output_index=0, delta="先查看"),
            _stream_event("response.output_text.delta", output_index=0, delta="当前目录。"),
            _stream_event("response.completed", response=SimpleNamespace(id="resp_stream_2")),
        ]
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    emitted: list[dict] = []
    result = session.send(
        input_items=[{"role": "user", "content": "list dir"}],
        allow_tools=False,
        turn_event_callback=emitted.append,
    )

    assert emitted == [
        {
            "type": "item.updated",
            "item": {"id": "stream_item_0", "type": "agent_message", "text": "先查看"},
        },
        {
            "type": "item.updated",
            "item": {"id": "stream_item_0", "type": "agent_message", "text": "先查看当前目录。"},
        },
        {
            "type": "item.completed",
            "item": {"id": "stream_item_0", "type": "agent_message", "text": "先查看当前目录。"},
        },
    ]
    assert result.output_text == "先查看当前目录。"


def test_openai_responses_session_reuses_stream_item_id_for_completed_message_item() -> None:
    client = _FakeStreamClient(
        [
            _stream_event("response.output_text.delta", output_index=0, delta="我先查看"),
            _stream_event(
                "response.output_item.done",
                item=SimpleNamespace(
                    type="message",
                    id="msg_native",
                    role="assistant",
                    content=[SimpleNamespace(type="output_text", text="我先查看")],
                ),
            ),
            _stream_event("response.completed", response=SimpleNamespace(id="resp_stream_3")),
        ]
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    emitted: list[dict] = []
    session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
        turn_event_callback=emitted.append,
    )

    assert emitted == [
        {
            "type": "item.updated",
            "item": {"id": "stream_item_0", "type": "agent_message", "text": "我先查看"},
        },
        {
            "type": "item.completed",
            "item": {"id": "stream_item_0", "type": "agent_message", "text": "我先查看"},
        },
    ]


def test_openai_responses_session_uses_native_message_id_and_phase_for_stream_updates() -> None:
    client = _FakeStreamClient(
        [
            _stream_event(
                "response.output_item.added",
                output_index=0,
                item=SimpleNamespace(
                    type="message", id="msg_native", role="assistant", phase="commentary"
                ),
            ),
            _stream_event("response.output_text.delta", output_index=0, delta="我先"),
            _stream_event("response.output_text.delta", output_index=0, delta="查看当前目录。"),
            _stream_event(
                "response.output_item.done",
                output_index=0,
                item=SimpleNamespace(
                    type="message",
                    id="msg_native",
                    role="assistant",
                    phase="commentary",
                    content=[SimpleNamespace(type="output_text", text="我先查看当前目录。")],
                ),
            ),
            _stream_event("response.completed", response=SimpleNamespace(id="resp_stream_4")),
        ]
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    emitted: list[dict] = []
    session.send(
        input_items=[{"role": "user", "content": "list dir"}],
        allow_tools=False,
        turn_event_callback=emitted.append,
    )

    assert emitted == [
        {
            "type": "item.updated",
            "item": {
                "id": "msg_native",
                "type": "agent_message",
                "text": "我先",
                "phase": "commentary",
            },
        },
        {
            "type": "item.updated",
            "item": {
                "id": "msg_native",
                "type": "agent_message",
                "text": "我先查看当前目录。",
                "phase": "commentary",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "msg_native",
                "type": "agent_message",
                "text": "我先查看当前目录。",
                "phase": "commentary",
            },
        },
    ]


def test_openai_responses_session_extracts_custom_tool_call_as_provider_tool_call() -> None:
    patch_text = "*** Begin Patch\n*** End Patch"
    client = _FakeClient(
        _response(
            _custom_tool_call("call_patch_1", "apply_patch", patch_text),
            response_id="resp_custom",
        )
    )
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    result = session.send(
        input_items=[{"role": "user", "content": "patch it"}],
        allow_tools=True,
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].item_type == "custom_tool_call"
    assert result.tool_calls[0].name == "apply_patch"
    assert result.tool_calls[0].arguments == {"patch": patch_text}
    assert result.continuation_input_items[-1] == {
        "type": "custom_tool_call",
        "call_id": "call_patch_1",
        "name": "apply_patch",
        "input": patch_text,
    }


def test_openai_responses_session_normalizes_custom_tool_call_output_inputs() -> None:
    client = _FakeClient(_response(response_id="resp_custom_output"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    session.send(
        input_items=[
            {
                "type": "custom_tool_call_output",
                "call_id": "call_patch_1",
                "output": "Patch applied",
            },
        ],
        allow_tools=False,
    )

    request = client.responses.requests[0]
    assert request["input"] == [
        {"type": "custom_tool_call_output", "call_id": "call_patch_1", "output": "Patch applied"}
    ]


def test_openai_responses_session_build_tool_result_items_emits_custom_tool_call_output() -> None:
    client = _FakeClient(_response(response_id="resp_tool_output"))
    session = OpenAIResponsesSession(
        client=client,
        model="gpt-5.4",
        instructions="system",
        tool_specs=[],
    )

    items = session.build_tool_result_items(
        call_id="call_patch_2",
        command_text="/apply_patch '*** Begin Patch\n*** End Patch'",
        assistant_text="Patch applied",
        events=[
            ToolEvent(
                name="apply_patch",
                ok=True,
                summary="Patch applied",
                payload={"provider_tool_type": "custom_tool_call"},
            )
        ],
    )

    assert items == [
        {
            "type": "custom_tool_call_output",
            "call_id": "call_patch_2",
            "output": "Patch applied",
            "success": True,
        }
    ]
