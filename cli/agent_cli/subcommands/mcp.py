from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass
from typing import Any, Sequence, TextIO

TOP_LEVEL_USAGE = "Usage: agenthub mcp <list|inspect|reconnect|enable|disable|auth|channel|permission|resource|tool-call> [args]"
SUBCOMMAND_USAGES = {
    "list": "Usage: agenthub mcp list",
    "inspect": "Usage: agenthub mcp inspect <server>",
    "reconnect": "Usage: agenthub mcp reconnect <server|all>",
    "enable": "Usage: agenthub mcp enable <server|all>",
    "disable": "Usage: agenthub mcp disable <server|all>",
    "auth": "Usage: agenthub mcp auth [set|callback|clear] [args]",
    "channel": "Usage: agenthub mcp channel [list] [args]",
    "permission": "Usage: agenthub mcp permission <list|respond> [args]",
    "resource": "Usage: agenthub mcp resource <list|read> [args]",
    "tool-call": "Usage: agenthub mcp tool-call --projected-name <name> [--arguments-json <json>]",
}
_MUTATION_ACTIONS = frozenset({"reconnect", "enable", "disable"})
_MCP_NESTED_ACTIONS = frozenset({"auth", "channel", "permission"})
_SLASH_BRIDGE_ACTIONS = {
    "resource": "/mcp_resource",
    "tool-call": "/mcp_tool_call",
    "tool_call": "/mcp_tool_call",
}


@dataclass(frozen=True)
class McpCommandParseResult:
    command_text: str | None
    usage_text: str | None


def parse_mcp_subcommand(argv: Sequence[str] | None) -> McpCommandParseResult:
    args = _normalize_args(argv)
    if not args:
        return McpCommandParseResult(command_text=None, usage_text=TOP_LEVEL_USAGE)

    action = str(args[0] or "").strip().lower()
    if action == "list":
        if len(args) != 1:
            return McpCommandParseResult(command_text=None, usage_text=SUBCOMMAND_USAGES["list"])
        return McpCommandParseResult(command_text="/mcp list", usage_text=None)

    if action == "inspect":
        if len(args) != 2:
            return McpCommandParseResult(command_text=None, usage_text=SUBCOMMAND_USAGES["inspect"])
        server_name = shlex.quote(str(args[1] or ""))
        return McpCommandParseResult(command_text=f"/mcp inspect {server_name}", usage_text=None)

    if action in _MUTATION_ACTIONS:
        if len(args) != 2:
            return McpCommandParseResult(command_text=None, usage_text=SUBCOMMAND_USAGES[action])
        target = shlex.quote(str(args[1] or ""))
        return McpCommandParseResult(command_text=f"/mcp {action} {target}", usage_text=None)

    if action in _MCP_NESTED_ACTIONS:
        return _build_passthrough_parse_result(prefix=f"/mcp {action}", trailing_args=args[1:])

    slash_prefix = _SLASH_BRIDGE_ACTIONS.get(action)
    if slash_prefix is not None:
        return _build_passthrough_parse_result(prefix=slash_prefix, trailing_args=args[1:])

    return McpCommandParseResult(command_text=None, usage_text=TOP_LEVEL_USAGE)


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime: Any | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    del stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr

    parsed = parse_mcp_subcommand(argv)
    if parsed.command_text is None:
        print(parsed.usage_text or TOP_LEVEL_USAGE, file=error_stream)
        return 2

    runner = runtime or _build_runtime()
    try:
        response = runner.handle_prompt(parsed.command_text)
    except Exception as exc:
        print(f"mcp error: {exc}", file=error_stream)
        return 1

    assistant_text = str(getattr(response, "assistant_text", "") or "")
    if assistant_text:
        print(assistant_text, file=output_stream)
    return 0


def run(
    argv: Sequence[str] | None = None,
    *,
    runtime: Any | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    return main(
        argv,
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )


def run_mcp_subcommand(
    argv: Sequence[str] | None = None,
    *,
    runtime: Any | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    return main(
        argv,
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )


def _normalize_args(argv: Sequence[str] | None) -> list[str]:
    args = [str(item or "").strip() for item in list(argv or [])]
    if args and args[0] == "mcp":
        return args[1:]
    return args


def _build_passthrough_parse_result(prefix: str, trailing_args: Sequence[str]) -> McpCommandParseResult:
    surfaced_args = [
        str(item or "").strip()[2:] if str(item or "").strip().startswith("--") else str(item or "").strip()
        for item in trailing_args
    ]
    suffix = " ".join(shlex.quote(str(item or "")) for item in surfaced_args if str(item or "").strip())
    if suffix:
        return McpCommandParseResult(command_text=f"{prefix} {suffix}", usage_text=None)
    return McpCommandParseResult(command_text=prefix, usage_text=None)


def _build_runtime() -> Any:
    from cli.agent_cli.runtime import AgentCliRuntime

    return AgentCliRuntime()
