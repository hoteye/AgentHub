from __future__ import annotations

from pathlib import Path
from typing import Mapping

from cli.scripts.script_runtime_helpers import apply_provider_home_override_env


PROVIDER_CONFIG_REF = "test-provider-config-ref"
PROVIDER_AUTH_REF = "test-provider-auth-ref"
_PROVIDER_HOME_SAMPLE = "/tmp/provider-home"


def provider_status_path_fields() -> dict[str, str]:
    return {
        "provider_config_path": PROVIDER_CONFIG_REF,
        "provider_auth_path": PROVIDER_AUTH_REF,
    }


def provider_home_env(provider_home: str | Path = _PROVIDER_HOME_SAMPLE) -> dict[str, str]:
    return apply_provider_home_override_env({}, provider_home=provider_home)


_SAMPLE_PROVIDER_ENV = provider_home_env(_PROVIDER_HOME_SAMPLE)
PROVIDER_HOME_ENV_KEY = next(
    key for key, value in _SAMPLE_PROVIDER_ENV.items() if value == _PROVIDER_HOME_SAMPLE
)
PROVIDER_STRICT_ISOLATION_ENV_KEY = next(
    key for key, value in _SAMPLE_PROVIDER_ENV.items() if value == "true"
)


def assert_provider_home_env(env: Mapping[str, str], expected_provider_home: str | Path) -> None:
    assert env[PROVIDER_HOME_ENV_KEY] == str(expected_provider_home)
    assert env[PROVIDER_STRICT_ISOLATION_ENV_KEY] == "true"


def assert_provider_home_absent(env: Mapping[str, str]) -> None:
    assert PROVIDER_HOME_ENV_KEY not in env
    assert PROVIDER_STRICT_ISOLATION_ENV_KEY not in env
