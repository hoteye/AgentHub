from pathlib import Path

import pytest

from cli.agent_cli.providers.config_catalog_selection import select_provider_config
from cli.agent_cli.providers.config_catalog_types import ProviderPathResolution


def _resolution() -> ProviderPathResolution:
    return ProviderPathResolution(
        config_path=Path("/tmp/config.toml"),
        auth_path=Path("/tmp/auth.json"),
        config_exists=True,
        auth_exists=True,
        used_project_local=True,
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.example.com/v1",
        "http://8.8.8.8:8080/v1",
        "http://[2606:4700:4700::1111]:8080/v1",
    ],
)
def test_public_endpoint_no_auth_is_blocked_without_allow_flag(base_url: str) -> None:
    config = select_provider_config(
        env_mapping={},
        auth_data={},
        toml_data={
            "model_provider": "public_openai_like",
            "model": "gpt_public",
            "model_providers": {
                "public_openai_like": {
                    "base_url": base_url,
                    "auth_mode": "none",
                    "default_model": "gpt_public",
                }
            },
            "models": {
                "gpt_public": {
                    "provider": "public_openai_like",
                    "model": "gpt-4o-mini",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is None


def test_public_endpoint_no_auth_can_be_explicitly_allowed() -> None:
    config = select_provider_config(
        env_mapping={},
        auth_data={},
        toml_data={
            "model_provider": "public_openai_like",
            "model": "gpt_public",
            "model_providers": {
                "public_openai_like": {
                    "base_url": "https://api.example.com/v1",
                    "auth_mode": "none",
                    "allow_no_auth": True,
                    "default_model": "gpt_public",
                }
            },
            "models": {
                "gpt_public": {
                    "provider": "public_openai_like",
                    "model": "gpt-4o-mini",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is not None
    assert config.auth_mode == "none"


def test_public_endpoint_no_auth_with_api_key_keeps_existing_api_key_flow() -> None:
    config = select_provider_config(
        env_mapping={"PUBLIC_OPENAI_LIKE_API_KEY": "test-key"},
        auth_data={},
        toml_data={
            "model_provider": "public_openai_like",
            "model": "gpt_public",
            "model_providers": {
                "public_openai_like": {
                    "base_url": "https://api.example.com/v1",
                    "auth_mode": "none",
                    "default_model": "gpt_public",
                }
            },
            "models": {
                "gpt_public": {
                    "provider": "public_openai_like",
                    "model": "gpt-4o-mini",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is not None
    assert config.api_key == "test-key"


def test_hostname_without_ip_defaults_to_conservative_public_block() -> None:
    config = select_provider_config(
        env_mapping={},
        auth_data={},
        toml_data={
            "model_provider": "localish_name",
            "model": "gpt_public",
            "model_providers": {
                "localish_name": {
                    "base_url": "http://mybox.local:8080/v1",
                    "auth_mode": "none",
                    "default_model": "gpt_public",
                }
            },
            "models": {
                "gpt_public": {
                    "provider": "localish_name",
                    "model": "gpt-4o-mini",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is None
