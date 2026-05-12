from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.config_catalog import ProviderConfig

PluginManagerFactory = Callable[[], Any]


def normalize_prompt_section(value: Any) -> str:
    lines = [line.rstrip() for line in str(value or "").strip().splitlines()]
    return "\n".join(lines).strip()


def web_search_surface_kind(
    config: ProviderConfig | None,
    *,
    resolve_native_web_search_capability_fn: Callable[[ProviderConfig], Any],
) -> str:
    if config is None:
        return ""
    capability = resolve_native_web_search_capability_fn(config)
    if str(getattr(capability, "effective_mode", "") or "").strip().lower() == "disabled":
        return "disabled"
    if str(getattr(capability, "main_loop_spec_kind", "") or "").strip() in {
        "openai_responses_native",
        "anthropic_native",
        "glm_native",
    }:
        return "native"
    if str(getattr(capability, "native_tool_type", "") or "").strip():
        return "fallback"
    return "fallback"


def tool_surface_profile(
    config: ProviderConfig | None,
    *,
    resolved_interaction_contract_for_config_fn: Callable[[ProviderConfig], Any],
) -> str:
    if config is None:
        return ""
    try:
        contract = resolved_interaction_contract_for_config_fn(config)
    except Exception:
        return ""
    return str(getattr(contract, "tool_surface_profile", "") or getattr(contract, "profile", "")).strip().lower()


def responses_editing_guidance_sections(
    *,
    available_tool_names: str,
    config: ProviderConfig | None = None,
    available_tool_name_set_fn: Callable[[str], set[str]],
    claude_code_editing_guidance_sections_fn: Callable[..., list[str]],
    tool_surface_profile_fn: Callable[[ProviderConfig | None], str],
    tool_usage_name_fn: Callable[[str], str],
) -> list[str]:
    names = available_tool_name_set_fn(available_tool_names)
    if tool_surface_profile_fn(config) != "claude_code":
        return []
    if "Write" not in names and "Edit" not in names:
        return []
    return claude_code_editing_guidance_sections_fn(read_tool_name=tool_usage_name_fn("read_file"))


def chat_profile_editing_guidance_sections(
    config: ProviderConfig | None,
    *,
    claude_code_editing_guidance_sections_fn: Callable[..., list[str]],
    tool_surface_profile_fn: Callable[[ProviderConfig | None], str],
) -> list[str]:
    if tool_surface_profile_fn(config) != "claude_code":
        return []
    return claude_code_editing_guidance_sections_fn(read_tool_name="read_file")


def build_shared_agenthub_addendum(
    host_platform: HostPlatform,
    *,
    native_tool_loop: bool = False,
    include_attachment_guidance: bool = True,
    config: ProviderConfig | None = None,
    compose_system_prompt_fn: Callable[..., str],
    concise_answer_prompt_text_fn: Callable[[], str],
    delegation_policy_prompt_text_fn: Callable[..., str],
    native_directory_snapshot_guidance_fn: Callable[[HostPlatform], str],
    structured_directory_snapshot_guidance_fn: Callable[[HostPlatform], str],
    tool_demo_answer_guidance_fn: Callable[[], str],
    tool_surface_profile_fn: Callable[[ProviderConfig | None], str],
) -> str:
    sections: list[str] = []
    if native_tool_loop:
        sections.extend(
            [
                "When the user asks to inspect, check, or answer questions about the current project, repository, or workspace, use local tools first and ground the answer in repository files instead of replying only from generic guidance.",
                native_directory_snapshot_guidance_fn(host_platform),
                "Use web_search only for current information or sources outside the local workspace. Only do this when web_search is exposed in this session.",
            ]
        )
    else:
        sections.extend(
            [
                "For local workspace file inspection, prefer grep_files, list_dir, and read_file.",
                "The canonical local inspection trio order is grep_files, list_dir, then read_file.",
                "Treat the session cwd from environment/reference context as the default base for grep_files, list_dir, read_file, and Claude-style Glob/Grep/Read calls.",
                "For the current working directory, omit path or use '.'. If repository-wide scope or a parent/sibling directory is needed, pass an explicit path that stays inside the active workspace/project root.",
                "When the user asks where a file lives in the current repository/workspace, use an explicit path rooted at workspace_root from reference context instead of assuming the file is under cwd.",
                structured_directory_snapshot_guidance_fn(host_platform),
                "Treat file_search, file_read, and file_list as compatibility aliases only.",
                "Do not choose the file_* aliases unless the user explicitly uses them or compatibility is required.",
                "When the user asks to inspect, check, or answer questions about the current project, repository, or workspace, use local file tools first and ground the answer in repository files instead of replying only from generic guidance.",
                "Use web_search only for current information or sources outside the local workspace. Only do this when web_search is exposed in this session.",
            ]
        )
    sections.append(tool_demo_answer_guidance_fn())
    if include_attachment_guidance:
        sections.extend(
            [
                "Structured local attachments may appear in an ATTACHMENTS_JSON block inside the user message.",
                "Treat those attachment objects as the authoritative file inputs for the current turn.",
            ]
        )
    tool_surface_profile = tool_surface_profile_fn(config)
    sections.extend(
        [
            "When the user asks where a prompt, error, or status text is generated, search for the exact literal text or a distinctive fragment, and identify the function that defines or assembles that text rather than a wrapper that only prints surrounding status.",
            delegation_policy_prompt_text_fn(tool_surface_profile=tool_surface_profile),
            concise_answer_prompt_text_fn(),
            f"Current host platform: {host_platform.os} ({host_platform.family}), shell={host_platform.shell_kind}.",
        ]
    )
    return compose_system_prompt_fn(*sections)


def build_responses_addendum(
    *,
    host_platform: HostPlatform,
    available_tool_names: str = "",
    plugin_manager_factory: PluginManagerFactory | None = None,
    native_tool_loop: bool = False,
    web_search_surface: str = "",
    config: ProviderConfig | None = None,
    available_tool_name_set_fn: Callable[[str], set[str]],
    compose_system_prompt_fn: Callable[..., str],
    expert_review_guidance_sections_fn: Callable[..., list[str]],
    plugin_system_prompt_addendum_fn: Callable[..., str],
    responses_command_guidance_section_fn: Callable[..., str],
    responses_editing_guidance_sections_fn: Callable[..., list[str]],
    responses_json_examples_fn: Callable[..., str],
    responses_primary_command_list_fn: Callable[[str], str],
    responses_request_user_input_guidance_sections_fn: Callable[[str], list[str]],
    responses_web_guidance_sections_fn: Callable[..., list[str]],
) -> str:
    if native_tool_loop:
        return compose_system_prompt_fn(
            "When tools are available, call tools directly instead of telling the user to run commands manually.",
            "Use only the structured tools exposed in this native Responses loop.",
            responses_command_guidance_section_fn(
                available_tool_names=available_tool_names,
                native_tool_loop=True,
            ),
            *responses_request_user_input_guidance_sections_fn(available_tool_names),
            *expert_review_guidance_sections_fn(
                available_tool_names=available_tool_names,
                available_by_contract="expert_review" in available_tool_name_set_fn(available_tool_names),
            ),
            *responses_editing_guidance_sections_fn(
                available_tool_names=available_tool_names,
                config=config,
                native_tool_loop=True,
            ),
            *responses_web_guidance_sections_fn(
                available_tool_names=available_tool_names,
                web_search_surface=web_search_surface,
                native_tool_loop=True,
            ),
            "When tools are available, first send a brief assistant message about the next concrete action, then call tools.",
            "Keep that pre-tool message concise and practical, and do not expose raw chain-of-thought.",
            "After tools finish, return plain concise Chinese text.",
            "Do not wrap the final answer in JSON.",
            f"Available structured tool/command names in this native Responses loop: {available_tool_names}." if available_tool_names else "",
        )

    plugin_prompt = plugin_system_prompt_addendum_fn(plugin_manager_factory=plugin_manager_factory)
    return compose_system_prompt_fn(
        "When the user's request should be handled by a local command or slash command, return an executable intent instead of telling the user to type it manually.",
        "When tools are available, call tools directly and do not emit slash commands in free-form text.",
        "Use only slash command names that are listed in the available structured tool/command names line below.",
        responses_primary_command_list_fn(available_tool_names),
        responses_command_guidance_section_fn(
            available_tool_names=available_tool_names,
            native_tool_loop=False,
        ),
        *responses_request_user_input_guidance_sections_fn(available_tool_names),
        *expert_review_guidance_sections_fn(
            available_tool_names=available_tool_names,
            available_by_contract="expert_review" in available_tool_name_set_fn(available_tool_names),
        ),
        *responses_editing_guidance_sections_fn(
            available_tool_names=available_tool_names,
            config=config,
            native_tool_loop=False,
        ),
        *responses_web_guidance_sections_fn(
            available_tool_names=available_tool_names,
            web_search_surface=web_search_surface,
            native_tool_loop=False,
        ),
        "Plugin slash commands may also be available when exposed by the host.",
        responses_json_examples_fn(
            host_platform=host_platform,
            available_tool_names=available_tool_names,
        ),
        "Return strict JSON with keys assistant_text, command_text, status_hint.",
        "Set command_text to null when no command should run.",
        "Do not wrap the JSON in markdown fences.",
        f"Available structured tool/command names in this session: {available_tool_names}." if available_tool_names else "",
        plugin_prompt,
    )


def build_chat_completions_addendum(
    *,
    host_platform: HostPlatform,
    use_glm_native_web_search: bool = False,
    use_native_web_search: bool | None = None,
    config: ProviderConfig | None = None,
    plugin_manager_factory: PluginManagerFactory | None = None,
    chat_profile_editing_guidance_sections_fn: Callable[[ProviderConfig | None], list[str]],
    compose_system_prompt_fn: Callable[..., str],
    expert_review_guidance_sections_fn: Callable[..., list[str]],
    plugin_system_prompt_addendum_fn: Callable[..., str],
    web_search_surface_kind_fn: Callable[[ProviderConfig | None], str],
) -> str:
    plugin_prompt = plugin_system_prompt_addendum_fn(plugin_manager_factory=plugin_manager_factory)
    if config is not None:
        web_search_surface = web_search_surface_kind_fn(config)
    else:
        web_search_surface = "native" if bool(use_glm_native_web_search) else "fallback"
    if use_native_web_search is not None and web_search_surface != "disabled":
        web_search_surface = "native" if bool(use_native_web_search) else "fallback"
    native_web_search_enabled = web_search_surface == "native"
    prompt = compose_system_prompt_fn(
        "Use tools whenever the task is about local files, shell commands, Office/PDF processing, public web search, or plugin-exposed capabilities.",
        (
            "For command execution, prefer exec_command and write_stdin on Codex-style surfaces. "
            "When using exec_command, set workdir instead of prepending cd when the target directory is already known. "
            "Do not wrap commands in cd ... && unless shell semantics genuinely require it. "
            "If a write or delete command fails because the workspace is read-only or returns Permission denied, do not keep retrying equivalent write variants in the same turn; summarize the block briefly and stop. "
            "Codex-style surfaces use exec_command and write_stdin; Claude-style surfaces use Bash and, on supported platforms, PowerShell, while write_stdin remains the continuation tool. "
            "On Claude-style surfaces, run_in_background means return early from a live session and use write_stdin later if more output is needed. "
            "Do not treat shell as the primary tool name."
        ),
        "For company policy, policy basis, clause, procedure, standard, rule, operating procedure, or audit remediation questions, search with short focused queries first, then read the top formal policy documents before answering.",
        "If web_search is exposed in this session, use it for general public-web discovery about news, changing external facts, live product documentation, or explicit online lookup requests.",
        "If web_fetch is exposed in this session, use it only to read a concrete known URL after discovery or when the user directly gives the URL.",
        "If the user already gives a concrete public URL, prefer web_fetch directly instead of web_search unless the task requires browser navigation or interaction.",
        "For search-then-read evidence flows, use web_search first to discover candidate sources, then use web_fetch on a selected URL when you need source content before answering.",
        "If browser is exposed in this session, use it as the canonical browser-family tool for page navigation or interaction. Treat open, click, and find as legacy aliases only when they are explicitly exposed or the exact compatibility path is required.",
        "Use browser only for navigation, interaction, or managed browser inspection. Do not use browser, open, click, or find just to read a known URL or to do general public-web discovery.",
        "Treat the session cwd from environment/reference context as the default base for grep_files, list_dir, read_file, and Claude-style Glob/Grep/Read calls.",
        "For the current working directory, omit path or use '.'. If repository-wide scope or a parent/sibling directory is needed, pass an explicit path that stays inside the active workspace/project root.",
        "When the user asks where a file lives in the current repository/workspace, use an explicit path rooted at workspace_root from reference context instead of assuming the file is under cwd.",
        *expert_review_guidance_sections_fn(available_by_contract=True),
        *chat_profile_editing_guidance_sections_fn(config),
        "Choose tools according to each tool's documented purpose and constraints.",
        "After tool results are available, answer briefly in Chinese.",
        plugin_prompt,
    )
    if web_search_surface == "disabled":
        prompt = compose_system_prompt_fn(
            prompt,
            "Do not promise live web lookup unless web_search is actually exposed in this session.",
        )
    elif native_web_search_enabled:
        prompt = compose_system_prompt_fn(
            prompt,
            "When the provider exposes native web_search in this session, prefer that native tool for general online lookup instead of manual multi-step browsing. Keep web_fetch for reading a known URL and browser tools for navigation or interaction.",
        )
    else:
        prompt = compose_system_prompt_fn(
            prompt,
            "When web_search is exposed only as a fallback tool path, still use it for general online lookup, but do not treat it as provider-native browsing or page navigation.",
        )
    return prompt
