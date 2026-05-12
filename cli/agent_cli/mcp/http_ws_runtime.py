from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.request
from typing import Any, Mapping
from urllib.parse import urlparse

from .auth import is_auth_status_code
from .transports import MCPTransportError


class HttpMcpSession:
    def __init__(
        self,
        *,
        url: str,
        headers: Mapping[str, str] | None,
        timeout_sec: float,
        transport: str,
    ) -> None:
        self._url = str(url or "").strip()
        self._headers = {str(key): str(value) for key, value in dict(headers or {}).items()}
        self._timeout_sec = max(float(timeout_sec), 0.01)
        self._transport = str(transport or "").strip() or "http"
        self._next_request_id = 0
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if self._closed:
            raise MCPTransportError("http session is closed", error_code="closed")
        self._next_request_id += 1
        request_id = self._next_request_id
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": str(method or "").strip(),
            "params": dict(params or {}),
        }
        request_headers = dict(self._headers)
        request_headers.setdefault("Content-Type", "application/json")
        request_headers.setdefault("Accept", "application/json, text/event-stream")
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_sec) as response:
                status = int(getattr(response, "status", 200) or 200)
                if status >= 400:
                    raise MCPTransportError(
                        f"http status {status}",
                        error_code="http-status",
                        status_code=status,
                    )
                body = bytes(response.read() or b"")
                content_type = str(response.headers.get("Content-Type") or "")
        except urllib.error.HTTPError as exc:
            raise MCPTransportError(
                f"http status {exc.code}",
                error_code="http-status",
                status_code=int(exc.code),
            ) from exc
        except TimeoutError as exc:
            raise MCPTransportError(f"{self._transport} request timeout", error_code="timeout") from exc
        except OSError as exc:
            raise MCPTransportError(f"{self._transport} request failed: {exc}", error_code="network-error") from exc
        message = _parse_jsonrpc_response(body=body, content_type=content_type)
        if message.get("id") != request_id:
            raise MCPTransportError("http session returned mismatched response id", error_code="protocol-error")
        error = message.get("error")
        if isinstance(error, Mapping):
            detail = str(error.get("message") or "request failed").strip() or "request failed"
            raise MCPTransportError(detail, error_code="remote-error")
        result = message.get("result")
        if not isinstance(result, Mapping):
            raise MCPTransportError("http session returned invalid result payload", error_code="protocol-error")
        return dict(result)

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        try:
            self.request(method, params)
        except MCPTransportError:
            return

    def tools_list(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {})
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            return []
        return [dict(item) for item in raw_tools if isinstance(item, dict)]

    def tools_call(self, *, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "tools/call",
            {
                "name": str(name or "").strip(),
                "arguments": dict(arguments or {}),
            },
        )

    def prompts_list(self) -> list[dict[str, Any]]:
        result = self.request("prompts/list", {})
        raw_prompts = result.get("prompts")
        if not isinstance(raw_prompts, list):
            return []
        return [dict(item) for item in raw_prompts if isinstance(item, dict)]

    def prompts_get(self, *, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "prompts/get",
            {
                "name": str(name or "").strip(),
                "arguments": dict(arguments or {}),
            },
        )

    def resources_list(self) -> list[dict[str, Any]]:
        result = self.request("resources/list", {})
        raw_resources = result.get("resources")
        if not isinstance(raw_resources, list):
            return []
        return [dict(item) for item in raw_resources if isinstance(item, dict)]

    def resources_read(self, *, uri: str) -> dict[str, Any]:
        return self.request(
            "resources/read",
            {
                "uri": str(uri or "").strip(),
            },
        )

    @staticmethod
    def drain_notifications() -> list[dict[str, Any]]:
        return []


def try_initialize_http_like_session(
    *,
    url: str,
    headers: Mapping[str, str],
    timeout_sec: float,
    transport: str,
) -> tuple[HttpMcpSession | None, dict[str, Any], dict[str, Any], str]:
    session = HttpMcpSession(
        url=url,
        headers=headers,
        timeout_sec=timeout_sec,
        transport=transport,
    )
    try:
        initialize_result = session.request(
            "initialize",
            {
                "clientInfo": {"name": "agenthub_cli", "version": "0.1"},
                "protocolVersion": "2024-11-05",
                "capabilities": {},
            },
        )
        session.notify("initialized", {})
        return (
            session,
            _mapping(initialize_result.get("serverInfo")),
            _mapping(initialize_result.get("capabilities")),
            str(initialize_result.get("instructions") or "").strip(),
        )
    except MCPTransportError as exc:
        if exc.status_code is not None and is_auth_status_code(exc.status_code):
            raise
    except Exception:
        pass
    session.close()
    return None, {}, {}, ""


def probe_ws_connection(*, url: str, timeout_sec: float) -> None:
    parsed_url = _validated_ws_url(url)
    timeout = max(float(timeout_sec), 0.01)
    host = str(parsed_url.hostname or "").strip()
    port = int(parsed_url.port or (443 if parsed_url.scheme == "wss" else 80))
    try:
        raw_sock = socket.create_connection((host, port), timeout=timeout)
        if parsed_url.scheme == "wss":
            context = ssl.create_default_context()
            tls_sock = context.wrap_socket(raw_sock, server_hostname=host)
            tls_sock.close()
        else:
            raw_sock.close()
    except TimeoutError as exc:
        raise MCPTransportError("ws connect timeout", error_code="timeout") from exc
    except OSError as exc:
        raise MCPTransportError(f"ws connect failed: {exc}", error_code="network-error") from exc


def _validated_ws_url(url: str):
    normalized = str(url or "").strip()
    if not normalized:
        raise MCPTransportError("ws transport requires url", error_code="invalid-config")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"ws", "wss"}:
        raise MCPTransportError(f"unsupported url scheme: {parsed.scheme or '-'}", error_code="invalid-config")
    if not parsed.netloc:
        raise MCPTransportError("url must include host", error_code="invalid-config")
    return parsed


def _parse_jsonrpc_response(*, body: bytes, content_type: str) -> dict[str, Any]:
    if not body:
        raise MCPTransportError("http session returned empty response", error_code="protocol-error")
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        raise MCPTransportError("http session returned empty response", error_code="protocol-error")
    payload_text = text
    if "text/event-stream" in str(content_type or "").lower():
        for line in text.splitlines():
            candidate = str(line or "").strip()
            if not candidate.startswith("data:"):
                continue
            data_text = candidate[5:].strip()
            if data_text:
                payload_text = data_text
                break
    try:
        parsed = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise MCPTransportError(f"http session returned invalid json: {exc.msg}", error_code="protocol-error") from exc
    if not isinstance(parsed, Mapping):
        raise MCPTransportError("http session returned non-object message", error_code="protocol-error")
    return dict(parsed)


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): value for key, value in value.items()}
