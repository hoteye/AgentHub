from __future__ import annotations

import tomllib
from pathlib import Path

from cli.agent_cli.provider_catalog_toml_runtime import save_user_model_selection
from cli.agent_cli.providers.auth_schema_runtime import (
    apply_typed_auth_to_provider_block,
    provider_auth_schema,
)
from cli.agent_cli.providers.config_catalog_types import build_provider_catalog


def test_provider_auth_schema_projects_legacy_api_key_env() -> None:
    schema = provider_auth_schema(
        {
            "api_key_env": "OPENAI_API_KEY",
        }
    )
    assert schema.auth_mode == "api_key"
    assert schema.auth == {"env_var": "OPENAI_API_KEY"}


def test_apply_typed_auth_to_provider_block_keeps_backward_compatibility() -> None:
    projected = apply_typed_auth_to_provider_block(
        {
            "base_url": "http://127.0.0.1:11434/v1",
            "auth_mode": "none",
        }
    )
    assert projected["auth_mode"] == "none"
    assert projected["auth"] == {}


def test_build_provider_catalog_contains_typed_auth_for_legacy_and_structured_blocks() -> None:
    catalog = build_provider_catalog(
        {
            "model_providers": {
                "legacy_openai": {
                    "api_key_env": "OPENAI_API_KEY",
                    "base_url": "https://example.invalid/v1",
                },
                "oauth_provider": {
                    "auth_mode": "oauth",
                    "auth": {
                        "client_id": "client-a",
                        "token_endpoint": "https://issuer/token",
                        "scopes": ["chat:read", "chat:write"],
                    },
                },
            },
            "models": {
                "m1": {"provider": "legacy_openai", "model_id": "gpt-5.4"},
                "m2": {"provider": "oauth_provider", "model_id": "vendor-model"},
            },
        }
    )
    legacy = catalog.providers["legacy_openai"]
    oauth = catalog.providers["oauth_provider"]
    assert legacy.auth_mode == "api_key"
    assert legacy.auth == {"env_var": "OPENAI_API_KEY"}
    assert oauth.auth_mode == "oauth"
    assert oauth.auth["client_id"] == "client-a"
    assert oauth.auth["token_endpoint"] == "https://issuer/token"
    assert oauth.auth["scopes"] == ["chat:read", "chat:write"]


def test_save_user_model_selection_writes_typed_auth_schema(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    save_user_model_selection(
        path=config_path,
        provider_name="local_ollama",
        model="qwen3",
        provider_name_for_auth="local_ollama",
        auth_mode="none",
        auth={},
    )
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert payload["model_provider"] == "local_ollama"
    assert payload["model"] == "qwen3"
    assert payload["model_providers"]["local_ollama"]["auth_mode"] == "none"
