from __future__ import annotations

import shlex
from typing import Any, Callable

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.slash_surface import surface_usage_text

from .resource_projection import project_mcp_resource_tool_descriptors

ListResourcesFn = Callable[..., list[dict[str, Any]]]
ReadResourceFn = Callable[..., dict[str, Any]]


def resource_tool_specs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(item.get("name") or ""),
            "label": str(item.get("name") or ""),
            "description": str(item.get("description") or ""),
        }
        for item in project_mcp_resource_tool_descriptors(payload)
        if str(item.get("name") or "").strip()
    ]


def resource_command_specs(payload: dict[str, Any]) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for item in project_mcp_resource_tool_descriptors(payload):
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        usage = surface_usage_text(name, f"/{name}")
        specs.append(
            {
                "name": name,
                "usage": usage,
                "description": str(item.get("description") or ""),
            }
        )
    return specs


def execute_resource_command(
    *,
    name: str,
    arg_text: str,
    runtime: Any,
    list_resources_fn: ListResourcesFn,
    read_resource_fn: ReadResourceFn,
) -> tuple[str, list[ToolEvent]] | None:
    command_name = str(name or "").strip()
    if command_name == "list_mcp_resources":
        positionals, options = parse_command_args(runtime, arg_text)
        server_name = str(options.get("server-name") or options.get("server_name") or "").strip()
        if not server_name and positionals:
            server_name = str(positionals[0] or "").strip()
        resources = list_resources_fn(server_name=server_name or None)
        lines = ["mcp resources", f"count={len(resources)}"]
        for item in resources:
            lines.append(
                f"{item['server_name']} uri={item['uri']} mime_type={item.get('mime_type') or '-'}"
            )
        event = ToolEvent(
            name="list_mcp_resources",
            ok=True,
            summary=f"listed {len(resources)} mcp resources",
            payload={"server_name": server_name or None, "resources": resources},
        )
        return ("\n".join(lines), [event])
    if command_name == "read_mcp_resource":
        positionals, options = parse_command_args(runtime, arg_text)
        server_name = str(options.get("server-name") or options.get("server_name") or "").strip()
        uri = str(options.get("uri") or "").strip()
        if not server_name and positionals:
            server_name = str(positionals[0] or "").strip()
        if not uri and len(positionals) > 1:
            uri = str(positionals[1] or "").strip()
        payload = read_resource_fn(server_name=server_name, uri=uri)
        ok = bool(payload.get("ok"))
        text = str(payload.get("text") or "").strip()
        if not text:
            contents = payload.get("contents")
            if contents is not None:
                text = repr(contents)
        if not text:
            text = str(payload.get("error") or "").strip() or "mcp resource read"
        event = ToolEvent(
            name="read_mcp_resource",
            ok=ok,
            summary="read mcp resource" if ok else "mcp resource read failed",
            payload=dict(payload),
        )
        return (text, [event])
    return None


def parse_command_args(runtime: Any, arg_text: str) -> tuple[list[str], dict[str, Any]]:
    parse_args = getattr(runtime, "_parse_args", None)
    if callable(parse_args):
        return parse_args(arg_text)
    try:
        tokens = shlex.split(str(arg_text or ""))
    except ValueError:
        tokens = [item for item in str(arg_text or "").split() if item]
    return tokens, {}
