from __future__ import annotations

from cli.agent_cli.mcp.client import MCPClient
from cli.agent_cli.mcp.config import effective_mcp_configs

from .mcp_testkit import build_client_configs, build_fake_snapshot, fake_mcp_sources, run_fake_serve_roundtrip


def test_mcp_e2e_fake_serve_roundtrip_respects_tool_policy() -> None:
    sources = fake_mcp_sources()
    merged = effective_mcp_configs(
        user=sources["user"],
        workspace=sources["workspace"],
        plugin=sources["plugin"],
        runtime_dynamic=sources["runtime_dynamic"],
    )
    client = MCPClient()
    results = client.connect_many(build_client_configs(merged["effective"]))
    snapshot = build_fake_snapshot(results)

    roundtrip = run_fake_serve_roundtrip(
        snapshot,
        deny_projected_tools={"mcp__ops__danger_delete_all"},
        call_arguments={"query": "index"},
    )

    init_result = roundtrip["initialize"]
    list_result = roundtrip["tools_list"]
    call_result = roundtrip["tools_call"]

    assert init_result["result"]["serverInfo"]["name"] == "agenthub_fake_mcp"
    listed_names = [item["name"] for item in list_result["result"]["tools"]]
    assert "mcp__atlas__search_docs" in listed_names
    assert "mcp__ops__danger_delete_all" not in listed_names

    assert "result" in call_result
    structured = call_result["result"]["structuredContent"]
    assert structured["ok"] is True
    assert structured["items"] == ["match:index"]


def test_mcp_e2e_fake_serve_roundtrip_unknown_tool_returns_error() -> None:
    sources = fake_mcp_sources()
    merged = effective_mcp_configs(
        user=sources["user"],
        workspace=sources["workspace"],
        plugin=sources["plugin"],
        runtime_dynamic=sources["runtime_dynamic"],
    )
    client = MCPClient()
    snapshot = build_fake_snapshot(client.connect_many(build_client_configs(merged["effective"])))

    roundtrip = run_fake_serve_roundtrip(
        snapshot,
        deny_projected_tools={"mcp__ops__danger_delete_all", "mcp__atlas__search_docs"},
    )
    call_result = roundtrip["tools_call"]
    assert "error" in call_result
    assert call_result["error"]["code"] == -32602
