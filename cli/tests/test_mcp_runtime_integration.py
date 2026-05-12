from __future__ import annotations

import sys
from typing import Any
from unittest.mock import patch

import pytest

from cli.agent_cli.mcp.client import MCPConnectionHandle, MCPConnectionResult
from cli.agent_cli.mcp.runtime import McpRuntimeFacade
from cli.agent_cli.mcp.transports import MCPTransportConnection
from cli.agent_cli.providers.tool_call_runtime import runtime_tool_call_command
from cli.agent_cli.runtime_core.mcp_commands import handle_mcp_command
from cli.agent_cli.tools_core.registry import runtime_registry_mcp_server_entries
from cli.agent_cli.tools_core.registry_runtime import build_capabilities_payload

from .mcp_testkit import inline_stdio_mcp_transport_config

class _PluginManagerStub:
    def __init__(self) -> None:
        self._runtime = None

    @staticmethod
    def workspace_trust_level() -> str:
        return "trusted"

    @staticmethod
    def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
        return {
            "atlas": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-c", "print('ready')"],
                "resources": [
                    {
                        "uri": "file:///atlas/readme.md",
                        "name": "Atlas README",
                        "mime_type": "text/markdown",
                        "contents": [{"text": "# Atlas"}],
                    }
                ],
            }
        }

    @staticmethod
    def effective_mcp_servers() -> dict[str, dict[str, object]]:
        return {}

    @staticmethod
    def effective_app_connectors() -> list[dict[str, object]]:
        return []

    def mcp_provider_tool_specs(self) -> list[dict[str, object]]:
        assert self._runtime is not None
        return self._runtime.provider_tool_specs()

    def mcp_server_runtime_map(self) -> dict[str, dict[str, object]]:
        assert self._runtime is not None
        return self._runtime.capability_mcp_servers()

    def mcp_server_entries(self) -> list[dict[str, object]]:
        assert self._runtime is not None
        return self._runtime.server_entries()


class _RuntimeStub:
    def __init__(self, mcp_runtime) -> None:
        self._mcp_runtime = mcp_runtime

    def get_mcp_runtime(self):
        return self._mcp_runtime

    @staticmethod
    def _parse_args(arg_text: str) -> tuple[list[str], dict[str, object]]:
        parts = [item for item in str(arg_text or "").split() if item]
        options: dict[str, object] = {}
        positionals: list[str] = []
        index = 0
        while index < len(parts):
            item = parts[index]
            if item.startswith("--") and index + 1 < len(parts):
                options[item[2:]] = parts[index + 1]
                index += 2
                continue
            positionals.append(item)
            index += 1
        return positionals, options


class _RuntimePolicyStub:
    def __init__(self, network_access_enabled: str | bool | None = None) -> None:
        self.network_access_enabled = network_access_enabled


class _RuntimePolicyAllowPluginOnly:
    allow_sources = ["plugin"]


class _RemoteDescriptorsSession:
    def __init__(
        self,
        *,
        prompts: list[dict[str, Any]] | None = None,
        resources: list[dict[str, Any]] | None = None,
        reads: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._prompts = [dict(item) for item in prompts or [] if isinstance(item, dict)]
        self._resources = [dict(item) for item in resources or [] if isinstance(item, dict)]
        self._reads = {str(key): dict(value) for key, value in dict(reads or {}).items()}
        self.read_calls: list[str] = []

    def prompts_list(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._prompts]

    def resources_list(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._resources]

    def resources_read(self, *, uri: str) -> dict[str, Any]:
        target_uri = str(uri or "").strip()
        self.read_calls.append(target_uri)
        return dict(self._reads.get(target_uri) or {"error": "resource not found"})

    @staticmethod
    def close() -> None:
        return


class _ToolsCallSessionStub(_RemoteDescriptorsSession):
    def __init__(
        self,
        *,
        tool_name: str = "approval_guard",
        call_response: dict[str, Any] | None = None,
        exception: Exception | None = None,
        prompts: list[dict[str, Any]] | None = None,
        resources: list[dict[str, Any]] | None = None,
        reads: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(prompts=prompts, resources=resources, reads=reads)
        self.tool_name = tool_name
        self._call_response = dict(call_response or {"isError": False})
        self._exception = exception
        self.call_history: list[dict[str, Any]] = []

    def tools_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": self.tool_name,
                "description": "approval guard tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "additionalProperties": True,
                },
            }
        ]

    def tools_call(self, *, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        self.call_history.append({"name": name, "arguments": dict(arguments or {})})
        if self._exception is not None:
            raise self._exception
        return dict(self._call_response)


class _ToolsCallSessionStub:
    def __init__(
        self,
        *,
        tool_name: str = "approval_guard",
        call_response: dict[str, Any] | None = None,
        exception: Exception | None = None,
    ) -> None:
        self.tool_name = tool_name
        self._call_response = dict(call_response or {"isError": False})
        self._exception = exception
        self.call_history: list[dict[str, Any]] = []

    def tools_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": self.tool_name,
                "description": "approval guard tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "additionalProperties": True,
                },
            }
        ]

    def tools_call(self, *, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        self.call_history.append({"name": name, "arguments": dict(arguments or {})})
        if self._exception is not None:
            raise self._exception
        return dict(self._call_response)

    @staticmethod
    def close() -> None:
        return


def _inject_remote_session(runtime: McpRuntimeFacade, session: _RemoteDescriptorsSession, *, server_name: str = "atlas") -> None:
    connection = MCPTransportConnection(transport="stdio", endpoint=f"session://{server_name}", session=session)
    handle = MCPConnectionHandle(
        name=server_name,
        fingerprint=f"{server_name}|test",
        connected_at=0.0,
        transport=connection,
        session=session,
    )

    def _connect_many(configs: dict[str, Any]) -> dict[str, MCPConnectionResult]:
        return {
            name: (MCPConnectionResult(name=name, status="connected", handle=handle) if name == server_name else MCPConnectionResult(name=name, status="failed", error_code="test-stub", error="not stubbed"))
            for name in configs
        }

    runtime._client.connect_many = _connect_many  # type: ignore[method-assign]
    runtime._client.get_cached_connection_by_name = lambda name: handle if str(name or "").strip() == server_name else None  # type: ignore[method-assign]


def _runtime() -> McpRuntimeFacade:
    manager = _PluginManagerStub()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime
    return runtime


def _stdio_dynamic_config(label: str) -> dict[str, object]:
    return {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-c", f"print('ready:{label}')"],
    }


def _real_stdio_server_config() -> dict[str, object]:
    transport = inline_stdio_mcp_transport_config(timeout_sec=3.0)
    return {
        "transport": "stdio",
        "command": list(transport.command),
        "args": list(transport.args),
        "env": dict(transport.env),
        "timeout_sec": transport.timeout_sec,
    }


def test_mcp_runtime_facade_exposes_resource_provider_tools_and_connected_status() -> None:
    runtime = _runtime()

    status = runtime.list_status()
    provider_specs = runtime.provider_tool_specs()
    capability_map = runtime.capability_mcp_servers()

    assert status["servers"][0]["status"] == "connected"
    assert [item["function"]["name"] for item in provider_specs] == ["list_mcp_resources", "read_mcp_resource"]
    assert capability_map["atlas"]["enabled"] is True
    assert capability_map["atlas"]["config"]["command"] == sys.executable
    assert capability_map["atlas"]["config"]["args"] == ["-c", "print('ready')"]


def test_mcp_resource_command_reads_from_runtime_projection() -> None:
    runtime = _runtime()
    command_runtime = _RuntimeStub(runtime)

    list_text, _ = handle_mcp_command(command_runtime, name="mcp_resource", arg_text="list") or ("", [])
    read_text, _ = handle_mcp_command(
        command_runtime,
        name="mcp_resource",
        arg_text="read --server atlas --uri file:///atlas/readme.md",
    ) or ("", [])

    assert "mcp resources" in list_text
    assert "count=1" in list_text
    assert "mcp resource read" in read_text
    assert "ok=true" in read_text
    assert "mime_type=text/markdown" in read_text


def test_runtime_tool_call_command_maps_projected_resource_tools() -> None:
    list_command = runtime_tool_call_command(
        "list_mcp_resources",
        {"server_name": "atlas"},
        host_platform=None,
        quote_arg_fn=lambda value: f'"{value}"',
    )
    read_command = runtime_tool_call_command(
        "read_mcp_resource",
        {"server_name": "atlas", "uri": "file:///atlas/readme.md"},
        host_platform=None,
        quote_arg_fn=lambda value: f'"{value}"',
    )

    assert list_command == '/mcp_resource list server "atlas"'
    assert read_command == '/mcp_resource read server "atlas" uri "file:///atlas/readme.md"'


def test_build_capabilities_payload_prefers_runtime_mcp_entries_when_available() -> None:
    manager = _PluginManagerStub()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    payload = build_capabilities_payload(
        plugin_manager_factory=lambda: manager,
        merged_capability_specs_fn=lambda **_: [{"name": "shell"}],
    )

    assert payload["mcp_servers"]["atlas"]["status"] == "connected"
    assert payload["mcp_server_entries"][0]["name"] == "atlas"


def test_runtime_registry_mcp_entries_keep_runtime_config_when_overlaying_canonical_metadata() -> None:
    class _PluginManagerWithCanonical(_PluginManagerStub):
        @staticmethod
        def gui_bridge_metadata() -> dict[str, object]:
            return {
                "mcpServers": [
                    {
                        "name": "atlas",
                        "source": "plugin",
                        "config": {"url": "https://canonical.example/mcp"},
                    }
                ]
            }

    manager = _PluginManagerWithCanonical()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    entries = runtime_registry_mcp_server_entries(
        manager,
        runtime_capabilities={
            "mcp_servers": runtime.capability_mcp_servers(),
        },
    )
    atlas = next(item for item in entries if item["name"] == "atlas")

    assert atlas["status"] == "connected"
    assert atlas["source"] == "user"
    assert atlas["config"]["command"] == sys.executable


def test_mcp_runtime_enable_disable_and_reconnect_all_keep_servers_visible() -> None:
    runtime = _runtime()
    runtime.set_runtime_dynamic("beta", _stdio_dynamic_config("beta"))

    disabled = runtime.disable("all")
    disabled_by_name = {item["name"]: item for item in runtime.list_status()["servers"]}

    assert disabled["target"] == "all"
    assert {item["name"] for item in disabled["servers"]} == {"atlas", "beta"}
    assert disabled_by_name["atlas"]["enabled"] is False
    assert disabled_by_name["atlas"]["status"] == "disabled"
    assert disabled_by_name["beta"]["enabled"] is False
    assert disabled_by_name["beta"]["status"] == "disabled"

    enabled = runtime.enable("all")
    enabled_by_name = {item["name"]: item for item in runtime.list_status()["servers"]}
    reconnect = runtime.reconnect("all")

    assert enabled["enabled"] is True
    assert enabled_by_name["atlas"]["enabled"] is True
    assert enabled_by_name["atlas"]["status"] == "connected"
    assert enabled_by_name["beta"]["enabled"] is True
    assert enabled_by_name["beta"]["status"] == "connected"
    assert reconnect["status"] == "ok"
    assert reconnect["target"] == "all"
    assert {item["name"] for item in reconnect["servers"]} == {"atlas", "beta"}


def test_mcp_runtime_set_runtime_dynamic_none_removes_server() -> None:
    runtime = _runtime()

    runtime.set_runtime_dynamic("beta", _stdio_dynamic_config("beta"))
    assert "beta" in runtime.server_entries_map()
    assert runtime._client.get_cached_connection_by_name("beta") is not None

    runtime.set_runtime_dynamic("beta", None)

    assert "beta" not in runtime.server_entries_map()
    assert runtime._client.get_cached_connection_by_name("beta") is None


def test_mcp_runtime_inspect_unknown_server_raises_value_error() -> None:
    runtime = _runtime()

    try:
        runtime.inspect("missing")
    except ValueError as exc:
        assert str(exc) == "unknown mcp server: missing"
    else:
        raise AssertionError("expected ValueError for missing server")


def test_mcp_runtime_list_status_exposes_blocked_duplicate_entries() -> None:
    class _PluginManagerWithDuplicate(_PluginManagerStub):
        @staticmethod
        def effective_mcp_servers() -> dict[str, dict[str, object]]:
            return {
                "atlas": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": ["-c", "print('plugin atlas')"],
                }
            }

    manager = _PluginManagerWithDuplicate()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    status = runtime.list_status()
    blocked_by_name = {item["name"]: item for item in status["blocked"]}

    assert "atlas" in {item["name"] for item in status["servers"]}
    assert blocked_by_name["atlas"]["source"] == "plugin"
    assert blocked_by_name["atlas"]["reason"] == "dedup.shadowed_by_precedence"


def test_mcp_runtime_network_disabled_policy_keeps_stdio_server_connected() -> None:
    manager = _PluginManagerStub()
    runtime = McpRuntimeFacade(
        plugin_manager_getter=lambda: manager,
        runtime_policy_getter=lambda: _RuntimePolicyStub(network_access_enabled="disabled"),
    )
    manager._runtime = runtime

    status = runtime.list_status()
    atlas = next(item for item in status["servers"] if item["name"] == "atlas")

    assert atlas["status"] == "connected"
    assert atlas["transport"] == "stdio"


def test_mcp_runtime_policy_allow_sources_blocks_user_server_from_status_and_surfaces_blocked_reason() -> None:
    manager = _PluginManagerStub()
    runtime = McpRuntimeFacade(
        plugin_manager_getter=lambda: manager,
        runtime_policy_getter=lambda: _RuntimePolicyAllowPluginOnly(),
    )
    manager._runtime = runtime

    status = runtime.list_status()
    server_names = {item["name"] for item in status["servers"]}
    blocked_by_name = {item["name"]: item for item in status["blocked"]}

    assert "atlas" not in server_names
    assert blocked_by_name["atlas"]["source"] == "user"
    assert blocked_by_name["atlas"]["reason"] == "policy.not_in_allow_sources"


def test_mcp_runtime_policy_allow_sources_hides_blocked_server_from_provider_tool_specs() -> None:
    class _PluginManagerWithAtlasToolAndResource(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {
                "atlas": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": ["-c", "print('ready')"],
                    "tools": [
                        {
                            "name": "atlas.echo",
                            "description": "Echo from atlas",
                            "input_schema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"],
                                "additionalProperties": False,
                            },
                        }
                    ],
                    "resources": [
                        {
                            "uri": "file:///atlas/readme.md",
                            "name": "Atlas README",
                            "mime_type": "text/markdown",
                            "contents": [{"text": "# Atlas"}],
                        }
                    ],
                }
            }

    manager = _PluginManagerWithAtlasToolAndResource()
    runtime = McpRuntimeFacade(
        plugin_manager_getter=lambda: manager,
        runtime_policy_getter=lambda: _RuntimePolicyAllowPluginOnly(),
    )
    manager._runtime = runtime

    provider_specs = runtime.provider_tool_specs()
    provider_names = [str(item.get("function", {}).get("name") or "") for item in provider_specs]
    atlas_resources = runtime.list_resources(server_name="atlas")

    assert not any(name.startswith("mcp__atlas__") for name in provider_names)
    assert atlas_resources == []


def test_mcp_runtime_policy_block_visibility_parity_across_status_contract_and_resources() -> None:
    manager = _PluginManagerStub()
    runtime = McpRuntimeFacade(
        plugin_manager_getter=lambda: manager,
        runtime_policy_getter=lambda: _RuntimePolicyAllowPluginOnly(),
    )
    manager._runtime = runtime

    status = runtime.list_status()
    server_names = {str(item.get("name") or "") for item in list(status.get("servers") or [])}
    blocked_by_name = {
        str(item.get("name") or ""): dict(item)
        for item in list(status.get("blocked") or [])
        if str(item.get("name") or "").strip()
    }
    contracts = runtime.projected_tool_contracts()
    provider_specs = runtime.provider_tool_specs()
    provider_names = {
        str(item.get("function", {}).get("name") or "")
        for item in provider_specs
        if isinstance(item, dict)
    }
    atlas_resources = runtime.list_resources(server_name="atlas")

    assert "atlas" not in server_names
    assert blocked_by_name["atlas"]["source"] == "user"
    assert blocked_by_name["atlas"]["reason"] == "policy.not_in_allow_sources"
    assert all(str(item.get("server_name") or "") != "atlas" for item in contracts)
    assert "mcp__atlas__search_docs" not in provider_names
    assert atlas_resources == []

    with pytest.raises(ValueError, match=r"unknown projected mcp tool: mcp__atlas__search_docs"):
        runtime.projected_tool_approval_request(
            projected_name="mcp__atlas__search_docs",
            arguments={"query": "blocked"},
            requested_by="runtime.mcp",
        )


def test_mcp_runtime_snapshot_prefers_remote_stdio_tools_list_when_session_available() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    snapshot = runtime.snapshot()
    atlas_entry = runtime.inspect("atlas")

    assert [item.name for item in snapshot.tools] == ["agenthub.file_read", "agenthub.list_dir"]
    assert snapshot.connection_states["atlas"].value == "connected"
    assert atlas_entry["server_info"]["name"] == "agenthub_mcp_server"
    assert [item["name"] for item in atlas_entry["tools"]] == ["agenthub.file_read", "agenthub.list_dir"]


def test_mcp_runtime_snapshot_prefers_remote_prompts_and_resources_when_session_available() -> None:
    class _PluginManagerWithStaticPromptsAndResources(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {
                "atlas": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": ["-c", "print('ready')"],
                    "prompts": [{"name": "static_prompt"}],
                    "resources": [{"uri": "file:///atlas/static.md", "name": "Static README"}],
                }
            }

    manager = _PluginManagerWithStaticPromptsAndResources()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime
    session = _RemoteDescriptorsSession(
        prompts=[{"name": "remote_prompt", "description": "Remote prompt"}],
        resources=[{"uri": "file:///atlas/remote.md", "name": "Remote README", "mimeType": "text/plain"}],
    )
    _inject_remote_session(runtime, session)

    snapshot = runtime.snapshot()
    atlas_entry = runtime.inspect("atlas")

    assert [item.name for item in snapshot.prompts] == ["remote_prompt"]
    assert [item.uri for item in snapshot.resources] == ["file:///atlas/remote.md"]
    assert [item["name"] for item in atlas_entry["prompts"]] == ["remote_prompt"]
    assert [item["uri"] for item in atlas_entry["resources"]] == ["file:///atlas/remote.md"]


def test_mcp_resource_command_reads_from_remote_session_before_projection() -> None:
    runtime = _runtime()
    command_runtime = _RuntimeStub(runtime)
    session = _RemoteDescriptorsSession(
        resources=[{"uri": "file:///atlas/readme.md", "name": "Atlas Remote README", "mimeType": "text/plain"}],
        reads={
            "file:///atlas/readme.md": {
                "contents": [{"uri": "file:///atlas/readme.md", "mimeType": "text/plain", "text": "remote-atlas"}]
            }
        },
    )
    _inject_remote_session(runtime, session)

    list_text, _ = handle_mcp_command(command_runtime, name="mcp_resource", arg_text="list") or ("", [])
    read_text, _ = handle_mcp_command(
        command_runtime,
        name="mcp_resource",
        arg_text="read --server atlas --uri file:///atlas/readme.md",
    ) or ("", [])
    payload = runtime.read_resource(server_name="atlas", uri="file:///atlas/readme.md")

    assert "Atlas Remote README" in list_text
    assert "ok=true" in read_text
    assert "mime_type=text/plain" in read_text
    assert session.read_calls == ["file:///atlas/readme.md", "file:///atlas/readme.md"]
    assert payload["contents"][0]["text"] == "remote-atlas"


def test_mcp_runtime_remote_tools_enter_provider_specs_and_execute_via_command_path() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime
    command_runtime = _RuntimeStub(runtime)

    provider_names = [item["function"]["name"] for item in runtime.provider_tool_specs()]
    command = runtime_tool_call_command(
        "mcp__atlas__agenthub_file_read",
        {"path": "README.md"},
        host_platform=None,
        quote_arg_fn=lambda value: f'"{value}"',
    )
    text, _ = handle_mcp_command(
        command_runtime,
        name="mcp_tool_call",
        arg_text='--projected-name mcp__atlas__agenthub_file_read --arguments-json {"path":"README.md"}',
    ) or ("", [])

    assert "mcp__atlas__agenthub_file_read" in provider_names
    assert "mcp__atlas__agenthub_list_dir" in provider_names
    assert command == '/mcp_tool_call projected-name "mcp__atlas__agenthub_file_read" arguments-json "{"path": "README.md"}"'
    assert "mcp tool call" in text
    assert "ok=true" in text
    assert "remote_name=agenthub.file_read" in text
    assert "text=read path=README.md" in text


def test_mcp_runtime_projected_tool_contracts_expose_approval_metadata() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    contracts = runtime.projected_tool_contracts()
    file_read = next(item for item in contracts if item["name"] == "mcp__atlas__agenthub_file_read")

    assert file_read["source"] == "mcp"
    assert file_read["tool_family"] == "mcp_remote"
    assert file_read["approval_required"] is True
    assert file_read["approval_family"] == "mcp_tool_call"
    assert file_read["approval_scope"] == "mcp.server:atlas"
    assert file_read["requires_confirmation"] is True
    assert file_read["mutates_ui"] is False


def test_mcp_runtime_call_projected_tool_includes_tool_contract_and_approval_projection() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    assert payload["ok"] is True
    assert payload["tool_contract"]["name"] == "mcp__atlas__agenthub_file_read"
    assert payload["tool_contract"]["approval_family"] == "mcp_tool_call"
    assert payload["tool_contract"]["approval_scope"] == "mcp.server:atlas"
    assert payload["approval"] == {
        "required": True,
        "family": "mcp_tool_call",
        "scope": "mcp.server:atlas",
    }
    _assert_call_observability(payload, expected_outcome="approved")


def _assert_call_approval_triplet(payload: dict[str, Any], *, expected_scope: str = "mcp.server:atlas") -> None:
    assert payload["tool_contract"]["approval_required"] is True
    assert payload["tool_contract"]["approval_family"] == "mcp_tool_call"
    assert payload["tool_contract"]["approval_scope"] == expected_scope
    assert payload["approval"]["required"] is True
    assert payload["approval"]["family"] == "mcp_tool_call"
    assert payload["approval"]["scope"] == expected_scope


def _assert_call_observability(
    payload: dict[str, Any],
    *,
    expected_outcome: str,
    expected_scope: str = "mcp.server:atlas",
) -> None:
    observability = payload["observability"]
    assert observability["schema_version"] == 1
    assert observability["decision_outcome"] == expected_outcome
    assert observability["decision_trace"] == [
        "approval.requested",
        f"approval.{expected_outcome}",
        "action.executed",
    ]
    assert observability["latency_bucket_field"] == "approval_latency_bucket"
    assert isinstance(observability["latency_ms"], int)
    assert observability["latency_bucket"] in {"lt_100ms", "100ms_500ms", "500ms_1s", "1s_5s", "ge_5s"}
    assert observability["reason_codes"]["approved"] == "approval.approved"
    assert observability["reason_codes"]["rejected"] == "approval.rejected"
    assert observability["reason_codes"]["timed_out"] == "approval.timed_out"
    assert observability["reason_codes"]["expired"] == "approval.expired"
    assert observability["reason_code"] == observability["reason_codes"][expected_outcome]
    snapshot = observability["tool_snapshot"]
    assert snapshot["projected_name"] == payload["tool_contract"]["name"]
    assert snapshot["server_name"] == payload["tool_contract"]["server_name"]
    assert snapshot["remote_name"] == payload["tool_contract"]["remote_name"]
    assert snapshot["connector_key"] == f"mcp:{payload['tool_contract']['server_name']}"
    assert snapshot["approval_scope"] == expected_scope


def test_mcp_runtime_call_projected_tool_approval_metadata_survives_tool_rejection() -> None:
    runtime = _runtime()
    session = _ToolsCallSessionStub(
        call_response={"isError": True, "error": "policy-blocked"},
    )
    _inject_remote_session(runtime, session)

    payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__approval_guard",
        arguments={"value": "reject"},
    )

    assert payload["ok"] is False
    assert payload["result"]["error"] == "policy-blocked"
    _assert_call_approval_triplet(payload)
    _assert_call_observability(payload, expected_outcome="rejected")
    assert session.call_history[-1]["name"] == "approval_guard"


def test_mcp_runtime_call_projected_tool_approval_metadata_survives_timeout() -> None:
    runtime = _runtime()
    session = _ToolsCallSessionStub(exception=TimeoutError("call-timeout"))
    _inject_remote_session(runtime, session)

    payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__approval_guard",
        arguments={"value": "wait"},
    )

    assert payload["ok"] is False
    assert "TimeoutError" in str(payload.get("error") or "")
    _assert_call_approval_triplet(payload)
    _assert_call_observability(payload, expected_outcome="timed_out")
    assert session.call_history[-1]["arguments"] == {"value": "wait"}


def test_mcp_approval_outcome_matrix_guard_retains_visible_fields() -> None:
    def _observed_outcome(payload: dict[str, Any]) -> str:
        if bool(payload.get("ok")):
            return "approved"
        error_text = " ".join(
            (
                str(payload.get("error") or ""),
                str(dict(payload.get("result") or {}).get("error") or ""),
            )
        ).strip().lower()
        if "timeout" in error_text:
            return "timed_out"
        if "expired" in error_text:
            return "expired"
        return "rejected"

    cases = [
        ("approved", _ToolsCallSessionStub(call_response={"isError": False, "content": [{"type": "text", "text": "ok"}]}), "approved"),
        ("rejected", _ToolsCallSessionStub(call_response={"isError": True, "error": "policy-blocked"}), "rejected"),
        ("timed_out", _ToolsCallSessionStub(exception=TimeoutError("call-timeout")), "timed_out"),
        ("expired", _ToolsCallSessionStub(call_response={"isError": True, "error": "approval expired by lease"}), "expired"),
    ]

    for label, session, expected_outcome in cases:
        runtime = _runtime()
        _inject_remote_session(runtime, session)
        payload = runtime.call_projected_tool(
            projected_name="mcp__atlas__approval_guard",
            arguments={"value": label},
        )
        assert "tool_contract" in payload, label
        assert "approval" in payload, label
        _assert_call_approval_triplet(payload)
        assert _observed_outcome(payload) == expected_outcome, label
        _assert_call_observability(payload, expected_outcome=expected_outcome)


def test_mcp_approval_outcome_matrix_guard_explicit_visible_fields_projection() -> None:
    cases = [
        (
            "approved",
            _ToolsCallSessionStub(call_response={"isError": False, "content": [{"type": "text", "text": "ok"}]}),
            "approved",
            True,
        ),
        (
            "rejected",
            _ToolsCallSessionStub(call_response={"isError": True, "error": "policy-blocked"}),
            "rejected",
            False,
        ),
        (
            "timed_out",
            _ToolsCallSessionStub(exception=TimeoutError("call-timeout")),
            "timed_out",
            False,
        ),
        (
            "expired",
            _ToolsCallSessionStub(call_response={"isError": True, "error": "approval expired by lease"}),
            "expired",
            False,
        ),
    ]

    for label, session, expected_outcome, expected_ok in cases:
        runtime = _runtime()
        _inject_remote_session(runtime, session)
        payload = runtime.call_projected_tool(
            projected_name="mcp__atlas__approval_guard",
            arguments={"value": label},
        )

        tool_contract = dict(payload.get("tool_contract") or {})
        approval = dict(payload.get("approval") or {})
        observability = dict(payload.get("observability") or {})
        reason_codes = dict(observability.get("reason_codes") or {})
        decision_trace = list(observability.get("decision_trace") or [])

        assert bool(payload.get("ok")) is expected_ok, label
        assert tool_contract["name"] == "mcp__atlas__approval_guard", label
        assert tool_contract["approval_required"] is True, label
        assert tool_contract["approval_family"] == "mcp_tool_call", label
        assert tool_contract["approval_scope"] == "mcp.server:atlas", label
        assert approval == {
            "required": True,
            "family": "mcp_tool_call",
            "scope": "mcp.server:atlas",
        }, label
        assert reason_codes["approved"] == "approval.approved", label
        assert reason_codes["rejected"] == "approval.rejected", label
        assert reason_codes["timed_out"] == "approval.timed_out", label
        assert reason_codes["expired"] == "approval.expired", label
        assert observability["decision_outcome"] == expected_outcome, label
        assert observability["reason_code"] == reason_codes[expected_outcome], label
        assert decision_trace[0] == "approval.requested", label
        assert decision_trace[1] == f"approval.{expected_outcome}", label
        assert decision_trace[-1] == "action.executed", label


def test_mcp_observability_reason_code_backfill_guard_for_partial_descriptor_contract() -> None:
    runtime = _runtime()
    session = _ToolsCallSessionStub(call_response={"isError": False, "content": [{"type": "text", "text": "ok"}]})
    _inject_remote_session(runtime, session)
    partial_descriptor = {
        "name": "mcp__atlas__approval_guard",
        "type": "mcp_tool",
        "tool_family": "mcp_remote",
        "source": "mcp",
        "server_name": "atlas",
        "remote_name": "approval_guard",
        "description": "approval guard",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        "requires_confirmation": True,
        "mutates_ui": False,
        "approval_required": True,
        "approval_family": "mcp_tool_call",
        "approval_scope": "mcp.server:atlas",
        "observability": {
            "schema_version": 1,
            "reason_codes": {"approved": "approval.approved.custom"},
            "tool_snapshot": {"projected_name": "mcp__atlas__approval_guard"},
        },
    }

    with patch("cli.agent_cli.mcp.runtime.project_mcp_tool_descriptors", return_value=[dict(partial_descriptor)]):
        with patch("cli.agent_cli.mcp.remote_calls.project_mcp_tool_descriptors", return_value=[dict(partial_descriptor)]):
            contracts = runtime.projected_tool_contracts()
            request = runtime.projected_tool_approval_request(
                projected_name="mcp__atlas__approval_guard",
                arguments={"value": "ok"},
                requested_by="runtime.mcp",
            )
            payload = runtime.call_projected_tool(
                projected_name="mcp__atlas__approval_guard",
                arguments={"value": "ok"},
            )

    assert len(contracts) == 1
    contract_observability = dict(contracts[0]["observability"])
    request_observability = dict(request["metadata"]["observability"])
    call_observability = dict(payload["observability"])
    for observed in (contract_observability, request_observability, call_observability):
        reason_codes = dict(observed["reason_codes"])
        assert reason_codes["pending"] == "approval.pending"
        assert reason_codes["approved"] == "approval.approved.custom"
        assert reason_codes["rejected"] == "approval.rejected"
        assert reason_codes["timed_out"] == "approval.timed_out"
        assert reason_codes["expired"] == "approval.expired"
    assert call_observability["reason_code"] == "approval.approved.custom"
    snapshot = dict(call_observability["tool_snapshot"])
    assert snapshot["projected_name"] == "mcp__atlas__approval_guard"
    assert snapshot["server_name"] == "atlas"
    assert snapshot["remote_name"] == "approval_guard"
    assert snapshot["connector_key"] == "mcp:atlas"
    assert snapshot["approval_scope"] == "mcp.server:atlas"


def test_mcp_runtime_projected_tool_approval_request_contract_is_stable() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )

    assert request["action_type"] == "mcp.tool.call"
    assert request["connector_key"] == "mcp:atlas"
    assert request["plugin_name"] == "mcp_runtime"
    assert request["requested_by"] == "runtime.mcp"
    assert request["request_payload"]["projected_name"] == "mcp__atlas__agenthub_file_read"
    assert request["request_payload"]["arguments"] == {"path": "README.md"}
    assert request["request_payload"]["tool_contract"]["approval_family"] == "mcp_tool_call"
    assert request["metadata"]["approval"] == {
        "required": True,
        "family": "mcp_tool_call",
        "scope": "mcp.server:atlas",
    }
    request_observability = request["metadata"]["observability"]
    assert request["request_payload"]["observability"] == request_observability
    assert request_observability["schema_version"] == 1
    assert request_observability["reason_code"] == "approval.pending"
    assert request_observability["decision_trace"] == ["approval.requested", "approval.pending"]
    assert request_observability["latency_bucket_field"] == "approval_latency_bucket"
    assert request_observability["latency_bucket"] == "pending"
    assert request_observability["reason_codes"]["approved"] == "approval.approved"
    assert request_observability["reason_codes"]["timed_out"] == "approval.timed_out"
    assert request_observability["tool_snapshot"]["projected_name"] == "mcp__atlas__agenthub_file_read"


def test_mcp_guard_combined_assertions_keep_contract_vector_consistent() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    for contract in (
        projected_contract,
        approval_request["request_payload"]["tool_contract"],
        approval_request["metadata"]["tool_contract"],
        call_payload["tool_contract"],
    ):
        assert contract["source"] == "mcp"
        assert contract["approval_required"] is True
        assert contract["requires_confirmation"] is True
        assert contract["mutates_ui"] is False
        assert isinstance(contract["approval_required"], bool)
        assert isinstance(contract["requires_confirmation"], bool)
        assert isinstance(contract["mutates_ui"], bool)

    assert call_payload["approval"] == {
        "required": True,
        "family": "mcp_tool_call",
        "scope": "mcp.server:atlas",
    }
    assert approval_request["metadata"]["approval"] == {
        "required": True,
        "family": "mcp_tool_call",
        "scope": "mcp.server:atlas",
    }


def test_mcp_contract_scope_guard_consistent_across_projection_nodes() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    expected_scope = projected_contract["approval_scope"]
    assert expected_scope == "mcp.server:atlas"
    assert approval_request["request_payload"]["tool_contract"]["approval_scope"] == expected_scope
    assert approval_request["metadata"]["tool_contract"]["approval_scope"] == expected_scope
    assert call_payload["tool_contract"]["approval_scope"] == expected_scope
    assert approval_request["metadata"]["approval"]["scope"] == expected_scope
    assert call_payload["approval"]["scope"] == expected_scope


def test_mcp_approval_family_guard_constant_across_projection_nodes() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    expected_family = "mcp_tool_call"
    assert projected_contract["approval_family"] == expected_family
    assert approval_request["request_payload"]["tool_contract"]["approval_family"] == expected_family
    assert approval_request["metadata"]["tool_contract"]["approval_family"] == expected_family
    assert approval_request["metadata"]["approval"]["family"] == expected_family
    assert call_payload["tool_contract"]["approval_family"] == expected_family
    assert call_payload["approval"]["family"] == expected_family


def test_mcp_approval_required_guard_consistent_across_projection_nodes() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    expected_required = bool(projected_contract["approval_required"])
    assert expected_required is True
    assert isinstance(projected_contract["approval_required"], bool)
    assert approval_request["request_payload"]["tool_contract"]["approval_required"] is expected_required
    assert approval_request["metadata"]["tool_contract"]["approval_required"] is expected_required
    assert approval_request["metadata"]["approval"]["required"] is expected_required
    assert call_payload["tool_contract"]["approval_required"] is expected_required
    assert call_payload["approval"]["required"] is expected_required
    assert isinstance(approval_request["metadata"]["approval"]["required"], bool)
    assert isinstance(call_payload["approval"]["required"], bool)


def test_mcp_requires_confirmation_guard_consistent_across_projection_nodes() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    expected_confirmation = bool(projected_contract["requires_confirmation"])
    assert expected_confirmation is True
    assert isinstance(projected_contract["requires_confirmation"], bool)
    assert approval_request["request_payload"]["tool_contract"]["requires_confirmation"] is expected_confirmation
    assert approval_request["metadata"]["tool_contract"]["requires_confirmation"] is expected_confirmation
    assert call_payload["tool_contract"]["requires_confirmation"] is expected_confirmation
    assert isinstance(approval_request["request_payload"]["tool_contract"]["requires_confirmation"], bool)
    assert isinstance(approval_request["metadata"]["tool_contract"]["requires_confirmation"], bool)
    assert isinstance(call_payload["tool_contract"]["requires_confirmation"], bool)


def test_mcp_mutates_ui_guard_consistent_across_projection_nodes() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    expected_mutates_ui = bool(projected_contract["mutates_ui"])
    assert expected_mutates_ui is False
    assert isinstance(projected_contract["mutates_ui"], bool)
    assert approval_request["request_payload"]["tool_contract"]["mutates_ui"] is expected_mutates_ui
    assert approval_request["metadata"]["tool_contract"]["mutates_ui"] is expected_mutates_ui
    assert call_payload["tool_contract"]["mutates_ui"] is expected_mutates_ui
    assert isinstance(approval_request["request_payload"]["tool_contract"]["mutates_ui"], bool)
    assert isinstance(approval_request["metadata"]["tool_contract"]["mutates_ui"], bool)
    assert isinstance(call_payload["tool_contract"]["mutates_ui"], bool)


def test_mcp_source_tool_family_guard_consistent_across_projection_nodes() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    expected_source = "mcp"
    expected_tool_family = "mcp_remote"
    assert projected_contract["source"] == expected_source
    assert projected_contract["tool_family"] == expected_tool_family
    assert approval_request["request_payload"]["tool_contract"]["source"] == expected_source
    assert approval_request["request_payload"]["tool_contract"]["tool_family"] == expected_tool_family
    assert approval_request["metadata"]["tool_contract"]["source"] == expected_source
    assert approval_request["metadata"]["tool_contract"]["tool_family"] == expected_tool_family
    assert call_payload["tool_contract"]["source"] == expected_source
    assert call_payload["tool_contract"]["tool_family"] == expected_tool_family


def test_mcp_family_mapping_guard_projection_family_maps_to_approval_family() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    assert projected_contract["tool_family"] == "mcp_remote"
    assert projected_contract["approval_family"] == "mcp_tool_call"
    assert approval_request["request_payload"]["tool_contract"]["tool_family"] == "mcp_remote"
    assert approval_request["request_payload"]["tool_contract"]["approval_family"] == "mcp_tool_call"
    assert approval_request["metadata"]["tool_contract"]["tool_family"] == "mcp_remote"
    assert approval_request["metadata"]["tool_contract"]["approval_family"] == "mcp_tool_call"
    assert call_payload["tool_contract"]["tool_family"] == "mcp_remote"
    assert call_payload["tool_contract"]["approval_family"] == "mcp_tool_call"
    assert approval_request["metadata"]["approval"]["family"] == "mcp_tool_call"
    assert call_payload["approval"]["family"] == "mcp_tool_call"


def test_mcp_approval_triplet_stability_guard_across_projection_nodes() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    expected_triplet = (True, "mcp_tool_call", "mcp.server:atlas")

    def _triplet_from_tool_contract(contract: dict[str, Any]) -> tuple[bool, str, str]:
        return (
            bool(contract["approval_required"]),
            str(contract["approval_family"]),
            str(contract["approval_scope"]),
        )

    assert _triplet_from_tool_contract(projected_contract) == expected_triplet
    assert _triplet_from_tool_contract(approval_request["request_payload"]["tool_contract"]) == expected_triplet
    assert _triplet_from_tool_contract(approval_request["metadata"]["tool_contract"]) == expected_triplet
    assert _triplet_from_tool_contract(call_payload["tool_contract"]) == expected_triplet
    assert (
        bool(approval_request["metadata"]["approval"]["required"]),
        str(approval_request["metadata"]["approval"]["family"]),
        str(approval_request["metadata"]["approval"]["scope"]),
    ) == expected_triplet
    assert (
        bool(call_payload["approval"]["required"]),
        str(call_payload["approval"]["family"]),
        str(call_payload["approval"]["scope"]),
    ) == expected_triplet
    assert isinstance(projected_contract["approval_required"], bool)
    assert isinstance(approval_request["metadata"]["approval"]["required"], bool)
    assert isinstance(call_payload["approval"]["required"], bool)


def test_mcp_approval_triplet_request_and_call_contracts_share_types() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    call_payload = runtime.call_projected_tool(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
    )

    request_contract = approval_request["request_payload"]["tool_contract"]
    call_contract = call_payload["tool_contract"]

    for contract in (request_contract, call_contract):
        assert isinstance(contract["approval_required"], bool)
        assert isinstance(contract["approval_family"], str)
        assert isinstance(contract["approval_scope"], str)

    assert request_contract["approval_required"] == call_contract["approval_required"]
    assert request_contract["approval_family"] == call_contract["approval_family"]
    assert request_contract["approval_scope"] == call_contract["approval_scope"]


def test_mcp_approval_triplet_variant_arguments_guard_replays_same_triplet() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            return {"atlas": _real_stdio_server_config()}

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_name = "mcp__atlas__agenthub_file_read"
    argument_variants = [
        {"path": "README.md"},
        {"path": "README.md", "mode": "text"},
    ]
    triplets: set[tuple[bool, str, str]] = set()

    def _approval_triplet_from_entry(approval_entry: dict[str, Any]) -> tuple[bool, str, str]:
        return (
            bool(approval_entry["required"]),
            str(approval_entry["family"]),
            str(approval_entry["scope"]),
        )

    for arguments in argument_variants:
        request = runtime.projected_tool_approval_request(
            projected_name=projected_name,
            arguments=arguments,
            requested_by="runtime.mcp",
        )
        payload = runtime.call_projected_tool(projected_name=projected_name, arguments=arguments)

        request_triplet = _approval_triplet_from_entry(request["metadata"]["approval"])
        call_triplet = _approval_triplet_from_entry(payload["approval"])

        assert request_triplet == call_triplet
        triplets.add(request_triplet)

    assert len(triplets) == 1


def test_mcp_approval_triplet_variant_guard_changes_scope_only_by_server() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            atlas = _real_stdio_server_config()
            atlas_prod = _real_stdio_server_config()
            atlas_prod["env"] = dict(atlas_prod.get("env") or {})
            atlas_prod["env"]["AGENTHUB_SERVER_ALIAS"] = "atlas_prod"
            return {
                "atlas": atlas,
                "atlas_prod": atlas_prod,
            }

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    servers = ["atlas", "atlas_prod"]
    required_values: set[bool] = set()
    family_values: set[str] = set()
    scope_values: set[str] = set()
    for server in servers:
        projected_name = f"mcp__{server}__agenthub_file_read"
        request = runtime.projected_tool_approval_request(
            projected_name=projected_name,
            arguments={"path": "README.md"},
            requested_by="runtime.mcp",
        )
        payload = runtime.call_projected_tool(
            projected_name=projected_name,
            arguments={"path": "README.md"},
        )
        request_triplet = (
            bool(request["metadata"]["approval"]["required"]),
            str(request["metadata"]["approval"]["family"]),
            str(request["metadata"]["approval"]["scope"]),
        )
        call_triplet = (
            bool(payload["approval"]["required"]),
            str(payload["approval"]["family"]),
            str(payload["approval"]["scope"]),
        )
        assert request_triplet == call_triplet
        assert request_triplet[2] == f"mcp.server:{server}"
        required_values.add(request_triplet[0])
        family_values.add(request_triplet[1])
        scope_values.add(request_triplet[2])

    assert required_values == {True}
    assert family_values == {"mcp_tool_call"}
    assert scope_values == {"mcp.server:atlas", "mcp.server:atlas_prod"}


def test_mcp_triplet_pairing_guard_binds_connector_scope_and_server_pairings() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            atlas = _real_stdio_server_config()
            atlas_prod = _real_stdio_server_config()
            atlas_prod["env"] = dict(atlas_prod.get("env") or {})
            atlas_prod["env"]["AGENTHUB_SERVER_ALIAS"] = "atlas_prod"
            return {
                "atlas": atlas,
                "atlas_prod": atlas_prod,
            }

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    pairings: set[tuple[str, str]] = set()
    for server in ("atlas", "atlas_prod"):
        projected_name = f"mcp__{server}__agenthub_file_read"
        request = runtime.projected_tool_approval_request(
            projected_name=projected_name,
            arguments={"path": "README.md"},
            requested_by="runtime.mcp",
        )
        payload = runtime.call_projected_tool(
            projected_name=projected_name,
            arguments={"path": "README.md"},
        )
        expected_connector = f"mcp:{server}"
        expected_scope = f"mcp.server:{server}"
        assert request["connector_key"] == expected_connector
        assert request["metadata"]["approval"]["scope"] == expected_scope
        assert payload["approval"]["scope"] == expected_scope
        assert request["metadata"]["approval"]["required"] is True
        assert request["metadata"]["approval"]["family"] == "mcp_tool_call"
        pairings.add((request["connector_key"], request["metadata"]["approval"]["scope"]))

    assert pairings == {
        ("mcp:atlas", "mcp.server:atlas"),
        ("mcp:atlas_prod", "mcp.server:atlas_prod"),
    }


def test_mcp_approval_metadata_server_key_matches_projected_contract() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            atlas = _real_stdio_server_config()
            atlas_prod = _real_stdio_server_config()
            atlas_prod["env"] = dict(atlas_prod.get("env") or {})
            atlas_prod["env"]["AGENTHUB_SERVER_ALIAS"] = "atlas_prod"
            return {
                "atlas": atlas,
                "atlas_prod": atlas_prod,
            }

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    projected_contract = next(
        item for item in runtime.projected_tool_contracts() if item["name"] == "mcp__atlas__agenthub_file_read"
    )
    approval_request = runtime.projected_tool_approval_request(
        projected_name="mcp__atlas__agenthub_file_read",
        arguments={"path": "README.md"},
        requested_by="runtime.mcp",
    )
    request_payload_contract = approval_request["request_payload"]["tool_contract"]
    metadata_contract = approval_request["metadata"]["tool_contract"]
    expected_server = str(projected_contract["server_name"])

    assert expected_server, "guard requires server_name to be present on the projected contract"
    assert approval_request["connector_key"] == f"mcp:{expected_server}"
    assert request_payload_contract["server_name"] == expected_server
    assert metadata_contract["server_name"] == expected_server
    assert request_payload_contract["approval_scope"] == projected_contract["approval_scope"]
    assert metadata_contract["approval_scope"] == projected_contract["approval_scope"]
    assert approval_request["metadata"]["approval"]["scope"] == projected_contract["approval_scope"]


def test_mcp_connector_scope_family_matrix_guard_projection_nodes() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            atlas = _real_stdio_server_config()
            atlas_prod = _real_stdio_server_config()
            team42 = _real_stdio_server_config()
            atlas_prod["env"] = dict(atlas_prod.get("env") or {})
            atlas_prod["env"]["AGENTHUB_SERVER_ALIAS"] = "atlas_prod"
            team42["env"] = dict(team42.get("env") or {})
            team42["env"]["AGENTHUB_SERVER_ALIAS"] = "team42"
            return {
                "atlas": atlas,
                "atlas_prod": atlas_prod,
                "team42": team42,
            }

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    matrix_rows: set[tuple[str, str, str]] = set()
    for server in ("atlas", "atlas_prod", "team42"):
        projected_name = f"mcp__{server}__agenthub_file_read"
        request = runtime.projected_tool_approval_request(
            projected_name=projected_name,
            arguments={"path": "README.md"},
            requested_by="runtime.mcp",
        )
        payload = runtime.call_projected_tool(
            projected_name=projected_name,
            arguments={"path": "README.md"},
        )
        connector = str(request["connector_key"] or "")
        scope = str(request["metadata"]["approval"]["scope"] or "")
        family = str(request["metadata"]["approval"]["family"] or "")
        assert connector == f"mcp:{server}"
        assert scope == f"mcp.server:{server}"
        assert family == "mcp_tool_call"
        assert payload["approval"]["scope"] == scope
        assert payload["approval"]["family"] == family
        matrix_rows.add((connector, scope, family))

    assert matrix_rows == {
        ("mcp:atlas", "mcp.server:atlas", "mcp_tool_call"),
        ("mcp:atlas_prod", "mcp.server:atlas_prod", "mcp_tool_call"),
        ("mcp:team42", "mcp.server:team42", "mcp_tool_call"),
    }


def test_mcp_matrix_field_type_guard_projection_nodes() -> None:
    class _PluginManagerWithRemoteTools(_PluginManagerStub):
        @staticmethod
        def user_configured_mcp_servers() -> dict[str, dict[str, object]]:
            atlas = _real_stdio_server_config()
            atlas_prod = _real_stdio_server_config()
            atlas_prod["env"] = dict(atlas_prod.get("env") or {})
            atlas_prod["env"]["AGENTHUB_SERVER_ALIAS"] = "atlas_prod"
            return {
                "atlas": atlas,
                "atlas_prod": atlas_prod,
            }

    manager = _PluginManagerWithRemoteTools()
    runtime = McpRuntimeFacade(plugin_manager_getter=lambda: manager)
    manager._runtime = runtime

    for server in ("atlas", "atlas_prod"):
        projected_name = f"mcp__{server}__agenthub_file_read"
        request = runtime.projected_tool_approval_request(
            projected_name=projected_name,
            arguments={"path": "README.md"},
            requested_by="runtime.mcp",
        )
        payload = runtime.call_projected_tool(
            projected_name=projected_name,
            arguments={"path": "README.md"},
        )
        connector_key = request["connector_key"]
        required = request["metadata"]["approval"]["required"]
        family = request["metadata"]["approval"]["family"]
        scope = request["metadata"]["approval"]["scope"]

        assert isinstance(connector_key, str), server
        assert isinstance(required, bool), server
        assert isinstance(family, str), server
        assert isinstance(scope, str), server
        assert isinstance(payload["approval"]["required"], bool), server
        assert isinstance(payload["approval"]["family"], str), server
        assert isinstance(payload["approval"]["scope"], str), server


class _RelaySessionStub:
    def __init__(self, *, notifications: list[dict[str, Any]] | None = None) -> None:
        self._notifications = [dict(item) for item in notifications or [] if isinstance(item, dict)]
        self.request_calls: list[tuple[str, dict[str, Any]]] = []

    def drain_notifications(self) -> list[dict[str, Any]]:
        pending = [dict(item) for item in self._notifications]
        self._notifications = []
        return pending

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized_method = str(method or "").strip()
        normalized_params = dict(params or {})
        self.request_calls.append((normalized_method, normalized_params))
        return {"ok": True, "method": normalized_method, "params": normalized_params}

    @staticmethod
    def close() -> None:
        return


def _runtime_with_policy(policy: dict[str, Any] | object | None) -> McpRuntimeFacade:
    manager = _PluginManagerStub()
    runtime = McpRuntimeFacade(
        plugin_manager_getter=lambda: manager,
        runtime_policy_getter=lambda: policy,
    )
    manager._runtime = runtime
    return runtime


def _require_runtime_method(runtime: McpRuntimeFacade, *candidates: str):
    for name in candidates:
        method = getattr(runtime, name, None)
        if callable(method):
            return method
    raise AssertionError(
        f"P2-02 runtime API missing: expected callable method in {candidates}, but none exists on McpRuntimeFacade"
    )


def _normalize_rows(payload: Any, candidate_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in candidate_keys:
            raw = payload.get(key)
            if isinstance(raw, list):
                return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def _call_or_fail(callable_obj, *, label: str, **kwargs: Any) -> Any:
    try:
        return callable_obj(**kwargs)
    except RuntimeError as exc:
        raise AssertionError(f"P2-02 runtime gap: {label} unavailable ({exc})") from exc


def test_mcp_runtime_channel_permission_gate_default_off_returns_empty_lists() -> None:
    runtime = _runtime()
    session = _RelaySessionStub(
        notifications=[
            {"method": "notifications/channel/message", "params": {"server": "atlas", "channel": "alerts", "id": "msg_1"}},
            {"method": "notifications/permission/request", "params": {"server": "atlas", "request_id": "perm_1"}},
        ]
    )
    _inject_remote_session(runtime, session)

    list_channel_messages = _require_runtime_method(runtime, "list_channel_messages")
    list_permission_requests = _require_runtime_method(runtime, "list_permission_requests")

    channels_payload = _call_or_fail(list_channel_messages, label="list_channel_messages", server_name="atlas")
    permissions_payload = _call_or_fail(list_permission_requests, label="list_permission_requests", server_name="atlas")
    channels = _normalize_rows(channels_payload, ("channels", "messages", "items", "requests"))
    permissions = _normalize_rows(permissions_payload, ("permissions", "requests", "items", "messages"))

    assert channels == [], (
        "P2-02 gate default expected channel list to be empty when channel/permission relay gate is disabled"
    )
    assert permissions == [], (
        "P2-02 gate default expected permission list to be empty when channel/permission relay gate is disabled"
    )


def test_mcp_runtime_channel_permission_gate_on_relays_session_notifications() -> None:
    runtime = _runtime_with_policy(
        {
            "mcp_channel_notifications_enabled": True,
            "mcp_permission_relay_enabled": True,
        }
    )
    session = _RelaySessionStub(
        notifications=[
            {
                "method": "notifications/channel/message",
                "params": {"server": "atlas", "channel": "alerts", "id": "msg_2", "text": "relay-ready"},
            },
            {
                "method": "notifications/permission/request",
                "params": {"server": "atlas", "request_id": "perm_2", "approved": None, "status": "pending"},
            },
        ]
    )
    _inject_remote_session(runtime, session)

    list_channel_messages = _require_runtime_method(runtime, "list_channel_messages")
    list_permission_requests = _require_runtime_method(runtime, "list_permission_requests")

    channels_payload = _call_or_fail(list_channel_messages, label="list_channel_messages", server_name="atlas")
    permissions_payload = _call_or_fail(list_permission_requests, label="list_permission_requests", server_name="atlas")
    channels = _normalize_rows(channels_payload, ("channels", "messages", "items", "requests"))
    permissions = _normalize_rows(permissions_payload, ("permissions", "requests", "items", "messages"))

    assert channels, "P2-02 relay expected list_channel_messages to expose at least one relayed notification when gate is on"
    assert permissions, (
        "P2-02 relay expected list_permission_requests to expose at least one relayed permission event when gate is on"
    )


def test_mcp_runtime_permission_respond_relays_to_session_request() -> None:
    runtime = _runtime_with_policy(
        {
            "mcp_channel_notifications_enabled": True,
            "mcp_permission_relay_enabled": True,
        }
    )
    session = _RelaySessionStub()
    _inject_remote_session(runtime, session)

    permission_respond = _require_runtime_method(
        runtime,
        "respond_permission_request",
        "permission_respond",
        "respond_permission",
        "respond_to_permission",
    )
    try:
        permission_respond(server_name="atlas", request_id="req_77", approved=False, reason="denied")
    except TypeError:
        permission_respond("atlas", "req_77", False, "denied")

    assert session.request_calls, (
        "P2-02 relay expected permission respond flow to call session.request, but no request was recorded by session stub"
    )
    method, params = session.request_calls[-1]
    assert method, "P2-02 relay expected forwarded permission respond call to include request method name"
    assert (
        params.get("request_id") == "req_77"
        or params.get("requestId") == "req_77"
        or params.get("id") == "req_77"
    ), (
        "P2-02 relay expected forwarded permission respond call params to carry request id req_77"
    )
