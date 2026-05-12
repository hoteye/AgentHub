from __future__ import annotations

from cli.agent_cli.mcp.client import MCPClient
from cli.agent_cli.mcp.config import effective_mcp_configs
from cli.agent_cli.mcp.resource_projection import list_projected_mcp_resources
from cli.agent_cli.mcp.tool_projection import project_mcp_tool_descriptors
from cli.agent_cli.runtime_core.mcp_commands import handle_mcp_command

from .mcp_testkit import (
    FakeMcpRuntime,
    build_client_configs,
    build_fake_snapshot,
    fake_mcp_sources,
    invoke_projected_tool,
)


def test_mcp_smoke_pipeline_load_connect_project_and_inspect() -> None:
    sources = fake_mcp_sources()
    merged = effective_mcp_configs(
        user=sources["user"],
        workspace=sources["workspace"],
        plugin=sources["plugin"],
        runtime_dynamic=sources["runtime_dynamic"],
        policy={"deny_names": ["legacy"]},
    )
    assert "legacy" not in merged["effective"]
    assert "atlas" in merged["effective"]
    assert "ops" in merged["effective"]

    client = MCPClient()
    results = client.connect_many(build_client_configs(merged["effective"]))
    assert results["atlas"].status == "connected"
    assert results["ops"].status == "connected"

    snapshot = build_fake_snapshot(results)
    projected_tools = project_mcp_tool_descriptors(snapshot)
    tool_names = [item["name"] for item in projected_tools]
    assert "mcp__atlas__search_docs" in tool_names
    assert "mcp__ops__danger_delete_all" in tool_names

    resources = list_projected_mcp_resources(snapshot, server_name="atlas")
    assert len(resources) == 1
    assert resources[0]["uri"] == "file:///atlas/readme.md"

    projected_output = invoke_projected_tool(
        snapshot,
        projected_name="mcp__atlas__search_docs",
        arguments={"query": "runtime"},
    )
    assert projected_output["ok"] is True
    assert projected_output["items"] == ["match:runtime"]

    runtime = FakeMcpRuntime(snapshot)
    list_text, events = handle_mcp_command(runtime, name="mcp", arg_text="list") or ("", [])
    inspect_text, _ = handle_mcp_command(runtime, name="mcp_inspect", arg_text="atlas") or ("", [])

    assert events == []
    assert "mcp servers" in list_text
    assert "atlas status=connected enabled=true" in list_text
    assert "target=atlas" in inspect_text
    assert "status=connected" in inspect_text
