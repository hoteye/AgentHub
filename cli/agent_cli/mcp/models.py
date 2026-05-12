from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from .state import (
    McpConfigScope,
    McpConfigState,
    McpConnectionState,
    McpProjectionState,
    McpTransportKind,
    coerce_dict,
    coerce_int,
    coerce_str_list,
    coerce_text,
    parse_enum,
)


SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class McpServerConfig:
    server_name: str
    transport: McpTransportKind = McpTransportKind.STDIO
    url: str = ""
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    timeout_seconds: int = 30
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "transport": self.transport.value,
            "url": self.url,
            "command": self.command,
            "args": list(self.args),
            "env": {str(k): str(v) for k, v in dict(self.env).items()},
            "headers": {str(k): str(v) for k, v in dict(self.headers).items()},
            "cwd": self.cwd,
            "timeout_seconds": int(self.timeout_seconds),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "McpServerConfig":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            server_name=coerce_text(data.get("server_name")),
            transport=parse_enum(
                McpTransportKind,
                data.get("transport") or McpTransportKind.STDIO.value,
                field_name="mcp_server_config.transport",
            ),
            url=coerce_text(data.get("url")),
            command=coerce_text(data.get("command")),
            args=coerce_str_list(data.get("args")),
            env={str(k): str(v) for k, v in coerce_dict(data.get("env")).items()},
            headers={str(k): str(v) for k, v in coerce_dict(data.get("headers")).items()},
            cwd=coerce_text(data.get("cwd")),
            timeout_seconds=coerce_int(data.get("timeout_seconds"), default=30, minimum=1),
            metadata=coerce_dict(data.get("metadata")),
        )


@dataclass(slots=True)
class ScopedMcpServerConfig:
    config: McpServerConfig
    scope: McpConfigScope = McpConfigScope.USER
    config_state: McpConfigState = McpConfigState.ENABLED
    source: str = ""
    priority: int = 0
    disabled_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "scope": self.scope.value,
            "config_state": self.config_state.value,
            "source": self.source,
            "priority": int(self.priority),
            "disabled_reason": self.disabled_reason,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "ScopedMcpServerConfig":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            config=McpServerConfig.from_dict(coerce_dict(data.get("config"))),
            scope=parse_enum(
                McpConfigScope,
                data.get("scope") or McpConfigScope.USER.value,
                field_name="scoped_mcp_server_config.scope",
            ),
            config_state=parse_enum(
                McpConfigState,
                data.get("config_state") or McpConfigState.ENABLED.value,
                field_name="scoped_mcp_server_config.config_state",
            ),
            source=coerce_text(data.get("source")),
            priority=coerce_int(data.get("priority"), default=0),
            disabled_reason=coerce_text(data.get("disabled_reason")),
        )


@dataclass(slots=True)
class McpResourceDescriptor:
    server_name: str
    uri: str
    name: str = ""
    title: str = ""
    description: str = ""
    mime_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "uri": self.uri,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "mime_type": self.mime_type,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "McpResourceDescriptor":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            server_name=coerce_text(data.get("server_name")),
            uri=coerce_text(data.get("uri")),
            name=coerce_text(data.get("name")),
            title=coerce_text(data.get("title")),
            description=coerce_text(data.get("description")),
            mime_type=coerce_text(data.get("mime_type")),
            metadata=coerce_dict(data.get("metadata")),
        )


@dataclass(slots=True)
class McpPromptDescriptor:
    server_name: str
    name: str
    title: str = ""
    description: str = ""
    arguments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "arguments": [dict(item) for item in self.arguments if isinstance(item, dict)],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "McpPromptDescriptor":
        data = payload if isinstance(payload, dict) else {}
        raw_arguments = data.get("arguments")
        arguments: List[Dict[str, Any]] = []
        if isinstance(raw_arguments, list):
            for item in raw_arguments:
                if isinstance(item, dict):
                    arguments.append(dict(item))
        return cls(
            server_name=coerce_text(data.get("server_name")),
            name=coerce_text(data.get("name")),
            title=coerce_text(data.get("title")),
            description=coerce_text(data.get("description")),
            arguments=arguments,
            metadata=coerce_dict(data.get("metadata")),
        )


@dataclass(slots=True)
class McpToolDescriptor:
    server_name: str
    name: str
    title: str = ""
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "McpToolDescriptor":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            server_name=coerce_text(data.get("server_name")),
            name=coerce_text(data.get("name")),
            title=coerce_text(data.get("title")),
            description=coerce_text(data.get("description")),
            input_schema=coerce_dict(data.get("input_schema")),
            metadata=coerce_dict(data.get("metadata")),
        )


@dataclass(slots=True)
class McpRuntimeSnapshot:
    servers: List[ScopedMcpServerConfig] = field(default_factory=list)
    connection_states: Dict[str, McpConnectionState] = field(default_factory=dict)
    tools: List[McpToolDescriptor] = field(default_factory=list)
    prompts: List[McpPromptDescriptor] = field(default_factory=list)
    resources: List[McpResourceDescriptor] = field(default_factory=list)
    projection_state: McpProjectionState = McpProjectionState.EMPTY
    generated_at: str = field(default_factory=utc_now_iso)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "servers": [item.to_dict() for item in self.servers],
            "connection_states": {name: state.value for name, state in sorted(self.connection_states.items())},
            "tools": [item.to_dict() for item in self.tools],
            "prompts": [item.to_dict() for item in self.prompts],
            "resources": [item.to_dict() for item in self.resources],
            "projection_state": self.projection_state.value,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "McpRuntimeSnapshot":
        data = payload if isinstance(payload, dict) else {}
        raw_states = data.get("connection_states")
        connection_states: Dict[str, McpConnectionState] = {}
        if isinstance(raw_states, dict):
            for name, raw_state in raw_states.items():
                server_name = str(name)
                if not server_name.strip():
                    continue
                connection_states[server_name] = parse_enum(
                    McpConnectionState,
                    raw_state,
                    field_name=f"mcp_runtime_snapshot.connection_states[{server_name}]",
                )
        return cls(
            servers=[
                ScopedMcpServerConfig.from_dict(item)
                for item in data.get("servers", [])
                if isinstance(item, dict)
            ],
            connection_states=connection_states,
            tools=[
                McpToolDescriptor.from_dict(item)
                for item in data.get("tools", [])
                if isinstance(item, dict)
            ],
            prompts=[
                McpPromptDescriptor.from_dict(item)
                for item in data.get("prompts", [])
                if isinstance(item, dict)
            ],
            resources=[
                McpResourceDescriptor.from_dict(item)
                for item in data.get("resources", [])
                if isinstance(item, dict)
            ],
            projection_state=parse_enum(
                McpProjectionState,
                data.get("projection_state") or McpProjectionState.EMPTY.value,
                field_name="mcp_runtime_snapshot.projection_state",
            ),
            generated_at=coerce_text(data.get("generated_at"), default=utc_now_iso()),
            schema_version=coerce_int(data.get("schema_version"), default=SCHEMA_VERSION, minimum=1),
        )


# Compatibility alias: runtime helpers still import the older symbol name.
RuntimeServerConfig = McpServerConfig
