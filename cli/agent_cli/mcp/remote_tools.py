from __future__ import annotations

from typing import Any, Callable

from .models import McpToolDescriptor

MappingFn = Callable[[Any], dict[str, Any]]


def remote_tool_descriptors(
    *,
    server_name: str,
    session: Any,
    mapping_fn: MappingFn,
) -> list[McpToolDescriptor]:
    tools_list = getattr(session, "tools_list", None)
    if not callable(tools_list):
        return []
    try:
        raw_tools = tools_list()
    except Exception:
        return []
    return remote_tool_descriptors_from_entries(
        server_name=server_name,
        raw_tools=raw_tools if isinstance(raw_tools, list) else [],
        mapping_fn=mapping_fn,
    )


def remote_tool_descriptors_from_entries(
    *,
    server_name: str,
    raw_tools: list[dict[str, Any]],
    mapping_fn: MappingFn,
) -> list[McpToolDescriptor]:
    tools: list[McpToolDescriptor] = []
    for entry in raw_tools:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        schema = entry.get("inputSchema")
        if not isinstance(schema, dict):
            schema = entry.get("input_schema")
        tools.append(
            McpToolDescriptor(
                server_name=server_name,
                name=name,
                title=str(entry.get("title") or "").strip(),
                description=str(entry.get("description") or "").strip(),
                input_schema=dict(schema or {}),
                metadata=mapping_fn(entry.get("metadata")),
            )
        )
    return tools
