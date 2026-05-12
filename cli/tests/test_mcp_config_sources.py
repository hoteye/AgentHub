from __future__ import annotations

from cli.agent_cli.mcp.config import effective_mcp_configs
from cli.agent_cli.mcp.config_sources import (
    SOURCE_PLUGIN,
    SOURCE_RUNTIME_DYNAMIC,
    SOURCE_USER,
    SOURCE_WORKSPACE,
    canonical_config_fingerprint,
    collect_mcp_config_sources,
    normalize_source_items,
)


def test_collect_mcp_config_sources_orders_by_fixed_precedence() -> None:
    items = collect_mcp_config_sources(
        plugin={"p": {"url": "https://plugin.example/mcp"}},
        workspace={"w": {"url": "https://workspace.example/mcp"}},
        user={"u": {"url": "https://user.example/mcp"}},
        runtime_dynamic={"r": {"url": "https://runtime.example/mcp"}},
    )
    assert [item.source for item in items] == [
        SOURCE_RUNTIME_DYNAMIC,
        SOURCE_USER,
        SOURCE_WORKSPACE,
        SOURCE_PLUGIN,
    ]
    assert [item.name for item in items] == ["r", "u", "w", "p"]


def test_normalize_source_items_supports_mapping_and_list_payloads() -> None:
    mapping_items = normalize_source_items(
        SOURCE_USER,
        {"docs": {"url": "https://docs.example/mcp"}},
    )
    assert len(mapping_items) == 1
    assert mapping_items[0].name == "docs"
    assert mapping_items[0].enabled is True

    list_items = normalize_source_items(
        SOURCE_WORKSPACE,
        [
            {
                "name": "vector",
                "config": {"url": "https://vector.example/mcp"},
                "enabled": False,
                "metadata": {"origin": ".mcp.json"},
            }
        ],
    )
    assert len(list_items) == 1
    assert list_items[0].name == "vector"
    assert list_items[0].enabled is False
    assert list_items[0].metadata == {"origin": ".mcp.json"}


def test_canonical_config_fingerprint_is_content_based() -> None:
    left = {"url": "https://x.example/mcp", "headers": {"a": "1", "b": "2"}}
    right = {"headers": {"b": "2", "a": "1"}, "url": "https://x.example/mcp"}
    assert canonical_config_fingerprint(left) == canonical_config_fingerprint(right)


def test_normalize_source_items_mapping_supports_config_enabled_and_metadata() -> None:
    items = normalize_source_items(
        SOURCE_PLUGIN,
        {
            "search": {
                "config": {"url": "https://search.example/mcp"},
                "enabled": False,
                "metadata": {"origin": "plugin/.mcp.json"},
            }
        },
    )
    assert len(items) == 1
    item = items[0]
    assert item.name == "search"
    assert item.config == {"url": "https://search.example/mcp"}
    assert item.enabled is False
    assert item.metadata == {"origin": "plugin/.mcp.json"}


def test_normalize_source_items_expands_env_placeholders(monkeypatch) -> None:
    monkeypatch.setenv("AGENTHUB_MCP_HOST", "mcp.example.internal")
    items = normalize_source_items(
        SOURCE_USER,
        {
            "svc": {
                "url": "https://${AGENTHUB_MCP_HOST}/stream",
                "headers": {"X-Token": "${AGENTHUB_MCP_TOKEN}"},
            }
        },
    )
    assert len(items) == 1
    assert items[0].config["url"] == "https://mcp.example.internal/stream"
    assert items[0].config["headers"]["X-Token"] == "${AGENTHUB_MCP_TOKEN}"


def test_canonical_config_fingerprint_handles_nested_non_json_values() -> None:
    class _Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    left = {"headers": {"a": _Opaque()}, "args": ("--flag",)}
    right = {"args": ["--flag"], "headers": {"a": _Opaque()}}
    assert canonical_config_fingerprint(left) == canonical_config_fingerprint(right)


def test_normalize_source_items_resolves_inline_official_registry_reference() -> None:
    items = normalize_source_items(
        SOURCE_USER,
        {
            "docs": {
                "registry_ref": "official/docs",
                "registry_catalog": {
                    "official/docs": {
                        "transport": "http",
                        "url": "https://docs.example/mcp",
                    }
                },
                "config": {"timeout_sec": 3.0},
            }
        },
    )
    assert len(items) == 1
    item = items[0]
    assert item.config["url"] == "https://docs.example/mcp"
    assert item.config["timeout_sec"] == 3.0
    assert item.metadata["registry_ref"] == "official/docs"
    assert item.metadata["registry_origin"] == "inline_catalog"


def test_effective_mcp_configs_blocks_missing_registry_reference_with_reason() -> None:
    result = effective_mcp_configs(
        user={
            "docs": {
                "registry_ref": "official/docs",
                "registry_catalog": {},
            }
        }
    )
    assert result["effective"] == {}
    blocked = {(item["name"], item["reason"]) for item in result["blocked"]}
    assert ("docs", "registry.lookup_failed") in blocked


def test_effective_mcp_configs_blocks_untrusted_headers_helper() -> None:
    result = effective_mcp_configs(
        user={
            "docs": {
                "config": {
                    "url": "https://docs.example/mcp",
                    "headers_helper": {"type": "env", "map": {"Authorization": "DOCS_TOKEN"}},
                },
                "metadata": {"workspace_trust": "untrusted"},
            }
        }
    )
    assert result["effective"] == {}
    blocked = {(item["name"], item["reason"]) for item in result["blocked"]}
    assert ("docs", "headers_helper.untrusted_workspace") in blocked


def test_effective_mcp_configs_promotes_headers_helper_to_env_headers_when_trusted() -> None:
    result = effective_mcp_configs(
        user={
            "docs": {
                "config": {
                    "url": "https://docs.example/mcp",
                    "headers": {"X-Client": "agenthub"},
                    "headers_helper": {"type": "env", "map": {"Authorization": "DOCS_TOKEN"}},
                },
                "metadata": {"workspace_trust": "trusted"},
            }
        }
    )
    assert "docs" in result["effective"]
    headers = result["effective"]["docs"]["headers"]
    assert headers["X-Client"] == "agenthub"
    assert headers["Authorization"] == "$env:DOCS_TOKEN"
