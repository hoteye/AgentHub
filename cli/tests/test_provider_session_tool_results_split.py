from cli.agent_cli.core import provider_session_tool_results_runtime
from cli.agent_cli.core import provider_session_tool_results_shell_runtime


def test_provider_session_tool_results_runtime_reexports_shell_helpers() -> None:
    assert (
        provider_session_tool_results_runtime.shell_tool_result_payload
        is provider_session_tool_results_shell_runtime.shell_tool_result_payload
    )
    assert (
        provider_session_tool_results_runtime.shell_tool_result_items
        is provider_session_tool_results_shell_runtime.shell_tool_result_items
    )
    assert (
        provider_session_tool_results_runtime.codex_apply_patch_warning_item
        is provider_session_tool_results_shell_runtime.codex_apply_patch_warning_item
    )
