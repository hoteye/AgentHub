from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cli.agent_cli.providers.config.catalog import ProviderPathResolution

if TYPE_CHECKING:
    from cli.agent_cli.provider_facade_paths_runtime import ProviderFacadePathRuntimeDeps
else:
    ProviderFacadePathRuntimeDeps = Any


@dataclass(frozen=True)
class ProviderFacadePathRuntimeBindings:
    save_user_model_selection: Callable[..., Path]
    read_user_model_selection_toml: Callable[[], dict[str, Any]]
    iter_project_roots: Callable[..., list[Path]]
    find_project_provider_file: Callable[..., Path | None]
    project_provider_layout: Callable[[], Any]
    related_provider_roots: Callable[..., list[Path]]
    discover_provider_project_local_paths: Callable[..., list[Path]]
    project_provider_search_excluded_dirs: Callable[[], set[Path]]
    ensure_project_provider_bootstrap: Callable[[], None]
    explicit_provider_home_paths: Callable[[], tuple[Path, Path] | None]
    provider_discovery_feature_settings: Callable[[], dict[str, Any]]
    provider_discovery_strict_isolation_enabled: Callable[[], bool]
    home_provider_paths: Callable[[], tuple[Path, Path, bool]]
    default_config_paths: Callable[[], list[Path]]
    private_provider_auth_paths: Callable[[], list[Path]]
    private_provider_config_paths: Callable[[], list[Path]]
    project_claude_home_dir: Callable[[], Path | None]
    resolve_provider_paths: Callable[..., ProviderPathResolution]
    load_provider_inputs: Callable[
        ..., tuple[ProviderPathResolution, dict[str, Any], dict[str, Any]]
    ]


def bind_path_runtime(
    deps_factory: Callable[[], ProviderFacadePathRuntimeDeps],
) -> ProviderFacadePathRuntimeBindings:
    from cli.agent_cli import provider_facade_paths_runtime as _runtime

    module_name = str(getattr(deps_factory, "__module__", _runtime.__name__) or _runtime.__name__)

    def _save_user_model_selection(
        *,
        provider_name: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> Path:
        return _runtime.save_user_model_selection(
            provider_name=provider_name,
            model=model,
            reasoning_effort=reasoning_effort,
            deps=deps_factory(),
        )

    def _read_user_model_selection_toml() -> dict[str, Any]:
        return _runtime.read_user_model_selection_toml(deps=deps_factory())

    def _iter_project_roots(*, cwd: str | Path | None = None) -> list[Path]:
        return _runtime.iter_project_roots(cwd=cwd, deps=deps_factory())

    def _find_project_provider_file(filename: str, *, cwd: str | Path | None = None) -> Path | None:
        return _runtime.find_project_provider_file(filename, cwd=cwd, deps=deps_factory())

    def _project_provider_layout():
        return _runtime.project_provider_layout(deps=deps_factory())

    def _related_provider_roots(*, cwd: str | Path) -> list[Path]:
        return _runtime.related_provider_roots(cwd=cwd, deps=deps_factory())

    def _discover_provider_project_local_paths(
        filename: str,
        *,
        cwd: str | Path,
        home_config_paths: list[Path] | None = None,
    ) -> list[Path]:
        return _runtime.discover_provider_project_local_paths(
            filename,
            cwd=cwd,
            home_config_paths=home_config_paths,
            deps=deps_factory(),
        )

    def _project_provider_search_excluded_dirs() -> set[Path]:
        return _runtime.project_provider_search_excluded_dirs(deps=deps_factory())

    def _ensure_project_provider_bootstrap() -> None:
        _runtime.ensure_project_provider_bootstrap(deps=deps_factory())

    def _explicit_provider_home_paths() -> tuple[Path, Path] | None:
        return _runtime.explicit_provider_home_paths(deps=deps_factory())

    def _provider_discovery_feature_settings() -> dict[str, Any]:
        return _runtime.provider_discovery_feature_settings(deps=deps_factory())

    def _provider_discovery_strict_isolation_enabled() -> bool:
        return _runtime.provider_discovery_strict_isolation_enabled(deps=deps_factory())

    def _home_provider_paths() -> tuple[Path, Path, bool]:
        return _runtime.home_provider_paths(deps=deps_factory())

    def _default_config_paths() -> list[Path]:
        return _runtime.default_provider_config_paths(deps=deps_factory())

    def _private_provider_auth_paths() -> list[Path]:
        return _runtime.private_provider_auth_paths(deps=deps_factory())

    def _private_provider_config_paths() -> list[Path]:
        return _runtime.private_provider_config_paths(deps=deps_factory())

    def _project_claude_home_dir() -> Path | None:
        return _runtime.project_claude_home_dir(deps=deps_factory())

    def _resolve_provider_paths(
        *,
        cwd: str | Path | None = None,
        strict_isolation: bool | None = None,
    ) -> ProviderPathResolution:
        return _runtime.resolve_provider_paths(
            cwd=cwd,
            strict_isolation=strict_isolation,
            deps=deps_factory(),
        )

    def _load_provider_inputs(
        *,
        cwd: str | Path | None = None,
        strict_isolation: bool | None = None,
    ) -> tuple[ProviderPathResolution, dict[str, Any], dict[str, Any]]:
        return _runtime.load_provider_inputs(
            cwd=cwd,
            strict_isolation=strict_isolation,
            deps=deps_factory(),
        )

    for function, name in (
        (_save_user_model_selection, "save_user_model_selection"),
        (_read_user_model_selection_toml, "_read_user_model_selection_toml"),
        (_iter_project_roots, "_iter_project_roots"),
        (_find_project_provider_file, "_find_project_provider_file"),
        (_project_provider_layout, "_project_provider_layout"),
        (_related_provider_roots, "_related_provider_roots"),
        (_discover_provider_project_local_paths, "_discover_provider_project_local_paths"),
        (_project_provider_search_excluded_dirs, "_project_provider_search_excluded_dirs"),
        (_ensure_project_provider_bootstrap, "_ensure_project_provider_bootstrap"),
        (_explicit_provider_home_paths, "_explicit_provider_home_paths"),
        (_provider_discovery_feature_settings, "_provider_discovery_feature_settings"),
        (
            _provider_discovery_strict_isolation_enabled,
            "_provider_discovery_strict_isolation_enabled",
        ),
        (_home_provider_paths, "_home_provider_paths"),
        (_default_config_paths, "_default_provider_config_paths"),
        (_private_provider_auth_paths, "_private_provider_auth_paths"),
        (_private_provider_config_paths, "_private_provider_config_paths"),
        (_project_claude_home_dir, "_project_claude_home_dir"),
        (_resolve_provider_paths, "resolve_provider_paths"),
        (_load_provider_inputs, "_load_provider_inputs"),
    ):
        function.__name__ = name
        function.__qualname__ = name
        function.__module__ = module_name

    return ProviderFacadePathRuntimeBindings(
        save_user_model_selection=_save_user_model_selection,
        read_user_model_selection_toml=_read_user_model_selection_toml,
        iter_project_roots=_iter_project_roots,
        find_project_provider_file=_find_project_provider_file,
        project_provider_layout=_project_provider_layout,
        related_provider_roots=_related_provider_roots,
        discover_provider_project_local_paths=_discover_provider_project_local_paths,
        project_provider_search_excluded_dirs=_project_provider_search_excluded_dirs,
        ensure_project_provider_bootstrap=_ensure_project_provider_bootstrap,
        explicit_provider_home_paths=_explicit_provider_home_paths,
        provider_discovery_feature_settings=_provider_discovery_feature_settings,
        provider_discovery_strict_isolation_enabled=_provider_discovery_strict_isolation_enabled,
        home_provider_paths=_home_provider_paths,
        default_config_paths=_default_config_paths,
        private_provider_auth_paths=_private_provider_auth_paths,
        private_provider_config_paths=_private_provider_config_paths,
        project_claude_home_dir=_project_claude_home_dir,
        resolve_provider_paths=_resolve_provider_paths,
        load_provider_inputs=_load_provider_inputs,
    )
