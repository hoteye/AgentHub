from __future__ import annotations

import pytest

from cli.agent_cli.mcp.models import (
    McpPromptDescriptor,
    McpResourceDescriptor,
    McpRuntimeSnapshot,
    McpServerConfig,
    McpToolDescriptor,
    ScopedMcpServerConfig,
)
from cli.agent_cli.mcp.projection import (
    McpProjectionSnapshot,
    projection_snapshot_from_payload,
    runtime_snapshot_projection_payload,
)
from cli.agent_cli.mcp.state import (
    McpConfigScope,
    McpConfigState,
    McpConnectionState,
    McpProjectionState,
    McpTransportKind,
)


def test_mcp_server_config_and_scoped_round_trip() -> None:
    config = McpServerConfig(
        server_name="docs",
        transport=McpTransportKind.HTTP,
        url="https://docs.example/mcp",
        headers={"Authorization": "Bearer token"},
        timeout_seconds=45,
        metadata={"origin": "plugin"},
    )
    scoped = ScopedMcpServerConfig(
        config=config,
        scope=McpConfigScope.PLUGIN,
        config_state=McpConfigState.ENABLED,
        source="plugins/docs/.mcp.json",
        priority=50,
    )

    restored = ScopedMcpServerConfig.from_dict(scoped.to_dict())

    assert restored.to_dict() == scoped.to_dict()


def test_runtime_snapshot_round_trip_preserves_nested_descriptors() -> None:
    snapshot = McpRuntimeSnapshot(
        servers=[
            ScopedMcpServerConfig(
                config=McpServerConfig(
                    server_name="docs",
                    transport=McpTransportKind.SSE,
                    url="https://docs.example/sse",
                ),
                scope=McpConfigScope.WORKSPACE,
                config_state=McpConfigState.ENABLED,
            )
        ],
        connection_states={
            "docs": McpConnectionState.CONNECTED,
            "broken": McpConnectionState.FAILED,
        },
        tools=[
            McpToolDescriptor(
                server_name="docs",
                name="search_docs",
                title="Search docs",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ],
        prompts=[
            McpPromptDescriptor(
                server_name="docs",
                name="summarize_page",
                arguments=[{"name": "url", "required": True}],
            )
        ],
        resources=[
            McpResourceDescriptor(
                server_name="docs",
                uri="docs://home",
                mime_type="text/markdown",
            )
        ],
        projection_state=McpProjectionState.PARTIAL,
    )

    restored = McpRuntimeSnapshot.from_dict(snapshot.to_dict())

    assert restored.to_dict() == snapshot.to_dict()


def test_invalid_state_values_raise_value_error() -> None:
    with pytest.raises(ValueError, match="mcp_server_config.transport"):
        McpServerConfig.from_dict({"server_name": "docs", "transport": "ftp"})

    with pytest.raises(ValueError, match="scoped_mcp_server_config.scope"):
        ScopedMcpServerConfig.from_dict(
            {
                "scope": "invalid_scope",
                "config": {"server_name": "docs", "transport": "http"},
            }
        )

    with pytest.raises(ValueError, match="mcp_runtime_snapshot.connection_states\\[docs\\]"):
        McpRuntimeSnapshot.from_dict(
            {
                "connection_states": {"docs": "unknown"},
            }
        )


def test_scope_transport_and_connection_state_accepted_values_round_trip() -> None:
    for transport in McpTransportKind:
        model = McpServerConfig.from_dict({"server_name": "srv", "transport": transport.value})
        assert model.transport is transport

    for scope in McpConfigScope:
        model = ScopedMcpServerConfig.from_dict(
            {
                "scope": scope.value,
                "config": {"server_name": "srv", "transport": "stdio"},
                "config_state": "enabled",
            }
        )
        assert model.scope is scope

    snapshot = McpRuntimeSnapshot.from_dict(
        {
            "connection_states": {state.value: state.value for state in McpConnectionState},
            "projection_state": "ready",
        }
    )
    assert set(snapshot.connection_states.values()) == set(McpConnectionState)


def test_snapshot_projection_contract_is_stable() -> None:
    snapshot = McpRuntimeSnapshot(
        tools=[McpToolDescriptor(server_name="docs", name="search_docs")],
        prompts=[McpPromptDescriptor(server_name="docs", name="summarize_page")],
        resources=[McpResourceDescriptor(server_name="docs", uri="docs://home")],
        connection_states={"docs": McpConnectionState.CONNECTED},
        projection_state=McpProjectionState.READY,
    )

    payload = runtime_snapshot_projection_payload(snapshot)
    projection = projection_snapshot_from_payload(payload)
    restored_projection = McpProjectionSnapshot.from_dict(projection.to_dict())

    assert payload["tool_names"] == ["search_docs"]
    assert payload["prompt_names"] == ["summarize_page"]
    assert payload["resource_uris"] == ["docs://home"]
    assert payload["connections"] == {"docs": "connected"}
    assert restored_projection.to_dict() == projection.to_dict()

