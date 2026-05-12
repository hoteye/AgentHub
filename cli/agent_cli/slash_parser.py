from __future__ import annotations

import shlex
from collections.abc import Iterable
from dataclasses import dataclass

from cli.agent_cli.slash_surface import (
    boolean_keywords,
    compat_normalize_arg_tokens,
    implicit_enum_mappings,
    value_keywords,
)

_RAW_TEXT_LEGACY_COMMANDS = {
    "apply_patch",
    "llm",
    "orchestrate",
    "orchestrate_confirm",
    "plan",
}

_RAW_JSON_LEGACY_COMMANDS = {
    "__request_orchestration",
    "request_user_input",
}


@dataclass(frozen=True, slots=True)
class SlashInvocation:
    source: str
    raw_text: str
    command_name: str
    raw_arg_text: str
    tokens: tuple[str, ...]
    arg_tokens: tuple[str, ...]
    positionals: tuple[str, ...]
    keywords: tuple[tuple[str, str], ...]
    switches: tuple[str, ...]
    extras: tuple[str, ...]
    legacy_compat_used: bool = False


def is_slash_command_text(text: str) -> bool:
    return str(text or "").lstrip().startswith("/")


def slash_name_and_rest(text: str) -> tuple[str, str]:
    raw = str(text or "")
    stripped = raw.lstrip()
    if not stripped.startswith("/"):
        raise ValueError("slash command must start with '/'")
    body = stripped[1:]
    if not body.strip():
        raise ValueError("empty slash command")
    name_chars: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char.isspace():
            break
        name_chars.append(char)
        index += 1
    command_name = "".join(name_chars).strip().lower()
    if not command_name:
        raise ValueError("empty slash command")
    raw_arg_text = body[index:].strip()
    return command_name, raw_arg_text


def split_slash_like_tokens(text_or_name: str) -> tuple[str, ...]:
    raw = str(text_or_name or "").strip()
    if not raw:
        return ()
    if is_slash_command_text(raw):
        try:
            command_name, raw_arg_text = slash_name_and_rest(raw)
        except ValueError:
            return ()
        arg_tokens = tokenize_slash_text(raw_arg_text)
        return (command_name, *arg_tokens)
    return tokenize_slash_text(raw)


def tokenize_slash_text(text: str) -> tuple[str, ...]:
    raw = str(text or "").strip()
    if not raw:
        return ()
    try:
        tokens = shlex.split(raw, posix=True)
    except ValueError:
        tokens = [item for item in raw.split() if item]
    return tuple(str(token) for token in tokens if str(token) != "")


def parse_slash_invocation(text: str, *, source: str = "runtime") -> SlashInvocation:
    command_name, raw_arg_text = slash_name_and_rest(text)
    arg_tokens = tokenize_slash_text(raw_arg_text)
    value_keyword_names = set(value_keywords(command_name))
    boolean_keyword_names = set(boolean_keywords(command_name))
    implicit_keywords = implicit_enum_mappings(command_name)
    positionals: list[str] = []
    keywords: list[tuple[str, str]] = []
    switches: list[str] = []
    extras: list[str] = []
    legacy_compat_used = False
    index = 0
    while index < len(arg_tokens):
        raw_token = str(arg_tokens[index] or "")
        normalized_token = raw_token.strip()
        lowered = normalized_token.lower()
        if not normalized_token:
            index += 1
            continue
        if raw_token.startswith("-"):
            legacy_compat_used = True
        if raw_token.startswith("--"):
            flag_name = lowered[2:]
            if flag_name in value_keyword_names:
                if index + 1 < len(arg_tokens):
                    keywords.append((flag_name, str(arg_tokens[index + 1] or "")))
                    index += 2
                    continue
                extras.append(raw_token)
                index += 1
                continue
            if flag_name in boolean_keyword_names:
                switches.append(flag_name)
                index += 1
                continue
        if lowered in implicit_keywords:
            keyword_name, keyword_value = implicit_keywords[lowered]
            if keyword_value is None:
                switches.append(keyword_name)
            else:
                keywords.append((keyword_name, keyword_value))
            index += 1
            continue
        if lowered in boolean_keyword_names:
            switches.append(lowered)
            index += 1
            continue
        if lowered in value_keyword_names and index + 1 < len(arg_tokens):
            keywords.append((lowered, str(arg_tokens[index + 1] or "")))
            index += 2
            continue
        positionals.append(raw_token)
        index += 1
    return SlashInvocation(
        source=str(source or "runtime").strip() or "runtime",
        raw_text=str(text or ""),
        command_name=command_name,
        raw_arg_text=raw_arg_text,
        tokens=(command_name, *arg_tokens),
        arg_tokens=arg_tokens,
        positionals=tuple(positionals),
        keywords=tuple(keywords),
        switches=tuple(switches),
        extras=tuple(extras),
        legacy_compat_used=legacy_compat_used,
    )


def legacy_handler_arg_text(invocation: SlashInvocation) -> str:
    if invocation.command_name in _RAW_TEXT_LEGACY_COMMANDS:
        return invocation.raw_arg_text
    if invocation.command_name in _RAW_JSON_LEGACY_COMMANDS:
        raw_arg_text = invocation.raw_arg_text.strip()
        if raw_arg_text.startswith(("{", "[")):
            return raw_arg_text
    normalized = compat_normalize_arg_tokens(invocation.command_name, invocation.arg_tokens)
    if not normalized:
        return ""
    return shlex.join(list(normalized))


def legacy_handler_argv(invocation: SlashInvocation) -> tuple[str, ...]:
    return tuple(compat_normalize_arg_tokens(invocation.command_name, invocation.arg_tokens))


def slash_keyword_map(invocation: SlashInvocation) -> dict[str, str]:
    merged: dict[str, str] = {}
    for key, value in invocation.keywords:
        normalized_key = str(key or "").strip().lower()
        if normalized_key:
            merged[normalized_key] = str(value or "")
    return merged


def slash_switch_set(invocation: SlashInvocation) -> set[str]:
    return {
        str(item or "").strip().lower() for item in invocation.switches if str(item or "").strip()
    }


def iter_slash_positionals(invocation: SlashInvocation) -> Iterable[str]:
    return tuple(invocation.positionals)
