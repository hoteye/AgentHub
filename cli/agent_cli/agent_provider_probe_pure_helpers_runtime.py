from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict


def probe_owner(agent: Any, *, availability_registry: Any) -> Any:
    state_path = getattr(agent, "_provider_availability_state_path", None)
    if state_path in (None, ""):
        state_path = getattr(agent, "provider_availability_state_path", None)
    return SimpleNamespace(
        _provider_availability_registry=availability_registry,
        _provider_availability_state_path=state_path,
        provider_availability_state_path=state_path,
    )


def noop_turn_event_callback(_event: Dict[str, Any]) -> None:
    return None


def probe_planner_placeholder(config: Any) -> Any:
    probe_summary = dict(getattr(config, "public_summary", lambda: {})() or {})
    return SimpleNamespace(public_summary=lambda: dict(probe_summary))


def resolve_agent_cwd(agent: Any) -> Any:
    cwd = getattr(agent, "cwd", None)
    if cwd is None:
        loader_kwargs_getter = getattr(agent, "_provider_loader_kwargs", None)
        if callable(loader_kwargs_getter):
            try:
                cwd = dict(loader_kwargs_getter() or {}).get("cwd")
            except Exception:
                cwd = None
    return cwd


def read_workspace_feature_config(
    agent: Any,
    *,
    read_merged_project_toml_fn,
    home_config_paths: list[str],
) -> Dict[str, Any]:
    cwd = resolve_agent_cwd(agent)
    merged_config: Dict[str, Any] = {}
    if cwd is not None:
        try:
            merged_config, _ = read_merged_project_toml_fn(
                cwd=Path(cwd),
                home_config_paths=home_config_paths,
            )
        except Exception:
            merged_config = {}
    return merged_config


def merge_probe_item(item: Dict[str, Any], probe: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(item)
    merged.update(probe)
    return merged


def load_remote_model_items_by_provider(
    catalog: Any,
    *,
    cwd: Any,
    refresh_remote_model_catalog_fn,
    load_cached_remote_models_fn,
) -> dict[str, list[dict[str, Any]]]:
    remote_model_items_by_provider: dict[str, list[dict[str, Any]]] = {}
    for config_provider_name, provider_entry in catalog.providers.items():
        endpoint = str(getattr(provider_entry, "raw_provider", {}).get("catalog_endpoint") or "").strip()
        if not endpoint:
            continue
        try:
            refresh_remote_model_catalog_fn(
                provider_name=config_provider_name,
                catalog_endpoint=endpoint,
                cwd=cwd,
            )
        except Exception:
            pass
        try:
            remote_model_items_by_provider[config_provider_name] = list(
                load_cached_remote_models_fn(
                    provider_name=config_provider_name,
                    cwd=cwd,
                )
                or []
            )
        except Exception:
            remote_model_items_by_provider[config_provider_name] = []
    return remote_model_items_by_provider
