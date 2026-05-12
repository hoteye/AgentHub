from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from cli.agent_cli.providers.config.catalog import (
    default_supports_reasoning_for_model,
    ProviderCatalog,
    ProviderConfig,
    ProviderPathResolution,
    default_model_entry,
    default_reasoning_effort_for_model,
    find_model_entry,
    supported_reasoning_efforts_for_model,
)
from cli.agent_cli.providers import model_catalog_cache_runtime as model_cache_runtime
from cli.agent_cli.providers import model_catalog_remote_runtime as model_remote_runtime
from cli.agent_cli import provider_catalog_paths_runtime as paths_runtime
from cli.agent_cli import provider_catalog_selection_runtime as selection_runtime
from cli.agent_cli import provider_catalog_toml_runtime as toml_runtime


quoted_toml_string = toml_runtime.quoted_toml_string
upsert_root_toml_string_key = toml_runtime.upsert_root_toml_string_key
read_user_model_selection_toml = toml_runtime.read_user_model_selection_toml
save_user_model_selection = toml_runtime.save_user_model_selection

iter_project_roots = paths_runtime.iter_project_roots
find_project_provider_file = paths_runtime.find_project_provider_file
related_provider_roots = paths_runtime.related_provider_roots
discover_provider_project_local_paths = paths_runtime.discover_provider_project_local_paths
ensure_project_provider_bootstrap = paths_runtime.ensure_project_provider_bootstrap
home_provider_paths = paths_runtime.home_provider_paths
project_claude_home_dir = paths_runtime.project_claude_home_dir
resolve_provider_paths = paths_runtime.resolve_provider_paths
load_provider_inputs = paths_runtime.load_provider_inputs
load_provider_catalog = paths_runtime.load_provider_catalog

remote_model_catalog_cache_path = model_cache_runtime.default_cache_path


@dataclass(frozen=True)
class ProviderManagementSnapshot:
    resolution: ProviderPathResolution
    toml_data: Dict[str, Any]
    auth_data: Dict[str, Any]
    catalog: ProviderCatalog
    selected_config: Optional[ProviderConfig]


def resolve_model_catalog_entry(
    *,
    catalog: Any,
    provider_name: str = "",
    model: str = "",
):
    selector = str(model or "").strip()
    preferred_provider = str(provider_name or "").strip() or None
    entry = find_model_entry(selector, catalog, preferred_provider=preferred_provider) if selector else None
    if entry is None and preferred_provider is not None and not selector:
        entry = default_model_entry(preferred_provider, catalog)
    if entry is None and selector:
        entry = find_model_entry(selector, catalog)
    return entry


def model_catalog_reasoning_profile(
    *,
    catalog: Any,
    provider_name: str = "",
    model: str = "",
    interaction_profile: str = "",
    planner_kind: str = "",
    wire_api: str = "",
) -> dict[str, Any]:
    entry = resolve_model_catalog_entry(
        catalog=catalog,
        provider_name=provider_name,
        model=model,
    )
    if entry is not None:
        supported_reasoning_efforts = tuple(getattr(entry, "supported_reasoning_efforts", ()) or ())
        resolved_planner_kind = str(planner_kind or getattr(entry, "planner_kind", "") or "").strip()
        resolved_wire_api = str(wire_api or getattr(entry, "wire_api", "") or "").strip()
        resolved_interaction_profile = str(
            interaction_profile or getattr(entry, "interaction_profile", "") or ""
        ).strip()
        return {
            "provider_name": str(entry.provider_name or "").strip(),
            "model_key": str(entry.key or "").strip(),
            "model_id": str(entry.model_id or "").strip(),
            "supported_reasoning_efforts": supported_reasoning_efforts,
            "default_reasoning_effort": default_reasoning_effort_for_model(
                provider_name=str(entry.provider_name or "").strip(),
                model_id=str(entry.model_id or "").strip(),
                interaction_profile=resolved_interaction_profile,
                planner_kind=resolved_planner_kind,
                wire_api=resolved_wire_api,
                supports_reasoning=bool(getattr(entry, "supports_reasoning", False)),
                reasoning_mode=str(getattr(entry, "reasoning_mode", "") or "").strip(),
                reasoning_output_field=str(getattr(entry, "reasoning_output_field", "") or "").strip(),
                supported_reasoning_efforts=supported_reasoning_efforts,
                default_reasoning_effort=str(getattr(entry, "default_reasoning_effort", "") or "").strip(),
            ),
            "supports_reasoning": bool(getattr(entry, "supports_reasoning", False)),
        }
    normalized_provider_name = str(provider_name or "").strip()
    normalized_model = str(model or "").strip()
    supported_reasoning_efforts = supported_reasoning_efforts_for_model(
        provider_name=normalized_provider_name,
        model_id=normalized_model,
    )
    supports_reasoning = default_supports_reasoning_for_model(
        provider_name=normalized_provider_name,
        model_id=normalized_model,
        supported_reasoning_efforts=supported_reasoning_efforts,
    )
    default_reasoning_effort = default_reasoning_effort_for_model(
        provider_name=normalized_provider_name,
        model_id=normalized_model,
        interaction_profile=interaction_profile,
        planner_kind=planner_kind,
        wire_api=wire_api,
        supported_reasoning_efforts=supported_reasoning_efforts,
    )
    return {
        "provider_name": normalized_provider_name,
        "model_key": "",
        "model_id": normalized_model,
        "supported_reasoning_efforts": supported_reasoning_efforts,
        "default_reasoning_effort": default_reasoning_effort,
        "supports_reasoning": supports_reasoning,
    }


def load_cached_remote_models(*, provider_name: str, cwd: str | Path | None = None) -> list[dict[str, Any]]:
    cache_path = model_cache_runtime.default_cache_path(cwd=cwd)
    payload = model_cache_runtime.read_cache(cache_path)
    return model_cache_runtime.cached_models(payload, provider_name=provider_name)


def refresh_remote_model_catalog(
    *,
    provider_name: str,
    catalog_endpoint: str,
    cwd: str | Path | None = None,
    ttl_seconds: int = 3600,
    force: bool = False,
) -> dict[str, Any]:
    cache_path = model_cache_runtime.default_cache_path(cwd=cwd)
    return model_remote_runtime.refresh_provider_catalog_cache(
        cache_path=cache_path,
        provider_name=provider_name,
        catalog_endpoint=catalog_endpoint,
        ttl_seconds=ttl_seconds,
        force=force,
    )


def load_provider_management_snapshot(
    *,
    cwd: str | Path | None = None,
    env_overrides: Optional[Dict[str, Optional[str]]] = None,
    load_provider_inputs_fn: Callable[..., tuple[ProviderPathResolution, Dict[str, Any], Dict[str, Any]]],
    build_provider_catalog_fn: Callable[[Dict[str, Any]], ProviderCatalog],
    select_provider_config_fn: Callable[..., Optional[ProviderConfig]],
    optional_bool_fn: Callable[[Any, bool], bool],
    infer_planner_kind_fn: Callable[[str, str, Optional[str], Dict[str, Any]], str],
    should_use_claude_provider_fn: Callable[..., bool],
    project_claude_home_dir_fn: Callable[[], Path | None],
    load_claude_provider_config_fn: Callable[..., Optional[ProviderConfig]],
) -> ProviderManagementSnapshot:
    resolution, toml_data, auth_data = load_provider_inputs_fn(cwd=cwd)
    catalog = build_provider_catalog_fn(toml_data)
    selected_config = selection_runtime.select_provider_config_from_inputs(
        resolution=resolution,
        toml_data=toml_data,
        auth_data=auth_data,
        env_overrides=env_overrides,
        select_provider_config_fn=select_provider_config_fn,
        optional_bool_fn=optional_bool_fn,
        infer_planner_kind_fn=infer_planner_kind_fn,
        should_use_claude_provider_fn=should_use_claude_provider_fn,
        project_claude_home_dir_fn=project_claude_home_dir_fn,
        load_claude_provider_config_fn=load_claude_provider_config_fn,
    )
    return ProviderManagementSnapshot(
        resolution=resolution,
        toml_data=toml_data,
        auth_data=auth_data,
        catalog=catalog,
        selected_config=selected_config,
    )


def load_provider_config(
    *,
    cwd: str | Path | None = None,
    env_overrides: Optional[Dict[str, Optional[str]]] = None,
    load_provider_inputs_fn: Callable[..., tuple[ProviderPathResolution, Dict[str, Any], Dict[str, Any]]],
    select_provider_config_fn: Callable[..., Optional[ProviderConfig]],
    optional_bool_fn: Callable[[Any, bool], bool],
    infer_planner_kind_fn: Callable[[str, str, Optional[str], Dict[str, Any]], str],
    should_use_claude_provider_fn: Callable[..., bool],
    project_claude_home_dir_fn: Callable[[], Path | None],
    load_claude_provider_config_fn: Callable[..., Optional[ProviderConfig]],
) -> Optional[ProviderConfig]:
    return selection_runtime.load_provider_config(
        cwd=cwd,
        env_overrides=env_overrides,
        load_provider_inputs_fn=load_provider_inputs_fn,
        select_provider_config_fn=select_provider_config_fn,
        optional_bool_fn=optional_bool_fn,
        infer_planner_kind_fn=infer_planner_kind_fn,
        should_use_claude_provider_fn=should_use_claude_provider_fn,
        project_claude_home_dir_fn=project_claude_home_dir_fn,
        load_claude_provider_config_fn=load_claude_provider_config_fn,
    )
