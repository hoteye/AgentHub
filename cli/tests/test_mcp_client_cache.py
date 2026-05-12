from __future__ import annotations

from typing import Any

from cli.agent_cli.mcp.auth import MCPAuthConfig
from cli.agent_cli.mcp.client import MCPClient, MCPServerConfig
from cli.agent_cli.mcp.transports import MCPTransportConfig, MCPTransportConnection, MCPTransportError


def test_cache_key_changes_when_auth_metadata_or_transport_changes(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_connect_transport(config: MCPTransportConfig) -> MCPTransportConnection:
        calls.append(config.url)
        return MCPTransportConnection(transport=config.transport, endpoint=f"endpoint-{len(calls)}")

    monkeypatch.setattr("cli.agent_cli.mcp.client.connect_transport", _fake_connect_transport)

    client = MCPClient()
    base = MCPServerConfig(
        name="atlas",
        transport=MCPTransportConfig(
            transport="http",
            url="http://example.local/health",
            auth=MCPAuthConfig(token="token-a", headers={"X-Tenant": "alpha"}),
        ),
        metadata={"scope": "read"},
    )

    first = client.connect(base)
    second = client.connect(base)
    assert first.status == "connected"
    assert second.from_cache is True
    assert len(calls) == 1

    token_changed = MCPServerConfig(
        name="atlas",
        transport=MCPTransportConfig(
            transport="http",
            url="http://example.local/health",
            auth=MCPAuthConfig(token="token-b", headers={"X-Tenant": "alpha"}),
        ),
        metadata={"scope": "read"},
    )
    metadata_changed = MCPServerConfig(
        name="atlas",
        transport=MCPTransportConfig(
            transport="http",
            url="http://example.local/health",
            auth=MCPAuthConfig(token="token-b", headers={"X-Tenant": "alpha"}),
        ),
        metadata={"scope": "write"},
    )
    transport_changed = MCPServerConfig(
        name="atlas",
        transport=MCPTransportConfig(
            transport="http",
            url="http://example.local/health?v=2",
            auth=MCPAuthConfig(token="token-b", headers={"X-Tenant": "alpha"}),
        ),
        metadata={"scope": "write"},
    )

    third = client.connect(token_changed)
    fourth = client.connect(metadata_changed)
    fifth = client.connect(transport_changed)

    assert third.from_cache is False
    assert fourth.from_cache is False
    assert fifth.from_cache is False
    assert client.cache_size() == 4
    assert len(calls) == 4


def test_invalidate_removes_only_target_server_cache(monkeypatch) -> None:
    def _fake_connect_transport(config: MCPTransportConfig) -> MCPTransportConnection:
        return MCPTransportConnection(transport=config.transport, endpoint=config.url or "stdio")

    monkeypatch.setattr("cli.agent_cli.mcp.client.connect_transport", _fake_connect_transport)

    client = MCPClient()
    alpha = MCPServerConfig(name="alpha", transport=MCPTransportConfig(transport="http", url="http://alpha.local"))
    alpha2 = MCPServerConfig(name="alpha2", transport=MCPTransportConfig(transport="http", url="http://alpha2.local"))

    client.connect(alpha)
    client.connect(alpha2)
    assert client.cache_size() == 2

    client.invalidate(" alpha ")

    assert client.get_cached_connection(alpha) is None
    assert client.get_cached_connection(alpha2) is not None
    assert client.cache_size() == 1


def test_reconnect_evicts_old_handle_and_returns_new_connection(monkeypatch) -> None:
    counter = {"value": 0}

    def _fake_connect_transport(config: MCPTransportConfig) -> MCPTransportConnection:
        counter["value"] += 1
        return MCPTransportConnection(transport=config.transport, endpoint=f"{config.url}#{counter['value']}")

    monkeypatch.setattr("cli.agent_cli.mcp.client.connect_transport", _fake_connect_transport)

    client = MCPClient()
    config = MCPServerConfig(name="ops", transport=MCPTransportConfig(transport="http", url="http://ops.local"))

    first = client.connect(config)
    second = client.reconnect(config)

    assert first.status == "connected"
    assert second.status == "connected"
    assert first.handle is not None
    assert second.handle is not None
    assert second.from_cache is False
    assert second.handle is not first.handle
    assert counter["value"] == 2


def test_from_cache_only_hits_exact_fingerprint(monkeypatch) -> None:
    calls = {"value": 0}

    def _fake_connect_transport(config: MCPTransportConfig) -> MCPTransportConnection:
        calls["value"] += 1
        return MCPTransportConnection(transport=config.transport, endpoint=f"{config.url}#{calls['value']}")

    monkeypatch.setattr("cli.agent_cli.mcp.client.connect_transport", _fake_connect_transport)

    client = MCPClient()
    config_a = MCPServerConfig(
        name="cache_http",
        transport=MCPTransportConfig(transport="http", url="http://cache.local"),
        metadata={"role": "reader"},
    )
    config_b = MCPServerConfig(
        name="cache_http",
        transport=MCPTransportConfig(transport="http", url="http://cache.local"),
        metadata={"role": "writer"},
    )

    first = client.connect(config_a)
    second = client.connect(config_a)
    third = client.connect(config_b)

    assert first.from_cache is False
    assert second.from_cache is True
    assert third.from_cache is False
    assert calls["value"] == 2


def test_remote_descriptor_cache_invalidation_by_list_changed_notification(monkeypatch) -> None:
    class _Session:
        def __init__(self) -> None:
            self.version = 1
            self.tools_list_calls = 0
            self.prompts_list_calls = 0
            self.resources_list_calls = 0
            self.notifications: list[dict[str, Any]] = []

        def tools_list(self) -> list[dict[str, Any]]:
            self.tools_list_calls += 1
            return [{"name": f"tool_v{self.version}"}]

        def prompts_list(self) -> list[dict[str, Any]]:
            self.prompts_list_calls += 1
            return [{"name": f"prompt_v{self.version}"}]

        def resources_list(self) -> list[dict[str, Any]]:
            self.resources_list_calls += 1
            return [{"uri": f"file:///v{self.version}.md", "name": f"resource_v{self.version}"}]

        def drain_notifications(self) -> list[dict[str, Any]]:
            items = list(self.notifications)
            self.notifications = []
            return items

    session = _Session()

    def _fake_connect_transport(config: MCPTransportConfig) -> MCPTransportConnection:
        return MCPTransportConnection(transport=config.transport, endpoint=config.url or "stdio", session=session)

    monkeypatch.setattr("cli.agent_cli.mcp.client.connect_transport", _fake_connect_transport)

    client = MCPClient()
    config = MCPServerConfig(name="atlas", transport=MCPTransportConfig(transport="http", url="http://atlas.local"))
    handle = client.connect(config).handle
    assert handle is not None

    first_tools = client.remote_tools(name="atlas", session=handle.session)
    first_prompts = client.remote_prompts(name="atlas", session=handle.session)
    first_resources = client.remote_resources(name="atlas", session=handle.session)

    session.version = 2
    cached_tools = client.remote_tools(name="atlas", session=handle.session)
    cached_prompts = client.remote_prompts(name="atlas", session=handle.session)
    cached_resources = client.remote_resources(name="atlas", session=handle.session)

    assert first_tools == cached_tools == [{"name": "tool_v1"}]
    assert first_prompts == cached_prompts == [{"name": "prompt_v1"}]
    assert first_resources == cached_resources == [{"uri": "file:///v1.md", "name": "resource_v1"}]
    assert session.tools_list_calls == 1
    assert session.prompts_list_calls == 1
    assert session.resources_list_calls == 1

    session.notifications = [
        {"method": "notifications/tools/list_changed"},
        {"method": "notifications/prompts/list_changed"},
        {"method": "notifications/resources/list_changed"},
    ]

    refreshed_tools = client.remote_tools(name="atlas", session=handle.session)
    refreshed_prompts = client.remote_prompts(name="atlas", session=handle.session)
    refreshed_resources = client.remote_resources(name="atlas", session=handle.session)

    assert refreshed_tools == [{"name": "tool_v2"}]
    assert refreshed_prompts == [{"name": "prompt_v2"}]
    assert refreshed_resources == [{"uri": "file:///v2.md", "name": "resource_v2"}]
    assert session.tools_list_calls == 2
    assert session.prompts_list_calls == 2
    assert session.resources_list_calls == 2


def test_non_stdio_connect_uses_backoff_between_failures(monkeypatch) -> None:
    now = {"value": 1000.0}
    attempts = {"value": 0}

    def _fake_time() -> float:
        return now["value"]

    def _fake_connect_transport(config: MCPTransportConfig) -> MCPTransportConnection:
        attempts["value"] += 1
        if attempts["value"] == 1:
            raise MCPTransportError("network down", error_code="network-error")
        return MCPTransportConnection(transport=config.transport, endpoint=config.url)

    monkeypatch.setattr("cli.agent_cli.mcp.client.time.time", _fake_time)
    monkeypatch.setattr("cli.agent_cli.mcp.client.connect_transport", _fake_connect_transport)

    client = MCPClient()
    config = MCPServerConfig(name="ops", transport=MCPTransportConfig(transport="http", url="http://ops.local"))

    first = client.connect(config)
    blocked = client.connect(config)

    assert first.status == "failed"
    assert first.retry_attempt == 1
    assert first.retry_in_sec == 0.5
    assert blocked.status == "failed"
    assert blocked.error_code == "retry-backoff"
    assert blocked.retry_attempt == 1
    assert attempts["value"] == 1

    now["value"] += 0.6
    recovered = client.connect(config)

    assert recovered.status == "connected"
    assert recovered.retry_attempt == 0
    assert attempts["value"] == 2


def test_prune_stale_servers_removes_cache_retry_and_descriptors(monkeypatch) -> None:
    class _Session:
        @staticmethod
        def tools_list() -> list[dict[str, Any]]:
            return [{"name": "remote_tool"}]

        @staticmethod
        def drain_notifications() -> list[dict[str, Any]]:
            return []

    def _fake_connect_transport(config: MCPTransportConfig) -> MCPTransportConnection:
        return MCPTransportConnection(transport=config.transport, endpoint=config.url or "stdio", session=_Session())

    monkeypatch.setattr("cli.agent_cli.mcp.client.connect_transport", _fake_connect_transport)

    client = MCPClient()
    alpha = MCPServerConfig(name="alpha", transport=MCPTransportConfig(transport="http", url="http://alpha.local"))
    beta = MCPServerConfig(name="beta", transport=MCPTransportConfig(transport="http", url="http://beta.local"))

    alpha_handle = client.connect(alpha).handle
    beta_handle = client.connect(beta).handle
    assert alpha_handle is not None
    assert beta_handle is not None
    assert client.remote_tools(name="alpha", session=alpha_handle.session) == [{"name": "remote_tool"}]
    assert client.remote_tools(name="beta", session=beta_handle.session) == [{"name": "remote_tool"}]
    assert client.cache_size() == 2

    client.prune_stale_servers({"alpha"})

    assert client.cache_size() == 1
    assert client.get_cached_connection_by_name("alpha") is not None
    assert client.get_cached_connection_by_name("beta") is None
