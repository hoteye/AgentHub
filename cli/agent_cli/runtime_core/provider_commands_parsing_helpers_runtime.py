from __future__ import annotations

import shlex
from typing import Any, Callable

from cli.agent_cli.slash_parser import SlashInvocation


def parse_flag_args(
    arg_text: str,
    *,
    value_flags: set[str],
    boolean_flags: set[str],
) -> tuple[list[str], dict[str, Any]]:
    if not arg_text:
        return [], {}
    tokens = shlex.split(str(arg_text), posix=True)
    positionals: list[str] = []
    options: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        token = str(tokens[index] or "").strip()
        if token in value_flags:
            if index + 1 >= len(tokens):
                break
            options[token[2:]] = str(tokens[index + 1] or "").strip()
            index += 2
            continue
        if token in boolean_flags:
            options[token[2:]] = True
            index += 1
            continue
        positionals.append(token)
        index += 1
    return positionals, options


def parse_generic_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
    if not arg_text:
        return [], {}
    tokens = shlex.split(str(arg_text), posix=True)
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


def slash_invocation_inputs(
    slash_invocation: SlashInvocation | None,
    *,
    slash_keyword_map_fn: Callable[[SlashInvocation], dict[str, Any]],
    slash_switch_set_fn: Callable[[SlashInvocation], set[str]],
) -> tuple[list[str], list[str], dict[str, Any], list[str]] | None:
    if slash_invocation is None:
        return None
    raw_tokens = [str(item) for item in slash_invocation.arg_tokens]
    positionals = [str(item) for item in slash_invocation.positionals]
    options: dict[str, Any] = dict(slash_keyword_map_fn(slash_invocation))
    for switch_name in slash_switch_set_fn(slash_invocation):
        options[switch_name] = True
    extras = [str(item) for item in slash_invocation.extras]
    return raw_tokens, positionals, options, extras


def model_inputs_from_source(
    runtime: Any,
    *,
    command_name: str,
    arg_text: str,
    slash_invocation: SlashInvocation | None,
    compat_normalize_arg_tokens_fn: Callable[[str, list[str]], list[str]],
    parse_generic_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]],
) -> tuple[list[str], dict[str, Any], list[str]]:
    if slash_invocation is not None:
        normalized_tokens = list(compat_normalize_arg_tokens_fn(command_name, slash_invocation.arg_tokens))
        normalized_arg_text = shlex.join(normalized_tokens) if normalized_tokens else ""
        positionals, options = parse_generic_args_fn(normalized_arg_text)
        return positionals, options, [str(item) for item in slash_invocation.extras]
    parser = getattr(runtime, "_parse_args", None)
    if callable(parser):
        positionals, options = parser(arg_text)
    else:
        positionals, options = parse_generic_args_fn(arg_text)
    return list(positionals), dict(options or {}), []


def normalized_selection_write_scope(
    value: Any,
    *,
    default: str,
    valid_scopes: set[str],
) -> str:
    normalized = str(value or "").strip().lower() or default
    if normalized not in valid_scopes:
        raise ValueError(normalized or "-")
    return normalized


def selection_write_path(status: dict[str, Any], *, write_scope: str) -> str:
    if write_scope == "user":
        return str(status.get("provider_selection_path") or "").strip()
    if write_scope == "project":
        return str(status.get("provider_config_path") or "").strip()
    return ""


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


__all__ = [
    "is_truthy",
    "model_inputs_from_source",
    "normalized_selection_write_scope",
    "parse_flag_args",
    "parse_generic_args",
    "safe_int",
    "selection_write_path",
    "slash_invocation_inputs",
]
