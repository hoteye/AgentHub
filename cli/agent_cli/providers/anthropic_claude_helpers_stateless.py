from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import anthropic_claude_runtime_helpers as runtime_helpers
from cli.agent_cli.providers.config_catalog import ProviderConfig

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096
ANTHROPIC_TURN_ENGINE_MAX_ROUNDS: int | None = None
CLAUDE_PROVIDER_ALIASES = frozenset({"anthropic", "claude", "claude_code", "anthropic_claude"})

PluginManagerFactory = Callable[[], PluginManager | None]

ClaudeConfigPaths = runtime_helpers.ClaudeConfigPaths


def log_anthropic_request(request: dict[str, Any]) -> None:
    runtime_helpers.log_anthropic_request(request)


def log_anthropic_response(response: Any) -> None:
    runtime_helpers.log_anthropic_response(response)


def message_text(content: Any) -> str:
    return runtime_helpers.message_text(content)


def claude_config_paths(home_dir: Path | None = None) -> ClaudeConfigPaths:
    return runtime_helpers.claude_config_paths(home_dir)


def should_use_claude_provider(
    *,
    env_mapping: Mapping[str, str],
    configured_provider: str = "",
    configured_model: str = "",
    selected_config: ProviderConfig | None = None,
    claude_provider_aliases: frozenset[str] | None = None,
) -> bool:
    return runtime_helpers.should_use_claude_provider(
        env_mapping=env_mapping,
        configured_provider=configured_provider,
        configured_model=configured_model,
        selected_config=selected_config,
        claude_provider_aliases=(
            CLAUDE_PROVIDER_ALIASES if claude_provider_aliases is None else claude_provider_aliases
        ),
    )


def load_claude_provider_config(
    *,
    env_mapping: Mapping[str, str],
    home_dir: Path | None = None,
    config_paths: ClaudeConfigPaths | None = None,
    fallback_model: str = "",
    fallback_base_url: str = "",
    default_claude_model: str = DEFAULT_CLAUDE_MODEL,
    default_max_tokens: int = DEFAULT_MAX_TOKENS,
) -> ProviderConfig | None:
    return runtime_helpers.load_claude_provider_config(
        env_mapping=env_mapping,
        home_dir=home_dir,
        config_paths=config_paths,
        fallback_model=fallback_model,
        fallback_base_url=fallback_base_url,
        default_claude_model=default_claude_model,
        default_max_tokens=default_max_tokens,
    )


def function_fields_from_spec(spec: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    return runtime_helpers.function_fields_from_spec(spec)


def anthropic_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> list[dict[str, Any]]:
    return runtime_helpers.anthropic_tool_specs(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    )


def quote_arg(value: Any) -> str:
    return runtime_helpers.quote_arg(value)


def command_for_tool_call(
    name: str,
    arguments: dict[str, Any],
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> str | None:
    return runtime_helpers.command_for_tool_call(
        name,
        arguments,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    )


def content_block_dict(block: Any) -> dict[str, Any]:
    return runtime_helpers.content_block_dict(block)


def pending_tool_use_ids_from_messages(messages: list[dict[str, Any]]) -> set[str]:
    if not messages:
        return set()
    last_message = messages[-1]
    if str(last_message.get("role") or "").strip() != "assistant":
        return set()
    ids: set[str] = set()
    for block in list(last_message.get("content") or []):
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "").strip() != "tool_use":
            continue
        call_id = str(block.get("id") or "").strip()
        if call_id:
            ids.add(call_id)
    return ids
