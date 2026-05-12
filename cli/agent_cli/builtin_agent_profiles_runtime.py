from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent

EXPLORE_AGENT_TYPE = "Explore"


@dataclass(frozen=True)
class BuiltinAgentProfile:
    agent_type: str
    when_to_use: str
    disallowed_tools: tuple[str, ...]
    system_prompt: str
    source: str = "built-in"
    model: str = "inherit"
    fresh_context: bool = True


_EXPLORE_WHEN_TO_USE = (
    "Fast agent specialized for exploring codebases. Use this when you need to quickly find files by patterns "
    '(for example, "src/components/**/*.tsx"), search code for keywords (for example, "API endpoints"), or answer '
    'questions about the codebase (for example, "how do API endpoints work?"). When calling this agent, specify the '
    'desired thoroughness level: "quick" for basic searches, "medium" for moderate exploration, or "very thorough" '
    "for comprehensive analysis across multiple locations and naming conventions."
)

_EXPLORE_SYSTEM_PROMPT = """You are a file search specialist for Claude Code, Anthropic's official CLI for Claude. You excel at thoroughly navigating and exploring codebases.

=== CRITICAL: READ-ONLY MODE - NO FILE MODIFICATIONS ===
This is a READ-ONLY exploration task. You are STRICTLY PROHIBITED from:
- Creating new files (no Write, touch, or file creation of any kind)
- Modifying existing files (no Edit operations)
- Deleting files (no rm or deletion)
- Moving or copying files (no mv or cp)
- Creating temporary files anywhere, including /tmp
- Using redirect operators (>, >>, |) or heredocs to write to files
- Running ANY commands that change system state

Your role is EXCLUSIVELY to search and analyze existing code. You do NOT have access to file editing tools - attempting to edit files will fail.

Your strengths:
- Rapidly finding files using glob patterns
- Searching code and text with powerful regex patterns
- Reading and analyzing file contents

Guidelines:
- Use Glob for broad file pattern matching
- Use Grep for searching file contents with regex
- Use Read when you know the specific file path you need to read
- Use Bash ONLY for read-only operations (ls, git status, git log, git diff, find, grep, cat, head, tail)
- NEVER use Bash for: mkdir, touch, rm, cp, mv, git add, git commit, npm install, pip install, or any file creation/modification
- Adapt your search approach based on the thoroughness level specified by the caller
- Communicate your final report directly as a regular message - do NOT attempt to create files

NOTE: You are meant to be a fast agent that returns output as quickly as possible. In order to achieve this you must:
- Make efficient use of the tools that you have at your disposal: be smart about how you search for files and implementations
- Wherever possible you should try to spawn multiple parallel tool calls for grepping and reading files

Complete the user's search request efficiently and report your findings clearly."""

_EXPLORE_PROFILE = BuiltinAgentProfile(
    agent_type=EXPLORE_AGENT_TYPE,
    when_to_use=_EXPLORE_WHEN_TO_USE,
    model="claude_haiku_45",
    disallowed_tools=(
        "Agent",
        "SendMessage",
        "Write",
        "Edit",
        "AskUserQuestion",
        "apply_patch",
        "spawn_agent",
        "send_input",
        "resume_agent",
        "wait_agent",
        "agent_workflow",
        "recover_agent",
        "close_agent",
        "request_orchestration",
        "request_user_input",
        "update_plan",
        "write_stdin",
        "office_run",
    ),
    system_prompt=_EXPLORE_SYSTEM_PROMPT,
)

_PROFILES = {EXPLORE_AGENT_TYPE.lower(): _EXPLORE_PROFILE}

_READ_ONLY_SLASH_COMMANDS = frozenset(
    {
        "list_dir",
        "glob_files",
        "grep_files",
        "read_file",
        "exec_command",
        "web_search",
        "web_fetch",
        "browser",
        "mcp_resource",
        "office_skills",
    }
)
_MUTATING_SLASH_COMMANDS = frozenset(
    {
        "apply_patch",
        "spawn_agent",
        "send_input",
        "resume_agent",
        "close_agent",
        "recover_agent",
        "update_plan",
        "request_user_input",
        "write_stdin",
        "mcp_tool_call",
        "office_run",
    }
)
_SHELL_WRITE_OR_SEQUENCE_PATTERN = re.compile(r"(>>|>|<<?|;)")
_SHELL_PIPE_OR_AND_TOKENS = {"|", "&&", "||"}
_SAFE_STDERR_REDIRECT_PATTERN = re.compile(r"(^|\s)2\s*>\s*(?:/dev/null|&1)(?=\s|$)")
_MUTATING_SHELL_COMMANDS = frozenset(
    {
        "cat >",
        "chmod",
        "chown",
        "cp",
        "curl",
        "dd",
        "install",
        "ln",
        "mkdir",
        "mv",
        "npm",
        "pnpm",
        "pip",
        "python -m pip",
        "rm",
        "tee",
        "touch",
        "truncate",
        "uv",
        "yarn",
    }
)
_READ_ONLY_GIT_SUBCOMMANDS = frozenset(
    {
        "branch",
        "diff",
        "grep",
        "log",
        "ls-files",
        "rev-parse",
        "show",
        "status",
    }
)


def builtin_agent_profiles() -> tuple[BuiltinAgentProfile, ...]:
    return tuple(_PROFILES.values())


def normalize_subagent_type(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    profile = _PROFILES.get(text.lower())
    return profile.agent_type if profile is not None else ""


def builtin_agent_profile(value: Any) -> BuiltinAgentProfile | None:
    normalized = normalize_subagent_type(value)
    return _PROFILES.get(normalized.lower()) if normalized else None


def agent_tools_description(profile: BuiltinAgentProfile) -> str:
    if not profile.disallowed_tools:
        return "All tools"
    return "All tools except " + ", ".join(profile.disallowed_tools)


def format_agent_line(profile: BuiltinAgentProfile) -> str:
    return (
        f"- {profile.agent_type}: {profile.when_to_use} (Tools: {agent_tools_description(profile)})"
    )


def agent_listing_text() -> str:
    return "\n".join(format_agent_line(profile) for profile in builtin_agent_profiles())


def claude_agent_tool_description() -> str:
    return """Launch a new agent to handle complex, multi-step tasks autonomously.

The Agent tool launches specialized agents (subprocesses) that autonomously handle complex tasks. Each agent type has specific capabilities and tools available to it.

Available agent types are listed in <system-reminder> messages in the conversation.

When using the Agent tool, specify a subagent_type parameter to select which agent type to use. If omitted, the general-purpose agent is used.

When NOT to use the Agent tool:
- If you want to read a specific file path, use the Read tool or the Glob tool instead of the Agent tool, to find the match more quickly
- If you are searching for a specific class definition like "class Foo", use the Glob tool instead, to find the match more quickly
- If you are searching for code within a specific file or set of 2-3 files, use the Read tool instead of the Agent tool, to find the match more quickly
- Other tasks that are not related to the agent descriptions above

Usage notes:
- Always include a short description (3-5 words) summarizing what the agent will do
- When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
- You can optionally run agents in the background using the run_in_background parameter. When an agent runs in the background, you will be automatically notified when it completes - do NOT sleep, poll, or proactively check on its progress. Continue with other work or respond to the user instead.
- Foreground vs background: Use foreground (default) when you need the agent's results before you can proceed - for example, research agents whose findings inform your next steps. Use background when you have genuinely independent work to do in parallel.
- To continue a previously spawned agent, use SendMessage with the agent's ID or name as the to field. The agent resumes with its full context preserved. Each Agent invocation starts fresh - provide a complete task description.
- The agent's outputs should generally be trusted
- Clearly tell the agent whether you expect it to write code or just to do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent
- If the agent description mentions that it should be used proactively, then you should try your best to use it without the user having to ask for it first. Use your judgement.
- If the user specifies that they want you to run agents "in parallel", you MUST send a single message with multiple Agent tool use content blocks.

## Writing the prompt

Brief the agent like a smart colleague who just walked into the room - it hasn't seen this conversation, doesn't know what you've tried, doesn't understand why this task matters.
- Explain what you're trying to accomplish and why.
- Describe what you've already learned or ruled out.
- Give enough context about the surrounding problem that the agent can make judgment calls rather than just following a narrow instruction.
- If you need a short response, say so ("report in under 200 words").
- For user-facing overviews or capability summaries, ask for a concise report with an explicit length bound unless the user requested exhaustive analysis.
- Write the Agent tool description and prompt in English. Summarize the result for the user in your own final response.
- Lookups: hand over the exact command. Investigations: hand over the question - prescribed steps become dead weight when the premise is wrong.

Terse command-style prompts produce shallow, generic work.

Never delegate understanding. Don't write "based on your findings, fix the bug" or "based on the research, implement it." Those phrases push synthesis onto the agent instead of doing it yourself. Write prompts that prove you understood: include file paths, line numbers, what specifically to change."""


def _message_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def agent_listing_system_reminder_text() -> str:
    return (
        "<system-reminder>\n"
        "Available agent types for the Agent tool:\n"
        f"{agent_listing_text()}\n"
        "</system-reminder>"
    )


def agent_listing_input_item() -> dict[str, Any]:
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": agent_listing_system_reminder_text()}],
    }


def with_agent_listing_input_item(
    input_items: list[dict[str, Any]] | None,
    *,
    tool_surface_profile: Any,
) -> list[dict[str, Any]]:
    normalized_profile = str(tool_surface_profile or "").strip().lower()
    items = [dict(item) for item in list(input_items or []) if isinstance(item, dict)]
    if normalized_profile != "claude_code":
        return items
    if any("Available agent types for the Agent tool:" in _message_text(item) for item in items):
        return items
    return [agent_listing_input_item(), *items]


def profile_instruction_items(subagent_type: Any) -> list[dict[str, Any]]:
    profile = builtin_agent_profile(subagent_type)
    if profile is None:
        return []
    return [
        {
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": profile.system_prompt}],
        }
    ]


def profile_system_prompt(subagent_type: Any) -> str:
    profile = builtin_agent_profile(subagent_type)
    return str(profile.system_prompt or "") if profile is not None else ""


def without_profile_instruction_items(
    input_items: list[dict[str, Any]] | None,
    *,
    subagent_type: Any,
) -> list[dict[str, Any]]:
    profile_prompt = profile_system_prompt(subagent_type).strip()
    items = [dict(item) for item in list(input_items or []) if isinstance(item, dict)]
    if not profile_prompt:
        return items
    return [item for item in items if _message_text(item).strip() != profile_prompt]


def profile_uses_fresh_context(subagent_type: Any) -> bool:
    profile = builtin_agent_profile(subagent_type)
    return bool(profile and profile.fresh_context)


def profile_default_model_selector(subagent_type: Any) -> str:
    profile = builtin_agent_profile(subagent_type)
    model = str(profile.model or "").strip() if profile is not None else ""
    return "" if model.lower() in {"", "inherit"} else model


def profile_needs_environment_context(subagent_type: Any) -> bool:
    return builtin_agent_profile(subagent_type) is not None


def profile_disallows_tool(subagent_type: Any, tool_name: str) -> bool:
    profile = builtin_agent_profile(subagent_type)
    normalized = str(tool_name or "").strip()
    if profile is None or not normalized:
        return False
    return normalized in set(profile.disallowed_tools)


def _spec_tool_name(spec: dict[str, Any]) -> str:
    name = str(spec.get("name") or "").strip()
    if name:
        return name
    function_block = spec.get("function")
    if isinstance(function_block, dict):
        return str(function_block.get("name") or "").strip()
    return ""


def filter_tool_specs_for_profile(
    tool_specs: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    subagent_type: Any,
) -> list[dict[str, Any]]:
    profile = builtin_agent_profile(subagent_type)
    specs = [dict(item) for item in list(tool_specs or []) if isinstance(item, dict)]
    if profile is None:
        return specs
    disallowed = set(profile.disallowed_tools)
    return [spec for spec in specs if _spec_tool_name(spec) not in disallowed]


def profiled_tool_executor(tool_executor: Any, *, subagent_type: Any) -> Any:
    profile = builtin_agent_profile(subagent_type)
    if profile is None:
        return tool_executor
    return ReadOnlyProfileToolExecutor(tool_executor, profile=profile)


def _slash_command_name(command_text: str) -> str:
    try:
        parts = shlex.split(str(command_text or ""), posix=True)
    except ValueError:
        parts = [part for part in str(command_text or "").split() if part]
    if not parts:
        return ""
    return parts[0].lstrip("/").strip()


def _exec_shell_command(command_text: str) -> str:
    try:
        parts = shlex.split(str(command_text or ""), posix=True)
    except ValueError:
        return ""
    if len(parts) < 2 or parts[0].lstrip("/") != "exec_command":
        return ""
    return str(parts[1] or "").strip()


def _shell_command_tokens(shell_command: str) -> list[str]:
    lexer = shlex.shlex(str(shell_command or "").strip(), posix=True, punctuation_chars="|&;<>")
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return []


def _shell_command_segment_denial(parts: list[str]) -> str:
    if not parts:
        return "empty shell command segment"
    first = str(parts[0] or "").strip()
    second = str(parts[1] or "").strip() if len(parts) > 1 else ""
    joined_prefix = f"{first} {second}".strip()
    if first == "git":
        if second in _READ_ONLY_GIT_SUBCOMMANDS:
            return ""
        return f"git {second or '<missing>'} is not allowed in Explore read-only mode"
    if joined_prefix in _MUTATING_SHELL_COMMANDS or first in _MUTATING_SHELL_COMMANDS:
        return f"{joined_prefix if joined_prefix in _MUTATING_SHELL_COMMANDS else first} is not allowed in Explore read-only mode"
    if first == "sed" and "-i" in parts:
        return "sed -i is not allowed in Explore read-only mode"
    return ""


def _shell_command_denial(shell_command: str) -> str:
    normalized = " ".join(str(shell_command or "").strip().split())
    if not normalized:
        return "empty shell command"
    inspectable = _SAFE_STDERR_REDIRECT_PATTERN.sub(" ", normalized)
    if _SHELL_WRITE_OR_SEQUENCE_PATTERN.search(inspectable):
        return "shell redirection or command sequencing is not allowed in Explore read-only mode"
    parts = _shell_command_tokens(inspectable)
    if not parts:
        return "unable to parse shell command in Explore read-only mode"
    segment: list[str] = []
    for token in parts:
        if token in _SHELL_PIPE_OR_AND_TOKENS:
            denial = _shell_command_segment_denial(segment)
            if denial:
                return denial
            segment = []
            continue
        segment.append(token)
    denial = _shell_command_segment_denial(segment)
    if denial:
        return denial
    return ""


def read_only_profile_denial(command_text: str) -> str:
    command_name = _slash_command_name(command_text)
    if not command_name:
        return "empty tool command"
    if command_name in _MUTATING_SLASH_COMMANDS:
        return f"/{command_name} is not allowed in Explore read-only mode"
    if command_name not in _READ_ONLY_SLASH_COMMANDS:
        return f"/{command_name} is not available in Explore read-only mode"
    if command_name == "exec_command":
        return _shell_command_denial(_exec_shell_command(command_text))
    return ""


class ReadOnlyProfileToolExecutor:
    def __init__(self, wrapped: Any, *, profile: BuiltinAgentProfile) -> None:
        self._wrapped = wrapped
        self.profile = profile
        self.runtime_owner = getattr(wrapped, "runtime_owner", None)

    def __call__(self, text: str) -> tuple[str, list[ToolEvent]]:
        result = self.run_structured(text)
        return str(result.assistant_text or ""), list(result.tool_events or [])

    def run_structured(self, text: str) -> CommandExecutionResult:
        denial = read_only_profile_denial(text)
        if denial:
            event = ToolEvent(
                name="delegated_agent_profile",
                ok=False,
                summary=denial,
                payload={
                    "ok": False,
                    "subagent_type": self.profile.agent_type,
                    "reason_code": "explore_read_only_denied",
                    "command": str(text or ""),
                    "error": denial,
                },
            )
            return CommandExecutionResult(assistant_text=denial, tool_events=[event])
        runner = getattr(self._wrapped, "run_structured", None)
        if callable(runner):
            return runner(text)
        assistant_text, events = self._wrapped(text)
        return CommandExecutionResult(
            assistant_text=str(assistant_text or ""),
            tool_events=list(events or []),
        )

    def interrupt_requested(self) -> bool:
        checker = getattr(self._wrapped, "interrupt_requested", None)
        return bool(checker()) if callable(checker) else False

    def interrupt_result(self) -> tuple[str, list[ToolEvent]]:
        getter = getattr(self._wrapped, "interrupt_result", None)
        if callable(getter):
            assistant_text, events = getter()
            return str(assistant_text or ""), list(events or [])
        return "", []
