from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Sequence


_DEFAULT_STRICT_ISOLATION = False
_STRICT_ISOLATION_ENV_VARS = (
    "AGENTHUB_PROVIDER_STRICT_ISOLATION",
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _boolish(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalized_text(value)
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def provider_discovery_feature_settings_from_config(config: Mapping[str, Any] | None) -> Dict[str, Any]:
    strict_isolation_value: Any = None
    config_source = "default"

    if isinstance(config, Mapping):
        features = config.get("features")
        if isinstance(features, Mapping) and "provider_discovery" in features:
            raw_feature_block = features.get("provider_discovery")
            config_source = "home_config"
            if isinstance(raw_feature_block, Mapping):
                strict_isolation_value = raw_feature_block.get("strict_isolation")
            else:
                strict_isolation_value = raw_feature_block

    return {
        "strict_isolation": _boolish(
            strict_isolation_value,
            default=_DEFAULT_STRICT_ISOLATION,
        ),
        "config_source": config_source,
    }


def provider_discovery_feature_settings(
    *,
    env_mapping: Mapping[str, Any] | None = None,
    config_paths: Sequence[Path] = (),
    read_toml_fn: Callable[[Path], Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    settings = provider_discovery_feature_settings_from_config(None)
    reader = read_toml_fn
    if reader is not None:
        for path in config_paths:
            payload = reader(path)
            if not payload:
                continue
            candidate = provider_discovery_feature_settings_from_config(payload)
            if candidate.get("config_source") != "default":
                settings = candidate
                break

    env_values = env_mapping if env_mapping is not None else os.environ
    for env_var in _STRICT_ISOLATION_ENV_VARS:
        raw_value = env_values.get(env_var)
        if raw_value in (None, ""):
            continue
        settings = {
            "strict_isolation": _boolish(
                raw_value,
                default=bool(settings.get("strict_isolation", _DEFAULT_STRICT_ISOLATION)),
            ),
            "config_source": "env",
        }
        break

    return settings

