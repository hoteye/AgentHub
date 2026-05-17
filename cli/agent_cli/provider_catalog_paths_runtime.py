from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli import (
    provider_catalog_paths_discovery_helpers_runtime as discovery_helpers,
)
from cli.agent_cli import provider_catalog_paths_merge_helpers_runtime as merge_helpers
from cli.agent_cli.providers.config.catalog import ProviderCatalog, ProviderPathResolution
from cli.agent_cli.workspace_context import merge_nested_mappings

_normalized_text = merge_helpers._normalized_text
_model_selection_matches_catalog = merge_helpers._model_selection_matches_catalog
_user_model_selection_matches_catalog = merge_helpers._user_model_selection_matches_catalog
_apply_user_model_selection = merge_helpers._apply_user_model_selection
_mapping = merge_helpers._mapping
_provider_profile_request = merge_helpers._provider_profile_request
_materialize_provider_profile = merge_helpers._materialize_provider_profile

iter_project_roots = discovery_helpers.iter_project_roots
find_project_provider_file = discovery_helpers.find_project_provider_file
related_provider_roots = discovery_helpers.related_provider_roots
discover_provider_project_local_paths = discovery_helpers.discover_provider_project_local_paths


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.expanduser().resolve() == right.expanduser().resolve()
    except OSError:
        return left.expanduser() == right.expanduser()


def ensure_project_provider_bootstrap(
    *,
    project_provider_layout_fn: Callable[[], Any],
    ensure_project_provider_bootstrap_fn: Callable[..., None],
    agent_cli_config_toml: Path,
    agent_cli_auth_json: Path,
    legacy_compat_config_toml: Path,
    legacy_compat_auth_json: Path,
    claude_settings_json: Path,
    claude_config_json: Path,
    claude_state_json: Path,
) -> None:
    layout = project_provider_layout_fn()
    ensure_project_provider_bootstrap_fn(
        project_config_toml=layout.config_toml,
        project_auth_json=layout.auth_json,
        project_openai_provider_toml=layout.openai_provider_toml,
        project_openai_auth_json=layout.openai_auth_json,
        project_claude_settings_json=layout.claude_settings_path,
        project_claude_config_json=layout.claude_config_path,
        project_claude_state_json=layout.claude_state_path,
        project_anthropic_snapshot_settings_json=layout.anthropic_snapshot_settings_json,
        project_anthropic_snapshot_config_json=layout.anthropic_snapshot_config_json,
        project_anthropic_snapshot_state_json=layout.anthropic_snapshot_state_json,
        agent_cli_config_toml=agent_cli_config_toml,
        agent_cli_auth_json=agent_cli_auth_json,
        legacy_compat_config_toml=legacy_compat_config_toml,
        legacy_compat_auth_json=legacy_compat_auth_json,
        legacy_claude_settings_json=claude_settings_json,
        legacy_claude_config_json=claude_config_json,
        legacy_claude_state_json=claude_state_json,
    )


def home_provider_paths(
    *,
    ensure_project_provider_bootstrap_fn: Callable[[], None],
    project_provider_layout_fn: Callable[[], Any],
    agent_cli_config_toml: Path,
    agent_cli_auth_json: Path,
    legacy_compat_config_toml: Path,
    legacy_compat_auth_json: Path,
) -> tuple[Path, Path, bool]:
    ensure_project_provider_bootstrap_fn()
    layout = project_provider_layout_fn()
    layout_is_agent_cli_home = _same_path(layout.config_toml, agent_cli_config_toml) and _same_path(
        layout.auth_json,
        agent_cli_auth_json,
    )
    if layout.config_toml.exists() or layout.auth_json.exists():
        return layout.config_toml, layout.auth_json, not layout_is_agent_cli_home
    if agent_cli_config_toml.exists() or agent_cli_auth_json.exists():
        return agent_cli_config_toml, agent_cli_auth_json, False
    return legacy_compat_config_toml, legacy_compat_auth_json, False


def project_claude_home_dir(
    *,
    project_provider_layout_fn: Callable[[], Any],
) -> Path | None:
    layout = project_provider_layout_fn()
    if any(
        path.exists()
        for path in (
            layout.claude_settings_path,
            layout.claude_config_path,
            layout.claude_state_path,
        )
    ):
        return layout.home_dir
    return None


def resolve_provider_paths(
    *,
    cwd: str | Path | None = None,
    home_provider_paths_fn: Callable[[], tuple[Path, Path, bool]],
    find_project_provider_file_fn: Callable[..., Path | None],
    resolve_provider_paths_impl_fn: Callable[..., ProviderPathResolution],
    legacy_compat_config_toml: Path,
    legacy_compat_auth_json: Path,
    strict_isolation: bool = False,
) -> ProviderPathResolution:
    home_config_path, home_auth_path, home_is_project_local = home_provider_paths_fn()
    if strict_isolation:
        return ProviderPathResolution(
            config_path=home_config_path,
            auth_path=home_auth_path,
            config_exists=home_config_path.exists(),
            auth_exists=home_auth_path.exists(),
            used_project_local=False,
        )
    elif cwd is None:
        project_config_path = find_project_provider_file_fn("config.toml")
        project_auth_path = find_project_provider_file_fn("auth.json")
    else:
        project_config_path = find_project_provider_file_fn("config.toml", cwd=cwd)
        project_auth_path = find_project_provider_file_fn("auth.json", cwd=cwd)
    if (
        not strict_isolation
        and project_config_path is None
        and project_auth_path is None
        and home_is_project_local
    ):
        if home_config_path.exists():
            project_config_path = home_config_path
        if home_auth_path.exists():
            project_auth_path = home_auth_path
    resolution = resolve_provider_paths_impl_fn(
        project_auth_path=project_auth_path,
        project_config_path=project_config_path,
        agent_cli_config_toml=home_config_path,
        agent_cli_auth_json=home_auth_path,
        legacy_compat_config_toml=legacy_compat_config_toml,
        legacy_compat_auth_json=legacy_compat_auth_json,
    )
    if not strict_isolation and (
        home_is_project_local
        and not resolution.used_project_local
        and (home_config_path.exists() or home_auth_path.exists())
    ):
        return ProviderPathResolution(
            config_path=home_config_path,
            auth_path=home_auth_path,
            config_exists=home_config_path.exists(),
            auth_exists=home_auth_path.exists(),
            used_project_local=True,
        )
    return resolution


def load_provider_inputs(
    *,
    cwd: str | Path | None = None,
    resolve_provider_paths_fn: Callable[..., ProviderPathResolution],
    home_provider_paths_fn: Callable[[], tuple[Path, Path, bool]],
    discover_provider_project_local_paths_fn: Callable[..., list[Path]],
    read_toml_fn: Callable[[Path], dict[str, Any]],
    read_json_fn: Callable[[Path], dict[str, Any]],
    read_user_model_selection_toml_fn: Callable[[], dict[str, Any]],
    default_config_paths_fn: Callable[[], list[Path]] | None = None,
    private_config_paths_fn: Callable[[], list[Path]] | None = None,
    private_auth_paths_fn: Callable[[], list[Path]] | None = None,
    strict_isolation: bool = False,
) -> tuple[ProviderPathResolution, dict[str, Any], dict[str, Any]]:
    resolution = resolve_provider_paths_fn(cwd=cwd, strict_isolation=strict_isolation)
    home_config_path, home_auth_path, home_is_project_local = home_provider_paths_fn()
    default_toml_data: dict[str, Any] = {}
    user_toml_data: dict[str, Any] = {}
    project_toml_data: dict[str, Any] = {}
    private_config_paths = list(
        private_config_paths_fn() if callable(private_config_paths_fn) else []
    )
    private_auth_paths = list(private_auth_paths_fn() if callable(private_auth_paths_fn) else [])
    default_config_paths = list(
        default_config_paths_fn() if callable(default_config_paths_fn) else []
    )
    existing_default_config_paths = [path for path in default_config_paths if path.exists()]
    if cwd is None or strict_isolation:
        toml_paths = list(existing_default_config_paths)
        for path in private_config_paths:
            if path.exists() and path != resolution.config_path and path not in toml_paths:
                toml_paths.append(path)
        if resolution.config_exists and resolution.config_path not in toml_paths:
            toml_paths.append(resolution.config_path)
        toml_data = {}
        for path in toml_paths:
            payload = read_toml_fn(path)
            toml_data = merge_nested_mappings(toml_data, payload)
            if path in existing_default_config_paths:
                default_toml_data = merge_nested_mappings(default_toml_data, payload)
            else:
                user_toml_data = merge_nested_mappings(user_toml_data, payload)
        auth_paths = [resolution.auth_path] if resolution.auth_exists else []
        for path in private_auth_paths:
            if path.exists() and path not in auth_paths:
                auth_paths.append(path)
        auth_data = {}
        for path in auth_paths:
            auth_data = merge_nested_mappings(auth_data, read_json_fn(path))
    else:
        config_home_paths = [home_config_path] if home_config_path.exists() else []
        auth_home_paths = [home_auth_path] if home_auth_path.exists() else []
        discovered_toml_paths = discover_provider_project_local_paths_fn(
            "config.toml",
            cwd=cwd,
            home_config_paths=config_home_paths,
        )
        auth_paths = discover_provider_project_local_paths_fn(
            "auth.json",
            cwd=cwd,
            home_config_paths=config_home_paths,
        )
        toml_paths = list(existing_default_config_paths)
        for path in config_home_paths:
            if path not in private_config_paths and path not in toml_paths:
                toml_paths.append(path)
        for path in private_config_paths:
            if path.exists() and path not in toml_paths:
                toml_paths.append(path)
        for path in discovered_toml_paths:
            if path not in toml_paths:
                toml_paths.append(path)
        for path in reversed(auth_home_paths):
            if path not in auth_paths:
                auth_paths.insert(0, path)
        for path in private_auth_paths:
            if path.exists() and path not in auth_paths:
                auth_paths.append(path)
        toml_data = {}
        for path in toml_paths:
            payload = read_toml_fn(path)
            toml_data = merge_nested_mappings(toml_data, payload)
            if path in existing_default_config_paths:
                default_toml_data = merge_nested_mappings(default_toml_data, payload)
            elif path == home_config_path or path in private_config_paths:
                user_toml_data = merge_nested_mappings(user_toml_data, payload)
            else:
                project_toml_data = merge_nested_mappings(project_toml_data, payload)
        auth_data: dict[str, Any] = {}
        for path in auth_paths:
            auth_data = merge_nested_mappings(auth_data, read_json_fn(path))
    user_model_selection = read_user_model_selection_toml_fn()
    if user_model_selection:
        # Persisted `/provider` selections are user-scoped. They may override
        # top-level provider/model defaults, but only when the persisted
        # selection still matches the active catalog. Project-local explicit
        # reasoning settings stay authoritative.
        toml_data = _apply_user_model_selection(
            toml_data=toml_data,
            user_model_selection=user_model_selection,
        )
    if user_model_selection and user_toml_data:
        user_toml_data = _apply_user_model_selection(
            toml_data=user_toml_data,
            user_model_selection=user_model_selection,
        )
        if project_toml_data:
            toml_data = merge_nested_mappings(default_toml_data, user_toml_data)
            toml_data = merge_nested_mappings(toml_data, project_toml_data)
            toml_data = _apply_user_model_selection(
                toml_data=toml_data,
                user_model_selection=user_model_selection,
            )
    toml_data = _materialize_provider_profile(
        user_toml_data=user_toml_data,
        project_toml_data=project_toml_data,
        merged_toml_data=toml_data,
    )
    non_default_toml_paths = [
        path for path in toml_paths if path not in existing_default_config_paths
    ]
    effective_config_path = toml_paths[-1] if toml_paths else resolution.config_path
    effective_auth_path = auth_paths[-1] if auth_paths else resolution.auth_path
    effective_resolution = ProviderPathResolution(
        config_path=effective_config_path,
        auth_path=effective_auth_path,
        config_exists=effective_config_path.exists(),
        auth_exists=effective_auth_path.exists(),
        used_project_local=bool(
            (not strict_isolation)
            and (
                resolution.used_project_local
                or home_is_project_local
                or any(path != home_config_path for path in non_default_toml_paths)
                or any(path != home_auth_path for path in auth_paths)
            )
        ),
    )
    return effective_resolution, toml_data, auth_data


def load_provider_catalog(
    *,
    cwd: str | Path | None = None,
    load_provider_inputs_fn: Callable[
        ..., tuple[ProviderPathResolution, dict[str, Any], dict[str, Any]]
    ],
    build_provider_catalog_fn: Callable[[dict[str, Any]], ProviderCatalog],
) -> ProviderCatalog:
    _, toml_data, _ = load_provider_inputs_fn(cwd=cwd)
    return build_provider_catalog_fn(toml_data)
