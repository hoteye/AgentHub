from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import (
    anthropic_claude_runtime_config as _runtime_config,
)
from cli.agent_cli.providers.adapters.openai_responses_output_runtime import (
    json_ready as _json_ready_impl,
)
from cli.agent_cli.providers.anthropic_request_logging import (  # noqa: F401 – re-exported for public API
    log_anthropic_request,
    log_anthropic_response,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.delegation_policy import planner_tool_execution_target
from cli.agent_cli.providers.openai_planner_support_runtime import quote_arg as _quote_arg_impl
from cli.agent_cli.providers.responses_tool_specs import (
    function_fields_from_spec as _function_fields_from_spec_impl,
)
from cli.agent_cli.providers.tool_calls import command_for_tool_call as _command_for_tool_call_impl

PlannerToolExecutor = Callable[[str], tuple[str, list[Any]]]
PluginManagerFactory = Callable[[], PluginManager | None]

DEFAULT_CLAUDE_PROVIDER_ALIASES = _runtime_config.DEFAULT_CLAUDE_PROVIDER_ALIASES
_CLAUDE_ALIAS_MODEL_KEYS = _runtime_config._CLAUDE_ALIAS_MODEL_KEYS
ClaudeConfigPaths = _runtime_config.ClaudeConfigPaths
claude_config_paths = _runtime_config.claude_config_paths
read_json_file = _runtime_config.read_json_file
is_claude_model = _runtime_config.is_claude_model
_claude_model_alias = _runtime_config._claude_model_alias
_is_supported_claude_selection = _runtime_config._is_supported_claude_selection
_default_model_for_alias = _runtime_config._default_model_for_alias
_configured_claude_model = _runtime_config._configured_claude_model
should_use_claude_provider = _runtime_config.should_use_claude_provider
_first_text = _runtime_config._first_text
load_claude_provider_config = _runtime_config.load_claude_provider_config


def json_ready(value: Any) -> Any:
    return _json_ready_impl(value)


def content_block_dict(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return dict(block)
    payload = json_ready(block)
    if isinstance(payload, dict):
        return payload

    normalized: dict[str, Any] = {}
    for key in (
        "type",
        "text",
        "id",
        "name",
        "input",
        "content",
        "tool_use_id",
        "is_error",
        "citations",
        "caller",
    ):
        value = getattr(block, key, None)
        if value is not None:
            normalized[key] = json_ready(value)
    return normalized


def message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        payload = content_block_dict(block)
        block_type = str(payload.get("type") or "").strip()
        text = ""
        if block_type in {"text", "input_text", "output_text", "summary_text", "reasoning"}:
            text = str(payload.get("text") or "").strip()
        elif block_type == "refusal":
            text = str(payload.get("refusal") or payload.get("text") or "").strip()
        elif not block_type:
            text = str(payload.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def function_fields_from_spec(spec: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    return _function_fields_from_spec_impl(spec)


def anthropic_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
    merged_provider_tool_specs_fn: Callable[..., list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for item in merged_provider_tool_specs_fn(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    ):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type and item_type != "function" and str(item.get("name") or "").strip():
            specs.append(dict(item))
            continue
        function_name, description, parameters = function_fields_from_spec(item)
        if str(item.get("name") or "").strip() and isinstance(item.get("input_schema"), dict):
            specs.append(
                {
                    "name": str(item.get("name") or "").strip(),
                    "description": str(item.get("description") or "").strip(),
                    "input_schema": dict(item.get("input_schema") or {}),
                }
            )
            continue
        if not function_name:
            continue
        specs.append(
            {
                "name": function_name,
                "description": description,
                "input_schema": (
                    dict(parameters)
                    if isinstance(parameters, dict)
                    else {"type": "object", "properties": {}, "additionalProperties": False}
                ),
            }
        )
    return specs


def quote_arg(value: Any) -> str:
    return _quote_arg_impl(value)


def command_for_tool_call(
    name: str,
    arguments: dict[str, Any],
    host_platform: HostPlatform,
    *,
    optional_bool_fn: Callable[[Any, bool], bool],
    command_for_tool_call_impl_fn: Callable[..., str | None] = _command_for_tool_call_impl,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> str | None:
    effective_name, enriched_arguments = planner_tool_execution_target(name, arguments)
    return command_for_tool_call_impl_fn(
        effective_name,
        enriched_arguments,
        host_platform,
        optional_bool_fn=optional_bool_fn,
        quote_arg_fn=quote_arg,
        plugin_manager_factory=plugin_manager_factory,
    )
