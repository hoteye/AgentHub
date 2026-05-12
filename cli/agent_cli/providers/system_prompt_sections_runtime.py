from __future__ import annotations

import shlex

from cli.agent_cli.host_platform import HostPlatform


def available_tool_name_set(value: str) -> set[str]:
    return {token for token in (part.strip() for part in str(value or "").split(",")) if token}


def tool_usage_name(name: str, *, native_tool_loop: bool) -> str:
    normalized = str(name or "").strip()
    if not normalized:
        return normalized
    return normalized if native_tool_loop else f"/{normalized}"


def tool_demo_answer_guidance() -> str:
    return (
        "When the user asks how to use a tool or asks for a demo/example, include a concise concrete example "
        "using the actual tool call you just used, naming the tool and its key arguments instead of only "
        "describing the tool abstractly."
    )


def responses_web_guidance_sections(
    *,
    available_tool_names: str,
    web_search_surface: str = "",
    native_tool_loop: bool = False,
) -> list[str]:
    names = available_tool_name_set(available_tool_names)
    sections: list[str] = []
    search_name = tool_usage_name("web_search", native_tool_loop=native_tool_loop)
    fetch_name = tool_usage_name("web_fetch", native_tool_loop=native_tool_loop)
    browser_name = tool_usage_name("browser", native_tool_loop=native_tool_loop)
    if "web_search" in names:
        if web_search_surface == "native":
            sections.append(
                "Use the provider-native web_search tool for general public-web discovery about current external facts."
            )
        elif native_tool_loop:
            sections.append(
                "Use the exposed web_search tool in this loop for general public-web discovery; do not assume browser navigation or page-reading semantics."
            )
        else:
            sections.append(
                "Use /web_search for general public-web discovery about current external facts; it is not the tool for reading a known URL."
            )
    else:
        sections.append(
            "Do not promise live web lookup unless web_search is actually exposed in this session."
        )
    if "web_fetch" in names:
        sections.append(
            "Use web_fetch only when you already have a concrete URL and need readable page content as evidence."
            if native_tool_loop
            else "Use /web_fetch only when you already have a concrete URL and need readable page content as evidence."
        )
        sections.append(
            f"If the user already gives a concrete public URL, skip {search_name} and use {fetch_name} directly unless the task requires browser navigation or interaction."
            if "web_search" in names
            else f"If the user already gives a concrete public URL, use {fetch_name} directly unless the task requires browser navigation or interaction."
        )
    if "web_search" in names and "web_fetch" in names:
        sections.append(
            f"For search-then-read evidence flows, use {search_name} first to discover candidate sources, then use {fetch_name} on a selected URL when you need page content before answering."
        )
    if "browser" in names:
        sections.append(
            "Use browser as the canonical browser-family tool for page navigation, interaction, or managed browser inspection; keep it separate from web_search discovery."
            if native_tool_loop
            else "Use /browser as the canonical browser-family tool for page navigation, interaction, or managed browser inspection; keep it separate from /web_search discovery."
        )
        sections.append(
            f"Use {browser_name} only for navigation, interaction, or managed browser inspection. Do not use it just to read a known URL or to do general public-web discovery."
        )
    legacy_aliases = [name for name in ("open", "click", "find") if name in names]
    if legacy_aliases:
        alias_list = ", ".join(
            tool_usage_name(name, native_tool_loop=native_tool_loop) for name in legacy_aliases
        )
        sections.append(
            f"Treat {alias_list} as legacy browser-family aliases only; prefer {browser_name} when the canonical browser tool is exposed."
        )
        sections.append(
            f"Do not route plain URL-reading or simple public-web discovery through {alias_list}; reserve them for browser-family compatibility flows."
        )
    return sections


def responses_json_examples(
    *,
    host_platform: HostPlatform,
    available_tool_names: str,
) -> str:
    names = available_tool_name_set(available_tool_names)
    examples: list[str] = []
    if "list_dir" in names:
        examples.append("list current directory files -> /list_dir . --depth 1")
    elif "exec_command" in names:
        examples.append(
            "show current directory -> "
            f"{_exec_command_example(host_platform, host_platform.print_working_dir_command)}"
        )
    if "grep_files" in names:
        examples.append(
            "search workspace for a symbol -> /grep_files 'symbol' --path src --limit 20"
        )
    if "read_file" in names:
        examples.append("read one source slice -> /read_file src/app.py --offset 120 --limit 80")
    if "exec_command" in names:
        examples.append(
            f"python version -> {_exec_command_example(host_platform, host_platform.python_version_command)}"
        )
    if "web_search" in names:
        examples.append("search the web for a current fact -> /web_search 'query' --limit 5")
    if "web_fetch" in names:
        examples.append("read one known URL -> /web_fetch 'https://example.com'")
    if "browser" in names:
        examples.append(
            "open one page in the managed browser -> /browser open --url 'https://example.com'"
        )
    return f"Examples: {'; '.join(examples)}." if examples else ""


def responses_primary_command_list(available_tool_names: str) -> str:
    names = available_tool_name_set(available_tool_names)
    commands: list[str] = []
    if "exec_command" in names:
        commands.append("/exec_command <cmd>")
    if "write_stdin" in names:
        commands.append("/write_stdin <session_id> [chars]")
    if "spawn_agent" in names:
        commands.append('/spawn_agent \'{"task":"..."}\'')
    if "request_orchestration" in names:
        commands.append(
            '/request_orchestration \'{"source_text":"...","goal":"...","reason":"...","needs_confirmation":true}\''
        )
    if "spawn_child_tab" in names:
        commands.append("spawn_child_tab(task=...)")
    if "send_child_tab" in names:
        commands.append("send_child_tab(target=..., message=...)")
    if "wait_child_tasks" in names:
        commands.append("wait_child_tasks(targets=[...])")
    if "request_user_input" in names:
        commands.append("request_user_input(questions=[...])")
    if "AskUserQuestion" in names:
        commands.append("AskUserQuestion(questions=[...])")
    if "apply_patch" in names:
        commands.append("/apply_patch <patch>")
    if "Write" in names:
        commands.append("Write(file_path=..., content=...)")
    if "Edit" in names:
        commands.append("Edit(file_path=..., old_string=..., new_string=..., replace_all=false)")
    if "grep_files" in names:
        commands.append("/grep_files <pattern>")
    if "read_file" in names:
        commands.append("/read_file <file_path>")
    if "list_dir" in names:
        commands.append("/list_dir [dir_path]")
    if "web_search" in names:
        commands.append("/web_search <query>")
    if "web_fetch" in names:
        commands.append("/web_fetch <url>")
    if "browser" in names:
        commands.append("/browser <action> [...]")
    if "Bash" in names:
        commands.append("Bash(command=...)")
    if "PowerShell" in names:
        commands.append("PowerShell(command=...)")
    return f"Primary built-in local commands are {', '.join(commands)}." if commands else ""


def responses_command_guidance_section(
    *,
    available_tool_names: str,
    native_tool_loop: bool = False,
) -> str:
    names = available_tool_name_set(available_tool_names)
    has_bash = "Bash" in names
    has_powershell = "PowerShell" in names
    has_write_stdin = "write_stdin" in names
    has_exec_pair = "exec_command" in names or "write_stdin" in names
    if has_bash or has_powershell:
        prefix = (
            "For command execution, use Bash as the primary command-execution tool."
            if native_tool_loop
            else "For command execution, use Bash as the primary command-execution tool name."
        )
        if has_powershell:
            prefix += " Use PowerShell only when it is also exposed and the command specifically needs Windows PowerShell semantics."
        if has_write_stdin:
            prefix += " Use write_stdin to continue or poll an existing command session."
            prefix += " If you set run_in_background, treat it as an early-return session launch and use write_stdin later when you need more output."
        prefix += " The session cwd is already set from context, so do not prepend cd just to re-enter the current directory."
        prefix += " Use dangerouslyDisableSandbox only when the command genuinely needs escalated execution."
        return f"{prefix} Do not treat shell as the primary tool name."
    if has_exec_pair:
        if native_tool_loop:
            return (
                "For command execution, prefer exec_command and write_stdin. "
                "When the command should run in the current directory or another known directory, set workdir instead of prepending cd. "
                "Do not wrap commands in cd ... && unless shell semantics genuinely require it. "
                "If a write or delete command fails because the workspace is read-only or returns Permission denied, do not keep retrying equivalent write variants in the same turn; summarize the block briefly and stop. "
                "Use shell only as a legacy fallback when that alias is explicitly exposed."
            )
        return (
            "For command execution, prefer exec_command and write_stdin. "
            "When the command should run in the current directory or another known directory, set workdir instead of prepending cd. "
            "Do not wrap commands in cd ... && unless shell semantics genuinely require it. "
            "If a write or delete command fails because the workspace is read-only or returns Permission denied, do not keep retrying equivalent write variants in the same turn; summarize the block briefly and stop. "
            "In slash-command text, prefer /exec_command and /write_stdin. "
            "Use /shell only as a legacy fallback when that alias is explicitly exposed."
        )
    return "Use only the command-execution tools that are actually exposed in this session. Do not invent shell, Bash, or PowerShell names."


def _exec_command_example(host_platform: HostPlatform, command: str) -> str:
    normalized = host_platform.normalize_shell_command(command)
    if not normalized:
        return "/exec_command '' --workdir ."
    return f"/exec_command {shlex.quote(normalized)} --workdir ."


def responses_request_user_input_guidance_sections(available_tool_names: str) -> list[str]:
    names = available_tool_name_set(available_tool_names)
    sections: list[str] = []
    if "request_user_input" in names:
        sections.append(
            "Use request_user_input only when you genuinely need the user to answer one to three short clarification or choice questions before proceeding."
        )
        sections.append(
            "When a structured clarification is necessary, prefer request_user_input over writing a multiple choice question as plain assistant text."
        )
    if "AskUserQuestion" in names:
        sections.append(
            "Use AskUserQuestion only for clarification or concrete user choices that require a real response; do not use it for plan approval, generic proceed confirmations, or narrative status updates."
        )
        sections.append(
            "When a structured clarification is necessary, prefer AskUserQuestion over writing a multiple choice question as plain assistant text."
        )
    return sections


def expert_review_guidance_sections(
    *,
    available_tool_names: str = "",
    available_by_contract: bool = False,
) -> list[str]:
    names = available_tool_name_set(available_tool_names)
    if available_tool_names and "expert_review" not in names:
        return []
    if not available_tool_names and not available_by_contract:
        return []
    return [
        "If expert_review is exposed in this session, use it when the user asks another provider, another model, a second opinion, an external review, or asks someone else to challenge, cross-check, pick apart, or verify the current answer before finalizing it.",
        "Treat requests to have a different provider or model review, challenge, cross-check, verify, or provide a second opinion on the current answer as expert_review triggers when the current mainline work should be reviewed read-only.",
        "Do not use expert_review when the user explicitly says not to re-check, not to call another model, or to answer directly without further review.",
    ]


def claude_code_editing_guidance_sections(*, read_tool_name: str) -> list[str]:
    return [
        f"Before modifying an existing file with Write or Edit, use {read_tool_name} first so the change is grounded in the current file contents.",
        "Use Write for new files or full rewrites. Prefer Edit for targeted changes to existing files.",
        "Use Edit for exact string replacements. Keep old_string to the smallest clearly unique span; it must match exactly once unless replace_all=true.",
        "Do not describe or emit raw apply_patch grammar when the surface exposes Write and Edit instead.",
    ]
