from __future__ import annotations

import types
from pathlib import Path

from cli.agent_cli.host import plugin_host_runtime

def test_state_round_trip_sorts_and_coerces_values(tmp_path: Path) -> None:
    state_path = tmp_path / "plugin_state.json"

    plugin_host_runtime.save_enabled_state(state_path, {"zeta": 1, "alpha": 0})  # type: ignore[arg-type]

    assert plugin_host_runtime.load_enabled_state(state_path) == {"alpha": False, "zeta": True}
    assert state_path.read_text(encoding="utf-8").splitlines()[1] == '  "enabled": {'

def test_clear_plugin_modules_only_removes_plugin_namespaces() -> None:
    modules = {
        "plugins": types.ModuleType("plugins"),
        "plugins.demo": types.ModuleType("plugins.demo"),
        "_host_plugins": types.ModuleType("_host_plugins"),
        "_host_plugins.demo.runtime": types.ModuleType("_host_plugins.demo.runtime"),
        "unrelated": types.ModuleType("unrelated"),
    }

    plugin_host_runtime.clear_plugin_modules(modules)

    assert list(modules.keys()) == ["unrelated"]

def test_host_plugin_package_and_module_loading_reuse_existing_modules(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "sample"
    plugin_dir.mkdir()
    module_path = plugin_dir / "runtime.py"
    module_path.write_text("VALUE = 7\n", encoding="utf-8")
    modules: dict[str, object] = {}

    plugin_host_runtime.ensure_host_plugin_package("sample", plugin_dir, modules)
    loaded = plugin_host_runtime.load_module_from_file("sample", "runtime", module_path, modules)

    assert getattr(loaded, "VALUE") == 7
    assert modules["_host_plugins.sample"].__path__ == [str(plugin_dir)]  # type: ignore[attr-defined]
    assert plugin_host_runtime.load_module_from_file("sample", "runtime", module_path, modules) is loaded
