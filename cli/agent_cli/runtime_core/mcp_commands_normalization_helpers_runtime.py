from __future__ import annotations

import shlex
from typing import Any, Callable

from cli.agent_cli.slash_parser import SlashInvocation, parse_slash_invocation, slash_keyword_map, slash_switch_set


def slash_parsed_args(slash_invocation: SlashInvocation | None) -> tuple[list[str], dict[str, Any]] | None:
    if slash_invocation is None:
        return None
    options: dict[str, Any] = dict(slash_keyword_map(slash_invocation))
    for switch_name in slash_switch_set(slash_invocation):
        options[switch_name] = True
    return [str(item) for item in slash_invocation.positionals], options


def first_slash_positional(slash_invocation: SlashInvocation | None) -> str:
    slash_args = slash_parsed_args(slash_invocation)
    if slash_args is None:
        return ""
    positionals, _ = slash_args
    return str(positionals[0] if positionals else "").strip()


def parse_generic_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
    try:
        tokens = shlex.split(str(arg_text or ""), posix=True)
    except ValueError:
        tokens = [item for item in str(arg_text or "").split() if item]
    positionals: list[str] = []
    options: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        token = str(tokens[index] or "").strip()
        if token.startswith("--"):
            key = token[2:]
            if index + 1 < len(tokens) and not str(tokens[index + 1] or "").strip().startswith("--"):
                options[key] = str(tokens[index + 1] or "").strip()
                index += 2
                continue
            options[key] = True
            index += 1
            continue
        positionals.append(token)
        index += 1
    return positionals, options


def parse_args(
    runtime: Any,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[list[str], dict[str, Any]]:
    slash_args = slash_parsed_args(slash_invocation)
    if slash_args is not None:
        return slash_args
    parse_args_fn = getattr(runtime, "_parse_args", None)
    if callable(parse_args_fn):
        return parse_args_fn(arg_text)
    return parse_generic_args(arg_text)


def parse_args_callback(
    slash_invocation: SlashInvocation | None,
) -> Callable[[Any, str], tuple[list[str], dict[str, Any]]]:
    def _parse(runtime: Any, arg_text: str) -> tuple[list[str], dict[str, Any]]:
        return parse_args(runtime, arg_text, slash_invocation=slash_invocation)

    return _parse


def parse_mcp_arg(
    runtime: Any,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, str]:
    slash_args = slash_parsed_args(slash_invocation)
    if slash_args is not None:
        positionals, _ = slash_args
    else:
        positionals, _ = parse_args(runtime, arg_text)
    action = str(positionals[0] if positionals else "").strip().lower()
    target = " ".join(str(item) for item in positionals[1:]).strip()
    return action, target


def command_target(arg_text: str, slash_invocation: SlashInvocation | None) -> str:
    return first_slash_positional(slash_invocation) or str(arg_text or "").strip()


def subcommand_arg_text(arg_text: str, action: str) -> str:
    text = str(arg_text or "").strip()
    if not text:
        return ""
    lower_text = text.lower()
    lower_action = str(action or "").strip().lower()
    if not lower_action:
        return text
    prefix = f"{lower_action} "
    if lower_text == lower_action:
        return ""
    if lower_text.startswith(prefix):
        return text[len(prefix) :]
    return text


def subcommand_slash_invocation(
    slash_invocation: SlashInvocation | None,
    *,
    command_name: str,
) -> SlashInvocation | None:
    if slash_invocation is None:
        return None
    arg_tokens = [str(item) for item in slash_invocation.arg_tokens]
    if not arg_tokens:
        return None
    remaining_tokens = arg_tokens[1:]
    raw_text = f"/{command_name}"
    if remaining_tokens:
        raw_text += " " + shlex.join(remaining_tokens)
    return parse_slash_invocation(raw_text, source=slash_invocation.source)
