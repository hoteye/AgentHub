from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli import provider_catalog_runtime as _provider_catalog_runtime
from cli.agent_cli import provider_helpers_runtime as _provider_helpers_runtime
from cli.agent_cli.providers.config.catalog import ProviderPathResolution
from cli.agent_cli.providers.config.paths import AGENTHUB_PROVIDER_HOME_ENV


def iter_project_roots(
    *,
    cwd: str | Path | None = None,
    app_dir: Path,
    runtime_project_root_fn,
    project_root_markers_fn,
    find_project_root_fn,
) -> list[Path]:
    try:
        resolved_cwd = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
    except OSError:
        resolved_cwd = Path(cwd) if cwd is not None else Path.cwd()
    try:
        markers = project_root_markers_fn(resolved_cwd)
        resolved_project_root = find_project_root_fn(resolved_cwd, markers)
    except Exception:
        resolved_project_root = None
    if resolved_project_root is not None:
        roots: list[Path] = []
        current = resolved_cwd
        while True:
            if current not in roots:
                roots.append(current)
            if current == resolved_project_root or current == current.parent:
                break
            current = current.parent
        return roots
    return _provider_catalog_runtime.iter_project_roots(
        cwd=cwd,
        app_dir=app_dir,
        runtime_project_root_fn=runtime_project_root_fn,
    )


def find_project_provider_file(
    filename: str,
    *,
    cwd: str | Path | None,
    iter_project_roots_fn,
    project_provider_search_excluded_dirs_fn,
    local_config_dir_candidates,
) -> Path | None:
    excluded_dirs = project_provider_search_excluded_dirs_fn()
    for root in iter_project_roots_fn(cwd=cwd):
        for dirname in local_config_dir_candidates:
            candidate = root / dirname / filename
            if not candidate.exists():
                continue
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = candidate
            if resolved.parent in excluded_dirs:
                continue
            return candidate
    return None


def discover_provider_project_local_paths(
    filename: str,
    *,
    cwd: str | Path,
    home_config_paths: list[Path] | None,
    related_provider_roots_fn,
    workspace_trust_level_fn,
    project_local_data_dir_candidates,
    project_provider_search_excluded_dirs_fn,
) -> list[Path]:
    excluded_dirs = project_provider_search_excluded_dirs_fn()
    discovered = _provider_catalog_runtime.discover_provider_project_local_paths(
        filename,
        cwd=cwd,
        home_config_paths=home_config_paths,
        related_provider_roots_fn=related_provider_roots_fn,
        workspace_trust_level_fn=workspace_trust_level_fn,
        project_local_data_dir_candidates=project_local_data_dir_candidates,
    )
    return [path for path in discovered if path.parent not in excluded_dirs]


def project_provider_search_excluded_dirs(
    *,
    env_mapping,
    project_provider_layout_fn,
    agent_cli_config_toml: Path,
    agent_cli_auth_json: Path,
    legacy_compat_config_toml: Path,
    legacy_compat_auth_json: Path,
    explicit_provider_home_paths_fn,
) -> set[Path]:
    excluded_dirs: set[Path] = set()
    if not str(env_mapping.get("AGENT_CLI_HOME") or "").strip():
        layout = project_provider_layout_fn()
        for path in (layout.config_toml, layout.auth_json):
            try:
                excluded_dirs.add(path.parent.resolve())
            except OSError:
                excluded_dirs.add(path.parent)
    for path in (
        agent_cli_config_toml,
        agent_cli_auth_json,
        legacy_compat_config_toml,
        legacy_compat_auth_json,
    ):
        try:
            excluded_dirs.add(path.parent.resolve())
        except OSError:
            excluded_dirs.add(path.parent)
    explicit_paths = explicit_provider_home_paths_fn()
    if explicit_paths is not None:
        for path in explicit_paths:
            try:
                excluded_dirs.add(path.parent.resolve())
            except OSError:
                excluded_dirs.add(path.parent)
    return excluded_dirs


def ensure_project_provider_bootstrap(
    *,
    project_provider_layout_fn,
    ensure_project_provider_bootstrap_fn,
    agent_cli_config_toml: Path,
    agent_cli_auth_json: Path,
    legacy_compat_config_toml: Path,
    legacy_compat_auth_json: Path,
    claude_settings_json: Path,
    claude_config_json: Path,
    claude_state_json: Path,
) -> None:
    _provider_helpers_runtime.ensure_project_provider_bootstrap(
        project_provider_layout_fn=project_provider_layout_fn,
        ensure_project_provider_bootstrap_fn=ensure_project_provider_bootstrap_fn,
        agent_cli_config_toml=agent_cli_config_toml,
        agent_cli_auth_json=agent_cli_auth_json,
        legacy_compat_config_toml=legacy_compat_config_toml,
        legacy_compat_auth_json=legacy_compat_auth_json,
        claude_settings_json=claude_settings_json,
        claude_config_json=claude_config_json,
        claude_state_json=claude_state_json,
    )


def explicit_provider_home_paths(
    *,
    env_mapping,
    project_provider_layout_fn,
) -> tuple[Path, Path] | None:
    if not str(env_mapping.get(AGENTHUB_PROVIDER_HOME_ENV) or "").strip():
        return None
    layout = project_provider_layout_fn()
    return layout.config_toml, layout.auth_json


def provider_discovery_feature_settings(
    *,
    env_mapping,
    agent_cli_config_toml: Path,
    legacy_compat_config_toml: Path,
    explicit_provider_home_paths_fn,
    provider_discovery_feature_settings_fn,
    read_toml_fn,
) -> dict[str, Any]:
    config_paths: list[Path] = [agent_cli_config_toml, legacy_compat_config_toml]
    explicit_paths = explicit_provider_home_paths_fn()
    if explicit_paths is not None:
        explicit_config_path, _ = explicit_paths
        config_paths.insert(0, explicit_config_path)
    return provider_discovery_feature_settings_fn(
        env_mapping=env_mapping,
        config_paths=tuple(dict.fromkeys(config_paths)),
        read_toml_fn=read_toml_fn,
    )


def home_provider_paths(
    *,
    env_mapping,
    provider_discovery_strict_isolation_enabled_fn,
    explicit_provider_home_paths_fn,
    ensure_project_provider_bootstrap_fn,
    project_provider_layout_fn,
    agent_cli_config_toml: Path,
    agent_cli_auth_json: Path,
    legacy_compat_config_toml: Path,
    legacy_compat_auth_json: Path,
) -> tuple[Path, Path, bool]:
    explicit_paths = explicit_provider_home_paths_fn()
    if explicit_paths is not None:
        ensure_project_provider_bootstrap_fn()
        explicit_config_path, explicit_auth_path = explicit_paths
        return explicit_config_path, explicit_auth_path, False
    if provider_discovery_strict_isolation_enabled_fn():
        if str(env_mapping.get("AGENT_CLI_HOME") or "").strip():
            return agent_cli_config_toml, agent_cli_auth_json, False
        if agent_cli_config_toml.exists() or agent_cli_auth_json.exists():
            return agent_cli_config_toml, agent_cli_auth_json, False
        return legacy_compat_config_toml, legacy_compat_auth_json, False
    if str(env_mapping.get("AGENT_CLI_HOME") or "").strip():
        return agent_cli_config_toml, agent_cli_auth_json, False
    return _provider_helpers_runtime.home_provider_paths(
        ensure_project_provider_bootstrap_fn=ensure_project_provider_bootstrap_fn,
        project_provider_layout_fn=project_provider_layout_fn,
        agent_cli_config_toml=agent_cli_config_toml,
        agent_cli_auth_json=agent_cli_auth_json,
        legacy_compat_config_toml=legacy_compat_config_toml,
        legacy_compat_auth_json=legacy_compat_auth_json,
    )


def project_claude_home_dir(*, project_provider_layout_fn) -> Path | None:
    return _provider_helpers_runtime.project_claude_home_dir(
        project_provider_layout_fn=project_provider_layout_fn,
    )


def resolve_provider_paths(
    *,
    cwd: str | Path | None,
    strict_isolation: bool | None,
    env_mapping,
    provider_discovery_strict_isolation_enabled_fn,
    home_provider_paths_fn,
    find_project_provider_file_fn,
    resolve_provider_paths_impl_fn,
    legacy_compat_config_toml: Path,
    legacy_compat_auth_json: Path,
) -> ProviderPathResolution:
    explicit_runtime_home = bool(
        str(env_mapping.get(AGENTHUB_PROVIDER_HOME_ENV) or "").strip()
        or str(env_mapping.get("AGENT_CLI_HOME") or "").strip()
    )
    resolved_strict_isolation = (
        provider_discovery_strict_isolation_enabled_fn() or explicit_runtime_home
        if strict_isolation is None
        else bool(strict_isolation)
    )
    resolution = _provider_catalog_runtime.resolve_provider_paths(
        cwd=cwd,
        home_provider_paths_fn=home_provider_paths_fn,
        find_project_provider_file_fn=find_project_provider_file_fn,
        resolve_provider_paths_impl_fn=resolve_provider_paths_impl_fn,
        legacy_compat_config_toml=legacy_compat_config_toml,
        legacy_compat_auth_json=legacy_compat_auth_json,
        strict_isolation=resolved_strict_isolation,
    )
    if explicit_runtime_home and not resolution.used_project_local:
        home_config_path, home_auth_path, _home_is_project_local = home_provider_paths_fn()
        return ProviderPathResolution(
            config_path=home_config_path,
            auth_path=home_auth_path,
            config_exists=home_config_path.exists(),
            auth_exists=home_auth_path.exists(),
            used_project_local=False,
        )
    return resolution
