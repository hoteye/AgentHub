from __future__ import annotations

import os
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, Protocol

from cli.agent_cli import provider_catalog_runtime as _provider_catalog_runtime
from cli.agent_cli import provider_helpers_runtime as _provider_helpers_runtime
from cli.agent_cli import provider_paths_helpers_runtime as _provider_paths_helpers_runtime
from cli.agent_cli.environment_context import environment_context_marker_offset
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent
from cli.agent_cli.providers import provider_discovery_feature_config_runtime
from cli.agent_cli.providers.config.bootstrap import ensure_project_provider_bootstrap
from cli.agent_cli.providers.config.catalog import (
    ModelCatalogEntry,
    ProviderCatalog,
    ProviderConfig,
    ProviderPathResolution,
)
from cli.agent_cli.providers.config.catalog import (
    build_provider_catalog as _build_provider_catalog_impl,
)
from cli.agent_cli.providers.config.catalog import (
    candidate_api_key_names as _candidate_api_key_names_impl,
)
from cli.agent_cli.providers.config.catalog import (
    default_model_entry as _default_model_entry_impl,
)
from cli.agent_cli.providers.config.catalog import (
    find_model_entry as _find_model_entry_impl,
)
from cli.agent_cli.providers.config.catalog import (
    first_configured_key as _first_configured_key_impl,
)
from cli.agent_cli.providers.config.catalog import (
    infer_planner_kind as _infer_planner_kind_impl,
)
from cli.agent_cli.providers.config.catalog import (
    optional_bool as _optional_bool_impl,
)
from cli.agent_cli.providers.config.catalog import (
    read_json_file as _read_json_impl,
)
from cli.agent_cli.providers.config.catalog import (
    read_toml_file as _read_toml_impl,
)
from cli.agent_cli.providers.config.catalog import (
    resolve_provider_paths as _resolve_provider_paths_impl,
)
from cli.agent_cli.providers.config.catalog import (
    select_provider_config as _select_provider_config_impl,
)
from cli.agent_cli.providers.config.paths import AGENTHUB_PROVIDER_HOME_ENV, project_provider_layout
from cli.agent_cli.providers.protocols.anthropic_messages import (
    load_claude_provider_config,
    should_use_claude_provider,
)
from cli.agent_cli.providers.registry import build_planner as _build_planner_impl
from cli.agent_cli.providers.shared.planners_common import BasePlanner as _BasePlannerImpl
from cli.agent_cli.providers.shared.policy_routing import (
    looks_like_policy_context as _looks_like_policy_context_impl,
)
from cli.agent_cli.providers.shared.policy_routing import (
    looks_like_policy_question as _looks_like_policy_question_impl,
)
from cli.agent_cli.providers.shared.tool_calls import (
    command_for_tool_call as _command_for_tool_call_impl,
)
from cli.agent_cli.providers.shared.tool_calls import (
    plugin_system_prompt_addendum as _plugin_system_prompt_addendum_impl,
)
from cli.agent_cli.providers.shared.tool_calls import (
    plugin_tool_call_command as _plugin_tool_call_command_impl,
)
from cli.agent_cli.providers.shared.tool_calls import (
    tool_result_payload as _tool_result_payload_impl,
)
from cli.agent_cli.runtime_paths import PROJECT_LOCAL_DATA_DIR_CANDIDATES, runtime_project_root
from cli.agent_cli.workspace_context import (
    find_project_root,
    project_root_markers,
    workspace_context_marker_offset,
    workspace_trust_level,
)

APP_DIR = Path(__file__).resolve().parent
LOCAL_CONFIG_DIRNAME = ".agent_cli"
LEGACY_LOCAL_CONFIG_DIRNAME = ".agent_cli_legacy"
LOCAL_CONFIG_DIR_CANDIDATES = PROJECT_LOCAL_DATA_DIR_CANDIDATES
AGENT_CLI_HOME = Path(os.environ.get("AGENT_CLI_HOME") or (Path.home() / LOCAL_CONFIG_DIRNAME))
LEGACY_COMPAT_HOME = Path.home() / LEGACY_LOCAL_CONFIG_DIRNAME
AGENT_CLI_CONFIG_TOML = AGENT_CLI_HOME / "config.toml"
AGENT_CLI_AUTH_JSON = AGENT_CLI_HOME / "auth.json"
LEGACY_COMPAT_CONFIG_TOML = LEGACY_COMPAT_HOME / "config.toml"
LEGACY_COMPAT_AUTH_JSON = LEGACY_COMPAT_HOME / "auth.json"
CLAUDE_SETTINGS_JSON = Path.home() / ".claude" / "settings.json"
CLAUDE_CONFIG_JSON = Path.home() / ".claude" / "config.json"
CLAUDE_STATE_JSON = Path.home() / ".claude.json"
_USER_MODEL_SELECTION_KEYS = ("model_provider", "model", "model_reasoning_effort")

PlannerToolExecutor = Callable[[str], tuple[str, list[ToolEvent]]]
PluginManagerFactory = Callable[[], PluginManager | None]
ProviderManagementSnapshot = _provider_catalog_runtime.ProviderManagementSnapshot


class Planner(Protocol):
    def public_summary(self) -> dict[str, Any]: ...

    def plan(
        self,
        user_text: str,
        history: list[dict[str, str]],
        *,
        tool_executor: PlannerToolExecutor | None = None,
        attachments: list[PromptAttachment] | None = None,
        input_items: list[dict[str, Any]] | None = None,
        turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentIntent: ...


build_ordered_request_prelude_items = _provider_helpers_runtime.build_ordered_request_prelude_items
request_prelude_contract = partial(
    _provider_helpers_runtime.request_prelude_contract,
    workspace_context_marker_offset_fn=workspace_context_marker_offset,
    environment_context_marker_offset_fn=environment_context_marker_offset,
)
extract_current_turn_prelude_items = partial(
    _provider_helpers_runtime.extract_current_turn_prelude_items,
    workspace_context_marker_offset_fn=workspace_context_marker_offset,
    environment_context_marker_offset_fn=environment_context_marker_offset,
)
extract_current_turn_prelude_contract = partial(
    _provider_helpers_runtime.extract_current_turn_prelude_contract,
    workspace_context_marker_offset_fn=workspace_context_marker_offset,
    environment_context_marker_offset_fn=environment_context_marker_offset,
)


_read_json = _read_json_impl
_read_toml = _read_toml_impl
_quoted_toml_string = _provider_catalog_runtime.quoted_toml_string
_upsert_root_toml_string_key = _provider_helpers_runtime.upsert_root_toml_string_key
_slugify_model_key = _provider_helpers_runtime.slugify_model_key
_candidate_api_key_names = _candidate_api_key_names_impl
_first_configured_key = _first_configured_key_impl
_infer_planner_kind = _infer_planner_kind_impl
_optional_bool = _optional_bool_impl
_tool_result_payload = _tool_result_payload_impl
_looks_like_policy_question = _looks_like_policy_question_impl
_looks_like_policy_context = _looks_like_policy_context_impl
BasePlanner = _BasePlannerImpl


def build_planner(
    config: ProviderConfig,
    *,
    host_platform: HostPlatform | None = None,
    cwd: str | Path | None = None,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> Planner:
    return _build_planner_impl(
        config,
        host_platform=host_platform,
        cwd=cwd,
        plugin_manager_factory=plugin_manager_factory,
    )


def save_user_model_selection(
    *,
    provider_name: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> Path:
    return _provider_catalog_runtime.save_user_model_selection(
        path=AGENT_CLI_CONFIG_TOML,
        provider_name=provider_name,
        model=model,
        reasoning_effort=reasoning_effort,
    )


def _read_user_model_selection_toml() -> dict[str, Any]:
    config_paths = [AGENT_CLI_CONFIG_TOML]
    if not str(os.environ.get("AGENT_CLI_HOME") or "").strip():
        config_paths.append(LEGACY_COMPAT_CONFIG_TOML)
    return _provider_helpers_runtime.read_user_model_selection_toml(
        config_paths=tuple(config_paths),
        read_toml_fn=_read_toml,
        selection_keys=_USER_MODEL_SELECTION_KEYS,
    )


def _iter_project_roots(*, cwd: str | Path | None = None) -> list[Path]:
    return _provider_paths_helpers_runtime.iter_project_roots(
        cwd=cwd,
        app_dir=APP_DIR,
        runtime_project_root_fn=runtime_project_root,
        project_root_markers_fn=project_root_markers,
        find_project_root_fn=find_project_root,
    )


def _find_project_provider_file(filename: str, *, cwd: str | Path | None = None) -> Path | None:
    return _provider_paths_helpers_runtime.find_project_provider_file(
        filename,
        cwd=cwd,
        iter_project_roots_fn=_iter_project_roots,
        project_provider_search_excluded_dirs_fn=_project_provider_search_excluded_dirs,
        local_config_dir_candidates=LOCAL_CONFIG_DIR_CANDIDATES,
    )


def _project_provider_layout():
    return project_provider_layout(cli_root=APP_DIR.parent)


def _related_provider_roots(*, cwd: str | Path) -> list[Path]:
    return _iter_project_roots(cwd=cwd)


def _discover_provider_project_local_paths(
    filename: str,
    *,
    cwd: str | Path,
    home_config_paths: list[Path] | None = None,
) -> list[Path]:
    return _provider_paths_helpers_runtime.discover_provider_project_local_paths(
        filename,
        cwd=cwd,
        home_config_paths=home_config_paths,
        related_provider_roots_fn=_related_provider_roots,
        workspace_trust_level_fn=workspace_trust_level,
        project_local_data_dir_candidates=PROJECT_LOCAL_DATA_DIR_CANDIDATES,
        project_provider_search_excluded_dirs_fn=_project_provider_search_excluded_dirs,
    )


def _project_provider_search_excluded_dirs() -> set[Path]:
    return _provider_paths_helpers_runtime.project_provider_search_excluded_dirs(
        env_mapping=os.environ,
        project_provider_layout_fn=_project_provider_layout,
        agent_cli_config_toml=AGENT_CLI_CONFIG_TOML,
        agent_cli_auth_json=AGENT_CLI_AUTH_JSON,
        legacy_compat_config_toml=LEGACY_COMPAT_CONFIG_TOML,
        legacy_compat_auth_json=LEGACY_COMPAT_AUTH_JSON,
        explicit_provider_home_paths_fn=_explicit_provider_home_paths,
    )


def _ensure_project_provider_bootstrap() -> None:
    _provider_paths_helpers_runtime.ensure_project_provider_bootstrap(
        project_provider_layout_fn=_project_provider_layout,
        ensure_project_provider_bootstrap_fn=ensure_project_provider_bootstrap,
        agent_cli_config_toml=AGENT_CLI_CONFIG_TOML,
        agent_cli_auth_json=AGENT_CLI_AUTH_JSON,
        legacy_compat_config_toml=LEGACY_COMPAT_CONFIG_TOML,
        legacy_compat_auth_json=LEGACY_COMPAT_AUTH_JSON,
        claude_settings_json=CLAUDE_SETTINGS_JSON,
        claude_config_json=CLAUDE_CONFIG_JSON,
        claude_state_json=CLAUDE_STATE_JSON,
    )


def _explicit_provider_home_paths() -> tuple[Path, Path] | None:
    return _provider_paths_helpers_runtime.explicit_provider_home_paths(
        env_mapping=os.environ,
        project_provider_layout_fn=_project_provider_layout,
    )


def _provider_discovery_feature_settings() -> dict[str, Any]:
    return _provider_paths_helpers_runtime.provider_discovery_feature_settings(
        env_mapping=os.environ,
        agent_cli_config_toml=AGENT_CLI_CONFIG_TOML,
        legacy_compat_config_toml=LEGACY_COMPAT_CONFIG_TOML,
        explicit_provider_home_paths_fn=_explicit_provider_home_paths,
        provider_discovery_feature_settings_fn=provider_discovery_feature_config_runtime.provider_discovery_feature_settings,
        read_toml_fn=_read_toml,
    )


def _provider_discovery_strict_isolation_enabled() -> bool:
    return bool(_provider_discovery_feature_settings().get("strict_isolation"))


def _home_provider_paths() -> tuple[Path, Path, bool]:
    return _provider_paths_helpers_runtime.home_provider_paths(
        env_mapping=os.environ,
        provider_discovery_strict_isolation_enabled_fn=_provider_discovery_strict_isolation_enabled,
        explicit_provider_home_paths_fn=_explicit_provider_home_paths,
        ensure_project_provider_bootstrap_fn=_ensure_project_provider_bootstrap,
        project_provider_layout_fn=_project_provider_layout,
        agent_cli_config_toml=AGENT_CLI_CONFIG_TOML,
        agent_cli_auth_json=AGENT_CLI_AUTH_JSON,
        legacy_compat_config_toml=LEGACY_COMPAT_CONFIG_TOML,
        legacy_compat_auth_json=LEGACY_COMPAT_AUTH_JSON,
    )


def _private_provider_auth_paths() -> list[Path]:
    paths: list[Path] = []
    if not str(os.environ.get("AGENT_CLI_HOME") or "").strip():
        paths.append(LEGACY_COMPAT_AUTH_JSON)
    paths.append(AGENT_CLI_AUTH_JSON)
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def _private_provider_config_paths() -> list[Path]:
    paths: list[Path] = []
    if not str(os.environ.get("AGENT_CLI_HOME") or "").strip():
        paths.append(LEGACY_COMPAT_CONFIG_TOML)
    paths.append(AGENT_CLI_CONFIG_TOML)
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def _project_claude_home_dir() -> Path | None:
    return _provider_paths_helpers_runtime.project_claude_home_dir(
        project_provider_layout_fn=_project_provider_layout,
    )


def resolve_provider_paths(
    *,
    cwd: str | Path | None = None,
    strict_isolation: bool | None = None,
) -> ProviderPathResolution:
    return _provider_paths_helpers_runtime.resolve_provider_paths(
        cwd=cwd,
        strict_isolation=strict_isolation,
        env_mapping=os.environ,
        provider_discovery_strict_isolation_enabled_fn=_provider_discovery_strict_isolation_enabled,
        home_provider_paths_fn=_home_provider_paths,
        find_project_provider_file_fn=_find_project_provider_file,
        resolve_provider_paths_impl_fn=_resolve_provider_paths_impl,
        legacy_compat_config_toml=LEGACY_COMPAT_CONFIG_TOML,
        legacy_compat_auth_json=LEGACY_COMPAT_AUTH_JSON,
    )


def _build_provider_catalog(toml_data: dict[str, Any]) -> ProviderCatalog:
    return _build_provider_catalog_impl(
        toml_data,
        optional_bool_fn=_optional_bool,
        infer_planner_kind_fn=_infer_planner_kind,
    )


def _find_model_entry(
    selector: str,
    catalog: ProviderCatalog,
    *,
    preferred_provider: str | None = None,
) -> ModelCatalogEntry | None:
    return _find_model_entry_impl(selector, catalog, preferred_provider=preferred_provider)


_default_model_entry = _default_model_entry_impl


def _load_provider_inputs(
    *,
    cwd: str | Path | None = None,
    strict_isolation: bool | None = None,
) -> tuple[ProviderPathResolution, dict[str, Any], dict[str, Any]]:
    resolved_strict_isolation = (
        _provider_discovery_strict_isolation_enabled()
        if strict_isolation is None
        else bool(strict_isolation)
    )
    explicit_runtime_home = bool(
        str(os.environ.get(AGENTHUB_PROVIDER_HOME_ENV) or "").strip()
        or str(os.environ.get("AGENT_CLI_HOME") or "").strip()
    )
    return _provider_catalog_runtime.load_provider_inputs(
        cwd=cwd,
        resolve_provider_paths_fn=resolve_provider_paths,
        home_provider_paths_fn=_home_provider_paths,
        discover_provider_project_local_paths_fn=_discover_provider_project_local_paths,
        read_toml_fn=_read_toml,
        read_json_fn=_read_json,
        read_user_model_selection_toml_fn=_read_user_model_selection_toml,
        private_config_paths_fn=_private_provider_config_paths,
        private_auth_paths_fn=_private_provider_auth_paths,
        strict_isolation=resolved_strict_isolation or explicit_runtime_home,
    )


def load_provider_catalog(*, cwd: str | Path | None = None) -> ProviderCatalog:
    return _provider_catalog_runtime.load_provider_catalog(
        cwd=cwd,
        load_provider_inputs_fn=_load_provider_inputs,
        build_provider_catalog_fn=_build_provider_catalog,
    )


def load_provider_management_snapshot(
    *,
    cwd: str | Path | None = None,
    env_overrides: dict[str, str | None] | None = None,
) -> ProviderManagementSnapshot:
    return _provider_catalog_runtime.load_provider_management_snapshot(
        cwd=cwd,
        env_overrides=env_overrides,
        load_provider_inputs_fn=_load_provider_inputs,
        build_provider_catalog_fn=_build_provider_catalog,
        select_provider_config_fn=_select_provider_config_impl,
        optional_bool_fn=_optional_bool,
        infer_planner_kind_fn=_infer_planner_kind,
        should_use_claude_provider_fn=should_use_claude_provider,
        project_claude_home_dir_fn=_project_claude_home_dir,
        load_claude_provider_config_fn=load_claude_provider_config,
    )


def load_provider_config(
    *,
    cwd: str | Path | None = None,
    env_overrides: dict[str, str | None] | None = None,
) -> ProviderConfig | None:
    return _provider_catalog_runtime.load_provider_config(
        cwd=cwd,
        env_overrides=env_overrides,
        load_provider_inputs_fn=_load_provider_inputs,
        select_provider_config_fn=_select_provider_config_impl,
        optional_bool_fn=_optional_bool,
        infer_planner_kind_fn=_infer_planner_kind,
        should_use_claude_provider_fn=should_use_claude_provider,
        project_claude_home_dir_fn=_project_claude_home_dir,
        load_claude_provider_config_fn=load_claude_provider_config,
    )


def _quote_arg(value: Any) -> str:
    return _provider_helpers_runtime.quote_arg(value)


def _plugin_system_prompt_addendum(
    *, plugin_manager_factory: PluginManagerFactory | None = None
) -> str:
    return _plugin_system_prompt_addendum_impl(plugin_manager_factory=plugin_manager_factory)


def _plugin_tool_call_command(
    name: str,
    arguments: dict[str, Any],
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> str | None:
    return _plugin_tool_call_command_impl(
        name,
        arguments,
        quote_arg_fn=_quote_arg,
        plugin_manager_factory=plugin_manager_factory,
    )


def _command_for_tool_call(
    name: str,
    arguments: dict[str, Any],
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> str | None:
    return _command_for_tool_call_impl(
        name,
        arguments,
        host_platform,
        optional_bool_fn=_optional_bool,
        quote_arg_fn=_quote_arg,
        plugin_manager_factory=plugin_manager_factory,
    )


def _tool_specs(
    host_platform: HostPlatform,
    *,
    cwd: str | Path | None = None,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> list[dict[str, Any]]:
    from cli.agent_cli.providers.protocols.openai_chat import (
        _tool_specs as _chat_completions_tool_specs,
    )

    config = load_provider_config(cwd=cwd) or ProviderConfig(model="", api_key="")
    factory = plugin_manager_factory or (lambda: PluginManager(cwd=cwd))
    return _chat_completions_tool_specs(config, host_platform, plugin_manager_factory=factory)
