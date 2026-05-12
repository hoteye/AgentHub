from cli.agent_cli.host.plugin_hooks import ProviderHooks


def provider_hooks():
    return ProviderHooks(
        tool_specs=[
            {
                "name": "demo_echo",
                "description": "Minimal demo-plugin tool used to validate provider-side plugin exposure.",
            }
        ],
        system_prompt_fragments=[
            "The demo_plugin exposes a minimal echo capability for plugin-architecture smoke tests."
        ],
        routing_hints=[
            "Use demo_plugin only for plugin smoke tests and contract verification."
        ],
    )
