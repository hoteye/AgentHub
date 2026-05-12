from __future__ import annotations

import http.server
import socketserver
import sys
import threading

import pytest

from cli.agent_cli.mcp.client import MCPClient, MCPServerConfig
from cli.agent_cli.mcp.auth import MCPAuthConfig
from cli.agent_cli.mcp.transports import MCPTransportConfig, MCPTransportError, connect_transport


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class _FailureHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/auth":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return
        if self.path == "/ok":
            auth_header = str(self.headers.get("Authorization") or "")
            if auth_header == "Bearer from_token":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
                return
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"forbidden"}')
            return
        if self.path == "/sse-bad-content":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        self.send_response(500)
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return


def _start_server() -> tuple[_ThreadedHTTPServer, str]:
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _FailureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_timeout_maps_to_failed_for_stdio_transport() -> None:
    client = MCPClient()
    config = MCPServerConfig(
        name="slow_stdio",
        transport=MCPTransportConfig(
            transport="stdio",
            command=(sys.executable,),
            args=("-c", "import time; time.sleep(1.0)"),
            timeout_sec=0.05,
        ),
    )

    result = client.connect(config)

    assert result.status == "failed"
    assert result.error_code == "timeout"


def test_auth_failure_maps_to_needs_auth_for_http_and_sse() -> None:
    server, base_url = _start_server()
    try:
        client = MCPClient()
        http_result = client.connect(
            MCPServerConfig(
                name="http_auth",
                transport=MCPTransportConfig(
                    transport="http",
                    url=f"{base_url}/auth",
                    timeout_sec=1.0,
                ),
            )
        )
        sse_result = client.connect(
            MCPServerConfig(
                name="sse_auth",
                transport=MCPTransportConfig(
                    transport="sse",
                    url=f"{base_url}/auth",
                    timeout_sec=1.0,
                ),
            )
        )

        assert http_result.status == "needs-auth"
        assert sse_result.status == "needs-auth"
    finally:
        server.shutdown()
        server.server_close()


def test_disabled_server_returns_disabled_status() -> None:
    client = MCPClient()
    config = MCPServerConfig(
        name="disabled",
        enabled=False,
        transport=MCPTransportConfig(
            transport="http",
            url="http://127.0.0.1:1/never",
            timeout_sec=0.2,
        ),
    )

    result = client.connect(config)

    assert result.status == "disabled"


def test_sse_invalid_content_type_maps_to_failed() -> None:
    server, base_url = _start_server()
    try:
        client = MCPClient()
        result = client.connect(
            MCPServerConfig(
                name="sse_bad_content",
                transport=MCPTransportConfig(
                    transport="sse",
                    url=f"{base_url}/sse-bad-content",
                    timeout_sec=1.0,
                ),
            )
        )
        assert result.status == "failed"
        assert result.error_code == "invalid-content-type"
    finally:
        server.shutdown()
        server.server_close()


def test_http_connect_includes_auth_token_header() -> None:
    server, base_url = _start_server()
    try:
        client = MCPClient()
        result = client.connect(
            MCPServerConfig(
                name="http_auth_header",
                transport=MCPTransportConfig(
                    transport="http",
                    url=f"{base_url}/ok",
                    timeout_sec=1.0,
                    auth=MCPAuthConfig(token="from_token"),
                ),
            )
        )
        assert result.status == "connected"
        assert result.error_code == ""
    finally:
        server.shutdown()
        server.server_close()


def test_http_connect_resolves_env_header_reference(monkeypatch) -> None:
    monkeypatch.setenv("AGENTHUB_DOCS_AUTH", "Bearer from_token")
    server, base_url = _start_server()
    try:
        client = MCPClient()
        result = client.connect(
            MCPServerConfig(
                name="http_auth_env_header",
                transport=MCPTransportConfig(
                    transport="http",
                    url=f"{base_url}/ok",
                    timeout_sec=1.0,
                    headers={"Authorization": "$env:AGENTHUB_DOCS_AUTH"},
                ),
            )
        )
        assert result.status == "connected"
        assert result.error_code == ""
    finally:
        server.shutdown()
        server.server_close()


def test_http_connect_missing_env_header_reference_returns_invalid_config() -> None:
    with pytest.raises(MCPTransportError) as excinfo:
        connect_transport(
            MCPTransportConfig(
                transport="http",
                url="http://127.0.0.1:9000/ok",
                headers={"Authorization": "$env:AGENTHUB_MISSING_TOKEN"},
            )
        )
    assert excinfo.value.error_code == "invalid-config"


def test_needs_auth_server_recovers_after_auth_update_and_reconnect() -> None:
    server, base_url = _start_server()
    try:
        client = MCPClient()
        unauthenticated = MCPServerConfig(
            name="http_recover",
            transport=MCPTransportConfig(
                transport="http",
                url=f"{base_url}/ok",
                timeout_sec=1.0,
            ),
        )
        authenticated = MCPServerConfig(
            name="http_recover",
            transport=MCPTransportConfig(
                transport="http",
                url=f"{base_url}/ok",
                timeout_sec=1.0,
                auth=MCPAuthConfig(token="from_token"),
            ),
        )

        first = client.connect(unauthenticated)
        recovered = client.reconnect(authenticated)

        assert first.status == "needs-auth"
        assert recovered.status == "connected"
        assert recovered.error_code == ""
    finally:
        server.shutdown()
        server.server_close()


def test_http_invalid_url_scheme_returns_invalid_config_error() -> None:
    with pytest.raises(MCPTransportError) as excinfo:
        connect_transport(
            MCPTransportConfig(
                transport="http",
                url="file:///tmp/x",
            )
        )
    assert excinfo.value.error_code == "invalid-config"


def test_ws_invalid_url_scheme_returns_invalid_config_error() -> None:
    with pytest.raises(MCPTransportError) as excinfo:
        connect_transport(
            MCPTransportConfig(
                transport="ws",
                url="http://127.0.0.1:9000/socket",
            )
        )
    assert excinfo.value.error_code == "invalid-config"
