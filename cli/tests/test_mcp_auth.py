from __future__ import annotations

from cli.agent_cli.mcp.auth import (
    MCPAuthConfig,
    auth_config_from_server_config,
    has_header,
    is_auth_status_code,
    merge_auth_headers,
    with_auth_config,
)


def test_merge_auth_headers_uses_token_when_authorization_missing() -> None:
    merged = merge_auth_headers(
        base_headers={"X-Base": "1"},
        auth=MCPAuthConfig(token="abc"),
    )
    assert merged["Authorization"] == "Bearer abc"
    assert merged["X-Base"] == "1"


def test_merge_auth_headers_preserves_existing_authorization_case_insensitive() -> None:
    merged = merge_auth_headers(
        base_headers={"authorization": "Bearer base"},
        auth=MCPAuthConfig(token="override_attempt"),
    )
    assert merged["authorization"] == "Bearer base"
    assert "Authorization" not in merged


def test_merge_auth_headers_explicit_auth_headers_override_token_and_base() -> None:
    merged = merge_auth_headers(
        base_headers={"Authorization": "Bearer base", "X-Base": "1"},
        auth=MCPAuthConfig(token="token_value", headers={"Authorization": "Bearer explicit", "X-Auth": "1"}),
    )
    assert merged["Authorization"] == "Bearer explicit"
    assert merged["X-Base"] == "1"
    assert merged["X-Auth"] == "1"


def test_has_header_is_case_insensitive() -> None:
    headers = {"aUtHoRiZaTiOn": "Bearer x"}
    assert has_header(headers, "Authorization") is True
    assert has_header(headers, "x-missing") is False


def test_is_auth_status_code_only_matches_401_and_403() -> None:
    assert is_auth_status_code(401) is True
    assert is_auth_status_code(403) is True
    assert is_auth_status_code(500) is False


def test_auth_config_from_server_config_reads_nested_auth_mapping() -> None:
    auth_config = auth_config_from_server_config(
        {
            "auth": {
                "token": "nested_token",
                "headers": {"X-Tenant": "alpha"},
            }
        }
    )
    assert auth_config is not None
    assert auth_config.token == "nested_token"
    assert auth_config.headers["X-Tenant"] == "alpha"


def test_auth_config_from_server_config_falls_back_to_legacy_fields() -> None:
    auth_config = auth_config_from_server_config(
        {
            "auth_token": "legacy_token",
            "auth_headers": {"X-Legacy": "1"},
        }
    )
    assert auth_config is not None
    assert auth_config.token == "legacy_token"
    assert auth_config.headers["X-Legacy"] == "1"


def test_with_auth_config_merges_existing_headers_and_overwrites_token() -> None:
    payload = with_auth_config(
        config={
            "transport": "http",
            "auth": {
                "token": "old_token",
                "headers": {"X-Base": "1"},
            },
        },
        token="new_token",
        headers={"X-Trace": "trace-1"},
    )
    auth_payload = payload["auth"]
    assert auth_payload["token"] == "new_token"
    assert auth_payload["headers"]["X-Base"] == "1"
    assert auth_payload["headers"]["X-Trace"] == "trace-1"
