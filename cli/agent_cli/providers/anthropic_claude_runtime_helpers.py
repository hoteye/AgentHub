from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import anthropic_claude_runtime as anthropic_claude_runtime_service
from cli.agent_cli.providers.config_catalog import ProviderConfig, optional_bool
from cli.agent_cli.providers.tool_calls import command_for_tool_call as _command_for_tool_call_impl
from cli.agent_cli.providers.tool_specs import merged_provider_tool_specs

PluginManagerFactory = Callable[[], PluginManager | None]

ClaudeConfigPaths = anthropic_claude_runtime_service.ClaudeConfigPaths


def read_json_file(path: Path) -> Dict[str, Any]:
    return anthropic_claude_runtime_service.read_json_file(path)


def json_ready(value: Any) -> Any:
    return anthropic_claude_runtime_service.json_ready(value)


def log_anthropic_request(request: Dict[str, Any]) -> None:
    anthropic_claude_runtime_service.log_anthropic_request(request)


def log_anthropic_response(response: Any) -> None:
    anthropic_claude_runtime_service.log_anthropic_response(response)


def message_text(content: Any) -> str:
    return anthropic_claude_runtime_service.message_text(content)


def is_claude_model(model: str) -> bool:
    return anthropic_claude_runtime_service.is_claude_model(model)


def claude_config_paths(home_dir: Path | None = None) -> ClaudeConfigPaths:
    return anthropic_claude_runtime_service.claude_config_paths(home_dir)


def should_use_claude_provider(
    *,
    env_mapping: Mapping[str, str],
    configured_provider: str = "",
    configured_model: str = "",
    selected_config: ProviderConfig | None = None,
    claude_provider_aliases: frozenset[str] | None = None,
) -> bool:
    return anthropic_claude_runtime_service.should_use_claude_provider(
        env_mapping=env_mapping,
        configured_provider=configured_provider,
        configured_model=configured_model,
        selected_config=selected_config,
        claude_provider_aliases=claude_provider_aliases,
    )


def load_claude_provider_config(
    *,
    env_mapping: Mapping[str, str],
    home_dir: Path | None = None,
    config_paths: ClaudeConfigPaths | None = None,
    fallback_model: str = "",
    fallback_base_url: str = "",
    default_claude_model: str,
    default_max_tokens: int,
) -> Optional[ProviderConfig]:
    paths = config_paths or claude_config_paths(home_dir)
    return anthropic_claude_runtime_service.load_claude_provider_config(
        env_mapping=env_mapping,
        config_paths=paths,
        fallback_model=fallback_model,
        fallback_base_url=fallback_base_url,
        default_claude_model=default_claude_model,
        default_max_tokens=default_max_tokens,
    )


def function_fields_from_spec(spec: Dict[str, Any]):
    return anthropic_claude_runtime_service.function_fields_from_spec(spec)


def anthropic_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: Optional[PluginManagerFactory] = None,
) -> List[Dict[str, Any]]:
    return anthropic_claude_runtime_service.anthropic_tool_specs(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
        merged_provider_tool_specs_fn=merged_provider_tool_specs,
    )


def quote_arg(value: Any) -> str:
    return anthropic_claude_runtime_service.quote_arg(value)


def command_for_tool_call(
    name: str,
    arguments: Dict[str, Any],
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: Optional[PluginManagerFactory] = None,
) -> Optional[str]:
    return anthropic_claude_runtime_service.command_for_tool_call(
        name,
        arguments,
        host_platform,
        optional_bool_fn=optional_bool,
        command_for_tool_call_impl_fn=_command_for_tool_call_impl,
        plugin_manager_factory=plugin_manager_factory,
    )


def content_block_dict(block: Any) -> Dict[str, Any]:
    return anthropic_claude_runtime_service.content_block_dict(block)
