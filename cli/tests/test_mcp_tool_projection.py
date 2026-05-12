from __future__ import annotations

from cli.agent_cli.mcp.resource_projection import (
    list_projected_mcp_resources,
    project_mcp_resource_provider_specs,
    project_mcp_resource_tool_descriptors,
    read_projected_mcp_resource,
)
from cli.agent_cli.mcp.tool_projection import (
    project_mcp_prompt_descriptors,
    project_mcp_provider_tool_specs,
    project_mcp_tool_descriptors,
)


def _snapshot() -> dict:
    return {
        "servers": {
            "atlas": {
                "status": "connected",
                "tools": [
                    {
                        "name": "search_docs",
                        "description": "Search documentation.",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                            "additionalProperties": False,
                        },
                    }
                ],
                "prompts": [
                    {
                        "name": "triage_bug",
                        "description": "Draft a bug triage report.",
                        "arguments_schema": {
                            "type": "object",
                            "properties": {"issue_id": {"type": "string"}},
                            "required": ["issue_id"],
                            "additionalProperties": False,
                        },
                    }
                ],
                "resources": [
                    {
                        "uri": "file:///atlas/readme.md",
                        "name": "Atlas README",
                        "description": "Server docs",
                        "mime_type": "text/markdown",
                        "text": "# Atlas",
                    }
                ],
            },
            "disabled_server": {
                "status": "disabled",
                "tools": [{"name": "should_not_show"}],
                "prompts": [{"name": "should_not_show"}],
                "resources": [{"uri": "file:///disabled/ignored.txt"}],
            },
            "beta": {
                "state": "connected",
                "tool_descriptors": {"ping": {"description": "Ping remote."}},
                "prompt_descriptors": {"ask": {"description": "Ask beta."}},
                "resource_descriptors": {
                    "file:///beta/config.json": {
                        "name": "Beta Config",
                        "mimeType": "application/json",
                        "contents": [{"text": "{\"ok\": true}"}],
                    }
                },
            },
        }
    }


def _connections_snapshot(order) -> dict:
    def _tool_payload(tool_name: str) -> dict:
        return {
            "name": tool_name,
            "description": f"Guard tool {tool_name}.",
            "input_schema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        }

    return {
        "connections": [
            {
                "name": server_name,
                "state": "connected",
                "tools": [_tool_payload(tool_name)],
            }
            for server_name, tool_name in order
        ]
    }


def test_projected_tool_descriptors_have_stable_order_and_approval_scope() -> None:
    ordering = [
        ("secondary", "beta_tool"),
        ("tertiary", "gamma_tool"),
        ("primary", "alpha_tool"),
    ]
    expected_names = [
        "mcp__primary__alpha_tool",
        "mcp__secondary__beta_tool",
        "mcp__tertiary__gamma_tool",
    ]

    forward = project_mcp_tool_descriptors(_connections_snapshot(ordering))
    backward = project_mcp_tool_descriptors(_connections_snapshot(list(reversed(ordering))))

    assert [descriptor["name"] for descriptor in forward] == expected_names
    assert [descriptor["name"] for descriptor in backward] == expected_names
    assert forward == backward

    approval_scopes = {descriptor["approval_scope"] for descriptor in forward}
    expected_scopes = {f"mcp.server:{server}" for server, _ in ordering}
    assert approval_scopes == expected_scopes

    ordered_scopes = [descriptor["approval_scope"] for descriptor in forward]
    expected_sequence = [f"mcp.server:{server}" for server in ["primary", "secondary", "tertiary"]]
    assert ordered_scopes == expected_sequence
    assert ordered_scopes == [descriptor["approval_scope"] for descriptor in backward]


def test_project_mcp_tools_from_connected_servers_only() -> None:
    tools = project_mcp_tool_descriptors(_snapshot())
    names = [item["name"] for item in tools]

    assert names == ["mcp__atlas__search_docs", "mcp__beta__ping"]
    assert tools[0]["server_name"] == "atlas"
    assert tools[0]["remote_name"] == "search_docs"
    assert tools[0]["parameters"]["required"] == ["query"]
    assert tools[0]["source"] == "mcp"
    assert tools[0]["tool_family"] == "mcp_remote"
    assert tools[0]["approval_required"] is True
    assert tools[0]["approval_family"] == "mcp_tool_call"
    assert tools[0]["approval_scope"] == "mcp.server:atlas"
    assert tools[0]["requires_confirmation"] is True
    assert tools[0]["mutates_ui"] is False


def test_projected_tool_descriptors_preserve_field_types_across_servers() -> None:
    projected_tools = project_mcp_tool_descriptors(_snapshot())
    assert projected_tools

    seen_servers = {descriptor["server_name"] for descriptor in projected_tools}
    assert {"atlas", "beta"}.issubset(seen_servers)

    for descriptor in projected_tools:
        assert isinstance(descriptor["name"], str)
        assert descriptor["name"].strip()

        assert isinstance(descriptor["server_name"], str)
        assert descriptor["server_name"]

        assert isinstance(descriptor["source"], str)
        assert isinstance(descriptor["tool_family"], str)

        assert isinstance(descriptor["approval_required"], bool)
        assert isinstance(descriptor["approval_family"], str)
        assert isinstance(descriptor["approval_scope"], str)
        assert descriptor["approval_scope"].startswith("mcp.server:")
        assert descriptor["approval_scope"].split(":", 1)[1] == descriptor["server_name"]
        observability = descriptor["observability"]
        assert isinstance(observability, dict)
        assert observability["schema_version"] == 1
        assert observability["latency_bucket_field"] == "approval_latency_bucket"
        assert observability["decision_trace_template"] == [
            "approval.requested",
            "approval.decided",
            "action.executed",
        ]
        assert observability["reason_codes"]["approved"] == "approval.approved"
        assert observability["reason_codes"]["rejected"] == "approval.rejected"
        assert observability["reason_codes"]["timed_out"] == "approval.timed_out"
        assert observability["reason_codes"]["expired"] == "approval.expired"
        snapshot = observability["tool_snapshot"]
        assert snapshot["projected_name"] == descriptor["name"]
        assert snapshot["server_name"] == descriptor["server_name"]
        assert snapshot["remote_name"] == descriptor["remote_name"]
        assert snapshot["connector_key"] == f"mcp:{descriptor['server_name']}"
        assert snapshot["approval_scope"] == descriptor["approval_scope"]


def test_project_mcp_prompt_descriptors_and_provider_specs() -> None:
    prompts = project_mcp_prompt_descriptors(_snapshot())
    provider_specs = project_mcp_provider_tool_specs(_snapshot())

    prompt_names = [item["name"] for item in prompts]
    provider_names = [item["function"]["name"] for item in provider_specs]
    assert prompt_names == ["mcp_prompt__atlas__triage_bug", "mcp_prompt__beta__ask"]
    assert provider_names == ["mcp__atlas__search_docs", "mcp__beta__ping"]
    assert all(item["type"] == "function" and item["strict"] for item in provider_specs)
    for item in provider_specs:
        observability = item["x_mcp_observability"]
        assert observability["schema_version"] == 1
        assert observability["latency_bucket_field"] == "approval_latency_bucket"
        assert observability["reason_codes"]["pending"] == "approval.pending"
        assert observability["reason_codes"]["approved"] == "approval.approved"


def test_resource_projection_list_read_and_tool_specs() -> None:
    snapshot = _snapshot()

    all_resources = list_projected_mcp_resources(snapshot)
    atlas_resources = list_projected_mcp_resources(snapshot, server_name="atlas")
    read_ok = read_projected_mcp_resource(snapshot, server_name="beta", uri="file:///beta/config.json")
    read_missing = read_projected_mcp_resource(snapshot, server_name="atlas", uri="file:///atlas/missing.txt")
    tool_descriptors = project_mcp_resource_tool_descriptors(snapshot)
    provider_specs = project_mcp_resource_provider_specs(snapshot)

    assert [item["uri"] for item in all_resources] == [
        "file:///atlas/readme.md",
        "file:///beta/config.json",
    ]
    assert len(atlas_resources) == 1
    assert atlas_resources[0]["server_name"] == "atlas"
    assert read_ok["ok"] is True
    assert read_ok["mime_type"] == "application/json"
    assert read_ok["contents"] == [{"text": "{\"ok\": true}"}]
    assert read_missing == {
        "ok": False,
        "error": "resource not found",
        "server_name": "atlas",
        "uri": "file:///atlas/missing.txt",
    }
    assert [item["name"] for item in tool_descriptors] == ["list_mcp_resources", "read_mcp_resource"]
    assert [item["function"]["name"] for item in provider_specs] == ["list_mcp_resources", "read_mcp_resource"]


def test_resource_projection_requires_server_and_uri_inputs() -> None:
    snapshot = _snapshot()

    missing_server = read_projected_mcp_resource(snapshot, server_name="", uri="file:///atlas/readme.md")
    missing_uri = read_projected_mcp_resource(snapshot, server_name="atlas", uri="")

    assert missing_server == {"ok": False, "error": "server_name and uri are required"}
    assert missing_uri == {"ok": False, "error": "server_name and uri are required"}


def test_resource_projection_ignores_unconnected_servers_and_preserves_text_and_blob_fields() -> None:
    snapshot = _snapshot()
    snapshot["servers"]["gamma"] = {
        "status": "connected",
        "resources": [
            {
                "uri": "file:///gamma/blob.bin",
                "name": "Gamma Blob",
                "mime_type": "application/octet-stream",
                "text": "preview",
                "blob": "AAEC",
            }
        ],
    }

    disconnected_resources = list_projected_mcp_resources(snapshot, server_name="disabled_server")
    gamma_resource = read_projected_mcp_resource(snapshot, server_name="gamma", uri="file:///gamma/blob.bin")
    tool_descriptors = project_mcp_resource_tool_descriptors(snapshot)

    assert disconnected_resources == []
    assert gamma_resource["ok"] is True
    assert gamma_resource["text"] == "preview"
    assert gamma_resource["blob"] == "AAEC"
    assert tool_descriptors[0]["connected_servers"] == ["atlas", "beta", "gamma"]
    assert tool_descriptors[1]["connected_servers"] == ["atlas", "beta", "gamma"]


def test_mcp_tool_projection_preserves_approval_and_observability_fields() -> None:
    projected_tools = project_mcp_tool_descriptors(_snapshot())

    assert projected_tools
    for descriptor in projected_tools:
        assert descriptor["source"] == "mcp"
        assert descriptor["tool_family"] == "mcp_remote"
        assert isinstance(descriptor["server_name"], str)
        assert descriptor["server_name"].strip()

        assert descriptor["approval_required"] is True
        assert descriptor["approval_family"] == "mcp_tool_call"
        approval_scope = descriptor["approval_scope"]
        assert isinstance(approval_scope, str)
        assert approval_scope.startswith("mcp.server:")
        assert approval_scope.split(":", 1)[1] == descriptor["server_name"]


def test_mcp_tool_projection_observability_contract_has_stable_snapshot_and_signal_fields() -> None:
    projected_tools = project_mcp_tool_descriptors(_snapshot())

    assert projected_tools
    for descriptor in projected_tools:
        observability = descriptor["observability"]
        assert observability["schema_version"] == 1
        assert observability["decision_trace_template"] == [
            "approval.requested",
            "approval.decided",
            "action.executed",
        ]
        assert observability["latency_bucket_field"] == "approval_latency_bucket"
        assert observability["tool_snapshot_fields"] == [
            "projected_name",
            "server_name",
            "remote_name",
            "connector_key",
            "approval_scope",
        ]
        snapshot = observability["tool_snapshot"]
        assert snapshot["projected_name"] == descriptor["name"]
        assert snapshot["server_name"] == descriptor["server_name"]
        assert snapshot["remote_name"] == descriptor["remote_name"]
        assert snapshot["connector_key"] == f"mcp:{descriptor['server_name']}"
        assert snapshot["approval_scope"] == descriptor["approval_scope"]
