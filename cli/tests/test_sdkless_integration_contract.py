from __future__ import annotations

import pytest

from cli.agent_cli import app_server_protocol_runtime
from cli.agent_cli import headless_stream_runtime
from cli.agent_cli.subcommands import mcp as mcp_subcommand


def test_app_server_sdkless_contract_includes_core_methods() -> None:
    methods = app_server_protocol_runtime.app_server_capability_methods()
    method_set = {str(item) for item in methods}
    for required in (
        "initialize",
        "session/run",
        "session/start",
        "command/exec",
        "command/start",
        "server/ping",
    ):
        assert required in method_set


def test_app_server_sdkless_contract_unsupported_method_mapping_is_stable() -> None:
    mapped = app_server_protocol_runtime.unsupported_reference_method_error_data("skills/list")
    assert mapped == {
        "detail": "skills/list",
        "compatibility": app_server_protocol_runtime.APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
        "replacement": "tools/list",
    }
    assert app_server_protocol_runtime.unsupported_reference_method_error_data("nonexistent/method") is None


def test_headless_serve_request_contract_provider_status_and_prompt() -> None:
    provider_status_prompt = headless_stream_runtime.resolve_serve_prompt(
        {"id": "req-1", "provider_status": True}
    )
    text_prompt = headless_stream_runtime.resolve_serve_prompt(
        {"id": "req-2", "prompt": "/provider"}
    )
    assert provider_status_prompt == "/provider"
    assert text_prompt == "/provider"


def test_headless_serve_request_contract_rejects_empty_prompt() -> None:
    with pytest.raises(ValueError, match=r"request\.prompt must not be empty"):
        headless_stream_runtime.resolve_serve_prompt({"id": "req-3", "prompt": "   "})


def test_headless_serve_request_id_contract_normalizes_scalar_ids() -> None:
    assert headless_stream_runtime.request_id_for_payload({"id": "abc"}) == "abc"
    assert headless_stream_runtime.request_id_for_payload({"id": 7}) == "7"
    assert headless_stream_runtime.request_id_for_payload({"prompt": "/provider"}) is None
    assert headless_stream_runtime.request_id_for_payload("not-an-object") is None


def test_headless_stream_event_type_contract_for_session_turn_tool_and_error() -> None:
    assert headless_stream_runtime.stream_json_event_type({"type": "thread.started"}) == "session"
    assert headless_stream_runtime.stream_json_event_type({"type": "turn.completed"}) == "turn"
    assert headless_stream_runtime.stream_json_event_type(
        {"type": "item.completed", "item": {"type": "mcp_tool_call"}}
    ) == "tool"
    assert headless_stream_runtime.stream_json_event_type({"type": "error", "error": "invalid_request"}) == "error"


def test_mcp_subcommand_contract_examples_map_to_slash_commands() -> None:
    assert mcp_subcommand.parse_mcp_subcommand(["list"]).command_text == "/mcp list"
    assert mcp_subcommand.parse_mcp_subcommand(["inspect", "atlas"]).command_text == "/mcp inspect atlas"
    assert mcp_subcommand.parse_mcp_subcommand(["reconnect", "all"]).command_text == "/mcp reconnect all"
    assert mcp_subcommand.parse_mcp_subcommand(["enable", "atlas"]).command_text == "/mcp enable atlas"
    assert mcp_subcommand.parse_mcp_subcommand(["disable", "atlas"]).command_text == "/mcp disable atlas"
