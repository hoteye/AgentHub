from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from cli.agent_cli.mcp.tool_projection import _as_mapping, _is_connected, _iter_servers, _string

_RESOURCE_COLLECTION_KEYS = ("resources", "resource_descriptors")


def _iter_resources(server_payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for key in _RESOURCE_COLLECTION_KEYS:
        raw = server_payload.get(key)
        if isinstance(raw, list):
            for item in raw:
                data = _as_mapping(item)
                if data:
                    yield data
            return
        if isinstance(raw, Mapping):
            for uri, item in raw.items():
                data = _as_mapping(item)
                if "uri" not in data:
                    data = dict(data)
                    data["uri"] = _string(uri)
                yield data
            return


def list_projected_mcp_resources(snapshot: Mapping[str, Any], *, server_name: str | None = None) -> List[Dict[str, Any]]:
    selected_server = _string(server_name)
    items: List[Dict[str, Any]] = []
    for current_server_name, server_payload in _iter_servers(snapshot):
        if not _is_connected(server_payload):
            continue
        if selected_server and current_server_name != selected_server:
            continue
        for resource_payload in _iter_resources(server_payload):
            uri = _string(resource_payload.get("uri"))
            if not uri:
                continue
            items.append(
                {
                    "server_name": current_server_name,
                    "uri": uri,
                    "name": _string(resource_payload.get("name")),
                    "description": _string(resource_payload.get("description")),
                    "mime_type": _string(resource_payload.get("mime_type") or resource_payload.get("mimeType")),
                }
            )
    items.sort(key=lambda item: (item["server_name"], item["uri"]))
    return items


def read_projected_mcp_resource(snapshot: Mapping[str, Any], *, server_name: str, uri: str) -> Dict[str, Any]:
    target_server = _string(server_name)
    target_uri = _string(uri)
    if not target_server or not target_uri:
        return {"ok": False, "error": "server_name and uri are required"}

    for current_server_name, server_payload in _iter_servers(snapshot):
        if current_server_name != target_server or not _is_connected(server_payload):
            continue
        for resource_payload in _iter_resources(server_payload):
            if _string(resource_payload.get("uri")) != target_uri:
                continue
            return {
                "ok": True,
                "server_name": current_server_name,
                "uri": target_uri,
                "name": _string(resource_payload.get("name")),
                "mime_type": _string(resource_payload.get("mime_type") or resource_payload.get("mimeType")),
                "description": _string(resource_payload.get("description")),
                "contents": resource_payload.get("contents"),
                "text": resource_payload.get("text"),
                "blob": resource_payload.get("blob"),
            }

    return {"ok": False, "error": "resource not found", "server_name": target_server, "uri": target_uri}


def project_mcp_resource_tool_descriptors(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    servers = sorted({item["server_name"] for item in list_projected_mcp_resources(snapshot)})
    return [
        {
            "name": "list_mcp_resources",
            "type": "mcp_resource_tool",
            "description": "List MCP resources available from connected servers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Optional server name filter."},
                },
                "additionalProperties": False,
            },
            "connected_servers": servers,
        },
        {
            "name": "read_mcp_resource",
            "type": "mcp_resource_tool",
            "description": "Read one MCP resource by server and URI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_name": {"type": "string"},
                    "uri": {"type": "string"},
                },
                "required": ["server_name", "uri"],
                "additionalProperties": False,
            },
            "connected_servers": servers,
        },
    ]


def project_mcp_resource_provider_specs(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "strict": True,
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["parameters"],
            },
        }
        for item in project_mcp_resource_tool_descriptors(snapshot)
    ]
