from cli.agent_cli.providers import tool_specs
from cli.agent_cli.providers import tool_specs_facade_runtime


def test_tool_specs_facade_reexports_tool_specs_surface() -> None:
    assert (
        tool_specs_facade_runtime.model_facing_builtin_tool_order()
        == tool_specs._MODEL_FACING_BUILTIN_TOOL_ORDER
    )
    assert tool_specs_facade_runtime.provider_tool_names is tool_specs.provider_tool_names
    assert tool_specs_facade_runtime.merged_provider_tool_specs is tool_specs.merged_provider_tool_specs
    assert tool_specs_facade_runtime.builtin_provider_tool_specs is tool_specs._builtin_provider_tool_specs
    assert tool_specs_facade_runtime.function_name_from_spec is tool_specs._function_name_from_spec
