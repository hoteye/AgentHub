from __future__ import annotations

import json
from pathlib import Path

from cli.agent_cli.host.plugin_manager import PluginManager, plugin_namespace_for_skill_path
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.provider import _tool_specs
from cli.agent_cli.providers.tool_calls import plugin_system_prompt_addendum
from cli.agent_cli.slash_commands import slash_command_specs


def _write_file(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _write_reference_plugin(
    reference_home: Path, plugin_key: str, *, plugin_name: str | None = None
) -> Path:
    parsed_name, marketplace = plugin_key.split("@", 1)
    resolved_name = plugin_name or parsed_name
    plugin_root = reference_home / "plugins" / "cache" / marketplace / parsed_name / "local"
    _write_file(
        plugin_root / ".agent_cli_legacy-plugin" / "plugin.json",
        json.dumps(
            {"name": resolved_name, "description": f"{resolved_name} plugin"}, ensure_ascii=False
        ),
    )
    return plugin_root


def _write_config(path: Path, contents: str) -> None:
    _write_file(path, contents)


def test_plugin_capability_declarations_accessor_reads_reference_plugin_payload(
    tmp_path: Path,
) -> None:
    reference_home = tmp_path / "home"
    plugin_root = _write_reference_plugin(reference_home, "sample@test")
    _write_file(
        plugin_root / ".agent_cli_legacy-plugin" / "capabilities.json",
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "tool.sample_search",
                        "kind": "provider_tool",
                        "tool_name": "sample_search",
                        "supported_profiles": ["generic_chat"],
                        "default_visibility": "model_visible",
                    }
                ]
            }
        ),
    )
    _write_config(
        reference_home / "config.toml",
        '[features]\nplugins = true\n\n[plugins."sample@test"]\nenabled = true\n',
    )

    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )

    declarations = manager.plugin_capability_declarations()
    assert len(declarations) == 1
    assert declarations[0]["capability_id"] == "tool.sample_search"
    assert declarations[0]["plugin_name"] == "sample"
    assert declarations[0]["source_kind"] in {
        "installed",
        "configured",
        "reference",
        "bundled",
        "legacy",
    }
    assert (
        manager.plugin_capability_declarations_for_plugin("sample")[0]["capability_id"]
        == "tool.sample_search"
    )


def test_plugin_capability_declarations_default_to_active_plugins(tmp_path: Path) -> None:
    reference_home = tmp_path / "home"
    plugin_root = _write_reference_plugin(reference_home, "sample@test")
    _write_file(
        plugin_root / ".agent_cli_legacy-plugin" / "capabilities.json",
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "tool.sample_hidden",
                        "kind": "provider_tool",
                        "tool_name": "sample_hidden",
                        "supported_profiles": ["generic_chat"],
                        "default_visibility": "model_visible",
                    }
                ]
            }
        ),
    )
    _write_config(
        reference_home / "config.toml",
        '[features]\nplugins = true\n\n[plugins."sample@test"]\nenabled = false\n',
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )

    assert manager.plugin_capability_declarations() == []
    inactive = manager.plugin_capability_declarations(include_inactive=True)
    assert len(inactive) == 1
    assert inactive[0]["capability_id"] == "tool.sample_hidden"


def test_load_plugins_loads_default_skills_and_mcp_servers(tmp_path: Path) -> None:
    reference_home = tmp_path / "home"
    plugin_root = _write_reference_plugin(reference_home, "sample@test")
    _write_file(
        plugin_root / "skills" / "sample-search" / "SKILL.md",
        "---\nname: sample-search\ndescription: search sample data\n---\n",
    )
    _write_file(
        plugin_root / ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "sample": {
                        "type": "http",
                        "url": "https://sample.example/mcp",
                        "cwd": "relative-workdir",
                    }
                }
            }
        ),
    )
    _write_file(
        plugin_root / ".app.json",
        json.dumps({"apps": {"example": {"id": "connector_example"}}}),
    )
    _write_config(
        reference_home / "config.toml",
        '[features]\nplugins = true\n\n[plugins."sample@test"]\nenabled = true\n',
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )

    plugins = manager.list_plugins()

    assert [item["name"] for item in plugins] == ["sample"]
    assert manager.effective_skill_roots() == [plugin_root / "skills"]
    assert manager.effective_mcp_servers()["sample"]["cwd"] == str(
        (plugin_root / "relative-workdir").resolve()
    )
    assert manager.effective_apps() == ["connector_example"]


def test_load_plugins_preserves_disabled_plugins_without_effective_contributions(
    tmp_path: Path,
) -> None:
    reference_home = tmp_path / "home"
    plugin_root = _write_reference_plugin(reference_home, "sample@test")
    _write_file(
        plugin_root / ".mcp.json",
        json.dumps({"mcpServers": {"sample": {"type": "http", "url": "https://x"}}}),
    )
    _write_config(
        reference_home / "config.toml",
        '[features]\nplugins = true\n\n[plugins."sample@test"]\nenabled = false\n',
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )

    plugins = manager.list_plugins()

    assert len(plugins) == 1
    assert plugins[0]["enabled"] is False
    assert manager.effective_skill_roots() == []
    assert manager.effective_mcp_servers() == {}
    assert manager.effective_apps() == []


def test_effective_apps_dedupes_connector_ids_across_plugins(tmp_path: Path) -> None:
    reference_home = tmp_path / "home"
    plugin_a_root = _write_reference_plugin(reference_home, "plugin-a@test")
    plugin_b_root = _write_reference_plugin(reference_home, "plugin-b@test")
    _write_file(
        plugin_a_root / ".app.json", json.dumps({"apps": {"a": {"id": "connector_example"}}})
    )
    _write_file(
        plugin_b_root / ".app.json",
        json.dumps(
            {"apps": {"b": {"id": "connector_example"}, "gmail": {"id": "connector_gmail"}}}
        ),
    )
    _write_config(
        reference_home / "config.toml",
        (
            "[features]\nplugins = true\n\n"
            '[plugins."plugin-a@test"]\nenabled = true\n\n'
            '[plugins."plugin-b@test"]\nenabled = true\n'
        ),
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )

    assert manager.effective_apps() == ["connector_example", "connector_gmail"]


def test_gui_bridge_metadata_exports_mcp_and_app_connectors(tmp_path: Path) -> None:
    reference_home = tmp_path / "home"
    plugin_root = _write_reference_plugin(reference_home, "sample@test")
    _write_file(
        plugin_root / ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "sample": {"type": "http", "url": "https://docs.example/mcp"},
                }
            }
        ),
    )
    _write_file(
        plugin_root / ".app.json",
        json.dumps(
            {
                "apps": {
                    "example": {
                        "id": "connector_example",
                        "display_name": "Example Connector",
                        "connector_kind": "app",
                        "description": "Example integration",
                        "supports_webhook": True,
                        "supports_polling": False,
                        "supports_actions": True,
                        "event_types": ["demo.event"],
                        "action_types": ["demo.action"],
                        "connector_key": "connector_example",
                        "metadata": {"team": "integration"},
                    }
                }
            }
        ),
    )
    _write_config(
        reference_home / "config.toml",
        ("[features]\nplugins = true\n\n" '[plugins."sample@test"]\nenabled = true\n'),
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )
    metadata = manager.gui_bridge_metadata()

    assert metadata["mcpServers"][0]["name"] == "sample"
    assert metadata["mcpServers"][0]["source"] == "plugin"
    assert metadata["mcpServers"][0]["config"]["url"] == "https://docs.example/mcp"

    connectors = metadata["appConnectors"]
    assert connectors[0]["connector_id"] == "connector_example"
    assert connectors[0]["display_name"] == "Example Connector"
    assert connectors[0]["supports_webhook"] is True
    assert connectors[0]["event_types"] == ["demo.event"]
    assert connectors[0]["metadata"]["team"] == "integration"


def test_gui_bridge_metadata_dedupes_connectors(tmp_path: Path) -> None:
    reference_home = tmp_path / "home"
    plugin_a_root = _write_reference_plugin(reference_home, "plugin-a@test")
    plugin_b_root = _write_reference_plugin(reference_home, "plugin-b@test")
    _write_file(
        plugin_a_root / ".app.json", json.dumps({"apps": {"a": {"id": "connector_example"}}})
    )
    _write_file(
        plugin_b_root / ".app.json", json.dumps({"apps": {"b": {"id": "connector_example"}}})
    )
    _write_config(
        reference_home / "config.toml",
        (
            "[features]\nplugins = true\n\n"
            '[plugins."plugin-a@test"]\nenabled = true\n'
            '[plugins."plugin-b@test"]\nenabled = true\n'
        ),
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )
    metadata = manager.gui_bridge_metadata()
    assert len(metadata["appConnectors"]) == 1


def test_plugin_namespace_for_skill_path_uses_manifest_name(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin-root"
    _write_file(plugin_root / ".agent_cli_legacy-plugin" / "plugin.json", '{"name":"sample"}')
    skill_path = plugin_root / "skills" / "search" / "SKILL.md"
    _write_file(skill_path, "---\ndescription: search\n---\n")

    assert plugin_namespace_for_skill_path(skill_path) == "sample"


def test_load_plugins_returns_empty_when_feature_disabled(tmp_path: Path) -> None:
    reference_home = tmp_path / "home"
    plugin_root = _write_reference_plugin(reference_home, "sample@test")
    _write_file(
        plugin_root / "skills" / "sample-search" / "SKILL.md",
        "---\nname: sample-search\ndescription: search\n---\n",
    )
    _write_config(
        reference_home / "config.toml",
        '[features]\nplugins = false\n\n[plugins."sample@test"]\nenabled = true\n',
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )

    assert manager.list_plugins() == []
    assert manager.effective_skill_roots() == []


def test_load_plugins_rejects_invalid_plugin_keys(tmp_path: Path) -> None:
    reference_home = tmp_path / "home"
    _write_reference_plugin(reference_home, "sample@test")
    _write_config(
        reference_home / "config.toml",
        '[features]\nplugins = true\n\n[plugins."sample"]\nenabled = true\n',
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )

    plugins = manager.list_plugins()

    assert len(plugins) == 1
    assert plugins[0]["error"] == "invalid plugin key `sample`; expected <plugin>@<marketplace>"
    assert manager.effective_skill_roots() == []
    assert manager.effective_mcp_servers() == {}


def test_install_plugin_updates_config_with_plugin_key(tmp_path: Path) -> None:
    reference_home = tmp_path / "home"
    source_root = tmp_path / "source"
    _write_file(
        source_root / ".agent_cli_legacy-plugin" / "plugin.json",
        '{"name":"sample-plugin","description":"sample"}',
    )
    _write_file(
        source_root / "skills" / "demo" / "SKILL.md",
        "---\nname: demo\ndescription: installed\n---\n",
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )

    installed = manager.install_plugin(str(source_root))

    assert installed["ok"] is True
    assert installed["plugin_id"] == "sample-plugin@debug"
    assert (reference_home / "plugins" / "cache" / "debug" / "sample-plugin" / "local").is_dir()
    config_text = (reference_home / "config.toml").read_text(encoding="utf-8")
    assert '[plugins."sample-plugin@debug"]' in config_text
    assert "enabled = true" in config_text
    installed_plugins = json.loads(
        (reference_home / "plugins" / "installed_plugins.json").read_text(encoding="utf-8")
    )
    assert installed_plugins["version"] == 2
    assert installed_plugins["plugins"]["sample-plugin@debug"][0]["scope"] == "user"
    assert installed_plugins["plugins"]["sample-plugin@debug"][0]["installPath"].endswith(
        "/plugins/cache/debug/sample-plugin/local"
    )


def test_configured_mcp_servers_include_plugins_without_overriding_user_config(
    tmp_path: Path,
) -> None:
    reference_home = tmp_path / "home"
    plugin_root = _write_reference_plugin(reference_home, "sample@test")
    _write_file(
        plugin_root / ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "sample": {"type": "http", "url": "https://plugin.example/mcp"},
                    "docs": {"type": "http", "url": "https://docs.example/mcp"},
                }
            }
        ),
    )
    _write_config(
        reference_home / "config.toml",
        (
            "[features]\nplugins = true\n"
            '\n[plugins."sample@test"]\nenabled = true\n'
            '\n[mcp_servers.sample]\nurl = "https://user.example/mcp"\n'
        ),
    )
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=tmp_path
    )

    assert manager.configured_mcp_servers()["sample"]["url"] == "https://user.example/mcp"
    assert manager.configured_mcp_servers()["docs"]["url"] == "https://docs.example/mcp"


def test_workspace_layer_switches_plugin_view_and_shared_manager_contracts(tmp_path: Path) -> None:
    reference_home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    nested = workspace / "apps" / "nested"
    nested.mkdir(parents=True)
    plugin_root = _write_reference_plugin(reference_home, "sample@test")
    _write_file(
        plugin_root / ".agent_cli_legacy-plugin" / "capabilities.json",
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "tool.sample_lookup",
                        "kind": "provider_tool",
                        "tool_name": "sample_lookup",
                        "canonical_family": "web_search",
                        "supported_profiles": ["generic_chat"],
                        "default_visibility": "model_visible",
                    }
                ]
            }
        ),
    )
    _write_file(
        plugin_root / "skills" / "sample-search" / "SKILL.md",
        "---\nname: sample-search\ndescription: search sample data\n---\n",
    )
    _write_file(
        plugin_root / "provider.py",
        (
            "from cli.agent_cli.host.plugin_hooks import ProviderHooks\n\n"
            "def provider_hooks():\n"
            "    return ProviderHooks(\n"
            "        tool_specs=[{\n"
            "            'name': 'sample_lookup',\n"
            "            'description': 'lookup sample',\n"
            "            'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False},\n"
            "        }],\n"
            "        system_prompt_fragments=['sample fragment'],\n"
            "    )\n"
        ),
    )
    _write_file(
        plugin_root / "commands.py",
        "def register_commands(registry):\n    registry.add_command(name='sample_lookup', usage='/sample_lookup', description='sample lookup', handler=lambda arg_text, runtime: ('ok', []))\n",
    )
    _write_file(plugin_root / "tools.py", "def register_tools(registry):\n    return None\n")
    _write_file(plugin_root / "runtime.py", "def runtime_hooks():\n    return {}\n")
    _write_file(
        plugin_root / "manifest.py",
        "from cli.agent_cli.host.plugin_manifest import PluginManifest\n\ndef manifest():\n    return PluginManifest(name='sample', version='0.0.1', description='sample', enabled_by_default=False)\n",
    )
    _write_config(reference_home / "config.toml", "[features]\nplugins = true\n")
    _write_config(
        workspace / ".config" / "config.toml", '[plugins."sample@test"]\nenabled = false\n'
    )
    _write_config(nested / ".config" / "config.toml", '[plugins."sample@test"]\nenabled = true\n')
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=workspace
    )

    assert all(item["name"] != "sample" or not item["enabled"] for item in manager.list_plugins())

    manager.set_cwd(nested)
    specs = slash_command_specs(plugin_manager=manager, discoverable_only=False)
    tool_names = [
        item["function"]["name"]
        for item in _tool_specs(
            current_host_platform(), cwd=nested, plugin_manager_factory=lambda: manager
        )
    ]

    assert any(spec.name == "sample_lookup" for spec in specs)
    assert "sample_lookup" in tool_names
    assert "sample fragment" in plugin_system_prompt_addendum(
        plugin_manager_factory=lambda: manager
    )
    assert manager.effective_skill_roots() == [plugin_root / "skills"]


def test_configured_mcp_servers_preserve_user_config_and_ignore_untrusted_project_layers(
    tmp_path: Path,
) -> None:
    reference_home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    nested = workspace / "child"
    nested.mkdir(parents=True)
    plugin_root = _write_reference_plugin(reference_home, "sample@test")
    _write_file(
        plugin_root / ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "sample": {"type": "http", "url": "https://plugin.example/mcp"},
                    "docs": {"type": "http", "url": "https://docs.example/mcp"},
                }
            }
        ),
    )
    _write_config(
        reference_home / "config.toml",
        (
            "[features]\nplugins = true\n"
            '[mcp_servers.sample]\nurl = "https://user.example/mcp"\n'
            f'\n[projects."{str(workspace.resolve()).replace(chr(92), "/")}"]\n'
            'trust_level = "untrusted"\n'
        ),
    )
    _write_config(nested / ".config" / "config.toml", '[plugins."sample@test"]\nenabled = true\n')
    manager = PluginManager(
        reference_home=reference_home, bundled_plugin_root=tmp_path / "bundled-empty", cwd=nested
    )

    assert manager.workspace_trust_level() == "untrusted"
    assert manager.list_plugins() == []
    assert manager.configured_mcp_servers() == {"sample": {"url": "https://user.example/mcp"}}
