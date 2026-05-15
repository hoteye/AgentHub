from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cli.agent_cli import (
    provider_facade_paths_runtime_bindings as _provider_facade_paths_runtime_bindings,
)
from cli.agent_cli import provider_paths_helpers_runtime as _provider_paths_helpers_runtime
from cli.agent_cli.providers.config.catalog import ProviderPathResolution


@dataclass(frozen=True)
class ProviderFacadePathRuntimeDeps:
    env_mapping: Mapping[str, str]
    app_dir: Path
    local_config_dir_candidates: tuple[str, ...]
    project_local_data_dir_candidates: tuple[str, ...]
    agenthub_provider_home_env: str
    agent_cli_config_toml: Path
    agent_cli_auth_json: Path
    legacy_compat_config_toml: Path
    legacy_compat_auth_json: Path
    claude_settings_json: Path
    claude_config_json: Path
    claude_state_json: Path
    user_model_selection_keys: tuple[str, ...]
    save_user_model_selection_fn: Callable[..., Path]
    read_user_model_selection_toml_impl_fn: Callable[..., dict[str, Any]]
    read_toml_fn: Callable[..., dict[str, Any]]
    read_json_fn: Callable[..., dict[str, Any]]
    runtime_project_root_fn: Callable[..., Path]
    project_root_markers_fn: Callable[..., Any]
    find_project_root_fn: Callable[..., Path | None]
    project_provider_layout_impl_fn: Callable[..., Any]
    project_provider_layout_fn: Callable[..., Any]
    ensure_project_provider_bootstrap_impl_fn: Callable[..., None]
    ensure_project_provider_bootstrap_fn: Callable[[], None]
    provider_discovery_feature_settings_impl_fn: Callable[..., dict[str, Any]]
    provider_discovery_feature_settings_fn: Callable[[], dict[str, Any]]
    provider_discovery_strict_isolation_enabled_fn: Callable[[], bool]
    workspace_trust_level_fn: Callable[..., Any]
    resolve_provider_paths_impl_fn: Callable[..., ProviderPathResolution]
    load_provider_inputs_fn: Callable[
        ..., tuple[ProviderPathResolution, dict[str, Any], dict[str, Any]]
    ]
    read_user_model_selection_toml_fn: Callable[[], dict[str, Any]]
    iter_project_roots_fn: Callable[..., list[Path]]
    find_project_provider_file_fn: Callable[..., Path | None]
    project_provider_search_excluded_dirs_fn: Callable[[], set[Path]]
    explicit_provider_home_paths_fn: Callable[[], tuple[Path, Path] | None]
    related_provider_roots_fn: Callable[..., list[Path]]
    home_provider_paths_fn: Callable[[], tuple[Path, Path, bool]]
    resolve_provider_paths_fn: Callable[..., ProviderPathResolution]
    discover_provider_project_local_paths_fn: Callable[..., list[Path]]
    private_config_paths_fn: Callable[[], list[Path]]
    private_auth_paths_fn: Callable[[], list[Path]]


_provider_facade_paths_runtime_bindings.ProviderFacadePathRuntimeDeps = (
    ProviderFacadePathRuntimeDeps
)
ProviderFacadePathRuntimeBindings = (
    _provider_facade_paths_runtime_bindings.ProviderFacadePathRuntimeBindings
)
bind_path_runtime = _provider_facade_paths_runtime_bindings.bind_path_runtime

# Keep facade exports introspecting as members of this module after the split.
ProviderFacadePathRuntimeBindings.__module__ = __name__
bind_path_runtime.__module__ = __name__


def save_user_model_selection(
    *,
    provider_name: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    deps: ProviderFacadePathRuntimeDeps,
) -> Path:
    return deps.save_user_model_selection_fn(
        path=deps.agent_cli_config_toml,
        provider_name=provider_name,
        model=model,
        reasoning_effort=reasoning_effort,
    )


def read_user_model_selection_toml(*, deps: ProviderFacadePathRuntimeDeps) -> dict[str, Any]:
    config_paths = [deps.agent_cli_config_toml]
    if not str(deps.env_mapping.get("AGENT_CLI_HOME") or "").strip():
        config_paths.append(deps.legacy_compat_config_toml)
    return deps.read_user_model_selection_toml_impl_fn(
        config_paths=tuple(config_paths),
        read_toml_fn=deps.read_toml_fn,
        selection_keys=deps.user_model_selection_keys,
    )


def iter_project_roots(
    *,
    cwd: str | Path | None = None,
    deps: ProviderFacadePathRuntimeDeps,
) -> list[Path]:
    return _provider_paths_helpers_runtime.iter_project_roots(
        cwd=cwd,
        app_dir=deps.app_dir,
        runtime_project_root_fn=deps.runtime_project_root_fn,
        project_root_markers_fn=deps.project_root_markers_fn,
        find_project_root_fn=deps.find_project_root_fn,
    )


def find_project_provider_file(
    filename: str,
    *,
    cwd: str | Path | None = None,
    deps: ProviderFacadePathRuntimeDeps,
) -> Path | None:
    return _provider_paths_helpers_runtime.find_project_provider_file(
        filename,
        cwd=cwd,
        iter_project_roots_fn=deps.iter_project_roots_fn,
        project_provider_search_excluded_dirs_fn=deps.project_provider_search_excluded_dirs_fn,
        local_config_dir_candidates=deps.local_config_dir_candidates,
    )


def project_provider_layout(*, deps: ProviderFacadePathRuntimeDeps):
    return deps.project_provider_layout_impl_fn(cli_root=deps.app_dir.parent)


def related_provider_roots(
    *,
    cwd: str | Path,
    deps: ProviderFacadePathRuntimeDeps,
) -> list[Path]:
    return deps.iter_project_roots_fn(cwd=cwd)


def discover_provider_project_local_paths(
    filename: str,
    *,
    cwd: str | Path,
    home_config_paths: list[Path] | None = None,
    deps: ProviderFacadePathRuntimeDeps,
) -> list[Path]:
    return _provider_paths_helpers_runtime.discover_provider_project_local_paths(
        filename,
        cwd=cwd,
        home_config_paths=home_config_paths,
        related_provider_roots_fn=deps.related_provider_roots_fn,
        workspace_trust_level_fn=deps.workspace_trust_level_fn,
        project_local_data_dir_candidates=deps.project_local_data_dir_candidates,
        project_provider_search_excluded_dirs_fn=deps.project_provider_search_excluded_dirs_fn,
    )


def project_provider_search_excluded_dirs(*, deps: ProviderFacadePathRuntimeDeps) -> set[Path]:
    return _provider_paths_helpers_runtime.project_provider_search_excluded_dirs(
        env_mapping=deps.env_mapping,
        project_provider_layout_fn=deps.project_provider_layout_fn,
        agent_cli_config_toml=deps.agent_cli_config_toml,
        agent_cli_auth_json=deps.agent_cli_auth_json,
        legacy_compat_config_toml=deps.legacy_compat_config_toml,
        legacy_compat_auth_json=deps.legacy_compat_auth_json,
        explicit_provider_home_paths_fn=deps.explicit_provider_home_paths_fn,
    )


def ensure_project_provider_bootstrap(*, deps: ProviderFacadePathRuntimeDeps) -> None:
    _provider_paths_helpers_runtime.ensure_project_provider_bootstrap(
        project_provider_layout_fn=deps.project_provider_layout_fn,
        ensure_project_provider_bootstrap_fn=deps.ensure_project_provider_bootstrap_impl_fn,
        agent_cli_config_toml=deps.agent_cli_config_toml,
        agent_cli_auth_json=deps.agent_cli_auth_json,
        legacy_compat_config_toml=deps.legacy_compat_config_toml,
        legacy_compat_auth_json=deps.legacy_compat_auth_json,
        claude_settings_json=deps.claude_settings_json,
        claude_config_json=deps.claude_config_json,
        claude_state_json=deps.claude_state_json,
    )


def explicit_provider_home_paths(
    *, deps: ProviderFacadePathRuntimeDeps
) -> tuple[Path, Path] | None:
    return _provider_paths_helpers_runtime.explicit_provider_home_paths(
        env_mapping=deps.env_mapping,
        project_provider_layout_fn=deps.project_provider_layout_fn,
    )


def provider_discovery_feature_settings(*, deps: ProviderFacadePathRuntimeDeps) -> dict[str, Any]:
    return _provider_paths_helpers_runtime.provider_discovery_feature_settings(
        env_mapping=deps.env_mapping,
        agent_cli_config_toml=deps.agent_cli_config_toml,
        legacy_compat_config_toml=deps.legacy_compat_config_toml,
        explicit_provider_home_paths_fn=deps.explicit_provider_home_paths_fn,
        provider_discovery_feature_settings_fn=deps.provider_discovery_feature_settings_impl_fn,
        read_toml_fn=deps.read_toml_fn,
    )


def provider_discovery_strict_isolation_enabled(*, deps: ProviderFacadePathRuntimeDeps) -> bool:
    return bool(deps.provider_discovery_feature_settings_fn().get("strict_isolation"))


def home_provider_paths(*, deps: ProviderFacadePathRuntimeDeps) -> tuple[Path, Path, bool]:
    return _provider_paths_helpers_runtime.home_provider_paths(
        env_mapping=deps.env_mapping,
        provider_discovery_strict_isolation_enabled_fn=deps.provider_discovery_strict_isolation_enabled_fn,
        explicit_provider_home_paths_fn=deps.explicit_provider_home_paths_fn,
        ensure_project_provider_bootstrap_fn=deps.ensure_project_provider_bootstrap_fn,
        project_provider_layout_fn=deps.project_provider_layout_fn,
        agent_cli_config_toml=deps.agent_cli_config_toml,
        agent_cli_auth_json=deps.agent_cli_auth_json,
        legacy_compat_config_toml=deps.legacy_compat_config_toml,
        legacy_compat_auth_json=deps.legacy_compat_auth_json,
    )


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def private_provider_auth_paths(*, deps: ProviderFacadePathRuntimeDeps) -> list[Path]:
    paths: list[Path] = []
    if not str(deps.env_mapping.get("AGENT_CLI_HOME") or "").strip():
        paths.append(deps.legacy_compat_auth_json)
    paths.append(deps.agent_cli_auth_json)
    return _unique_paths(paths)


def private_provider_config_paths(*, deps: ProviderFacadePathRuntimeDeps) -> list[Path]:
    paths: list[Path] = []
    if not str(deps.env_mapping.get("AGENT_CLI_HOME") or "").strip():
        paths.append(deps.legacy_compat_config_toml)
    paths.append(deps.agent_cli_config_toml)
    return _unique_paths(paths)


def project_claude_home_dir(*, deps: ProviderFacadePathRuntimeDeps) -> Path | None:
    return _provider_paths_helpers_runtime.project_claude_home_dir(
        project_provider_layout_fn=deps.project_provider_layout_fn,
    )


def resolve_provider_paths(
    *,
    cwd: str | Path | None = None,
    strict_isolation: bool | None = None,
    deps: ProviderFacadePathRuntimeDeps,
) -> ProviderPathResolution:
    return _provider_paths_helpers_runtime.resolve_provider_paths(
        cwd=cwd,
        strict_isolation=strict_isolation,
        env_mapping=deps.env_mapping,
        provider_discovery_strict_isolation_enabled_fn=deps.provider_discovery_strict_isolation_enabled_fn,
        home_provider_paths_fn=deps.home_provider_paths_fn,
        find_project_provider_file_fn=deps.find_project_provider_file_fn,
        resolve_provider_paths_impl_fn=deps.resolve_provider_paths_impl_fn,
        legacy_compat_config_toml=deps.legacy_compat_config_toml,
        legacy_compat_auth_json=deps.legacy_compat_auth_json,
    )


def load_provider_inputs(
    *,
    cwd: str | Path | None = None,
    strict_isolation: bool | None = None,
    deps: ProviderFacadePathRuntimeDeps,
) -> tuple[ProviderPathResolution, dict[str, Any], dict[str, Any]]:
    resolved_strict_isolation = (
        deps.provider_discovery_strict_isolation_enabled_fn()
        if strict_isolation is None
        else bool(strict_isolation)
    )
    explicit_runtime_home = bool(
        str(deps.env_mapping.get(deps.agenthub_provider_home_env) or "").strip()
        or str(deps.env_mapping.get("AGENT_CLI_HOME") or "").strip()
    )
    return deps.load_provider_inputs_fn(
        cwd=cwd,
        resolve_provider_paths_fn=deps.resolve_provider_paths_fn,
        home_provider_paths_fn=deps.home_provider_paths_fn,
        discover_provider_project_local_paths_fn=deps.discover_provider_project_local_paths_fn,
        read_toml_fn=deps.read_toml_fn,
        read_json_fn=deps.read_json_fn,
        read_user_model_selection_toml_fn=deps.read_user_model_selection_toml_fn,
        private_config_paths_fn=deps.private_config_paths_fn,
        private_auth_paths_fn=deps.private_auth_paths_fn,
        strict_isolation=resolved_strict_isolation or explicit_runtime_home,
    )
