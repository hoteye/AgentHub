from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import system_prompts_helpers as system_prompts_helper_impl
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.delegation_policy import delegation_policy_prompt_text
from cli.agent_cli.providers.interaction_contract_runtime import (
    resolved_interaction_contract_for_config,
)
from cli.agent_cli.providers.planner_postprocessing import concise_answer_prompt_text
from cli.agent_cli.providers.platform_guidance import (
    native_directory_snapshot_guidance,
    structured_directory_snapshot_guidance,
)
from cli.agent_cli.providers.reference_parity import (
    load_claude_code_base_prompt,
    load_reference_base_prompt,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    available_tool_name_set as _available_tool_name_set,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    claude_code_editing_guidance_sections as _claude_code_editing_guidance_sections,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    expert_review_guidance_sections as _expert_review_guidance_sections,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    responses_command_guidance_section as _responses_command_guidance_section,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    responses_json_examples as _responses_json_examples,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    responses_primary_command_list as _responses_primary_command_list,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    responses_request_user_input_guidance_sections as _responses_request_user_input_guidance_sections,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    responses_web_guidance_sections as _responses_web_guidance_sections,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    tool_demo_answer_guidance as _tool_demo_answer_guidance,
)
from cli.agent_cli.providers.system_prompt_sections_runtime import (
    tool_usage_name as _tool_usage_name,
)
from cli.agent_cli.providers.tool_calls import (
    plugin_system_prompt_addendum as _plugin_system_prompt_addendum_impl,
)
from cli.agent_cli.providers.tool_specs import resolve_native_web_search_capability

PluginManagerFactory = Callable[[], Any]
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_BASE_PROMPT_PATH = _PROMPTS_DIR / "agenthub_base.md"
_RUNTIME_LEAK_MARKERS = (
    "<environment_context>",
    "<permissions instructions>",
    "sandbox_mode",
    "approval_policy",
    "current_date",
    "timezone",
    "cwd=",
)
_CLAUDE_CODE_RUNTIME_ALIGNMENT_ADDENDUM = """# Using your tools

- Do NOT use the Bash tool to run commands when a relevant dedicated tool is provided. Using dedicated tools allows the user to better understand and review your work.
- To read files use Read instead of cat, head, tail, or sed.
- To edit files use Edit instead of sed or awk.
- To create files use Write instead of cat with heredoc or echo redirection.
- To search for files use Glob instead of find or ls.
- To search the content of files, use Grep instead of grep or rg.
- Reserve using Bash exclusively for system commands and terminal operations that require shell execution. If you are unsure and there is a relevant dedicated tool, default to the dedicated tool and only fall back to Bash if it is absolutely necessary.
- You can call multiple tools in a single response. If you intend to call multiple tools and there are no dependencies between them, make all independent tool calls in parallel.
- Use the Agent tool with specialized agents when the task at hand matches the agent's description. Subagents are valuable for parallelizing independent queries or for protecting the main context window from excessive results, but they should not be used excessively when not needed.
- For simple, directed codebase searches (e.g. for a specific file/class/function) use the Glob or Grep tools directly.
- For broader codebase exploration and deep research, use the Agent tool with subagent_type=Explore. This is slower than using the Glob or Grep directly, so use this only when a simple, directed search proves to be insufficient or when your task will clearly require more than 3 queries.
- Write Agent tool description and prompt arguments in English. The user-facing answer can still follow the user's language in your final response.

# Output efficiency

- Go straight to the point. Try the simplest approach first without going in circles. Do not overdo it. Be extra concise.
- Keep your text output brief and direct. Lead with the answer or action, not the reasoning. Skip filler words, preamble, and unnecessary transitions. Do not restate what the user said - just do it.
- If you can say it in one sentence, don't use three. Prefer short, direct sentences over long explanations. This does not apply to code or tool calls.
- For user-facing overviews or capability summaries delegated to Agent, ask for a concise report with an explicit length bound unless the user requested exhaustive analysis."""


def _normalize_prompt_section(value: Any) -> str:
    return system_prompts_helper_impl.normalize_prompt_section(value)


@lru_cache(maxsize=1)
def load_agenthub_base_prompt() -> str:
    text = _normalize_prompt_section(_BASE_PROMPT_PATH.read_text(encoding="utf-8"))
    if not text:
        raise ValueError(f"empty base prompt: {_BASE_PROMPT_PATH}")
    return text


def compose_system_prompt(*sections: Any) -> str:
    normalized = [_normalize_prompt_section(section) for section in sections]
    return "\n\n".join(section for section in normalized if section)


def _web_search_surface_kind(config: ProviderConfig | None) -> str:
    return system_prompts_helper_impl.web_search_surface_kind(
        config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
    )


def _tool_surface_profile(config: ProviderConfig | None) -> str:
    return system_prompts_helper_impl.tool_surface_profile(
        config,
        resolved_interaction_contract_for_config_fn=resolved_interaction_contract_for_config,
    )


def _responses_editing_guidance_sections(
    *,
    available_tool_names: str,
    config: ProviderConfig | None = None,
    native_tool_loop: bool = False,
) -> list[str]:
    return system_prompts_helper_impl.responses_editing_guidance_sections(
        available_tool_names=available_tool_names,
        config=config,
        available_tool_name_set_fn=_available_tool_name_set,
        claude_code_editing_guidance_sections_fn=_claude_code_editing_guidance_sections,
        tool_surface_profile_fn=_tool_surface_profile,
        tool_usage_name_fn=lambda name: _tool_usage_name(name, native_tool_loop=native_tool_loop),
    )


def _chat_profile_editing_guidance_sections(config: ProviderConfig | None) -> list[str]:
    return system_prompts_helper_impl.chat_profile_editing_guidance_sections(
        config,
        claude_code_editing_guidance_sections_fn=_claude_code_editing_guidance_sections,
        tool_surface_profile_fn=_tool_surface_profile,
    )


def build_shared_agenthub_addendum(
    host_platform: HostPlatform,
    *,
    native_tool_loop: bool = False,
    include_attachment_guidance: bool = True,
    config: ProviderConfig | None = None,
) -> str:
    return system_prompts_helper_impl.build_shared_agenthub_addendum(
        host_platform,
        native_tool_loop=native_tool_loop,
        include_attachment_guidance=include_attachment_guidance,
        config=config,
        compose_system_prompt_fn=compose_system_prompt,
        concise_answer_prompt_text_fn=concise_answer_prompt_text,
        delegation_policy_prompt_text_fn=delegation_policy_prompt_text,
        native_directory_snapshot_guidance_fn=native_directory_snapshot_guidance,
        structured_directory_snapshot_guidance_fn=structured_directory_snapshot_guidance,
        tool_demo_answer_guidance_fn=_tool_demo_answer_guidance,
        tool_surface_profile_fn=_tool_surface_profile,
    )


def build_responses_addendum(
    *,
    host_platform: HostPlatform,
    available_tool_names: str = "",
    plugin_manager_factory: PluginManagerFactory | None = None,
    native_tool_loop: bool = False,
    web_search_surface: str = "",
    config: ProviderConfig | None = None,
) -> str:
    return system_prompts_helper_impl.build_responses_addendum(
        host_platform=host_platform,
        available_tool_names=available_tool_names,
        plugin_manager_factory=plugin_manager_factory,
        native_tool_loop=native_tool_loop,
        web_search_surface=web_search_surface,
        config=config,
        available_tool_name_set_fn=_available_tool_name_set,
        compose_system_prompt_fn=compose_system_prompt,
        expert_review_guidance_sections_fn=_expert_review_guidance_sections,
        plugin_system_prompt_addendum_fn=_plugin_system_prompt_addendum_impl,
        responses_command_guidance_section_fn=_responses_command_guidance_section,
        responses_editing_guidance_sections_fn=_responses_editing_guidance_sections,
        responses_json_examples_fn=_responses_json_examples,
        responses_primary_command_list_fn=_responses_primary_command_list,
        responses_request_user_input_guidance_sections_fn=_responses_request_user_input_guidance_sections,
        responses_web_guidance_sections_fn=_responses_web_guidance_sections,
    )


def build_chat_completions_addendum(
    *,
    host_platform: HostPlatform,
    use_glm_native_web_search: bool = False,
    use_native_web_search: bool | None = None,
    config: ProviderConfig | None = None,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> str:
    return system_prompts_helper_impl.build_chat_completions_addendum(
        host_platform=host_platform,
        use_glm_native_web_search=use_glm_native_web_search,
        use_native_web_search=use_native_web_search,
        config=config,
        plugin_manager_factory=plugin_manager_factory,
        chat_profile_editing_guidance_sections_fn=_chat_profile_editing_guidance_sections,
        compose_system_prompt_fn=compose_system_prompt,
        expert_review_guidance_sections_fn=_expert_review_guidance_sections,
        plugin_system_prompt_addendum_fn=_plugin_system_prompt_addendum_impl,
        web_search_surface_kind_fn=_web_search_surface_kind,
    )


def build_openai_json_system_prompt(
    *,
    host_platform: HostPlatform,
    available_tool_names: str = "",
    plugin_manager_factory: PluginManagerFactory | None = None,
    config: ProviderConfig | None = None,
) -> str:
    if (
        config is not None
        and resolved_interaction_contract_for_config(config).base_prompt_profile == "codex_openai"
    ):
        return load_reference_base_prompt()
    web_search_surface = _web_search_surface_kind(config)
    return compose_system_prompt(
        load_agenthub_base_prompt(),
        build_shared_agenthub_addendum(host_platform, native_tool_loop=False, config=config),
        build_responses_addendum(
            host_platform=host_platform,
            available_tool_names=available_tool_names,
            plugin_manager_factory=plugin_manager_factory,
            native_tool_loop=False,
            web_search_surface=web_search_surface,
            config=config,
        ),
    )


def build_openai_native_system_prompt(
    *,
    host_platform: HostPlatform,
    available_tool_names: str = "",
    config: ProviderConfig | None = None,
) -> str:
    if (
        config is not None
        and resolved_interaction_contract_for_config(config).base_prompt_profile == "codex_openai"
    ):
        return load_reference_base_prompt()
    web_search_surface = _web_search_surface_kind(config)
    return compose_system_prompt(
        load_agenthub_base_prompt(),
        build_shared_agenthub_addendum(host_platform, native_tool_loop=True, config=config),
        build_responses_addendum(
            host_platform=host_platform,
            available_tool_names=available_tool_names,
            native_tool_loop=True,
            web_search_surface=web_search_surface,
            config=config,
        ),
    )


def build_chat_completions_system_prompt(
    *,
    host_platform: HostPlatform,
    use_glm_native_web_search: bool = False,
    use_native_web_search: bool | None = None,
    config: ProviderConfig | None = None,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> str:
    if (
        config is not None
        and resolved_interaction_contract_for_config(config).base_prompt_profile == "claude_code"
    ):
        return compose_system_prompt(
            load_claude_code_base_prompt(),
            _CLAUDE_CODE_RUNTIME_ALIGNMENT_ADDENDUM,
        )
    else:
        base = load_agenthub_base_prompt()
    return compose_system_prompt(
        base,
        build_shared_agenthub_addendum(host_platform, native_tool_loop=False, config=config),
        build_chat_completions_addendum(
            host_platform=host_platform,
            use_glm_native_web_search=use_glm_native_web_search,
            use_native_web_search=use_native_web_search,
            config=config,
            plugin_manager_factory=plugin_manager_factory,
        ),
    )


def system_prompt_contract(prompt: str) -> dict[str, Any]:
    text = _normalize_prompt_section(prompt)
    sections = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
    return {
        "length": len(text),
        "section_count": len(sections),
        "sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12] if text else "",
        "contains_environment_context": "<environment_context>" in text,
        "contains_permissions_instructions": "<permissions instructions>" in text,
        "contains_runtime_leakage": any(marker in text for marker in _RUNTIME_LEAK_MARKERS),
    }
