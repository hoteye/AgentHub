from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import (
    builtin_provider_tool_specs_catalog_runtime as _catalog_helpers,
)


def exec_command_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.exec_command_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def write_stdin_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.write_stdin_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def update_plan_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.update_plan_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def request_user_input_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.request_user_input_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def shell_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
    host_platform: HostPlatform,
) -> Dict[str, Any]:
    return _catalog_helpers.shell_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        host_platform=host_platform,
    )


def apply_patch_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.apply_patch_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def write_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.write_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def edit_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.edit_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def grep_files_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.grep_files_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def read_file_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.read_file_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def list_dir_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.list_dir_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def file_search_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.file_search_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def file_read_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.file_read_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def file_list_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.file_list_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def office_skills_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.office_skills_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def office_run_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.office_run_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def view_image_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.view_image_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def web_fetch_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.web_fetch_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def browser_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
    provider_action_names: Callable[[str], Tuple[str, ...]],
    browser_provider_actions: Tuple[str, ...],
) -> Dict[str, Any]:
    return _catalog_helpers.browser_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        provider_action_names=provider_action_names,
        browser_provider_actions=browser_provider_actions,
    )


def open_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.open_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def click_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.click_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def find_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.find_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def policy_doc_import_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.policy_doc_import_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def policy_doc_list_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.policy_doc_list_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def policy_doc_search_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.policy_doc_search_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def policy_doc_read_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _catalog_helpers.policy_doc_read_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )
