from __future__ import annotations

import json
from pathlib import Path

from cli.agent_cli.host.plugin_manifest import PluginManifest
from cli.agent_cli.host import plugin_runtime_loader
from cli.agent_cli.host import plugin_sources
from cli.agent_cli.host import plugin_types


def _write_file(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def test_read_plugin_capability_declarations_merges_root_and_reference_payloads(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin-a"
    _write_file(
        plugin_root / "capabilities.json",
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "tool.docs_search",
                        "kind": "provider_tool",
                        "tool_name": "docs_search",
                        "canonical_family": "docs_search",
                        "supported_profiles": ["generic_chat"],
                        "default_visibility": "model_visible",
                    }
                ]
            }
        ),
    )
    _write_file(
        plugin_root / ".agent_cli_legacy-plugin" / "plugin.json",
        json.dumps(
            {
                "name": "plugin-a",
                "version": "1.0.0",
                "capabilities": [
                    {
                        "tool_name": "docs_lookup",
                        "kind": "provider_tool",
                        "supported_profiles": ["codex_openai"],
                        "default_visibility": "model_visible",
                    }
                ],
            }
        ),
    )

    declarations = plugin_sources.read_plugin_capability_declarations(plugin_root)

    assert len(declarations) == 2
    ids = {str(item.get("capability_id") or "") for item in declarations}
    assert "tool.docs_search" in ids
    assert "docs_lookup" in ids
    assert all(str(item.get("plugin_name") or "") == "plugin-a" for item in declarations)
    docs_search = next(item for item in declarations if item["capability_id"] == "tool.docs_search")
    assert docs_search["canonical_family"] == "docs_search"
    assert docs_search["canonical_family_source"] == "dynamic"
    docs_lookup = next(item for item in declarations if item["capability_id"] == "docs_lookup")
    assert docs_lookup["canonical_family"] == "docs_lookup"
    assert docs_lookup["canonical_family_source"] == "dynamic"


def test_read_plugin_capability_declarations_dedupes_after_single_normalize_pass(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin-c"
    payload = {
        "capabilities": [
            {
                "tool_name": "docs_search",
                "kind": "provider_tool",
                "canonical_family": "docs_search",
                "supported_profiles": ["generic_chat"],
                "default_visibility": "model_visible",
            }
        ]
    }
    _write_file(plugin_root / "capabilities.json", json.dumps(payload))
    _write_file(
        plugin_root / ".agent_cli_legacy-plugin" / "capabilities.json",
        json.dumps(payload),
    )

    declarations = plugin_sources.read_plugin_capability_declarations(plugin_root)

    assert declarations == [
        {
            "capability_id": "docs_search",
            "kind": "provider_tool",
            "tool_name": "docs_search",
            "canonical_family": "docs_search",
            "declared_canonical_family": "docs_search",
            "canonical_family_source": "dynamic",
            "canonical_family_owner": "plugin-c",
            "tool_capability_kind": "local_runtime_tool",
            "tool_runtime_binding": "plugin_runtime",
            "supported_profiles": ["generic_chat"],
            "default_visibility": "model_visible",
            "plugin_name": "plugin-c",
            "canonical_family_record": {
                "canonical_family": "docs_search",
                "family_source": "dynamic",
                "family_owner": "plugin-c",
                "canonical_tool_names": ["docs_search"],
                "compatibility_aliases": [],
                "tool_capability_kind": "local_runtime_tool",
                "tool_runtime_binding": "plugin_runtime",
            },
        }
    ]


def test_read_plugin_capability_declarations_normalizes_media_capability_aliases(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin-media"
    _write_file(
        plugin_root / "capabilities.json",
        json.dumps(
            {
                "capabilities": [
                    {
                        "toolName": "view_document",
                        "kind": "provider_tool",
                        "canonicalFamily": "view_document",
                        "supported_profiles": ["generic_chat"],
                        "default_visibility": "model_visible",
                        "mediaCapability": {
                            "mediaKind": "document",
                            "ingestSemantics": "shared_media_ingest_v1",
                            "sourceModes": ["tool_path", "user_attachment"],
                            "projectionModes": ["tool_result_content_block"],
                            "supportedMimeTypes": ["application/pdf", "application/pdf"],
                            "maxSizeBytes": 4096,
                        },
                    }
                ]
            }
        ),
    )

    declarations = plugin_sources.read_plugin_capability_declarations(plugin_root)

    assert declarations == [
        {
            "capability_id": "view_document",
            "kind": "provider_tool",
            "tool_name": "view_document",
            "canonical_family": "view_document",
            "declared_canonical_family": "view_document",
            "canonical_family_source": "dynamic",
            "canonical_family_owner": "plugin-media",
            "tool_capability_kind": "local_runtime_tool",
            "tool_runtime_binding": "shared_media_ingest",
            "supported_profiles": ["generic_chat"],
            "default_visibility": "model_visible",
            "plugin_name": "plugin-media",
            "media_capability": {
                "media_kind": "document",
                "ingest_semantics": "shared_media_ingest_v1",
                "source_modes": ["tool_path", "user_attachment"],
                "projection_modes": ["tool_result_content_block"],
                "mime_types": ["application/pdf"],
                "max_size_bytes": 4096,
            },
            "canonical_family_record": {
                "canonical_family": "view_document",
                "family_source": "dynamic",
                "family_owner": "plugin-media",
                "canonical_tool_names": ["view_document"],
                "compatibility_aliases": [],
                "tool_capability_kind": "local_runtime_tool",
                "tool_runtime_binding": "shared_media_ingest",
            },
        }
    ]


def test_read_plugin_capability_declarations_normalizes_legacy_family_aliases_only_through_compat_path(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin-legacy"
    _write_file(
        plugin_root / ".agent_cli_legacy-plugin" / "capabilities.json",
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "demo.shell",
                        "kind": "provider_tool",
                        "tool_name": "demo_shell",
                        "canonical_family": "shell",
                        "supported_profiles": ["generic_chat"],
                        "default_visibility": "model_visible",
                    }
                ]
            }
        ),
    )

    declarations = plugin_sources.read_plugin_capability_declarations(plugin_root)

    assert len(declarations) == 1
    declaration = declarations[0]
    assert declaration["canonical_family"] == "command_execution"
    assert declaration["canonical_family_alias_input"] == "shell"
    assert declaration["canonical_family_source"] == "builtin"
    assert declaration["tool_runtime_binding"] == "local_runtime"


def test_load_runtime_capabilities_attaches_declarations_for_enabled_and_disabled_plugin(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin-b"
    _write_file(
        plugin_root / "capabilities.json",
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "tool.echo",
                        "kind": "provider_tool",
                        "tool_name": "echo_tool",
                        "canonical_family": "echo_tool",
                        "supported_profiles": ["generic_chat"],
                        "default_visibility": "model_visible",
                    }
                ]
            }
        ),
    )
    manifest = PluginManifest(name="plugin-b", version="1.0.0", description="demo")

    loaded_disabled, runtime_disabled = plugin_runtime_loader.load_runtime_capabilities(
        plugin_name="plugin-b",
        plugin_dir=plugin_root,
        manifest=manifest,
        enabled=False,
        config_name="plugin-b@test",
        source_kind="configured",
        installed=True,
        required_plugin_files=("commands.py",),
        default_skill_roots_fn=lambda _root: [],
        load_mcp_servers_from_file_fn=lambda _root, _path: {},
        load_apps_from_file_fn=lambda _root, _path: [],
        ensure_host_plugin_package_fn=lambda _name, _root: None,
        load_module_from_file_fn=lambda _name, _module, _path: None,
        plugin_command_registry_type=plugin_types.PluginCommandRegistry,
        plugin_tool_registry_type=plugin_types.PluginToolRegistry,
        loaded_plugin_type=plugin_types.LoadedPlugin,
        default_mcp_config_file=".mcp.json",
        default_app_config_file=".app.json",
    )
    assert runtime_disabled == {}
    disabled_declarations = getattr(loaded_disabled, "plugin_capability_declarations", [])
    assert isinstance(disabled_declarations, list)
    assert len(disabled_declarations) == 1
    assert disabled_declarations[0]["capability_id"] == "tool.echo"

    loaded_enabled, runtime_enabled = plugin_runtime_loader.load_runtime_capabilities(
        plugin_name="plugin-b",
        plugin_dir=plugin_root,
        manifest=manifest,
        enabled=True,
        config_name="plugin-b@test",
        source_kind="reference",
        installed=True,
        required_plugin_files=("commands.py",),
        default_skill_roots_fn=lambda _root: [],
        load_mcp_servers_from_file_fn=lambda _root, _path: {},
        load_apps_from_file_fn=lambda _root, _path: [],
        ensure_host_plugin_package_fn=lambda _name, _root: None,
        load_module_from_file_fn=lambda _name, _module, _path: None,
        plugin_command_registry_type=plugin_types.PluginCommandRegistry,
        plugin_tool_registry_type=plugin_types.PluginToolRegistry,
        loaded_plugin_type=plugin_types.LoadedPlugin,
        default_mcp_config_file=".mcp.json",
        default_app_config_file=".app.json",
    )
    enabled_declarations = getattr(loaded_enabled, "plugin_capability_declarations", [])
    assert isinstance(enabled_declarations, list)
    assert len(enabled_declarations) == 1
    assert runtime_enabled["plugin_capability_declarations"] == enabled_declarations
