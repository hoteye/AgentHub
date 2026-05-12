from cli.agent_cli import provider
from cli.agent_cli import provider_helpers


def test_provider_helpers_reexports_provider_surface() -> None:
    assert provider_helpers.load_provider_config is provider.load_provider_config
    assert provider_helpers.save_user_model_selection is provider.save_user_model_selection
    assert provider_helpers.resolve_provider_paths is provider.resolve_provider_paths
    assert provider_helpers._find_project_provider_file is provider._find_project_provider_file
    assert provider_helpers._tool_specs is provider._tool_specs
