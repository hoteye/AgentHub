from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Optional

from cli.agent_cli.host.plugin_manager import PluginManager


def registry_module() -> ModuleType:
    cached = getattr(registry_module, "_cached", None)
    if isinstance(cached, ModuleType):
        return cached
    try:
        from cli.agent_cli.runtime_core import command_registry as module
    except ImportError as import_error:
        module_path = Path(__file__).resolve().parent / "runtime_core" / "command_registry.py"
        spec = importlib.util.spec_from_file_location(
            "cli.agent_cli._standalone_command_registry",
            module_path,
        )
        if spec is None or spec.loader is None:
            raise import_error
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    setattr(registry_module, "_cached", module)
    return module


def plugin_command_specs(plugin_manager: Optional[PluginManager]) -> list[dict[str, str]]:
    try:
        manager = plugin_manager or PluginManager()
        return [
            dict(item)
            for item in list(manager.command_specs() or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
    except Exception:
        return []
