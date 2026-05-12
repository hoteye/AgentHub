from __future__ import annotations

from cli.agent_cli.mcp.config import effective_mcp_configs
from cli.agent_cli.mcp.policy import policy_filter_mcp_items
from cli.agent_cli.mcp.config_sources import normalize_source_items


def test_effective_mcp_configs_applies_precedence_and_content_dedup() -> None:
    result = effective_mcp_configs(
        plugin={
            "docs_plugin": {"type": "http", "url": "https://docs.example/mcp"},
            "search": {"type": "http", "url": "https://search.example/mcp"},
        },
        workspace={
            "docs_workspace": {"type": "http", "url": "https://docs.example/mcp"},
            "search": {"type": "http", "url": "https://workspace-search.example/mcp"},
        },
    )
    assert "search" in result["effective"]
    assert result["effective"]["search"]["url"] == "https://workspace-search.example/mcp"
    assert "docs_workspace" in result["effective"]
    assert "docs_plugin" not in result["effective"]
    blocked_reasons = {item["reason"] for item in result["blocked"]}
    assert "dedup.duplicate_content" in blocked_reasons
    assert "dedup.shadowed_by_precedence" in blocked_reasons


def test_effective_mcp_configs_policy_allow_and_deny_with_reason() -> None:
    result = effective_mcp_configs(
        user={"allowed_user": {"url": "https://u.example/mcp"}},
        plugin={"blocked_plugin": {"url": "https://p.example/mcp"}},
        policy={
            "allow_sources": ["user", "workspace"],
            "deny_names": ["forbidden_name"],
        },
    )
    assert set(result["effective"]) == {"allowed_user"}
    assert {entry["name"] for entry in result["entries"]} == {"allowed_user"}
    blocked_by_name = {item["name"]: item["reason"] for item in result["blocked"]}
    assert blocked_by_name["blocked_plugin"] == "policy.not_in_allow_sources"


def test_effective_mcp_configs_enabled_state_is_stable_and_filters_effective() -> None:
    sources = {"alpha": {"url": "https://alpha.example/mcp"}, "beta": {"url": "https://beta.example/mcp"}}
    first = effective_mcp_configs(user=sources, enabled_state={"alpha": False})
    assert "alpha" not in first["effective"]
    assert "beta" in first["effective"]
    assert first["enabled_state"]["alpha"] is False
    assert first["enabled_state"]["beta"] is True

    second = effective_mcp_configs(user=sources, enabled_state=first["enabled_state"])
    assert second["enabled_state"] == first["enabled_state"]
    assert second["effective"] == first["effective"]


def test_policy_filter_can_require_enabled() -> None:
    items = normalize_source_items(
        "user",
        [
            {"name": "enabled_one", "config": {"url": "https://enabled.example/mcp"}, "enabled": True},
            {"name": "disabled_one", "config": {"url": "https://disabled.example/mcp"}, "enabled": False},
        ],
    )
    allowed, blocked = policy_filter_mcp_items(items, policy={"require_enabled": True})
    assert [item.name for item in allowed] == ["enabled_one"]
    assert blocked == [{"name": "disabled_one", "source": "user", "reason": "policy.require_enabled"}]


def test_effective_mcp_configs_dedup_respects_enabled_and_metadata_difference() -> None:
    result = effective_mcp_configs(
        user={
            "same_config_enabled": {
                "config": {"url": "https://docs.example/mcp"},
                "enabled": True,
                "metadata": {"origin": "user"},
            },
            "same_config_disabled": {
                "config": {"url": "https://docs.example/mcp"},
                "enabled": False,
                "metadata": {"origin": "user"},
            },
            "same_config_other_meta": {
                "config": {"url": "https://docs.example/mcp"},
                "enabled": True,
                "metadata": {"origin": "workspace"},
            },
        },
    )
    assert "same_config_enabled" in result["effective"]
    assert "same_config_other_meta" in result["effective"]
    assert "same_config_disabled" not in result["effective"]
    names = {entry["name"] for entry in result["entries"]}
    assert names == {"same_config_enabled", "same_config_disabled", "same_config_other_meta"}
    assert all(item["reason"] != "dedup.duplicate_content" for item in result["blocked"])


def test_policy_filter_sources_are_case_insensitive() -> None:
    result = effective_mcp_configs(
        user={"allowed_user": {"url": "https://u.example/mcp"}},
        plugin={"blocked_plugin": {"url": "https://p.example/mcp"}},
        policy={"allow_sources": ["USER"]},
    )
    assert set(result["effective"]) == {"allowed_user"}
    blocked_by_name = {item["name"]: item["reason"] for item in result["blocked"]}
    assert blocked_by_name["blocked_plugin"] == "policy.not_in_allow_sources"
