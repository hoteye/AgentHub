from __future__ import annotations

from typing import Any

from cli.agent_cli.slash_parser import SlashInvocation

from .mcp_commands_normalization_helpers_runtime import (
    command_target,
    parse_mcp_arg,
    subcommand_arg_text,
    subcommand_slash_invocation,
)
from .mcp_commands_projection_helpers_runtime import (
    handle_mcp_auth,
    handle_mcp_channel,
    handle_mcp_inspect,
    handle_mcp_list,
    handle_mcp_mutation,
    handle_mcp_permission,
    handle_mcp_resource,
    handle_mcp_tool_call,
)


def handle_mcp_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]] | None:
    if name == "mcp":
        action, target = parse_mcp_arg(runtime, arg_text, slash_invocation=slash_invocation)
        if action in {"", "list"}:
            return handle_mcp_list(runtime)
        if action == "inspect":
            if not target:
                return ("Usage: /mcp inspect <server>", [])
            return handle_mcp_inspect(runtime, target)
        if action == "auth":
            return handle_mcp_auth(
                runtime,
                subcommand_arg_text(arg_text, action),
                mode_hint="",
                slash_invocation=subcommand_slash_invocation(slash_invocation, command_name="mcp_auth"),
            )
        if action == "auth_callback":
            return handle_mcp_auth(
                runtime,
                subcommand_arg_text(arg_text, action),
                mode_hint="callback",
                slash_invocation=subcommand_slash_invocation(slash_invocation, command_name="mcp_auth_callback"),
            )
        if action == "auth_clear":
            return handle_mcp_auth(
                runtime,
                subcommand_arg_text(arg_text, action),
                mode_hint="clear",
                slash_invocation=subcommand_slash_invocation(slash_invocation, command_name="mcp_auth_clear"),
            )
        if action == "channel":
            return handle_mcp_channel(
                runtime,
                subcommand_arg_text(arg_text, action),
                slash_invocation=subcommand_slash_invocation(slash_invocation, command_name="mcp"),
            )
        if action == "permission":
            return handle_mcp_permission(
                runtime,
                subcommand_arg_text(arg_text, action),
                slash_invocation=subcommand_slash_invocation(slash_invocation, command_name="mcp"),
            )
        if action in {"reconnect", "enable", "disable"}:
            if not target:
                return (f"Usage: /mcp {action} <server|all>", [])
            return handle_mcp_mutation(runtime, action, target)
        return ("Usage: /mcp [list|inspect|reconnect|enable|disable|auth|channel|permission] ...", [])
    if name == "mcp_reconnect":
        target = command_target(arg_text, slash_invocation)
        if not target:
            return ("Usage: /mcp_reconnect <server|all>", [])
        return handle_mcp_mutation(runtime, "reconnect", target)
    if name == "mcp_enable":
        target = command_target(arg_text, slash_invocation)
        if not target:
            return ("Usage: /mcp_enable <server|all>", [])
        return handle_mcp_mutation(runtime, "enable", target)
    if name == "mcp_disable":
        target = command_target(arg_text, slash_invocation)
        if not target:
            return ("Usage: /mcp_disable <server|all>", [])
        return handle_mcp_mutation(runtime, "disable", target)
    if name == "mcp_inspect":
        target = command_target(arg_text, slash_invocation)
        if not target:
            return ("Usage: /mcp_inspect <server>", [])
        return handle_mcp_inspect(runtime, target)
    if name == "mcp_auth":
        return handle_mcp_auth(runtime, arg_text, mode_hint="", slash_invocation=slash_invocation)
    if name == "mcp_auth_callback":
        return handle_mcp_auth(runtime, arg_text, mode_hint="callback", slash_invocation=slash_invocation)
    if name == "mcp_auth_clear":
        return handle_mcp_auth(runtime, arg_text, mode_hint="clear", slash_invocation=slash_invocation)
    if name == "mcp_resource":
        return handle_mcp_resource(runtime, arg_text, slash_invocation=slash_invocation)
    if name == "mcp_tool_call":
        return handle_mcp_tool_call(runtime, arg_text, slash_invocation=slash_invocation)
    return None
