from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Tuple

_CONNECTED_STATES = {"connected"}
_SERVER_COLLECTION_KEYS = ("servers", "connections", "server_states")
_TOOL_COLLECTION_KEYS = ("tools", "tool_descriptors")
_PROMPT_COLLECTION_KEYS = ("prompts", "prompt_descriptors")
_OBSERVABILITY_REASON_CODES = {
    "pending": "approval.pending",
    "approved": "approval.approved",
    "rejected": "approval.rejected",
    "timed_out": "approval.timed_out",
    "expired": "approval.expired",
}
_OBSERVABILITY_DECISION_TRACE_TEMPLATE = [
    "approval.requested",
    "approval.decided",
    "action.executed",
]
_OBSERVABILITY_TOOL_SNAPSHOT_FIELDS = [
    "projected_name",
    "server_name",
    "remote_name",
    "connector_key",
    "approval_scope",
]
_OBSERVABILITY_LATENCY_BUCKET_FIELD = "approval_latency_bucket"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unknown"


def _server_status(server_payload: Mapping[str, Any]) -> str:
    for key in ("status", "state", "connection_state"):
        value = _string(server_payload.get(key))
        if value:
            return value.lower()
    return ""


def _iter_servers(snapshot: Mapping[str, Any]) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    for key in _SERVER_COLLECTION_KEYS:
        raw = snapshot.get(key)
        if isinstance(raw, Mapping):
            for name, payload in raw.items():
                server_name = _string(name)
                if not server_name:
                    continue
                data = _as_mapping(payload)
                if "name" not in data:
                    data = dict(data)
                    data["name"] = server_name
                yield server_name, data
            return
        if isinstance(raw, list):
            for item in raw:
                data = _as_mapping(item)
                server_name = _string(data.get("name") or data.get("server_name"))
                if not server_name:
                    continue
                yield server_name, data
            return


def _iter_named_collection(server_payload: Mapping[str, Any], keys: Tuple[str, ...]) -> Iterable[Mapping[str, Any]]:
    for key in keys:
        raw = server_payload.get(key)
        if isinstance(raw, list):
            for item in raw:
                data = _as_mapping(item)
                if data:
                    yield data
            return
        if isinstance(raw, Mapping):
            for name, item in raw.items():
                data = _as_mapping(item)
                if "name" not in data:
                    data = dict(data)
                    data["name"] = _string(name)
                yield data
            return


def _is_connected(server_payload: Mapping[str, Any]) -> bool:
    status = _server_status(server_payload)
    return not status or status in _CONNECTED_STATES


def _tool_schema(tool_payload: Mapping[str, Any]) -> Dict[str, Any]:
    schema = tool_payload.get("input_schema")
    if not isinstance(schema, Mapping):
        schema = tool_payload.get("arguments_schema")
    if not isinstance(schema, Mapping):
        schema = tool_payload.get("parameters")
    if not isinstance(schema, Mapping):
        return {"type": "object", "properties": {}, "additionalProperties": True}
    return dict(schema)


def _observability_contract(*, projected_name: str, server_name: str, remote_name: str) -> Dict[str, Any]:
    approval_scope = f"mcp.server:{server_name}"
    connector_key = f"mcp:{server_name}"
    return {
        "schema_version": 1,
        "decision_trace_template": list(_OBSERVABILITY_DECISION_TRACE_TEMPLATE),
        "reason_codes": dict(_OBSERVABILITY_REASON_CODES),
        "latency_bucket_field": _OBSERVABILITY_LATENCY_BUCKET_FIELD,
        "tool_snapshot_fields": list(_OBSERVABILITY_TOOL_SNAPSHOT_FIELDS),
        "tool_snapshot": {
            "projected_name": projected_name,
            "server_name": server_name,
            "remote_name": remote_name,
            "connector_key": connector_key,
            "approval_scope": approval_scope,
        },
    }


def project_mcp_tool_descriptors(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    projected: List[Dict[str, Any]] = []
    for server_name, server_payload in _iter_servers(snapshot):
        if not _is_connected(server_payload):
            continue
        for tool_payload in _iter_named_collection(server_payload, _TOOL_COLLECTION_KEYS):
            tool_name = _string(tool_payload.get("name"))
            if not tool_name:
                continue
            projected_name = f"mcp__{_slug(server_name)}__{_slug(tool_name)}"
            projected.append(
                {
                    "name": projected_name,
                    "type": "mcp_tool",
                    "tool_family": "mcp_remote",
                    "source": "mcp",
                    "server_name": server_name,
                    "remote_name": tool_name,
                    "description": _string(tool_payload.get("description")) or f"MCP tool {tool_name} from {server_name}.",
                    "parameters": _tool_schema(tool_payload),
                    "requires_confirmation": True,
                    "mutates_ui": False,
                    "approval_required": True,
                    "approval_family": "mcp_tool_call",
                    "approval_scope": f"mcp.server:{server_name}",
                    "observability": _observability_contract(
                        projected_name=projected_name,
                        server_name=server_name,
                        remote_name=tool_name,
                    ),
                }
            )
    projected.sort(key=lambda item: item["name"])
    return projected


def project_mcp_prompt_descriptors(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    projected: List[Dict[str, Any]] = []
    for server_name, server_payload in _iter_servers(snapshot):
        if not _is_connected(server_payload):
            continue
        for prompt_payload in _iter_named_collection(server_payload, _PROMPT_COLLECTION_KEYS):
            prompt_name = _string(prompt_payload.get("name"))
            if not prompt_name:
                continue
            projected_name = f"mcp_prompt__{_slug(server_name)}__{_slug(prompt_name)}"
            projected.append(
                {
                    "name": projected_name,
                    "type": "mcp_prompt",
                    "server_name": server_name,
                    "remote_name": prompt_name,
                    "description": _string(prompt_payload.get("description"))
                    or f"Invoke MCP prompt {prompt_name} from {server_name}.",
                    "arguments_schema": _tool_schema(prompt_payload),
                }
            )
    projected.sort(key=lambda item: item["name"])
    return projected


def project_mcp_provider_tool_specs(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for descriptor in project_mcp_tool_descriptors(snapshot):
        specs.append(
            {
                "type": "function",
                "strict": True,
                "x_mcp_observability": dict(descriptor.get("observability") or {}),
                "function": {
                    "name": descriptor["name"],
                    "description": descriptor["description"],
                    "parameters": descriptor["parameters"],
                },
            }
        )
    return specs
