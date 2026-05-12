from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonRpcServerRequest
from cli.agent_cli.runtime_kernels.codex_sidecar.server_requests import (
    CodexServerRequestRegistry,
    envelope_from_server_request,
    kind_for_method,
    unsupported_server_request_response,
)


def _request(method: str, params: dict[str, object] | None = None) -> JsonRpcServerRequest:
    payload = dict(params or {})
    return JsonRpcServerRequest(
        request_id="req-1",
        method=method,
        params=payload,
        raw={"id": "req-1", "method": method, "params": payload},
    )


def test_envelope_extracts_common_request_ownership_fields() -> None:
    runtime = SimpleNamespace(tab_id="tab-a")

    envelope = envelope_from_server_request(
        _request(
            "item/commandExecution/requestApproval",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "itemId": "cmd-1",
                "command": "printf ok",
            },
        ),
        runtime=runtime,
    )

    assert envelope.kind == "command_execution_approval"
    assert envelope.thread_id == "thread-1"
    assert envelope.turn_id == "turn-1"
    assert envelope.item_id == "cmd-1"
    assert envelope.tab_id == "tab-a"
    assert envelope.status == "pending"


def test_known_codex_server_request_method_kinds_are_classified() -> None:
    assert kind_for_method("item/fileChange/requestApproval") == "file_change_approval"
    assert kind_for_method("item/permissions/requestApproval") == "permission_approval"
    assert kind_for_method("item/tool/requestUserInput") == "tool_user_input"
    assert kind_for_method("mcpServer/elicitation/request") == "mcp_elicitation"
    assert kind_for_method("item/tool/call") == "dynamic_tool_call"
    assert kind_for_method("missing/method") == "unsupported"


def test_registry_dispatches_handler_and_tracks_pending_until_explicit_resolution() -> None:
    registry = CodexServerRequestRegistry()
    responses: list[tuple[JsonRpcServerRequest, dict[str, object]]] = []

    def handler(runtime, envelope):
        assert runtime == "runtime"
        assert envelope.request_id == "req-1"
        return None

    registry.register("item/tool/requestUserInput", handler)
    envelope = registry.dispatch(
        "runtime",
        _request("item/tool/requestUserInput", {"threadId": "thread-1", "turnId": "turn-1"}),
        respond=lambda request, response: responses.append((request, response)),
    )

    assert envelope.status == "pending"
    assert registry.get("req-1") is envelope
    assert responses == []

    registry.resolve("req-1", status="responded")

    assert registry.get("req-1") is None
    assert envelope.status == "responded"


def test_registry_writes_error_for_unsupported_request_and_clears_pending() -> None:
    registry = CodexServerRequestRegistry()
    responses: list[dict[str, object]] = []

    envelope = registry.dispatch(
        None,
        _request("unknown/request", {"threadId": "thread-1"}),
        respond=lambda _request, response: responses.append(response),
    )

    assert envelope.status == "unsupported"
    assert registry.pending() == []
    assert responses == [unsupported_server_request_response(envelope)]
