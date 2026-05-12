from __future__ import annotations

import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

from .auth import MCPAuthConfig, merge_auth_headers
from .transports_helpers import (
    MCPTransportError,
    StdioMcpSession,
    _build_stdio_command,
    _connect_stdio_session,
    _closed_process_detail,
    _mapping,
    _merged_env,
    _validated_http_url,
)

from .http_ws_runtime import probe_ws_connection, try_initialize_http_like_session

MCPTransportName = Literal["stdio", "http", "sse", "ws"]


@dataclass(frozen=True)
class MCPTransportConfig:
    transport: MCPTransportName
    timeout_sec: float = 5.0
    command: tuple[str, ...] = ()
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    auth: MCPAuthConfig | None = None
    enabled: bool = True


@dataclass(frozen=True)
class MCPTransportConnection:
    transport: MCPTransportName
    endpoint: str
    session: Any | None = None
    server_info: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    instructions: str = ""

    def close(self) -> None:
        if self.session is None:
            return
        self.session.close()


def connect_transport(config: MCPTransportConfig) -> MCPTransportConnection:
    if config.transport == "stdio":
        return _connect_stdio(config)
    if config.transport == "http":
        return _connect_http_like(config, expected_content_type=None)
    if config.transport == "sse":
        return _connect_http_like(config, expected_content_type="text/event-stream")
    if config.transport == "ws":
        return _connect_ws_like(config)
    raise MCPTransportError(f"unsupported transport: {config.transport}", error_code="unsupported-transport")


def _connect_stdio(config: MCPTransportConfig) -> MCPTransportConnection:
    command = _build_stdio_command(config.command, config.args)
    if not command:
        raise MCPTransportError("stdio transport requires command", error_code="invalid-config")
    merged_env = _merged_env(config.env)
    endpoint = " ".join(command)
    session_error: MCPTransportError | None = None
    session: StdioMcpSession | None = None
    try:
        session = _connect_stdio_session(command, merged_env, timeout_sec=config.timeout_sec)
        initialize_result = session.request(
            "initialize",
            {
                "clientInfo": {"name": "agenthub_cli", "version": "0.1"},
                "protocolVersion": "2024-11-05",
                "capabilities": {},
            },
        )
        session.notify("initialized", {})
        return MCPTransportConnection(
            transport="stdio",
            endpoint=endpoint,
            session=session,
            server_info=_mapping(initialize_result.get("serverInfo")),
            capabilities=_mapping(initialize_result.get("capabilities")),
            instructions=str(initialize_result.get("instructions") or "").strip(),
        )
    except MCPTransportError as exc:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        session_error = exc
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(float(config.timeout_sec), 0.01),
            env=merged_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise MCPTransportError("stdio connect timeout", error_code="timeout") from exc
    except OSError as exc:
        raise MCPTransportError(f"stdio process start failed: {exc}", error_code="start-failed") from exc
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        detail = stderr or f"exit code {completed.returncode}"
        raise MCPTransportError(f"stdio process failed: {detail}", error_code="process-failed")
    if session_error is not None and session_error.error_code not in {"protocol-error", "closed", "remote-error"}:
        raise session_error
    return MCPTransportConnection(transport="stdio", endpoint=endpoint)


def _connect_http_like(config: MCPTransportConfig, *, expected_content_type: str | None) -> MCPTransportConnection:
    _validated_http_url(config)
    headers = merge_auth_headers(base_headers=config.headers, auth=config.auth)
    headers = _resolved_headers(headers)
    request = urllib.request.Request(config.url, headers=headers, method="GET")
    timeout = max(float(config.timeout_sec), 0.01)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            if status >= 400:
                raise MCPTransportError(f"http status {status}", error_code="http-status", status_code=status)
            if expected_content_type:
                content_type = str(response.headers.get("Content-Type") or "")
                if expected_content_type not in content_type:
                    raise MCPTransportError(
                        f"unexpected content type: {content_type or '-'}",
                        error_code="invalid-content-type",
                    )
            try:
                response.read(1)
            except Exception:
                # Reading payload is best-effort and does not block handshake success.
                pass
    except urllib.error.HTTPError as exc:
        raise MCPTransportError(
            f"http status {exc.code}",
            error_code="http-status",
            status_code=int(exc.code),
        ) from exc
    except TimeoutError as exc:
        raise MCPTransportError(f"{config.transport} connect timeout", error_code="timeout") from exc
    except OSError as exc:
        raise MCPTransportError(f"{config.transport} connect failed: {exc}", error_code="network-error") from exc

    session, server_info, capabilities, instructions = try_initialize_http_like_session(
        url=config.url,
        headers=headers,
        timeout_sec=config.timeout_sec,
        transport=config.transport,
    )
    return MCPTransportConnection(
        transport=config.transport,
        endpoint=config.url,
        session=session,
        server_info=server_info,
        capabilities=capabilities,
        instructions=instructions,
    )


def _resolved_headers(headers: Mapping[str, Any]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, value in dict(headers or {}).items():
        header_name = str(key)
        raw_value = str(value)
        if raw_value.startswith("$env:"):
            env_key = raw_value[5:].strip()
            if not env_key:
                raise MCPTransportError("invalid env header reference", error_code="invalid-config")
            env_value = os.environ.get(env_key)
            if env_value is None:
                raise MCPTransportError(
                    f"missing environment variable for header: {env_key}",
                    error_code="invalid-config",
                )
            resolved[header_name] = str(env_value)
            continue
        resolved[header_name] = raw_value
    return resolved


def _connect_ws_like(config: MCPTransportConfig) -> MCPTransportConnection:
    probe_ws_connection(url=config.url, timeout_sec=config.timeout_sec)
    return MCPTransportConnection(transport="ws", endpoint=config.url)
