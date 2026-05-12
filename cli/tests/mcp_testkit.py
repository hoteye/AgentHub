from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from cli.agent_cli.mcp.client import MCPConnectionResult, MCPServerConfig
from cli.agent_cli.mcp.tool_projection import project_mcp_tool_descriptors
from cli.agent_cli.mcp.transports import MCPTransportConfig


def fake_mcp_sources() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "runtime_dynamic": {
            "atlas": {
                "transport": "stdio",
                "command": [sys.executable],
                "args": ["-c", "print('atlas-ready')"],
                "timeout_sec": 2.0,
            }
        },
        "user": {
            "atlas": {
                "transport": "stdio",
                "command": [sys.executable],
                "args": ["-c", "print('atlas-user')"],
                "timeout_sec": 2.0,
            }
        },
        "workspace": {
            "ops": {
                "transport": "stdio",
                "command": [sys.executable],
                "args": ["-c", "print('ops-ready')"],
                "timeout_sec": 2.0,
            }
        },
        "plugin": {
            "legacy": {
                "transport": "stdio",
                "command": [sys.executable],
                "args": ["-c", "print('legacy-ready')"],
                "timeout_sec": 2.0,
            }
        },
    }


def inline_stdio_mcp_transport_config(*, timeout_sec: float = 5.0) -> MCPTransportConfig:
    repo_root = Path(__file__).resolve().parents[2]
    pythonpath_parts = [str(repo_root)]
    existing_pythonpath = str(os.environ.get("PYTHONPATH") or "").strip()
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    script = """
import sys
from cli.agent_cli.mcp.serve import main
from cli.agent_cli.models import CommandExecutionResult, ToolEvent

class _Tools:
    def list_dir_result(self, *, dir_path=None, offset=1, limit=25, depth=2):
        return CommandExecutionResult(
            assistant_text=f"listed path={dir_path or '.'}",
            tool_events=[ToolEvent(name="list_dir", ok=True, summary="list_dir ok", payload={"dir_path": dir_path})],
        )

    def file_read_result(self, path, *, offset=None, limit=None, max_chars=None):
        return CommandExecutionResult(
            assistant_text=f"read path={path}",
            tool_events=[ToolEvent(name="file_read", ok=True, summary="file_read ok", payload={"path": path})],
        )

class _Runtime:
    def __init__(self):
        self.tools = _Tools()

raise SystemExit(main(["serve"], runtime=_Runtime()))
""".strip()
    return MCPTransportConfig(
        transport="stdio",
        command=(sys.executable,),
        args=("-c", script),
        env={
            "PYTHONPATH": os.pathsep.join(pythonpath_parts),
            "PYTHONUNBUFFERED": "1",
        },
        timeout_sec=timeout_sec,
    )


def build_client_configs(effective: dict[str, dict[str, Any]]) -> dict[str, MCPServerConfig]:
    configs: dict[str, MCPServerConfig] = {}
    for server_name, config in sorted(effective.items()):
        transport_name = str(config.get("transport") or config.get("type") or "stdio").strip().lower()
        command = _as_text_tuple(config.get("command"))
        args = _as_text_tuple(config.get("args"))
        transport = MCPTransportConfig(
            transport=transport_name if transport_name in {"stdio", "http", "sse", "ws"} else "stdio",
            timeout_sec=float(config.get("timeout_sec") or config.get("timeout_seconds") or 2.0),
            command=command,
            args=args,
            url=str(config.get("url") or "").strip(),
            headers=_as_str_dict(config.get("headers")),
            enabled=bool(config.get("enabled", True)),
        )
        configs[server_name] = MCPServerConfig(
            name=server_name,
            transport=transport,
            enabled=bool(config.get("enabled", True)),
        )
    return configs


def build_fake_snapshot(connection_results: dict[str, MCPConnectionResult]) -> dict[str, Any]:
    servers: dict[str, dict[str, Any]] = {}
    for server_name, result in sorted(connection_results.items()):
        server_tools = []
        server_resources = []
        if result.status == "connected":
            if server_name == "atlas":
                server_tools.append(
                    {
                        "name": "search_docs",
                        "description": "Search atlas docs.",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                            "additionalProperties": False,
                        },
                    }
                )
                server_resources.append(
                    {
                        "uri": "file:///atlas/readme.md",
                        "name": "Atlas README",
                        "mime_type": "text/markdown",
                        "text": "# Atlas",
                    }
                )
            elif server_name == "ops":
                server_tools.append(
                    {
                        "name": "danger_delete_all",
                        "description": "Unsafe destructive op.",
                        "input_schema": {
                            "type": "object",
                            "properties": {"confirm": {"type": "boolean"}},
                            "required": ["confirm"],
                            "additionalProperties": False,
                        },
                    }
                )
        servers[server_name] = {
            "name": server_name,
            "status": result.status,
            "enabled": result.status != "disabled",
            "tools": server_tools,
            "resources": server_resources,
        }
    return {"servers": servers}


def invoke_projected_tool(snapshot: dict[str, Any], *, projected_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    for descriptor in project_mcp_tool_descriptors(snapshot):
        if descriptor["name"] != projected_name:
            continue
        remote_name = str(descriptor.get("remote_name") or "")
        if remote_name == "search_docs":
            return {
                "ok": True,
                "server_name": descriptor["server_name"],
                "remote_name": remote_name,
                "items": [f"match:{str(arguments.get('query') or '').strip()}"],
            }
        if remote_name == "danger_delete_all":
            return {"ok": False, "error": "policy-blocked"}
        return {"ok": True, "server_name": descriptor["server_name"], "remote_name": remote_name}
    raise ValueError(f"unknown projected tool: {projected_name}")


class FakeMcpRuntime:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self._snapshot = snapshot
        self._disabled: set[str] = set()

    def get_mcp_runtime(self) -> "FakeMcpRuntime":
        return self

    def list_status(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for server_name, payload in sorted((self._snapshot.get("servers") or {}).items()):
            row = dict(payload) if isinstance(payload, dict) else {}
            row["name"] = server_name
            if server_name in self._disabled:
                row["enabled"] = False
                row["status"] = "disabled"
            rows.append(row)
        return {"servers": rows}

    def inspect(self, target: str) -> dict[str, Any]:
        payload = dict((self._snapshot.get("servers") or {}).get(target) or {})
        if not payload:
            raise ValueError(f"unknown mcp server: {target}")
        if target in self._disabled:
            payload["status"] = "disabled"
            payload["enabled"] = False
        payload.setdefault("enabled", True)
        payload.setdefault("scope", "runtime")
        return payload

    def reconnect(self, target: str) -> dict[str, Any]:
        return {"status": "ok", "target": target}

    def enable(self, target: str) -> dict[str, Any]:
        self._disabled.discard(target)
        return {"status": "ok", "target": target}

    def disable(self, target: str) -> dict[str, Any]:
        self._disabled.add(target)
        return {"status": "ok", "target": target}


def run_fake_serve_roundtrip(
    snapshot: dict[str, Any],
    *,
    deny_projected_tools: Iterable[str] = (),
    call_arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    denied = {str(item) for item in deny_projected_tools}
    projected = [
        item
        for item in project_mcp_tool_descriptors(snapshot)
        if str(item.get("name") or "") and str(item.get("name") or "") not in denied
    ]
    tool_by_name = {str(item["name"]): dict(item) for item in projected}

    def _request(message_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == "initialize":
            return {
                "id": message_id,
                "result": {
                    "serverInfo": {"name": "agenthub_fake_mcp", "version": "0-test"},
                    "capabilities": {"tools": True},
                },
            }
        if method == "tools/list":
            return {
                "id": message_id,
                "result": {
                    "tools": [
                        {
                            "name": item["name"],
                            "description": item["description"],
                            "inputSchema": item["parameters"],
                        }
                        for item in projected
                    ]
                },
            }
        if method == "tools/call":
            tool_name = str((params or {}).get("name") or "")
            arguments = dict((params or {}).get("arguments") or {})
            if tool_name not in tool_by_name:
                return {"id": message_id, "error": {"code": -32602, "message": "unknown tool"}}
            output = invoke_projected_tool(snapshot, projected_name=tool_name, arguments=arguments)
            return {
                "id": message_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=True, sort_keys=True)}],
                    "structuredContent": output,
                    "isError": not bool(output.get("ok", True)),
                },
            }
        return {"id": message_id, "error": {"code": -32601, "message": "method not found"}}

    init_result = _request("init-1", "initialize", {"clientInfo": {"name": "test"}})
    tools_list_result = _request("tools-1", "tools/list", {})
    listed_tools = list((tools_list_result.get("result") or {}).get("tools") or [])
    chosen_tool = str(listed_tools[0].get("name") if listed_tools else "")
    tools_call_result = _request(
        "call-1",
        "tools/call",
        {"name": chosen_tool, "arguments": dict(call_arguments or {"query": "health"})},
    )
    return {"initialize": init_result, "tools_list": tools_list_result, "tools_call": tools_call_result}


def _as_text_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item or "").strip())
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


def _as_str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}
