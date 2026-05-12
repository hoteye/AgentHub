from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.providers.adapters.chat_completions import ChatCompletionsSession

class _FakeChatCompletions:
    def __init__(self, response) -> None:
        self.response = response
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.response

class _FakeSequencedChatCompletions:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected extra completion request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

def _tool_call(call_id: str, name: str, arguments: str):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )

def test_chat_completions_session_sends_tools_and_timeout():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="done",
                    tool_calls=[_tool_call("call_1", "file_read", '{"path":"README.md"}')],
                )
            )
        ]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[{"type": "function", "function": {"name": "file_read"}}],
        supports_tools=True,
        extra_body={"provider": "glm"},
        timeout=12.5,
    )

    result = session.send(
        input_items=[{"role": "user", "content": "read"}],
        allow_tools=True,
    )

    assert result.output_text == "done"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "file_read"
    assert result.tool_calls[0].arguments == {"path": "README.md"}
    assert completions.requests[0]["tools"][0]["function"]["name"] == "file_read"
    assert completions.requests[0]["tool_choice"] == "auto"
    assert completions.requests[0]["timeout"] == 12.5
    assert completions.requests[0]["extra_body"] == {"provider": "glm"}


def test_chat_completions_session_trace_includes_contract_fields() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content="done",
                    tool_calls=[],
                ),
            )
        ]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[],
        supports_tools=False,
        interaction_profile="generic_chat",
        turn_protocol_policy="generic_chat_turn",
    )

    result = session.send(
        input_items=[{"role": "user", "content": "hi"}],
        allow_tools=False,
    )

    assert result.trace["interaction_profile"] == "generic_chat"
    assert result.trace["turn_protocol_policy"] == "generic_chat_turn"

def test_chat_completions_session_omits_tools_when_disabled():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=[{"type": "text", "text": "plain answer"}], tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[{"type": "function", "function": {"name": "file_read"}}],
        supports_tools=True,
    )

    result = session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
    )

    assert result.output_text == "plain answer"
    assert result.tool_calls == []
    assert result.response_items[0].extra["phase"] == "final_answer"
    assert result.response_items[0].content == [{"type": "output_text", "text": "plain answer"}]
    assert "tools" not in completions.requests[0]
    assert "tool_choice" not in completions.requests[0]

def test_chat_completions_session_accumulates_messages_and_builds_tool_items():
    response_one = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="先读文件",
                    tool_calls=[_tool_call("call_1", "file_read", '{"path":"README.md"}')],
                )
            )
        ]
    )
    response_two = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="已读完", tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response_one)
    completions.response = response_one
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[{"type": "function", "function": {"name": "file_read"}}],
        supports_tools=True,
    )

    first = session.send(
        input_items=[{"role": "system", "content": "sys"}, {"role": "user", "content": "read"}],
        allow_tools=True,
    )
    tool_items = session.build_tool_result_items(
        call_id="call_1",
        command_text="/file_read README.md",
        assistant_text="执行完成",
        events=[],
    )
    completions.response = response_two
    second = session.send(
        input_items=tool_items,
        allow_tools=True,
    )

    assert first.response_id == "chatcmpl-1"
    assert second.response_id == "chatcmpl-2"
    assert completions.requests[1]["messages"][0]["role"] == "system"
    assert completions.requests[1]["messages"][1]["role"] == "user"
    assert completions.requests[1]["messages"][2]["role"] == "assistant"
    assert completions.requests[1]["messages"][3]["role"] == "tool"
    assert completions.requests[1]["messages"][3]["tool_call_id"] == "call_1"
    assert second.output_text == "已读完"

def test_chat_completions_session_normalizes_structured_message_items():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[],
        supports_tools=False,
    )

    session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ],
        allow_tools=False,
    )

    assert completions.requests[0]["messages"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hello"}],
        }
    ]

def test_chat_completions_session_downgrades_developer_role_when_provider_disallows_it():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="deepseek-chat",
        tool_specs=[],
        supports_tools=False,
        supports_developer_role=False,
    )

    session.send(
        input_items=[
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "dev rules"}],
            }
        ],
        allow_tools=False,
    )

    assert completions.requests[0]["messages"] == [
        {
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": "dev rules"}],
        }
    ]

def test_chat_completions_session_retries_network_error_finish_reason():
    first_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="network_error",
                message=SimpleNamespace(content="", tool_calls=[]),
            )
        ]
    )
    second_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="ok", tool_calls=[]),
            )
        ]
    )
    completions = _FakeSequencedChatCompletions([first_response, second_response])
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[],
        supports_tools=False,
    )

    result = session.send(
        input_items=[{"role": "user", "content": "hello"}],
        allow_tools=False,
    )

    assert result.output_text == "ok"
    assert result.trace["finish_reason"] == "stop"
    assert len(completions.requests) == 2

def test_chat_completions_session_normalizes_response_item_wrappers():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[],
        supports_tools=False,
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

    assert completions.requests[0]["messages"] == [{"role": "assistant", "content": "structured assistant"}]

def test_chat_completions_session_normalizes_function_call_output_items():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[],
        supports_tools=False,
    )

    session.send(
        input_items=[
            {"type": "function_call_output", "call_id": "call_1", "output": {"ok": True}},
            {"role": "tool", "tool_call_id": "call_2", "output": {"rows": 3}},
        ],
        allow_tools=False,
    )

    assert completions.requests[0]["messages"] == [
        {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'},
        {"role": "tool", "tool_call_id": "call_2", "content": '{"rows": 3}'},
    ]

def test_chat_completions_session_projects_workspace_reference_context_item_to_message() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[],
        supports_tools=False,
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
                        "instructions_excerpt": "workspace baseline",
                    },
                },
            }
        ],
        allow_tools=False,
    )

    assert completions.requests[0]["messages"] == [
        {
            "role": "user",
            "content": "REFERENCE_CONTEXT_BASELINE:\ncwd=/repo\ntrust=trusted\ninstructions_digest=digest-v1\nrule_count=0\n\nworkspace baseline",
        }
    ]

def test_chat_completions_session_flattens_content_item_outputs_to_text() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[],
        supports_tools=False,
    )

    session.send(
        input_items=[
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": [
                    {"type": "input_text", "text": "line 1"},
                    {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
                    {"type": "input_text", "text": "line 2"},
                ],
            }
        ],
        allow_tools=False,
    )

    assert completions.requests[0]["messages"] == [
        {"role": "tool", "tool_call_id": "call_1", "content": "line 1\nline 2"},
    ]

def test_chat_completions_session_build_tool_result_items_returns_structured_item():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[],
        supports_tools=False,
    )

    items = session.build_tool_result_items(
        call_id="call_1",
        command_text="/file_read README.md",
        assistant_text="done",
        events=[],
    )

    assert len(items) == 1
    assert items[0]["type"] == "function_call_output"
    assert items[0]["call_id"] == "call_1"
    assert items[0]["output"] == "done"
    assert items[0]["success"] is True

def test_chat_completions_session_build_tool_result_items_prefers_textual_event_output():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
    )
    completions = _FakeChatCompletions(response)
    session = ChatCompletionsSession(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="glm-5",
        tool_specs=[],
        supports_tools=False,
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

    assert items[0]["type"] == "function_call_output"
    assert items[0]["call_id"] == "call_2"
    assert items[0]["output"] == "web page loaded"
    assert items[0]["success"] is True
