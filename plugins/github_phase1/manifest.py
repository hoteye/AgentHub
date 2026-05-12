from cli.agent_cli.host.plugin_manifest import PluginManifest


def manifest() -> PluginManifest:
    return PluginManifest(
        name="github_phase1",
        version="0.1.0",
        description="GitHub Phase 1 webhook and controlled action integration plugin.",
        api_version="1",
        plugin_kind="integration",
        distribution="bundled",
        min_host_version="0.1.0",
        enabled_by_default=True,
        commercial=False,
        dependencies=[],
    )
