from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core.command_parsing import split_command
from cli.agent_cli.runtime_core.mcp_commands import handle_mcp_command
from cli.agent_cli.slash_parser import parse_slash_invocation


class _McpRuntimeStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.dynamic_configs: dict[str, dict[str, Any]] = {}
        self.base_configs: dict[str, dict[str, Any]] = {
            "docs": {"transport": "http", "url": "https://docs.example/mcp"},
            "github": {"transport": "sse", "url": "https://github.example/mcp"},
        }

    def list_status(self) -> dict[str, Any]:
        self.calls.append(("list_status", None))
        return {
            "servers": [
                {"name": "docs", "status": "connected", "enabled": True},
                {"name": "github", "status": "disconnected", "enabled": False},
            ]
        }

    def reconnect(self, target: str) -> dict[str, Any]:
        self.calls.append(("reconnect", target))
        return {"status": "ok"}

    def enable(self, target: str) -> dict[str, Any]:
        self.calls.append(("enable", target))
        return {"status": "ok"}

    def disable(self, target: str) -> dict[str, Any]:
        self.calls.append(("disable", target))
        return {"status": "ok"}

    def inspect(self, target: str) -> dict[str, Any]:
        self.calls.append(("inspect", target))
        config = dict(self.dynamic_configs.get(target) or self.base_configs.get(target) or {})
        return {"status": "connected", "enabled": True, "scope": "workspace", "reason": "healthy", "config": config}

    def set_runtime_dynamic(self, name: str, config: dict[str, Any] | None) -> None:
        self.calls.append(("set_runtime_dynamic", name))
        if not isinstance(config, dict):
            self.dynamic_configs.pop(name, None)
            return
        self.dynamic_configs[name] = dict(config)

    def list_resources(self, *, server_name: str | None = None) -> list[dict[str, Any]]:
        self.calls.append(("list_resources", server_name))
        items = [
            {"server_name": "docs", "uri": "file:///docs/readme.md", "name": "Docs README"},
            {"server_name": "atlas", "uri": "file:///atlas/runbook.md", "name": "Atlas Runbook"},
        ]
        if server_name:
            return [item for item in items if item["server_name"] == server_name]
        return items

    def read_resource(self, *, server_name: str, uri: str) -> dict[str, Any]:
        self.calls.append(("read_resource", f"{server_name}|{uri}"))
        if server_name == "atlas" and uri == "file:///atlas/runbook.md":
            return {
                "ok": True,
                "server_name": server_name,
                "uri": uri,
                "mime_type": "text/markdown",
                "contents": [{"text": "# Atlas Runbook"}],
            }
        return {"ok": False, "error": "resource not found", "server_name": server_name, "uri": uri}

    def call_projected_tool(self, *, projected_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(("call_projected_tool", projected_name))
        if projected_name == "mcp__atlas__search_docs":
            query = str((arguments or {}).get("query") or "").strip()
            return {
                "ok": True,
                "projected_name": projected_name,
                "server_name": "atlas",
                "remote_name": "search_docs",
                "result": {"content": [{"type": "text", "text": f"match:{query}"}], "isError": False},
            }
        return {"ok": False, "projected_name": projected_name, "error": "unknown projected mcp tool"}

    def list_channels(self, *, server_name: str | None = None) -> dict[str, Any]:
        self.calls.append(("list_channels", server_name))
        items = [
            {"server": "docs", "channel": "default", "status": "open"},
            {"server": "atlas", "channel": "alerts", "status": "muted"},
        ]
        if server_name:
            items = [item for item in items if item["server"] == server_name]
        return {"channels": items}

    def list_permissions(self, *, server_name: str | None = None) -> dict[str, Any]:
        self.calls.append(("list_permissions", server_name))
        items = [
            {"server": "docs", "request_id": "req_1", "approved": None, "status": "pending"},
            {"server": "atlas", "request_id": "req_2", "approved": True, "status": "approved"},
        ]
        if server_name:
            items = [item for item in items if item["server"] == server_name]
        return {"permissions": items}

    def respond_permission(
        self,
        *,
        server_name: str,
        request_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("respond_permission", f"{server_name}|{request_id}|{approved}|{reason or ''}"))
        return {
            "status": "ok",
            "server": server_name,
            "request_id": request_id,
            "approved": approved,
            "reason": reason or "",
        }


class _RuntimeStub:
    def __init__(self, mcp_runtime: Any | None = None) -> None:
        self._mcp_runtime = mcp_runtime

    def get_mcp_runtime(self) -> Any | None:
        return self._mcp_runtime

    @staticmethod
    def _parse_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
        parts = [item for item in str(arg_text or "").split() if item]
        options: dict[str, Any] = {}
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


class _RuntimeNoParseArgsStub:
    def __init__(self, mcp_runtime: Any | None = None) -> None:
        self._mcp_runtime = mcp_runtime

    def get_mcp_runtime(self) -> Any | None:
        return self._mcp_runtime


def test_split_command_normalizes_mcp_permission_surface_keywords() -> None:
    name, arg_text = split_command(
        "/mcp permission respond server atlas request-id req_77 approved false reason denied"
    )

    assert name == "mcp"
    assert arg_text == "permission respond --server atlas --request-id req_77 --approved false --reason denied"


def test_split_command_normalizes_mcp_resource_and_tool_call_surface_keywords() -> None:
    resource_name, resource_args = split_command("/mcp_resource read server atlas uri file:///atlas/runbook.md")
    tool_name, tool_args = split_command(
        "/mcp_tool_call projected-name mcp__atlas__search_docs arguments-json '{\"query\":\"runtime\"}'"
    )

    assert resource_name == "mcp_resource"
    assert resource_args == "read --server atlas --uri file:///atlas/runbook.md"
    assert tool_name == "mcp_tool_call"
    assert tool_args == "--projected-name mcp__atlas__search_docs --arguments-json '{\"query\":\"runtime\"}'"


def test_mcp_list_reads_runtime_status_via_getter() -> None:
    runtime = _RuntimeStub(_McpRuntimeStub())

    text, events = handle_mcp_command(runtime, name="mcp", arg_text="") or ("", [])

    assert events == []
    assert "mcp servers" in text
    assert "count=2" in text
    assert "docs status=connected enabled=true" in text
    assert "github status=disconnected enabled=false" in text


def test_mcp_reconnect_requires_target() -> None:
    text, events = handle_mcp_command(_RuntimeStub(_McpRuntimeStub()), name="mcp_reconnect", arg_text="") or ("", [])
    assert events == []
    assert text == "Usage: /mcp_reconnect <server|all>"


def test_mcp_mutation_commands_dispatch_to_runtime() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeStub(mcp_runtime)

    reconnect_text, _ = handle_mcp_command(runtime, name="mcp_reconnect", arg_text="docs") or ("", [])
    enable_text, _ = handle_mcp_command(runtime, name="mcp_enable", arg_text="github") or ("", [])
    disable_text, _ = handle_mcp_command(runtime, name="mcp_disable", arg_text="all") or ("", [])

    assert "mcp reconnect requested" in reconnect_text
    assert "mcp enable requested" in enable_text
    assert "mcp disable requested" in disable_text
    assert ("reconnect", "docs") in mcp_runtime.calls
    assert ("enable", "github") in mcp_runtime.calls
    assert ("disable", "all") in mcp_runtime.calls


def test_mcp_inspect_formats_runtime_payload() -> None:
    runtime = _RuntimeStub(_McpRuntimeStub())

    text, events = handle_mcp_command(runtime, name="mcp_inspect", arg_text="docs") or ("", [])

    assert events == []
    assert "mcp server inspect" in text
    assert "target=docs" in text
    assert "status=connected" in text
    assert "enabled=true" in text
    assert "scope=workspace" in text
    assert "reason=healthy" in text


def test_mcp_runtime_unavailable_returns_message() -> None:
    text, events = handle_mcp_command(_RuntimeStub(None), name="mcp", arg_text="list") or ("", [])
    assert events == []
    assert text == "mcp runtime unavailable"


def test_mcp_value_error_surfaces_to_operator() -> None:
    class _FailingMcpRuntime:
        def inspect(self, target: str) -> dict[str, Any]:
            raise ValueError(f"unknown mcp server: {target}")

    text, events = handle_mcp_command(
        _RuntimeStub(_FailingMcpRuntime()),
        name="mcp_inspect",
        arg_text="missing",
    ) or ("", [])
    assert events == []
    assert text == "unknown mcp server: missing"


def test_mcp_subcommand_mode_works_for_list_and_inspect() -> None:
    runtime = _RuntimeStub(_McpRuntimeStub())

    list_text, _ = handle_mcp_command(runtime, name="mcp", arg_text="list") or ("", [])
    inspect_text, _ = handle_mcp_command(runtime, name="mcp", arg_text="inspect docs") or ("", [])

    assert "mcp servers" in list_text
    assert "mcp server inspect" in inspect_text


def test_mcp_permission_slash_invocation_native_path_does_not_require_runtime_parse_args() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeNoParseArgsStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp",
        arg_text="",
        slash_invocation=parse_slash_invocation(
            "/mcp permission respond server atlas request-id req_77 approved false reason denied"
        ),
    ) or ("", [])

    assert events == []
    assert "mcp permission respond" in text
    assert "approved=false" in text
    assert ("respond_permission", "atlas|req_77|False|denied") in mcp_runtime.calls


def test_mcp_tool_call_slash_invocation_native_path_does_not_require_runtime_parse_args() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeNoParseArgsStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp_tool_call",
        arg_text="",
        slash_invocation=parse_slash_invocation(
            "/mcp_tool_call projected-name mcp__atlas__search_docs arguments-json '{\"query\":\"runtime\"}'"
        ),
    ) or ("", [])

    assert events == []
    assert "mcp tool call" in text
    assert "match:runtime" in text
    assert ("call_projected_tool", "mcp__atlas__search_docs") in mcp_runtime.calls


def test_mcp_resource_requires_valid_subcommand_and_read_arguments() -> None:
    runtime = _RuntimeStub(_McpRuntimeStub())

    usage_text, usage_events = handle_mcp_command(runtime, name="mcp_resource", arg_text="") or ("", [])
    read_usage_text, read_usage_events = handle_mcp_command(
        runtime,
        name="mcp_resource",
        arg_text="read --server atlas",
    ) or ("", [])

    assert usage_events == []
    assert read_usage_events == []
    assert usage_text == "Usage: /mcp_resource <list|read> ..."
    assert read_usage_text == "Usage: /mcp_resource read server <server> uri <uri>"


def test_mcp_resource_list_passes_server_filter_and_formats_items() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp_resource",
        arg_text="list --server atlas",
    ) or ("", [])

    assert events == []
    assert ("list_resources", "atlas") in mcp_runtime.calls
    assert "mcp resources" in text
    assert "server=atlas" in text
    assert "count=1" in text
    assert "atlas file:///atlas/runbook.md Atlas Runbook" in text


def test_mcp_resource_read_formats_missing_resource_error() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp_resource",
        arg_text="read --server atlas --uri file:///atlas/missing.md",
    ) or ("", [])

    assert events == []
    assert ("read_resource", "atlas|file:///atlas/missing.md") in mcp_runtime.calls
    assert "mcp resource read" in text
    assert "ok=false" in text
    assert "error=resource not found" in text


def test_mcp_tool_call_dispatches_projected_tool_and_formats_result() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp_tool_call",
        arg_text='--projected-name mcp__atlas__search_docs --arguments-json {"query":"runtime"}',
    ) or ("", [])

    assert events == []
    assert ("call_projected_tool", "mcp__atlas__search_docs") in mcp_runtime.calls
    assert "mcp tool call" in text
    assert "ok=true" in text
    assert "server=atlas" in text
    assert "remote_name=search_docs" in text
    assert "text=match:runtime" in text


def test_mcp_auth_set_updates_runtime_dynamic_auth_and_reconnects() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp_auth",
        arg_text='--server docs --token token_123 --headers-json {"X-Tenant":"alpha"}',
    ) or ("", [])

    assert events == []
    assert ("set_runtime_dynamic", "docs") in mcp_runtime.calls
    assert ("reconnect", "docs") in mcp_runtime.calls
    auth_payload = mcp_runtime.dynamic_configs["docs"]["auth"]
    assert auth_payload["token"] == "token_123"
    assert auth_payload["headers"]["X-Tenant"] == "alpha"
    assert "mcp auth updated" in text
    assert "status=connected" in text


def test_mcp_auth_callback_mode_accepts_callback_json_and_marks_received() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp_auth_callback",
        arg_text='--server docs --callback-json {"access_token":"cb_token","headers":{"X-Trace":"1"}}',
    ) or ("", [])

    assert events == []
    auth_payload = mcp_runtime.dynamic_configs["docs"]["auth"]
    assert auth_payload["token"] == "cb_token"
    assert auth_payload["headers"]["X-Trace"] == "1"
    assert auth_payload["callback"]["received"] is True
    assert "mode=callback" in text


def test_mcp_auth_clear_removes_auth_from_runtime_dynamic() -> None:
    mcp_runtime = _McpRuntimeStub()
    mcp_runtime.dynamic_configs["docs"] = {
        "transport": "http",
        "url": "https://docs.example/mcp",
        "auth": {"token": "old_token"},
    }
    runtime = _RuntimeStub(mcp_runtime)

    text, events = handle_mcp_command(runtime, name="mcp_auth_clear", arg_text="--server docs") or ("", [])

    assert events == []
    assert ("set_runtime_dynamic", "docs") in mcp_runtime.calls
    assert ("reconnect", "docs") in mcp_runtime.calls
    assert "auth" not in mcp_runtime.dynamic_configs["docs"]
    assert "mode=clear" in text


def test_mcp_channel_list_formats_count_and_server_filter() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp",
        arg_text="channel list --server atlas",
    ) or ("", [])

    assert events == []
    assert ("list_channels", "atlas") in mcp_runtime.calls
    assert "mcp channels" in text
    assert "server=atlas" in text
    assert "count=1" in text
    assert "server=atlas channel=alerts status=muted" in text


def test_mcp_permission_list_formats_rows() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp",
        arg_text="permission list",
    ) or ("", [])

    assert events == []
    assert ("list_permissions", None) in mcp_runtime.calls
    assert "mcp permissions" in text
    assert "count=2" in text
    assert "server=docs request_id=req_1 approved=- status=pending" in text
    assert "server=atlas request_id=req_2 approved=true status=approved" in text


def test_mcp_permission_respond_requires_required_flags() -> None:
    runtime = _RuntimeStub(_McpRuntimeStub())

    text, events = handle_mcp_command(
        runtime,
        name="mcp",
        arg_text="permission respond --server atlas --request-id req_77",
    ) or ("", [])

    assert events == []
    assert (
        text
        == "Usage: /mcp permission respond server <server> request-id <id> approved <true|false> [reason <text>]"
    )


def test_mcp_permission_respond_dispatches_and_formats_response() -> None:
    mcp_runtime = _McpRuntimeStub()
    runtime = _RuntimeStub(mcp_runtime)

    text, events = handle_mcp_command(
        runtime,
        name="mcp",
        arg_text="permission respond --server atlas --request-id req_77 --approved false --reason denied",
    ) or ("", [])

    assert events == []
    assert ("respond_permission", "atlas|req_77|False|denied") in mcp_runtime.calls
    assert "mcp permission respond" in text
    assert "server=atlas" in text
    assert "request_id=req_77" in text
    assert "approved=false" in text
    assert "status=ok" in text
    assert "reason=denied" in text


def test_mcp_permission_requires_valid_subcommand_usage() -> None:
    runtime = _RuntimeStub(_McpRuntimeStub())

    text, events = handle_mcp_command(
        runtime,
        name="mcp",
        arg_text="permission",
    ) or ("", [])

    assert events == []
    assert text == "Usage: /mcp permission <list|respond> ..."


def test_mcp_channel_requires_valid_subcommand_usage() -> None:
    runtime = _RuntimeStub(_McpRuntimeStub())

    text, events = handle_mcp_command(
        runtime,
        name="mcp",
        arg_text="channel watch",
    ) or ("", [])

    assert events == []
    assert text == "Usage: /mcp channel [list] [server <server>]"
