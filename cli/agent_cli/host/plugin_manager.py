from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cli.agent_cli.gateway_core.models import (
    ConnectorRegistration,
    PolicyRegistration,
    TriggerRegistration,
)
from cli.agent_cli.host import plugin_index_runtime as _plugin_index_runtime
from cli.agent_cli.host import plugin_manager_helpers as helpers
from cli.agent_cli.host import plugin_manager_runtime as _plugin_manager_runtime
from cli.agent_cli.host import plugin_types as _plugin_types
from cli.agent_cli.host.plugin_installation_state import PluginInstallationStore
from cli.agent_cli.host.plugin_store_runtime import (
    DEFAULT_APP_CONFIG_FILE,
    DEFAULT_MCP_CONFIG_FILE,
    DEFAULT_PLUGIN_SECTION_MARKETPLACE,
    LEGACY_COMPAT_HOME,
    PluginStore,
    default_reference_home,
    default_plugin_root,
    default_plugin_state_path,
    plugin_namespace_for_skill_path as _plugin_namespace_for_skill_path,
    _safe_resolve,
)

CommandHandler = _plugin_types.CommandHandler
ToolHandler = _plugin_types.ToolHandler
WorkflowHandler = _plugin_types.WorkflowHandler
PluginId = _plugin_types.PluginId
PluginStoreError = _plugin_types.PluginStoreError
RegisteredCommand = _plugin_types.RegisteredCommand
RegisteredTool = _plugin_types.RegisteredTool
RegisteredWorkflowHandler = _plugin_types.RegisteredWorkflowHandler
LoadedPlugin = _plugin_types.LoadedPlugin
PluginCommandRegistry = _plugin_types.PluginCommandRegistry
PluginToolRegistry = _plugin_types.PluginToolRegistry
_PluginSource = _plugin_types._PluginSource


class PluginManager:
    _required_plugin_files = staticmethod(helpers.required_plugin_files)
    _normalize_connector_registration = helpers.normalize_connector_registration
    _normalize_trigger_registration = helpers.normalize_trigger_registration
    _normalize_policy_registration = helpers.normalize_policy_registration
    _normalize_workflow_handler_registration = helpers.normalize_workflow_handler_registration
    _call_runtime_builder = helpers.call_runtime_builder
    _ensure_unique_registration = helpers.ensure_unique_registration
    _ensure_project_root_on_path = staticmethod(helpers.ensure_project_root_on_path)
    _load_state = helpers.load_state
    _save_state = helpers.save_state
    _clear_plugin_modules = staticmethod(helpers.clear_plugin_modules)
    _ensure_host_plugin_package = staticmethod(helpers.ensure_host_plugin_package)
    _load_module_from_file = staticmethod(helpers.load_module_from_file)
    _config_home_paths = staticmethod(helpers.config_home_paths)
    _merged_workspace_config = helpers.merged_workspace_config
    workspace_trust_level = helpers.workspace_trust_level_from_paths
    _plugins_feature_enabled_from_config = staticmethod(helpers.plugins_feature_enabled_from_config)
    _configured_plugins_from_config = staticmethod(helpers.configured_plugins_from_config)
    _plugin_enabled = staticmethod(helpers.plugin_enabled)
    _bundled_plugin_key = staticmethod(helpers.bundled_plugin_key)
    _discover_bundled_sources = helpers.discover_bundled_sources
    _configured_external_sources = helpers.configured_external_sources
    _compat_reload = helpers.compat_reload
    _reference_reload = helpers.reference_reload
    _load_runtime_capabilities = helpers.load_runtime_capabilities
    _merge_loaded_plugin = staticmethod(helpers.merge_loaded_plugin)
    _assign_state = staticmethod(helpers.assign_state)
    reload = helpers.reload_manager
    _write_plugin_enabled_config = staticmethod(helpers.write_plugin_enabled_config)
    _remove_plugin_config_section = staticmethod(helpers.remove_plugin_config_section)
    install_plugin = helpers.install_plugin
    remove_plugin = helpers.remove_plugin
    list_plugins = helpers.list_plugins
    enable_plugin = helpers.enable_plugin
    disable_plugin = helpers.disable_plugin
    disable_all_plugins = helpers.disable_all_plugins
    _resolve_plugin = helpers.resolve_plugin

    def __init__(
        self,
        *,
        cwd: str | Path | None = None,
        plugin_root: Path | None = None,
        state_path: Path | None = None,
        reference_home: Path | None = None,
        bundled_plugin_root: Path | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.cwd = _safe_resolve(Path(cwd or Path.cwd()))
        self._explicit_plugin_root = Path(plugin_root).resolve() if plugin_root is not None else None
        self._compat_state_path = Path(state_path).resolve() if state_path is not None else None
        self._compat_mode = self._explicit_plugin_root is not None or self._compat_state_path is not None
        self.reference_home = _safe_resolve(Path(reference_home) if reference_home is not None else default_reference_home())
        self.store = PluginStore(self.reference_home)
        self.installation_store = PluginInstallationStore.from_reference_home(self.reference_home)
        self.plugin_root = (
            self._explicit_plugin_root
            if self._explicit_plugin_root is not None
            else (default_plugin_root() if self._compat_mode else self.store.root)
        )
        self.bundled_plugin_root = (
            _safe_resolve(Path(bundled_plugin_root))
            if bundled_plugin_root is not None
            else default_plugin_root()
        )
        self.config_path = (
            _safe_resolve(Path(config_path))
            if config_path is not None
            else self.reference_home / "config.toml"
        )
        self.state_path = (
            self._compat_state_path
            if self._compat_state_path is not None
            else default_plugin_state_path(project_root=self.plugin_root.parent)
        )
        self._plugins: List[LoadedPlugin] = []
        self._commands: Dict[str, RegisteredCommand] = {}
        self._tools: Dict[str, RegisteredTool] = {}
        self._connectors: Dict[str, ConnectorRegistration] = {}
        self._triggers: Dict[str, TriggerRegistration] = {}
        self._policies: Dict[str, PolicyRegistration] = {}
        self._workflow_handlers: Dict[Tuple[str, str], RegisteredWorkflowHandler] = {}
        self._cache_by_cwd: Dict[Path, Dict[str, Any]] = {}
        self.reload()

    def _clear_cache(self) -> None:
        self._cache_by_cwd.pop(self.cwd, None)

    def _validate_plugin_dir(self, candidate_dir: Path) -> Optional[str]:
        return helpers.validate_plugin_dir(
            candidate_dir,
            required_plugin_files_fn=self._required_plugin_files,
        )

    def _extract_source_dir(self, source_path: str) -> Tuple[Optional[Path], Optional[Path], str, Dict[str, Any]]:
        return helpers.extract_source_dir(
            source_path,
            validate_plugin_dir_fn=self._validate_plugin_dir,
        )

    def set_cwd(self, cwd: str | Path) -> Path:
        resolved = _safe_resolve(Path(cwd))
        if resolved != self.cwd:
            self.cwd = resolved
            self.reload()
        return self.cwd

    def gui_bridge_metadata(self) -> Dict[str, Any]:
        return {
            "mcpServers": self.mcp_server_summaries(),
            "appConnectors": self.effective_app_connectors(),
        }

    def invoke_tool(self, name: str, *args: Any, **kwargs: Any) -> Any:
        item = self._tools.get(str(name or "").strip())
        if item is None:
            raise KeyError(name)
        return item.handler(*args, **kwargs)


_plugin_manager_runtime.bind_plugin_manager_methods(PluginManager)

plugin_namespace_for_skill_path = _plugin_namespace_for_skill_path
