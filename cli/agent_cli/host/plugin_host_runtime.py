from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, MutableMapping


_HOST_PLUGIN_ROOT_KEY = "_host_plugins"
_PLUGIN_NAMESPACE_PREFIXES = ("plugins", _HOST_PLUGIN_ROOT_KEY)


def load_enabled_state(state_path: Path) -> Dict[str, bool]:
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = payload.get("enabled") or {}
    return {str(name): bool(value) for name, value in raw.items()}


def save_enabled_state(state_path: Path, enabled_map: Dict[str, bool]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"enabled": {str(name): bool(value) for name, value in sorted(enabled_map.items())}}
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_plugin_modules(modules: MutableMapping[str, Any] | None = None) -> None:
    target_modules = modules if modules is not None else sys.modules
    for key in list(target_modules.keys()):
        if any(key == prefix or key.startswith(f"{prefix}.") for prefix in _PLUGIN_NAMESPACE_PREFIXES):
            target_modules.pop(key, None)


def ensure_host_plugin_package(
    plugin_name: str,
    plugin_dir: Path,
    modules: MutableMapping[str, Any] | None = None,
) -> None:
    target_modules = modules if modules is not None else sys.modules
    root_module = target_modules.get(_HOST_PLUGIN_ROOT_KEY)
    if root_module is None:
        root_module = types.ModuleType(_HOST_PLUGIN_ROOT_KEY)
        root_module.__path__ = []  # type: ignore[attr-defined]
        target_modules[_HOST_PLUGIN_ROOT_KEY] = root_module
    package_key = f"{_HOST_PLUGIN_ROOT_KEY}.{plugin_name}"
    package_module = target_modules.get(package_key)
    if package_module is None:
        package_module = types.ModuleType(package_key)
        target_modules[package_key] = package_module
    package_module.__path__ = [str(plugin_dir)]  # type: ignore[attr-defined]


def load_module_from_file(
    plugin_name: str,
    module_name: str,
    file_path: Path,
    modules: MutableMapping[str, Any] | None = None,
) -> Any:
    target_modules = modules if modules is not None else sys.modules
    module_key = f"{_HOST_PLUGIN_ROOT_KEY}.{plugin_name}.{module_name}"
    existing = target_modules.get(module_key)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_key, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load module: {file_path}")
    module = importlib.util.module_from_spec(spec)
    target_modules[module_key] = module
    spec.loader.exec_module(module)
    return module
