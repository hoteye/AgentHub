from __future__ import annotations

import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cli.agent_cli.providers.auth_token_encryption_runtime import (
    encrypt_session_payload,
    token_encryption_supported,
)
from cli.agent_cli.providers.config_catalog_selection import select_provider_config
from cli.agent_cli.providers.config_catalog_types import ProviderPathResolution


def _resolution() -> ProviderPathResolution:
    return ProviderPathResolution(
        config_path=Path("/tmp/config.toml"),
        auth_path=Path("/tmp/auth.json"),
        config_exists=True,
        auth_exists=True,
        used_project_local=False,
    )


def test_select_provider_config_injects_api_key_from_oauth_token_store_session() -> None:
    now = time.time()
    config = select_provider_config(
        env_mapping={},
        auth_data={
            "sessions": {
                "openai::default": {
                    "provider_name": "openai",
                    "token_ref": "default",
                    "access_token": "oauth-access-token",
                    "expires_at": now + 3600,
                }
            }
        },
        toml_data={
            "model_provider": "openai",
            "model": "gpt-oauth",
            "model_providers": {
                "openai": {
                    "base_url": "https://example.invalid/v1",
                    "auth_mode": "oauth",
                    "auth": {"token_ref": "default"},
                }
            },
        },
        resolution=_resolution(),
    )

    assert config is not None
    assert config.auth_mode == "oauth"
    assert config.api_key == "oauth-access-token"
    assert config.auth_status == "ready"
    assert config.token_source == "token_store.sessions"


def test_select_provider_config_injects_wellknown_session_and_keeps_api_key_mode_unchanged() -> None:
    now = time.time()
    oauth_cfg = select_provider_config(
        env_mapping={},
        auth_data={
            "sessions": {
                "wk::session-a": {
                    "provider_name": "wk",
                    "token_ref": "session-a",
                    "access_token": "wellknown-token",
                    "expires_at": now + 600,
                }
            }
        },
        toml_data={
            "model_provider": "wk",
            "model": "wk-model",
            "model_providers": {
                "wk": {
                    "auth_mode": "wellknown",
                    "auth": {"session": "session-a"},
                }
            },
        },
        resolution=_resolution(),
    )
    assert oauth_cfg is not None
    assert oauth_cfg.auth_mode == "wellknown"
    assert oauth_cfg.api_key == "wellknown-token"
    assert oauth_cfg.auth_status == "ready"

    api_key_cfg = select_provider_config(
        env_mapping={},
        auth_data={
            "OPENAI_API_KEY": "sk-api-key-mode",
            "sessions": {
                "openai::default": {
                    "provider_name": "openai",
                    "token_ref": "default",
                    "access_token": "should-not-override",
                    "expires_at": now + 3600,
                }
            },
        },
        toml_data={
            "model_provider": "openai",
            "model": "gpt-5.4",
            "model_providers": {
                "openai": {
                    "auth_mode": "api_key",
                    "api_key_env": "OPENAI_API_KEY",
                }
            },
        },
        resolution=_resolution(),
    )
    assert api_key_cfg is not None
    assert api_key_cfg.auth_mode == "api_key"
    assert api_key_cfg.api_key == "sk-api-key-mode"
    assert api_key_cfg.auth_status == ""
    assert api_key_cfg.token_source == ""


def test_select_provider_config_can_read_encrypted_oauth_session_payload() -> None:
    if not token_encryption_supported():
        return
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        now = time.time()
        with patch.dict(os.environ, {"AGENTHUB_AUTH_TOKEN_ENCRYPTION": "on"}, clear=False):
            encrypted_payload = encrypt_session_payload(
                {
                    "provider_name": "openai",
                    "token_ref": "default",
                    "access_token": "oauth-token-encrypted",
                    "expires_at": now + 600,
                },
                store_path=auth_path,
            )
            config = select_provider_config(
                env_mapping={},
                auth_data={"sessions": {"openai::default": encrypted_payload}},
                toml_data={
                    "model_provider": "openai",
                    "model": "gpt-oauth",
                    "model_providers": {
                        "openai": {
                            "auth_mode": "oauth",
                            "auth": {"token_ref": "default"},
                        }
                    },
                },
                resolution=ProviderPathResolution(
                    config_path=Path(temp_dir) / "config.toml",
                    auth_path=auth_path,
                    config_exists=True,
                    auth_exists=True,
                    used_project_local=True,
                ),
            )
        assert config is not None
        assert config.api_key == "oauth-token-encrypted"
        assert config.auth_status == "ready"
