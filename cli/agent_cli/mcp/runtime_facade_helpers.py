from __future__ import annotations

import shlex
from typing import Any, Mapping, Sequence

from .auth import auth_config_from_server_config
from .client import MCPClient, MCPConnectionResult, MCPServerConfig
from .models import (
    McpPromptDescriptor,
    McpResourceDescriptor,
    McpRuntimeSnapshot,
    McpServerConfig,
    McpToolDescriptor,
    ScopedMcpServerConfig,
)
from .remote_descriptors import prompt_descriptors, resource_descriptors
from .remote_tools import remote_tool_descriptors_from_entries
from .runtime_support import ResolvedMcpServer
from .state import (
    McpConfigScope,
    McpConfigState,
    McpConnectionState,
    McpProjectionState,
    McpTransportKind,
)
from .transports import MCPTransportConfig

_SCOPE_BY_SOURCE = {
    "user": McpConfigScope.USER,
    "workspace": McpConfigScope.WORKSPACE,
    "plugin": McpConfigScope.PLUGIN,
    "runtime_dynamic": McpConfigScope.RUNTIME,
}
_CONNECTION_STATE_BY_STATUS = {
    "connected": McpConnectionState.CONNECTED,
    "needs-auth": McpConnectionState.NEEDS_AUTH,
    "failed": McpConnectionState.FAILED,
    "disabled": McpConnectionState.DISABLED,
    "pending": McpConnectionState.PENDING,
}


def transport_name(config: Mapping[str, Any]) -> str:
    raw = str(config.get("transport") or config.get("type") or "stdio").strip().lower()
    if raw in {"http", "sse", "stdio", "ws"}:
        return raw
    if raw in {"sdk", "inprocess"}:
        return "stdio"
    return "stdio"


def list_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def command_parts(config: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    raw_command = config.get("command")
    raw_args = config.get("args")
    base_args = list_values(raw_args)
    if isinstance(raw_command, Sequence) and not isinstance(raw_command, (str, bytes)):
        parts = tuple(str(item).strip() for item in raw_command if str(item).strip())
        return parts[:1], parts[1:] + base_args
    if isinstance(raw_command, str):
        parts = tuple(item for item in shlex.split(raw_command) if item)
        return parts[:1], parts[1:] + base_args
    return (), base_args


def mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): value for key, value in value.items()}


def build_tool_descriptors(
    client: MCPClient,
    item: ResolvedMcpServer,
    result: MCPConnectionResult | None = None,
) -> list[McpToolDescriptor]:
    session = getattr(getattr(result, "handle", None), "session", None)
    remote_tools = client.remote_tools(name=item.name, session=session)
    remote_descriptors = remote_tool_descriptors_from_entries(
        server_name=item.name,
        raw_tools=remote_tools,
        mapping_fn=mapping,
    )
    if remote_descriptors:
        return remote_descriptors

    tools: list[McpToolDescriptor] = []
    raw = item.config.get("tools") or item.config.get("tool_descriptors") or []
    if isinstance(raw, Mapping):
        raw = [{**(value if isinstance(value, dict) else {}), "name": name} for name, value in raw.items()]
    if not (isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))):
        return tools

    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        schema = entry.get("input_schema")
        if not isinstance(schema, Mapping):
            schema = entry.get("parameters")
        tools.append(
            McpToolDescriptor(
                server_name=item.name,
                name=name,
                title=str(entry.get("title") or "").strip(),
                description=str(entry.get("description") or "").strip(),
                input_schema=dict(schema or {}),
                metadata=mapping(entry.get("metadata")),
            )
        )
    return tools


def build_prompt_descriptors(
    client: MCPClient,
    item: ResolvedMcpServer,
    result: MCPConnectionResult | None = None,
) -> list[McpPromptDescriptor]:
    session = getattr(getattr(result, "handle", None), "session", None)
    remote_entries = client.remote_prompts(name=item.name, session=session)
    return prompt_descriptors(
        server_name=item.name,
        config=item.config,
        session=session,
        remote_entries=remote_entries,
        mapping_fn=mapping,
    )


def build_resource_descriptors(
    client: MCPClient,
    item: ResolvedMcpServer,
    result: MCPConnectionResult | None = None,
) -> list[McpResourceDescriptor]:
    session = getattr(getattr(result, "handle", None), "session", None)
    remote_entries = client.remote_resources(name=item.name, session=session)
    return resource_descriptors(
        server_name=item.name,
        config=item.config,
        session=session,
        remote_entries=remote_entries,
        mapping_fn=mapping,
    )


def scoped_config_from_resolved_server(item: ResolvedMcpServer) -> ScopedMcpServerConfig:
    config = item.config
    transport_kind = McpTransportKind(transport_name(config))
    command, args = command_parts(config)
    return ScopedMcpServerConfig(
        config=McpServerConfig(
            server_name=item.name,
            transport=transport_kind,
            url=str(config.get("url") or "").strip(),
            command=command[0] if command else "",
            args=list(args),
            env={str(key): str(value) for key, value in mapping(config.get("env")).items()},
            headers={str(key): str(value) for key, value in mapping(config.get("headers")).items()},
            cwd=str(config.get("cwd") or "").strip(),
            timeout_seconds=int(config.get("timeout_sec") or config.get("timeout_seconds") or 5),
            metadata=dict(item.metadata),
        ),
        scope=_SCOPE_BY_SOURCE.get(item.source, McpConfigScope.PLUGIN),
        config_state=McpConfigState.ENABLED if item.enabled else McpConfigState.DISABLED,
        source=item.source,
        priority=item.precedence,
        disabled_reason="" if item.enabled else "disabled by operator state",
    )


def build_snapshot(
    resolved: list[ResolvedMcpServer],
    connection_results: Mapping[str, MCPConnectionResult],
    client: MCPClient,
) -> McpRuntimeSnapshot:
    servers: list[ScopedMcpServerConfig] = []
    tools: list[McpToolDescriptor] = []
    prompts: list[McpPromptDescriptor] = []
    resources: list[McpResourceDescriptor] = []
    connection_states: dict[str, McpConnectionState] = {}

    for item in resolved:
        servers.append(scoped_config_from_resolved_server(item))
        connection = connection_results.get(item.name)
        status = str(getattr(connection, "status", "failed") or "failed")
        connection_states[item.name] = _CONNECTION_STATE_BY_STATUS.get(status, McpConnectionState.FAILED)
        tools.extend(build_tool_descriptors(client, item, connection))
        prompts.extend(build_prompt_descriptors(client, item, connection))
        resources.extend(build_resource_descriptors(client, item, connection))

    projection_state = McpProjectionState.EMPTY
    if tools or prompts or resources:
        projection_state = McpProjectionState.READY if servers else McpProjectionState.EMPTY
    elif servers:
        projection_state = McpProjectionState.PARTIAL

    return McpRuntimeSnapshot(
        servers=servers,
        connection_states=connection_states,
        tools=tools,
        prompts=prompts,
        resources=resources,
        projection_state=projection_state,
    )


def build_server_entries(
    resolved: list[ResolvedMcpServer],
    connection_results: Mapping[str, MCPConnectionResult],
    snapshot: McpRuntimeSnapshot,
    client: MCPClient,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in resolved:
        connection = connection_results.get(item.name)
        status = str(getattr(connection, "status", "failed") or "failed")
        entry_config = dict(item.config)
        payload: dict[str, Any] = dict(entry_config)
        tool_payloads = [descriptor.to_dict() for descriptor in build_tool_descriptors(client, item, connection)]
        prompt_payloads = [descriptor.to_dict() for descriptor in build_prompt_descriptors(client, item, connection)]
        resource_payloads = [descriptor.to_dict() for descriptor in build_resource_descriptors(client, item, connection)]
        payload.update(
            {
                "name": item.name,
                "status": status,
                "enabled": bool(item.enabled),
                "scope": item.source,
                "source": item.source,
                "transport": transport_name(item.config),
                "error": str(getattr(connection, "error", "") or ""),
                "error_code": str(getattr(connection, "error_code", "") or ""),
                "retry_attempt": int(getattr(connection, "retry_attempt", 0) or 0),
                "retry_in_sec": float(getattr(connection, "retry_in_sec", 0.0) or 0.0),
                "projection_state": snapshot.projection_state.value,
                "config": entry_config,
                "server_info": dict(getattr(getattr(connection, "handle", None), "server_info", {}) or {}),
                "capabilities": dict(getattr(getattr(connection, "handle", None), "capabilities", {}) or {}),
                "instructions": str(getattr(getattr(connection, "handle", None), "instructions", "") or ""),
                "tools": tool_payloads,
                "prompts": prompt_payloads,
                "resources": resource_payloads,
            }
        )
        if not payload["enabled"]:
            payload["status"] = "disabled"
        entries.append(payload)
    entries.sort(key=lambda entry: str(entry.get("name") or ""))
    return entries


def payload_from_entries(entries: list[dict[str, Any]], snapshot: McpRuntimeSnapshot) -> dict[str, Any]:
    servers = {str(item.get("name") or ""): dict(item) for item in entries if str(item.get("name") or "").strip()}
    return {
        "projection_state": snapshot.projection_state.value,
        "connections": {name: state.value for name, state in snapshot.connection_states.items()},
        "servers": servers,
    }


def client_config_from_resolved_server(item: ResolvedMcpServer) -> MCPServerConfig:
    config = item.config
    command, args = command_parts(config)
    return MCPServerConfig(
        name=item.name,
        transport=MCPTransportConfig(
            transport=transport_name(config),
            timeout_sec=float(config.get("timeout_sec") or config.get("timeout_seconds") or 5.0),
            command=command,
            args=args,
            env={str(key): str(value) for key, value in mapping(config.get("env")).items()},
            url=str(config.get("url") or "").strip(),
            headers={str(key): str(value) for key, value in mapping(config.get("headers")).items()},
            auth=auth_config_from_server_config(config),
            enabled=bool(item.enabled),
        ),
        enabled=bool(item.enabled),
        metadata={str(key): str(value) for key, value in item.metadata.items()},
    )
