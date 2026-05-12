from __future__ import annotations

import importlib
import importlib.machinery
import json
import os
import re
import sys
import types
from pathlib import Path, PureWindowsPath
from typing import Any, Dict

from cli.agent_cli.runtime_paths import PROJECT_ROOT_ENV, runtime_project_root


def find_project_root(start: Path) -> Path:
    env_root = runtime_project_root()
    if (
        PROJECT_ROOT_ENV in os.environ
        and
        (env_root / "plugins").exists()
        and (
            (env_root / "document_tools").exists()
            or (env_root / "internal_policy_docs").exists()
            or (env_root / "tools").exists()
        )
    ):
        return env_root
    for candidate in (start, *start.parents):
        if (candidate / "plugins").exists() and (
            (candidate / "document_tools").exists()
            or (candidate / "internal_policy_docs").exists()
            or (candidate / "tools").exists()
        ):
            return candidate
    return start.parents[2]


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        path_text = str(value)
        if path_text.startswith("\\\\") or _WINDOWS_DRIVE_RE.match(path_text):
            return str(PureWindowsPath(path_text))
        return path_text
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, set):
        return sorted(json_safe(v) for v in value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return repr(value)
    if hasattr(value, "shape") and hasattr(value, "dtype"):
        return {
            "type": "ndarray",
            "shape": list(getattr(value, "shape", [])),
            "dtype": str(getattr(value, "dtype", "")),
        }
    return value


def dumps_pretty(payload: Dict[str, Any]) -> str:
    return json.dumps(json_safe(payload), ensure_ascii=False, indent=2)


def load_project_tool_module(
    module_name: str,
    *,
    project_root: Path,
    tools_module_file: Path,
):
    root = str(project_root)
    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)
    existing = sys.modules.get("tools")
    existing_file = getattr(existing, "__file__", None)
    if existing_file:
        try:
            if Path(existing_file).resolve() == tools_module_file.resolve():
                sys.modules.pop("tools", None)
        except OSError:
            pass
    try:
        return importlib.import_module(f"tools.{module_name}")
    except ModuleNotFoundError:
        pass
    package = sys.modules.get("tools")
    if package is None or not getattr(package, "__path__", None):
        package = types.ModuleType("tools")
        search_path = [str(project_root / "tools")]
        package.__path__ = search_path
        package.__package__ = "tools"
        spec = importlib.machinery.ModuleSpec("tools", loader=None, is_package=True)
        spec.submodule_search_locations = search_path
        package.__spec__ = spec
        sys.modules["tools"] = package
    return importlib.import_module(f"tools.{module_name}")


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = find_project_root(APP_DIR)
