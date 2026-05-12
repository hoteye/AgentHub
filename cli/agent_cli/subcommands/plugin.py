from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass
from typing import Sequence, TextIO

from cli.agent_cli.runtime import AgentCliRuntime


PLUGIN_USAGE = (
    "Usage: agenthub plugin <list|enable|disable|reload|install|remove|uninstall|marketplace> [args]\n"
    "  list\n"
    "  enable <name>\n"
    "  disable <name>\n"
    "  reload\n"
    "  install <zip-or-dir> [--replace] [--scope <user|project|local|managed>]\n"
    "  remove <name> (or uninstall <name>)\n"
    "  marketplace <add|list|remove|update|plugins|install|uninstall|enable|disable> ..."
)


@dataclass(frozen=True)
class PluginCommandResolution:
    ok: bool
    command_text: str = ""


def has_plugin_subcommand_request(argv: Sequence[str] | None) -> bool:
    if argv is None:
        return False
    args = [str(item or "").strip() for item in list(argv)]
    return bool(args) and args[0] == "plugin"


def plugin_usage_text() -> str:
    return PLUGIN_USAGE


def _usage_error() -> PluginCommandResolution:
    return PluginCommandResolution(ok=False)


def _resolve_install_command(args: Sequence[str]) -> PluginCommandResolution:
    plugin_path: str | None = None
    replace = False
    scope: str | None = None
    parsed_args = list(args)
    index = 0
    while index < len(parsed_args):
        token = str(parsed_args[index] or "").strip()
        value = str(token or "").strip()
        if not value:
            return _usage_error()
        if value == "--replace":
            replace = True
            index += 1
            continue
        if value in {"--scope", "--plugin-scope"}:
            if index + 1 >= len(parsed_args):
                return _usage_error()
            scope_value = str(parsed_args[index + 1] or "").strip().lower()
            if scope_value not in {"user", "project", "local", "managed"}:
                return _usage_error()
            scope = scope_value
            index += 2
            continue
        if value.startswith("-"):
            return _usage_error()
        if plugin_path is not None:
            return _usage_error()
        plugin_path = value
        index += 1
    if not plugin_path:
        return _usage_error()
    command_text = f"/plugin_install {shlex.quote(plugin_path)}"
    if replace:
        command_text += " replace"
    if scope:
        command_text += f" scope {shlex.quote(scope)}"
    return PluginCommandResolution(ok=True, command_text=command_text)


def _quote_tokens(tokens: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(item or "").strip()) for item in tokens)


def _resolve_marketplace_command(args: Sequence[str]) -> PluginCommandResolution:
    marketplace_args = [str(item or "").strip() for item in list(args)]
    if not marketplace_args:
        return _usage_error()
    marketplace_action = marketplace_args[0].lower()
    marketplace_action_args = marketplace_args[1:]
    if marketplace_action == "list":
        if len(marketplace_action_args) > 1:
            return _usage_error()
        command_text = "/plugin_marketplace list"
        if marketplace_action_args:
            command_text += f" {shlex.quote(marketplace_action_args[0])}"
        return PluginCommandResolution(ok=True, command_text=command_text)
    if marketplace_action == "remove":
        if len(marketplace_action_args) != 1:
            return _usage_error()
        return PluginCommandResolution(
            ok=True,
            command_text=f"/plugin_marketplace remove {shlex.quote(marketplace_action_args[0])}",
        )
    if marketplace_action == "plugins":
        if marketplace_action_args:
            return _usage_error()
        return PluginCommandResolution(ok=True, command_text="/plugin_marketplace plugins")
    if marketplace_action in {"install", "uninstall", "enable", "disable"}:
        if not marketplace_action_args:
            return _usage_error()
        if marketplace_action in {"uninstall", "enable", "disable"} and len(marketplace_action_args) != 1:
            return _usage_error()
        if marketplace_action == "install":
            plugin_key = str(marketplace_action_args[0] or "").strip()
            trailing = [str(item or "").strip() for item in marketplace_action_args[1:]]
            if any(item not in {"--replace"} for item in trailing):
                return _usage_error()
            command_text = f"/plugin_marketplace install {shlex.quote(plugin_key)}"
            if "--replace" in trailing:
                command_text += " replace"
            return PluginCommandResolution(ok=True, command_text=command_text)
        return PluginCommandResolution(
            ok=True,
            command_text=f"/plugin_marketplace {marketplace_action} {_quote_tokens(marketplace_action_args)}",
        )
    if marketplace_action in {"add", "update"}:
        if not marketplace_action_args:
            return _usage_error()
        plugin_key = str(marketplace_action_args[0] or "").strip()
        trailing = [str(item or "").strip() for item in marketplace_action_args[1:]]
        if marketplace_action == "add":
            if not trailing:
                return _usage_error()
            source_path = str(trailing[0] or "").strip()
            option_tokens = trailing[1:]
            scope: str | None = None
            index = 0
            while index < len(option_tokens):
                token = option_tokens[index]
                if token != "--scope" or index + 1 >= len(option_tokens):
                    return _usage_error()
                scope_value = str(option_tokens[index + 1] or "").strip().lower()
                if scope_value not in {"project", "user"}:
                    return _usage_error()
                scope = scope_value
                index += 2
            command_text = f"/plugin_marketplace add {shlex.quote(plugin_key)} {shlex.quote(source_path)}"
            if scope:
                command_text += f" scope {shlex.quote(scope)}"
            return PluginCommandResolution(ok=True, command_text=command_text)
        path_value: str | None = None
        scope: str | None = None
        index = 0
        while index < len(trailing):
            token = trailing[index]
            if token == "--path" and index + 1 < len(trailing):
                path_value = str(trailing[index + 1] or "").strip()
                index += 2
                continue
            if token == "--scope" and index + 1 < len(trailing):
                scope_value = str(trailing[index + 1] or "").strip().lower()
                if scope_value not in {"project", "user"}:
                    return _usage_error()
                scope = scope_value
                index += 2
                continue
            return _usage_error()
        command_text = f"/plugin_marketplace update {shlex.quote(plugin_key)}"
        if path_value:
            command_text += f" path {shlex.quote(path_value)}"
        if scope:
            command_text += f" scope {shlex.quote(scope)}"
        return PluginCommandResolution(
            ok=True,
            command_text=command_text,
        )
    return _usage_error()


def resolve_plugin_command(argv: Sequence[str]) -> PluginCommandResolution:
    args = [str(item or "").strip() for item in list(argv)]
    if args and args[0] == "plugin":
        args = args[1:]
    if not args:
        return _usage_error()

    action = args[0].lower()
    action_args = args[1:]
    if action == "list":
        return (
            PluginCommandResolution(ok=True, command_text="/plugins")
            if not action_args
            else _usage_error()
        )
    if action == "reload":
        return (
            PluginCommandResolution(ok=True, command_text="/plugin_reload")
            if not action_args
            else _usage_error()
        )
    if action == "enable":
        if len(action_args) != 1:
            return _usage_error()
        return PluginCommandResolution(
            ok=True,
            command_text=f"/plugin_enable {shlex.quote(action_args[0])}",
        )
    if action == "disable":
        if len(action_args) != 1:
            return _usage_error()
        return PluginCommandResolution(
            ok=True,
            command_text=f"/plugin_disable {shlex.quote(action_args[0])}",
        )
    if action in {"remove", "uninstall"}:
        if len(action_args) != 1:
            return _usage_error()
        return PluginCommandResolution(
            ok=True,
            command_text=f"/plugin_remove {shlex.quote(action_args[0])}",
        )
    if action == "install":
        return _resolve_install_command(action_args)
    if action == "marketplace":
        return _resolve_marketplace_command(action_args)
    return _usage_error()


def run_plugin_subcommand(
    argv: Sequence[str] | None = None,
    *,
    runtime: AgentCliRuntime | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    del stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    resolution = resolve_plugin_command(list(argv) if argv is not None else [])
    if not resolution.ok:
        print(plugin_usage_text(), file=error_stream)
        return 2

    runner = runtime or AgentCliRuntime()
    try:
        response = runner.handle_prompt(resolution.command_text)
    except Exception as exc:
        print(f"plugin error: {exc}", file=error_stream)
        return 1

    assistant_text = str(getattr(response, "assistant_text", "") or "")
    if assistant_text.strip():
        print(assistant_text, file=output_stream)
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime: AgentCliRuntime | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    return run_plugin_subcommand(
        argv,
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )
