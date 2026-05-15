from __future__ import annotations

import re
import shlex
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent

EXPLORE_AGENT_TYPE = "Explore"

EXPLORE_WHEN_TO_USE = (
    "Fast agent specialized for exploring codebases. Use this when you need to quickly find files by patterns "
    '(for example, "src/components/**/*.tsx"), search code for keywords (for example, "API endpoints"), or answer '
    'questions about the codebase (for example, "how do API endpoints work?"). When calling this agent, specify the '
    'desired thoroughness level: "quick" for basic searches, "medium" for moderate exploration, or "very thorough" '
    "for comprehensive analysis across multiple locations and naming conventions."
)

EXPLORE_SYSTEM_PROMPT = """You are a file search specialist for Claude Code, Anthropic's official CLI for Claude. You excel at thoroughly navigating and exploring codebases.

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

EXPLORE_MODEL = "claude_haiku_45"

EXPLORE_DISALLOWED_TOOLS = (
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
)

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


def explore_profile_kwargs() -> dict[str, Any]:
    return {
        "agent_type": EXPLORE_AGENT_TYPE,
        "when_to_use": EXPLORE_WHEN_TO_USE,
        "model": EXPLORE_MODEL,
        "disallowed_tools": EXPLORE_DISALLOWED_TOOLS,
        "system_prompt": EXPLORE_SYSTEM_PROMPT,
    }


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
    def __init__(self, wrapped: Any, *, profile: Any) -> None:
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
