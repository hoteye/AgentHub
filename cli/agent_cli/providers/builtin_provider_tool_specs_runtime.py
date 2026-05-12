from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers import builtin_provider_tool_specs_catalog_runtime as builtin_provider_tool_specs_catalog_runtime_helpers
from cli.agent_cli.providers import builtin_provider_tool_specs_helpers_runtime as _spec_helpers

_BASE_FUNCTION_SPEC_ORDER: Tuple[str, ...] = (
    "exec_command",
    "write_stdin",
    "update_plan",
    "request_user_input",
    "shell",
    "apply_patch",
    "grep_files",
    "read_file",
    "list_dir",
    "file_search",
    "file_read",
    "file_list",
    "office_skills",
    "office_run",
    "view_image",
    "expert_review",
    "web_fetch",
    "browser",
    "open",
    "click",
    "find",
    "policy_doc_import",
    "policy_doc_list",
    "policy_doc_search",
    "policy_doc_read",
)


def shell_description(
    *,
    host_platform: HostPlatform,
    provider_description: Callable[[str], str],
) -> str:
    return builtin_provider_tool_specs_catalog_runtime_helpers.shell_description(
        host_platform=host_platform,
        provider_description=provider_description,
    )


def base_function_specs(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
    provider_action_names: Callable[[str], Tuple[str, ...]],
    browser_provider_actions: Tuple[str, ...],
    host_platform: HostPlatform,
) -> List[Dict[str, Any]]:
    by_name = base_function_specs_by_name(
        function_tool=function_tool,
        provider_description=provider_description,
        provider_action_names=provider_action_names,
        browser_provider_actions=browser_provider_actions,
        host_platform=host_platform,
    )
    return [dict(by_name[name]) for name in _BASE_FUNCTION_SPEC_ORDER if isinstance(by_name.get(name), dict)]


def base_function_specs_by_name(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
    provider_action_names: Callable[[str], Tuple[str, ...]],
    browser_provider_actions: Tuple[str, ...],
    host_platform: HostPlatform,
) -> Dict[str, Dict[str, Any]]:
    specs: Dict[str, Dict[str, Any]] = {
        "exec_command": exec_command_spec(function_tool=function_tool, provider_description=provider_description),
        "write_stdin": write_stdin_spec(function_tool=function_tool, provider_description=provider_description),
        "update_plan": update_plan_spec(function_tool=function_tool, provider_description=provider_description),
        "request_user_input": request_user_input_spec(function_tool=function_tool, provider_description=provider_description),
        "shell": shell_spec(
            function_tool=function_tool,
            provider_description=provider_description,
            host_platform=host_platform,
        ),
        "apply_patch": apply_patch_spec(function_tool=function_tool, provider_description=provider_description),
        "office_skills": office_skills_spec(function_tool=function_tool, provider_description=provider_description),
        "office_run": office_run_spec(function_tool=function_tool, provider_description=provider_description),
        "view_image": view_image_spec(function_tool=function_tool, provider_description=provider_description),
        "expert_review": expert_review_spec(function_tool=function_tool, provider_description=provider_description),
        "web_fetch": web_fetch_spec(function_tool=function_tool, provider_description=provider_description),
        "browser": browser_spec(
            function_tool=function_tool,
            provider_description=provider_description,
            provider_action_names=provider_action_names,
            browser_provider_actions=browser_provider_actions,
        ),
        "open": open_spec(function_tool=function_tool, provider_description=provider_description),
        "click": click_spec(function_tool=function_tool, provider_description=provider_description),
        "find": find_spec(function_tool=function_tool, provider_description=provider_description),
        "policy_doc_import": policy_doc_import_spec(function_tool=function_tool, provider_description=provider_description),
        "policy_doc_list": policy_doc_list_spec(function_tool=function_tool, provider_description=provider_description),
        "policy_doc_search": policy_doc_search_spec(function_tool=function_tool, provider_description=provider_description),
        "policy_doc_read": policy_doc_read_spec(function_tool=function_tool, provider_description=provider_description),
    }
    specs.update(
        {
            "grep_files": grep_files_spec(function_tool=function_tool, provider_description=provider_description),
            "read_file": read_file_spec(function_tool=function_tool, provider_description=provider_description),
            "list_dir": list_dir_spec(function_tool=function_tool, provider_description=provider_description),
            "file_search": file_search_spec(function_tool=function_tool, provider_description=provider_description),
            "file_read": file_read_spec(function_tool=function_tool, provider_description=provider_description),
            "file_list": file_list_spec(function_tool=function_tool, provider_description=provider_description),
        }
    )
    return specs


def file_tool_specs(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
) -> List[Dict[str, Any]]:
    return [
        grep_files_spec(function_tool=function_tool, provider_description=provider_description),
        read_file_spec(function_tool=function_tool, provider_description=provider_description),
        list_dir_spec(function_tool=function_tool, provider_description=provider_description),
        file_search_spec(function_tool=function_tool, provider_description=provider_description),
        file_read_spec(function_tool=function_tool, provider_description=provider_description),
        file_list_spec(function_tool=function_tool, provider_description=provider_description),
    ]


def web_search_provider_spec(
    *,
    config: ProviderConfig,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
    resolve_native_web_search_capability_fn: Callable[[ProviderConfig], Any],
) -> Dict[str, Any]:
    function_spec = _web_search_function_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )
    capability = resolve_native_web_search_capability_fn(config)
    kind = _web_search_provider_spec_kind(capability)
    if kind == "openai_responses_native":
        return {
            "type": "web_search",
            "external_web_access": _openai_native_web_search_external_web_access(capability),
        }
    if kind == "anthropic_native":
        return _anthropic_native_web_search_spec()
    if kind == "glm_native":
        return {
            "type": "web_search",
            "web_search": {
                "enable": True,
                "search_engine": "search_pro",
                "search_result": True,
                "count": 5,
                "content_size": "medium",
            },
            "function": function_spec["function"],
        }
    return function_spec


def _web_search_provider_spec_kind(capability: Any) -> str:
    if str(getattr(capability, "effective_mode", "") or "").strip().lower() == "disabled":
        return "disabled"
    return str(getattr(capability, "main_loop_spec_kind", "") or "").strip() or "function"


def _openai_native_web_search_external_web_access(capability: Any) -> bool:
    return str(getattr(capability, "effective_mode", "") or "").strip().lower() != "cached"


def _web_search_function_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
) -> Dict[str, Any]:
    return function_tool(
        name="web_search",
        description=provider_description("web_search"),
        properties={
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "domains": {"type": "array", "items": {"type": "string"}},
            "recency_days": {"type": "integer"},
            "market": {"type": "string"},
        },
        required=["query"],
    )


def _anthropic_native_web_search_spec() -> Dict[str, Any]:
    return {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 8,
    }


def exec_command_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.exec_command_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def write_stdin_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.write_stdin_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def update_plan_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.update_plan_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def request_user_input_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.request_user_input_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def shell_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
    host_platform: HostPlatform,
) -> Dict[str, Any]:
    return _spec_helpers.shell_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        host_platform=host_platform,
    )


def apply_patch_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.apply_patch_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def grep_files_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.grep_files_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def read_file_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.read_file_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def list_dir_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.list_dir_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def file_search_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.file_search_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def file_read_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.file_read_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def file_list_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.file_list_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def office_skills_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.office_skills_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def office_run_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.office_run_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def view_image_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _spec_helpers.view_image_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def expert_review_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return builtin_provider_tool_specs_catalog_runtime_helpers.expert_review_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


web_fetch_spec = _spec_helpers.web_fetch_spec
browser_spec = _spec_helpers.browser_spec
open_spec = _spec_helpers.open_spec
click_spec = _spec_helpers.click_spec
find_spec = _spec_helpers.find_spec
policy_doc_import_spec = _spec_helpers.policy_doc_import_spec
policy_doc_list_spec = _spec_helpers.policy_doc_list_spec
policy_doc_search_spec = _spec_helpers.policy_doc_search_spec
policy_doc_read_spec = _spec_helpers.policy_doc_read_spec
