from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from cli.agent_cli.host import plugin_config_runtime as _plugin_config_runtime
from cli.agent_cli.host import plugin_host_runtime as _plugin_host_runtime
from cli.agent_cli.host.plugin_store_runtime import LEGACY_COMPAT_HOME, default_reference_home, _find_project_root
from cli.agent_cli.workspace_context import read_merged_project_toml, workspace_trust_level


def ensure_project_root_on_path() -> None:
    root_text = str(_find_project_root())
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def load_enabled_state(state_path: Path) -> Dict[str, bool]:
    return _plugin_host_runtime.load_enabled_state(state_path)


def save_enabled_state(state_path: Path, enabled_map: Dict[str, bool]) -> None:
    _plugin_host_runtime.save_enabled_state(state_path, enabled_map)


def clear_plugin_modules() -> None:
    _plugin_host_runtime.clear_plugin_modules(sys.modules)


def ensure_host_plugin_package(plugin_name: str, plugin_dir: Path) -> None:
    _plugin_host_runtime.ensure_host_plugin_package(plugin_name, plugin_dir, sys.modules)


def load_module_from_file(plugin_name: str, module_name: str, file_path: Path) -> Any:
    return _plugin_host_runtime.load_module_from_file(plugin_name, module_name, file_path, sys.modules)


def config_home_paths(config_path: Path, reference_home: Path, legacy_compat_home: Path) -> List[Path]:
    return _plugin_config_runtime.config_home_paths(
        config_path=config_path,
        reference_home=reference_home,
        default_reference_home=default_reference_home,
        legacy_compat_home=legacy_compat_home,
    )


def merged_workspace_config(manager: Any) -> Dict[str, Any]:
    return _plugin_config_runtime.merged_workspace_config(
        cwd=manager.cwd,
        home_config_paths=config_home_paths(
            config_path=manager.config_path,
            reference_home=manager.reference_home,
            legacy_compat_home=LEGACY_COMPAT_HOME,
        ),
        read_merged_project_toml_fn=read_merged_project_toml,
    )


def workspace_trust_level_from_paths(manager: Any) -> str:
    return _plugin_config_runtime.workspace_trust_level_from_paths(
        cwd=manager.cwd,
        home_config_paths=config_home_paths(
            config_path=manager.config_path,
            reference_home=manager.reference_home,
            legacy_compat_home=LEGACY_COMPAT_HOME,
        ),
        workspace_trust_level_fn=workspace_trust_level,
    )
