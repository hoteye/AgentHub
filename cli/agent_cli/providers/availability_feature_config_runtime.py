from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from cli.agent_cli import workspace_context
from cli.agent_cli.providers.availability_models import DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS


def _intish(value: Any, *, default: int, minimum: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, normalized)


def _owner_cwd(owner: Any) -> Path | None:
    cwd = getattr(owner, "cwd", None)
    if cwd is not None:
        return Path(cwd)
    loader_kwargs_getter = getattr(owner, "_provider_loader_kwargs", None)
    if not callable(loader_kwargs_getter):
        return None
    try:
        loader_kwargs = dict(loader_kwargs_getter() or {})
    except Exception:
        return None
    resolved_cwd = loader_kwargs.get("cwd")
    if resolved_cwd is None:
        return None
    return Path(resolved_cwd)


def _effective_home_provider_config_path(*, cwd: Path) -> Path:
    from cli.agent_cli.provider_persistence_paths_runtime import (
        resolve_effective_home_provider_config_path,
    )

    return resolve_effective_home_provider_config_path(cwd=cwd)


def provider_availability_feature_settings_from_config(config: Mapping[str, Any] | None) -> Dict[str, Any]:
    feature_block: Mapping[str, Any] | None = None
    stale_after_value: Any = None
    config_source = "default"

    if isinstance(config, Mapping):
        features = config.get("features")
        if isinstance(features, Mapping) and "provider_availability" in features:
            raw_feature_block = features.get("provider_availability")
            config_source = "workspace_config"
            if isinstance(raw_feature_block, Mapping):
                feature_block = raw_feature_block
                stale_after_value = raw_feature_block.get("stale_after_seconds")
            else:
                stale_after_value = raw_feature_block

    return {
        "stale_after_seconds": _intish(
            stale_after_value,
            default=DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS,
            minimum=1,
        ),
        "config_source": config_source,
    }


def provider_availability_feature_settings(owner: Any) -> Dict[str, Any]:
    cwd = _owner_cwd(owner)
    merged_config: Dict[str, Any] = {}
    if cwd is not None:
        try:
            home_config_path = _effective_home_provider_config_path(cwd=Path(cwd))
            merged_config, _ = workspace_context.read_merged_project_toml(
                cwd=Path(cwd),
                home_config_paths=[home_config_path],
            )
        except Exception:
            merged_config = {}
    return provider_availability_feature_settings_from_config(merged_config)
