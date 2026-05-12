from cli.agent_cli.host.plugin_manifest import PluginManifest


def manifest() -> PluginManifest:
    return PluginManifest(
        name="demo_plugin",
        version="0.1.0",
        description="Minimal plugin used to validate plugin loading, commands, and tools.",
        api_version="1",
        plugin_kind="generic",
        distribution="bundled",
        min_host_version="0.1.0",
        enabled_by_default=True,
        commercial=False,
        dependencies=[],
    )
