from __future__ import annotations

import threading

import pytest

from cli.agent_cli.mcp.sdk_bridge import MCP_BRIDGE_METHOD, SdkMcpClientBridge, SdkMcpServerBridge


def test_sdk_mcp_client_bridge_send_round_trip() -> None:
    emitted: list[dict[str, object]] = []
    holder: dict[str, SdkMcpClientBridge] = {}

    def _emit(message: dict[str, object]) -> None:
        emitted.append(message)
        holder["bridge"].handle_response_message(
            {
                "id": message["id"],
                "result": {"serverName": "calc", "message": {"ok": True, "answer": 42}},
            }
        )

    bridge = SdkMcpClientBridge(emit=_emit)
    holder["bridge"] = bridge

    result = bridge.send(server_name="calc", message={"op": "sum", "values": [19, 23]})

    assert result == {"ok": True, "answer": 42}
    assert emitted[0]["method"] == MCP_BRIDGE_METHOD
    assert emitted[0]["params"] == {"serverName": "calc", "message": {"op": "sum", "values": [19, 23]}}


def test_sdk_mcp_client_bridge_close_aborts_pending_request() -> None:
    sent_event = threading.Event()
    bridge = SdkMcpClientBridge(emit=lambda _message: sent_event.set())
    captured: dict[str, BaseException] = {}

    def _run_send() -> None:
        try:
            bridge.send(server_name="calc", message={"op": "sum"})
        except BaseException as exc:  # pragma: no cover - assert-driven capture path
            captured["error"] = exc

    thread = threading.Thread(target=_run_send, daemon=True)
    thread.start()
    assert sent_event.wait(timeout=1.0)

    bridge.close()
    thread.join(timeout=1.0)

    assert "error" in captured
    assert isinstance(captured["error"], RuntimeError)
    assert "Bridge closed before response was received" in str(captured["error"])


def test_sdk_mcp_server_bridge_routes_registered_handler_and_emits_result() -> None:
    emitted: list[dict[str, object]] = []
    bridge = SdkMcpServerBridge(emit=emitted.append)

    bridge.register_handler("calc", lambda message: {"echo": message.get("value"), "ok": True})

    handled = bridge.handle_request_message(
        {
            "id": "req_1",
            "method": MCP_BRIDGE_METHOD,
            "params": {"serverName": "calc", "message": {"value": 7}},
        }
    )

    assert handled is True
    assert emitted == [{"id": "req_1", "result": {"serverName": "calc", "message": {"echo": 7, "ok": True}}}]


def test_sdk_mcp_server_bridge_missing_handler_emits_error() -> None:
    emitted: list[dict[str, object]] = []
    bridge = SdkMcpServerBridge(emit=emitted.append)

    handled = bridge.handle_request_message(
        {
            "id": "req_2",
            "method": MCP_BRIDGE_METHOD,
            "params": {"serverName": "unknown", "message": {"value": 1}},
        }
    )

    assert handled is True
    assert emitted and emitted[0]["id"] == "req_2"
    error = emitted[0]["error"]
    assert isinstance(error, dict)
    assert "No MCP handler registered for \"unknown\"" in str(error.get("message"))


def test_sdk_mcp_server_bridge_handler_exception_emits_error() -> None:
    emitted: list[dict[str, object]] = []
    bridge = SdkMcpServerBridge(emit=emitted.append)

    def _boom(_message: dict[str, object]) -> dict[str, object]:
        raise ValueError("bad payload")

    bridge.register_handler("calc", _boom)
    handled = bridge.handle_request_message(
        {
            "id": "req_3",
            "method": MCP_BRIDGE_METHOD,
            "params": {"serverName": "calc", "message": {"value": 1}},
        }
    )

    assert handled is True
    assert emitted and emitted[0]["id"] == "req_3"
    error = emitted[0]["error"]
    assert isinstance(error, dict)
    assert "ValueError: bad payload" in str(error.get("message"))


def test_sdk_mcp_client_bridge_send_times_out() -> None:
    bridge = SdkMcpClientBridge(emit=lambda _message: None)

    with pytest.raises(TimeoutError):
        bridge.send(server_name="calc", message={"op": "sum"}, timeout_sec=0.01)


def test_sdk_mcp_client_bridge_send_requires_server_name() -> None:
    bridge = SdkMcpClientBridge(emit=lambda _message: None)

    with pytest.raises(ValueError, match="server_name is required"):
        bridge.send(server_name=" ", message={"op": "sum"})
