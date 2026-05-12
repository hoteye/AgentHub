from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest
from cli.tests.provider_boundary_test_support import provider_home_env

def _import_config_module():
    try:
        return importlib.import_module("cli.agent_cli.background_tasks.config")
    except ModuleNotFoundError:
        pytest.skip("background_tasks.config not implemented yet")

def _pick_callable(module, *names):
    for name in names:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    pytest.skip(f"no config loader found in module: tried {names}")

def _lookup_value(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

def _invoke_loader(loader, *, project_root: Path, project_config_path: Path, home_config_path: Path):
    params = inspect.signature(loader).parameters
    kwargs = {}

    if "project_root" in params:
        kwargs["project_root"] = project_root
    elif "root" in params:
        kwargs["root"] = project_root
    elif "cwd" in params:
        kwargs["cwd"] = project_root

    if "config_path" in params:
        kwargs["config_path"] = project_config_path
    if "project_config_path" in params:
        kwargs["project_config_path"] = project_config_path
    if "home_config_path" in params:
        kwargs["home_config_path"] = home_config_path

    return loader(**kwargs)

def test_reads_background_task_huey_config(tmp_path: Path) -> None:
    module = _import_config_module()
    loader = _pick_callable(
        module,
        "load_background_tasks_config",
        "read_background_tasks_config",
        "resolve_background_tasks_config",
    )

    project_root = tmp_path / "workspace"
    project_root.mkdir(parents=True)
    project_config_dir = project_root / ".config"
    project_config_dir.mkdir()
    project_config_path = project_config_dir / "config.toml"
    project_config_path.write_text(
        "\n".join(
            [
                "[background_tasks]",
                "enabled = true",
                'provider = "huey"',
                "",
                "[background_tasks.huey]",
                'backend = "sqlite"',
                'path = "cli/.local/state/huey/agenthub_huey.db"',
                'results_dir = "cli/.local/state/huey/results"',
                "worker_count = 1",
                "immediate = true",
            ]
        ),
        encoding="utf-8",
    )
    home_config_path = tmp_path / "home_config.toml"
    home_config_path.write_text("", encoding="utf-8")

    config = _invoke_loader(
        loader,
        project_root=project_root,
        project_config_path=project_config_path,
        home_config_path=home_config_path,
    )

    assert _lookup_value(config, "enabled") is True
    assert _lookup_value(config, "provider") == "huey"
    huey_cfg = _lookup_value(config, "huey")
    if huey_cfg is None and isinstance(config, dict):
        huey_cfg = config.get("background_tasks", {}).get("huey")
    assert huey_cfg is not None
    assert _lookup_value(huey_cfg, "immediate") is True
    assert _lookup_value(huey_cfg, "backend") == "sqlite"

def test_project_layer_overrides_home_layer_when_supported(tmp_path: Path) -> None:
    module = _import_config_module()
    loader = _pick_callable(
        module,
        "load_background_tasks_config",
        "read_background_tasks_config",
        "resolve_background_tasks_config",
    )
    params = inspect.signature(loader).parameters
    if "home_config_path" not in params and "project_config_path" not in params:
        pytest.skip("loader does not expose layered config inputs yet")

    project_root = tmp_path / "workspace"
    project_root.mkdir(parents=True)
    project_config_path = tmp_path / "project.toml"
    home_config_path = tmp_path / "home.toml"
    home_config_path.write_text(
        "\n".join(
            [
                "[background_tasks]",
                "enabled = true",
                'provider = "huey"',
                "",
                "[background_tasks.huey]",
                "immediate = false",
                "worker_count = 4",
            ]
        ),
        encoding="utf-8",
    )
    project_config_path.write_text(
        "\n".join(
            [
                "[background_tasks]",
                "enabled = true",
                'provider = "huey"',
                "",
                "[background_tasks.huey]",
                "immediate = true",
                "worker_count = 1",
            ]
        ),
        encoding="utf-8",
    )

    config = _invoke_loader(
        loader,
        project_root=project_root,
        project_config_path=project_config_path,
        home_config_path=home_config_path,
    )
    huey_cfg = _lookup_value(config, "huey")
    if huey_cfg is None and isinstance(config, dict):
        huey_cfg = config.get("background_tasks", {}).get("huey")
    assert huey_cfg is not None
    assert _lookup_value(huey_cfg, "immediate") is True
    assert _lookup_value(huey_cfg, "worker_count") == 1


def test_default_home_candidates_follow_unified_provider_home_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _import_config_module()
    loader = _pick_callable(
        module,
        "load_background_tasks_config",
        "read_background_tasks_config",
        "resolve_background_tasks_config",
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    provider_home = tmp_path / "provider-home"
    provider_home.mkdir(parents=True)
    (provider_home / "config.toml").write_text(
        "\n".join(
            [
                "[background_tasks]",
                "enabled = true",
                'provider = "huey"',
            ]
        ),
        encoding="utf-8",
    )
    for key, value in provider_home_env(provider_home).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AGENT_CLI_HOME", str(tmp_path / "home" / ".agent_cli"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    config = loader(cwd=workspace)

    assert _lookup_value(config, "enabled") is True
    assert str(provider_home / "config.toml") in {
        str(path) for path in (_lookup_value(config, "source_paths") or ())
    }
