from __future__ import annotations

import json
import http.server
import socketserver
import sys
import threading

from cli.agent_cli.mcp.client import MCPClient, MCPServerConfig
from cli.agent_cli.mcp.transports import MCPTransportConfig

from .mcp_testkit import inline_stdio_mcp_transport_config


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class _ConnectHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: ready\n\n")
            return
        if self.path == "/mcp":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self.send_response(404)
            self.end_headers()
            return
        content_length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(content_length)
        try:
            message = json.loads(raw.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"bad json"}')
            return
        method = str(message.get("method") or "").strip()
        message_id = message.get("id")
        if method == "initialize":
            payload = {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {
                    "serverInfo": {"name": "http_mcp_server", "version": "0-test"},
                    "capabilities": {"tools": {"listChanged": False}},
                    "instructions": "http transport session ready",
                },
            }
        elif method == "initialized":
            payload = {"jsonrpc": "2.0", "id": message_id, "result": {}}
        elif method == "tools/list":
            payload = {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {
                    "tools": [
                        {
                            "name": "http.echo",
                            "description": "Echo one text payload.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"],
                                "additionalProperties": False,
                            },
                        }
                    ]
                },
            }
        elif method == "tools/call":
            params = dict(message.get("params") or {})
            arguments = dict(params.get("arguments") or {})
            text = str(arguments.get("text") or "").strip()
            payload = {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {
                    "isError": False,
                    "content": [{"type": "text", "text": f"echo:{text}"}],
                },
            }
        else:
            payload = {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": -32601, "message": "method not found"},
            }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=True).encode("utf-8"))

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return


def _start_server() -> tuple[_ThreadedHTTPServer, str]:
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _ConnectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_connect_many_supports_stdio_http_sse_ws() -> None:
    server, base_url = _start_server()
    try:
        client = MCPClient()
        configs = {
            "stdio_ok": MCPServerConfig(
                name="stdio_ok",
                transport=MCPTransportConfig(
                    transport="stdio",
                    command=(sys.executable,),
                    args=("-c", "print('ready')"),
                    timeout_sec=2.0,
                ),
            ),
            "http_ok": MCPServerConfig(
                name="http_ok",
                transport=MCPTransportConfig(
                    transport="http",
                    url=f"{base_url}/health",
                    timeout_sec=2.0,
                ),
            ),
            "sse_ok": MCPServerConfig(
                name="sse_ok",
                transport=MCPTransportConfig(
                    transport="sse",
                    url=f"{base_url}/events",
                    timeout_sec=2.0,
                ),
            ),
            "ws_ok": MCPServerConfig(
                name="ws_ok",
                transport=MCPTransportConfig(
                    transport="ws",
                    url=f"ws://{base_url.split('://', 1)[1]}/socket",
                    timeout_sec=2.0,
                ),
            ),
        }

        results = client.connect_many(configs)

        assert results["stdio_ok"].status == "connected"
        assert results["http_ok"].status == "connected"
        assert results["sse_ok"].status == "connected"
        assert results["ws_ok"].status == "connected"
        assert client.cache_size() == 4
    finally:
        server.shutdown()
        server.server_close()


def test_cache_invalidate_and_reconnect() -> None:
    server, base_url = _start_server()
    try:
        client = MCPClient()
        config = MCPServerConfig(
            name="cache_http",
            transport=MCPTransportConfig(
                transport="http",
                url=f"{base_url}/health",
                timeout_sec=2.0,
            ),
        )

        first = client.connect(config)
        second = client.connect(config)

        assert first.status == "connected"
        assert second.status == "connected"
        assert second.from_cache is True
        assert first.handle is not None
        assert second.handle is first.handle

        client.invalidate("cache_http")
        third = client.connect(config)

        assert third.status == "connected"
        assert third.from_cache is False
        assert third.handle is not None
        assert third.handle is not first.handle
    finally:
        server.shutdown()
        server.server_close()


def test_stdio_connect_establishes_session_and_lists_remote_tools() -> None:
    client = MCPClient()
    config = MCPServerConfig(
        name="stdio_mcp",
        transport=inline_stdio_mcp_transport_config(timeout_sec=3.0),
    )

    result = client.connect(config)

    assert result.status == "connected"
    assert result.handle is not None
    assert result.handle.session is not None
    assert result.handle.server_info["name"] == "agenthub_mcp_server"
    assert result.handle.capabilities["tools"]["listChanged"] is False
    remote_tool_names = [item["name"] for item in result.handle.session.tools_list()]
    assert remote_tool_names == ["agenthub.file_read", "agenthub.list_dir"]

    client.clear_cache()


def test_http_connect_establishes_session_and_lists_remote_tools() -> None:
    server, base_url = _start_server()
    try:
        client = MCPClient()
        config = MCPServerConfig(
            name="http_mcp",
            transport=MCPTransportConfig(
                transport="http",
                url=f"{base_url}/mcp",
                timeout_sec=2.0,
            ),
        )

        result = client.connect(config)

        assert result.status == "connected"
        assert result.handle is not None
        assert result.handle.session is not None
        assert result.handle.server_info["name"] == "http_mcp_server"
        assert result.handle.capabilities["tools"]["listChanged"] is False
        remote_tool_names = [item["name"] for item in result.handle.session.tools_list()]
        assert remote_tool_names == ["http.echo"]
        tool_call = result.handle.session.tools_call(name="http.echo", arguments={"text": "ping"})
        assert tool_call.get("isError") is False
    finally:
        server.shutdown()
        server.server_close()


def test_invalidate_closes_stdio_session_process() -> None:
    client = MCPClient()
    config = MCPServerConfig(
        name="stdio_mcp",
        transport=inline_stdio_mcp_transport_config(timeout_sec=3.0),
    )

    result = client.connect(config)

    assert result.handle is not None
    session = result.handle.session
    assert session is not None
    assert session.process.poll() is None

    client.invalidate("stdio_mcp")

    assert session.process.wait(timeout=2.0) is not None
