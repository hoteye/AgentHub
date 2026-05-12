from __future__ import annotations

import zipfile
from pathlib import Path

from cli.agent_cli.host import plugin_index_runtime
from cli.agent_cli.host.plugin_manifest import PluginManifest
from cli.agent_cli.host.plugin_types import LoadedPlugin

def _write_file(path: Path, contents: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")

def _loaded_plugin(*, plugin_name: str, config_name: str = "", source_kind: str = "installed") -> LoadedPlugin:
    return LoadedPlugin(
        manifest=PluginManifest(name=plugin_name, version="1.2.3", description=f"{plugin_name} desc"),
        plugin_name=plugin_name,
        enabled=True,
        command_count=1,
        tool_count=2,
        connector_count=3,
        trigger_count=4,
        policy_count=5,
        workflow_count=6,
        provider_hooks=None,
        runtime_hooks=None,
        connector_registrations=[],
        trigger_registrations=[],
        policy_registrations=[],
        workflow_handlers=[],
        config_name=config_name,
        root=Path("/tmp") / plugin_name,
        skill_roots=[Path("/tmp") / plugin_name / "skills"],
        apps=[{"id": "app"}],
        mcp_servers={"docs": {"url": "https://example.test/mcp"}},
        installed=(source_kind != "bundled"),
        source_kind=source_kind,
    )

def test_validate_plugin_dir_requires_legacy_runtime_files_when_reference_manifest_missing(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "legacy-plugin"
    plugin_dir.mkdir()
    _write_file(plugin_dir / "manifest.py")
    _write_file(plugin_dir / "commands.py")

    error = plugin_index_runtime.validate_plugin_dir(
        plugin_dir,
        read_reference_manifest_fn=lambda _: None,
    )

    assert error == "missing_required_file:tools.py"

def test_extract_source_dir_rejects_zip_with_multiple_top_level_directories(tmp_path: Path) -> None:
    zip_path = tmp_path / "plugin.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a/manifest.py", "")
        zf.writestr("b/manifest.py", "")

    staging_dir, candidate_dir, source_kind, error = plugin_index_runtime.extract_source_dir(
        str(zip_path),
        validate_plugin_dir_fn=lambda _: None,
    )

    assert staging_dir is not None
    assert candidate_dir is None
    assert source_kind == "zip"
    assert error == {"ok": False, "reason": "zip_structure_invalid", "path": str(zip_path)}

def test_resolve_plugin_and_project_plugins_preserve_manager_compatibility_fields() -> None:
    bundled = _loaded_plugin(plugin_name="bundled-plugin", source_kind="bundled")
    installed = _loaded_plugin(plugin_name="sample", config_name="sample@test")

    assert plugin_index_runtime.resolve_plugin([bundled, installed], "sample@test") is installed
    assert plugin_index_runtime.resolve_plugin([bundled, installed], "sample") is installed

    projected = plugin_index_runtime.project_plugins([bundled, installed])

    assert projected[0]["plugin_id"] == "bundled-plugin"
    assert projected[1]["plugin_id"] == "sample@test"
    assert projected[1]["config_name"] == "sample@test"
    assert projected[1]["name"] == "sample"
    assert projected[1]["skill_root_count"] == 1
    assert projected[1]["app_count"] == 1
    assert projected[1]["mcp_server_count"] == 1
