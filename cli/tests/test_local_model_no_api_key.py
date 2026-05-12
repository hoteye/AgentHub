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
        "http://127.0.0.1:11434/v1",
        "http://[::1]:11434/v1",
        "http://10.10.8.7:11434/v1",
        "http://192.168.1.9:11434/v1",
        "http://172.20.6.8:11434/v1",
        "http://169.254.3.20:11434/v1",
        "http://[fe80::1]:11434/v1",
        "http://[fc00::1]:11434/v1",
    ],
)
def test_local_endpoint_with_auth_mode_none_is_allowed_without_api_key(base_url: str) -> None:
    config = select_provider_config(
        env_mapping={},
        auth_data={},
        toml_data={
            "model_provider": "local_ollama",
            "model": "llama3_local",
            "model_providers": {
                "local_ollama": {
                    "base_url": base_url,
                    "auth_mode": "none",
                    "default_model": "llama3_local",
                }
            },
            "models": {
                "llama3_local": {
                    "provider": "local_ollama",
                    "model": "llama3.2",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is not None
    assert config.auth_mode == "none"
    assert config.api_key == ""
