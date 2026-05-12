from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import builtin_provider_tool_specs_browser_runtime
from cli.agent_cli.providers import builtin_provider_tool_specs_catalog_helper_runtime as catalog_helper_runtime
from cli.agent_cli.providers import builtin_provider_tool_specs_catalog_schema_runtime as catalog_schema_runtime


def shell_description(
    *,
    host_platform: HostPlatform,
    provider_description: Callable[[str], str],
) -> str:
    description = provider_description("shell")
    if description:
        return (
            f"{description} "
            f"Current platform is {host_platform.os} ({host_platform.family}) with {host_platform.shell_kind}."
        )
    return (
        "Run a local shell command on the current host. "
        f"Current platform is {host_platform.os} ({host_platform.family}) with {host_platform.shell_kind}."
    )


def exec_command_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.exec_command_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def write_stdin_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.write_stdin_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def update_plan_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.update_plan_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def request_user_input_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.request_user_input_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def shell_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
    host_platform: HostPlatform,
) -> Dict[str, Any]:
    return function_tool(
        name="shell",
        description=shell_description(host_platform=host_platform, provider_description=provider_description),
        properties={
            "command": {"type": "string", "description": "Raw shell command to execute."},
        },
        required=["command"],
    )


def apply_patch_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.apply_patch_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def write_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.write_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def edit_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.edit_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def grep_files_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.grep_files_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def read_file_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="read_file",
        properties=catalog_helper_runtime.read_file_properties(),
        required=["file_path"],
    )


def list_dir_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="list_dir",
        properties=catalog_helper_runtime.list_dir_properties(),
        required=["dir_path"],
    )


def file_search_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="file_search",
        properties=catalog_helper_runtime.file_search_properties(),
        required=["query"],
    )


def file_read_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="file_read",
        properties=catalog_helper_runtime.file_read_properties(),
        required=["path"],
    )


def file_list_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="file_list",
        properties=catalog_helper_runtime.file_list_properties(),
    )


def office_skills_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return function_tool(
        name="office_skills",
        description=provider_description("office_skills"),
    )


def office_run_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.office_run_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def view_image_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.view_image_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def expert_review_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_schema_runtime.expert_review_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def web_fetch_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="web_fetch",
        properties=catalog_helper_runtime.web_fetch_properties(),
        required=["url"],
    )


def browser_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
    provider_action_names: Callable[[str], Tuple[str, ...]],
    browser_provider_actions: Tuple[str, ...],
) -> Dict[str, Any]:
    return function_tool(
        name="browser",
        description=provider_description("browser"),
        properties=builtin_provider_tool_specs_browser_runtime.browser_properties(
            provider_action_names=provider_action_names,
            browser_provider_actions=browser_provider_actions,
        ),
        required=["action"],
    )


def open_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="open",
        properties=catalog_helper_runtime.open_properties(),
        required=["ref"],
    )


def click_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="click",
        properties=catalog_helper_runtime.click_properties(),
        required=["ref_id", "id"],
    )


def find_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="find",
        properties=catalog_helper_runtime.find_properties(),
        required=["ref_id", "pattern"],
    )


def policy_doc_import_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="policy_doc_import",
        properties=catalog_helper_runtime.policy_doc_import_properties(),
        required=["path"],
    )


def policy_doc_list_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="policy_doc_list",
        properties=catalog_helper_runtime.policy_doc_list_properties(),
    )


def policy_doc_search_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="policy_doc_search",
        properties=catalog_helper_runtime.policy_doc_search_properties(),
        required=["query"],
    )


def policy_doc_read_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return catalog_helper_runtime.function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="policy_doc_read",
        properties=catalog_helper_runtime.policy_doc_read_properties(),
    )
