from __future__ import annotations

import shlex
from typing import Iterable, Sequence

from cli.agent_cli.slash_surface_catalog import (
    BOOLEAN_KEYWORDS as _BOOLEAN_KEYWORDS,
    IMPLICIT_ENUMS as _IMPLICIT_ENUMS,
    LEADING_OPTION_COMMANDS as _LEADING_OPTION_COMMANDS,
    OPTION_VALUES as _OPTION_VALUES,
    RIGHT_BOUNDARY_OPTION_COMMANDS as _RIGHT_BOUNDARY_OPTION_COMMANDS,
    SECOND_POSITION_AS_PATH_COMMANDS as _SECOND_POSITION_AS_PATH_COMMANDS,
    SURFACE_USAGE as _SURFACE_USAGE,
    VALUE_KEYWORDS as _VALUE_KEYWORDS,
)


def surface_usage_text(name: str, fallback: str = "") -> str:
    normalized = str(name or "").strip().lower()
    return _SURFACE_USAGE.get(normalized, str(fallback or "").strip())


def option_keywords(name: str) -> tuple[str, ...]:
    normalized = str(name or "").strip().lower()
    ordered: list[str] = []
    seen: set[str] = set()
    for mapping in (
        _VALUE_KEYWORDS.get(normalized, {}),
        _BOOLEAN_KEYWORDS.get(normalized, {}),
    ):
        for keyword in mapping:
            if keyword in seen:
                continue
            seen.add(keyword)
            ordered.append(keyword)
    return tuple(ordered)


def value_keywords(name: str) -> tuple[str, ...]:
    normalized = str(name or "").strip().lower()
    return tuple(_VALUE_KEYWORDS.get(normalized, {}).keys())


def boolean_keywords(name: str) -> tuple[str, ...]:
    normalized = str(name or "").strip().lower()
    return tuple(_BOOLEAN_KEYWORDS.get(normalized, {}).keys())


def implicit_enum_mappings(name: str) -> dict[str, tuple[str, str | None]]:
    normalized = str(name or "").strip().lower()
    return dict(_IMPLICIT_ENUMS.get(normalized, {}))


def compat_normalize_arg_tokens(name: str, args: Sequence[str]) -> tuple[str, ...]:
    normalized_name = str(name or "").strip().lower()
    return tuple(_normalize_args_for_command(normalized_name, [str(item) for item in args]))


def option_value_choices(name: str, keyword: str) -> tuple[str, ...]:
    normalized_name = str(name or "").strip().lower()
    normalized_keyword = _keyword_name(normalized_name, keyword)
    return _OPTION_VALUES.get((normalized_name, normalized_keyword), ())


def pending_value_keyword(name: str, completed_tokens: Sequence[str]) -> str | None:
    normalized_name = str(name or "").strip().lower()
    if not completed_tokens:
        return None
    last = str(completed_tokens[-1] or "").strip().lower()
    value_keywords = _VALUE_KEYWORDS.get(normalized_name, {})
    if last in value_keywords:
        return last
    if last.startswith("--"):
        legacy = last[2:]
        if legacy in value_keywords.values():
            return legacy
    return None


def normalize_command_text(text: str) -> str:
    raw = str(text or "")
    stripped = raw.lstrip()
    if not stripped.startswith("/"):
        return raw
    try:
        tokens = shlex.split(stripped[1:], posix=True)
    except ValueError:
        return raw
    if not tokens:
        return raw
    command_name = str(tokens[0] or "").strip().lower()
    if not command_name:
        return raw
    args = [str(item) for item in tokens[1:]]
    normalized_args = _normalize_args_for_command(command_name, args)
    if normalized_args == args:
        return raw
    return "/" + shlex.join([command_name, *normalized_args])


def usage_contains_surface_options(usage: str) -> bool:
    return "--" not in str(usage or "")


def surface_commands_with_options() -> Iterable[str]:
    return tuple(sorted(set(_SURFACE_USAGE)))


def _normalize_args_for_command(name: str, args: list[str]) -> list[str]:
    normalized_name = str(name or "").strip().lower()
    if normalized_name in _RIGHT_BOUNDARY_OPTION_COMMANDS:
        return _normalize_tail_options_command(normalized_name, args)
    if normalized_name in _LEADING_OPTION_COMMANDS:
        return _normalize_leading_options_command(normalized_name, args)
    if normalized_name == "model":
        return _normalize_model_command(args)
    if normalized_name == "send_input":
        return _normalize_send_input(args)
    if normalized_name in {"approve", "reject"}:
        return _normalize_note_command(args)
    if normalized_name in _SECOND_POSITION_AS_PATH_COMMANDS:
        return _normalize_office_run(args)
    return _normalize_simple_command(normalized_name, args)


def _normalize_simple_command(name: str, args: list[str]) -> list[str]:
    positionals: list[str] = []
    options: list[str] = []
    value_keywords = _VALUE_KEYWORDS.get(name, {})
    boolean_keywords = _BOOLEAN_KEYWORDS.get(name, {})
    implicit = _IMPLICIT_ENUMS.get(name, {})
    index = 0
    while index < len(args):
        raw_token = str(args[index] or "")
        token = raw_token.strip()
        lower = token.lower()
        if not token:
            index += 1
            continue
        if raw_token.startswith("--"):
            flag_name = lower[2:]
            if flag_name in value_keywords.values():
                options.append(raw_token)
                if index + 1 < len(args):
                    options.append(args[index + 1])
                    index += 2
                    continue
                index += 1
                continue
            if flag_name in boolean_keywords.values():
                options.append(token)
                index += 1
                continue
        if lower in implicit:
            keyword, value = implicit[lower]
            options.append(f"--{keyword}")
            if value is not None:
                options.append(value)
            index += 1
            continue
        if lower in value_keywords and index + 1 < len(args):
            options.append(f"--{value_keywords[lower]}")
            options.append(args[index + 1])
            index += 2
            continue
        if lower in boolean_keywords:
            options.append(f"--{boolean_keywords[lower]}")
            index += 1
            continue
        positionals.append(raw_token)
        index += 1
    return [*positionals, *options]


def _normalize_model_command(args: list[str]) -> list[str]:
    positionals: list[str] = []
    options: list[str] = []
    residual: list[str] = []
    value_keywords = _VALUE_KEYWORDS.get("model", {})
    reasoning_values = set(_OPTION_VALUES.get(("model", "reasoning-effort"), ()))
    write_values = set(_OPTION_VALUES.get(("model", "write"), ()))
    model_selector: str | None = None
    reasoning_effort: str | None = None
    write_scope: str | None = None
    index = 0
    while index < len(args):
        token = str(args[index] or "").strip()
        lower = token.lower()
        if not token:
            index += 1
            continue
        if token.startswith("--"):
            flag_name = token[2:]
            if flag_name in value_keywords.values():
                options.append(token)
                if index + 1 < len(args):
                    value = args[index + 1]
                    options.append(value)
                    if flag_name == "reasoning-effort":
                        reasoning_effort = str(value or "").strip().lower() or reasoning_effort
                    elif flag_name == "write":
                        write_scope = str(value or "").strip().lower() or write_scope
                    index += 2
                    continue
                index += 1
                continue
        if lower in value_keywords and index + 1 < len(args):
            keyword = value_keywords[lower]
            value = args[index + 1]
            options.append(f"--{keyword}")
            options.append(value)
            if keyword == "reasoning-effort":
                reasoning_effort = str(value or "").strip().lower() or reasoning_effort
            elif keyword == "write":
                write_scope = str(value or "").strip().lower() or write_scope
            index += 2
            continue
        residual.append(token)
        index += 1

    for position, token in enumerate(residual):
        lower = token.lower()
        if lower in write_values and write_scope is None:
            write_scope = lower
            continue
        if lower in reasoning_values:
            if model_selector is None and _model_token_should_stay_positional(
                lower,
                residual_tokens=residual,
                position=position,
                reasoning_effort=reasoning_effort,
                write_scope=write_scope,
            ):
                model_selector = token
                continue
            if reasoning_effort is None:
                reasoning_effort = lower
                continue
        if model_selector is None:
            model_selector = token
            continue
        positionals.append(token)

    if model_selector is not None:
        positionals.insert(0, model_selector)
    if reasoning_effort is not None and "--reasoning-effort" not in options:
        options.extend(["--reasoning-effort", reasoning_effort])
    if write_scope is not None and "--write" not in options:
        options.extend(["--write", write_scope])
    return [*positionals, *options]


def _model_token_should_stay_positional(
    token: str,
    *,
    residual_tokens: Sequence[str],
    position: int,
    reasoning_effort: str | None,
    write_scope: str | None,
) -> bool:
    if reasoning_effort is not None:
        return True
    if token == "default":
        return True
    next_tokens = [
        str(item or "").strip().lower()
        for item in residual_tokens[position + 1 :]
        if str(item or "").strip()
    ]
    if not next_tokens:
        return False
    reasoning_values = set(_OPTION_VALUES.get(("model", "reasoning-effort"), ()))
    write_values = set(_OPTION_VALUES.get(("model", "write"), ()))
    next_token = next_tokens[0]
    if next_token in write_values and write_scope is None:
        return False
    if next_token in reasoning_values:
        return True
    return True


def _normalize_send_input(args: list[str]) -> list[str]:
    if not args:
        return []
    target = args[0]
    tail = list(args[1:])
    interrupt = False
    if tail and str(tail[-1] or "").strip().lower() in {"interrupt", "--interrupt"}:
        interrupt = True
        tail = tail[:-1]
    normalized = [target]
    if tail:
        normalized.extend(tail)
    if interrupt:
        normalized.append("--interrupt")
    return normalized


def _normalize_note_command(args: list[str]) -> list[str]:
    if not args:
        return []
    approval_id = args[0]
    tail = list(args[1:])
    if not tail:
        return [approval_id]
    normalized: list[str] = [approval_id]
    index = 0
    while index < len(tail):
        token = str(tail[index] or "").strip()
        lower = token.lower()
        if lower in {"mode", "--mode"}:
            normalized.append("--mode")
            if index + 1 < len(tail):
                normalized.append(tail[index + 1])
                index += 2
                continue
            index += 1
            continue
        if lower in {"note", "--note"}:
            note_tokens = tail[index + 1 :]
            if not note_tokens:
                normalized.append("--note")
            else:
                normalized.extend(("--note", " ".join(note_tokens)))
            return normalized
        normalized.append(token)
        index += 1
    return normalized


def _normalize_office_run(args: list[str]) -> list[str]:
    if not args:
        return []
    skill = args[0]
    if len(args) == 1:
        return [skill]
    second = str(args[1] or "").strip().lower()
    if second in {"path", "--path"}:
        return [skill, "--path", *args[2:]]
    return [skill, "--path", args[1], *args[2:]]


def _normalize_leading_options_command(name: str, args: list[str]) -> list[str]:
    value_keywords = _VALUE_KEYWORDS.get(name, {})
    positionals: list[str] = []
    options: list[str] = []
    index = 0
    if name == "background_smoke" and args:
        first = str(args[0] or "").strip()
        if first in {"multi_llm", "policy_helper"}:
            positionals.append(first)
            index = 1
    while index < len(args):
        token = str(args[index] or "").strip()
        lower = token.lower()
        if lower in value_keywords and index + 1 < len(args):
            options.extend((f"--{value_keywords[lower]}", args[index + 1]))
            index += 2
            continue
        break
    positionals.extend(args[index:])
    return [*positionals, *options]


def _normalize_tail_options_command(name: str, args: list[str]) -> list[str]:
    value_keywords = _VALUE_KEYWORDS.get(name, {})
    tail_options: list[str] = []
    index = len(args) - 1
    while index >= 1:
        value = args[index]
        keyword = str(args[index - 1] or "").strip().lower()
        if keyword.startswith("--"):
            flag_name = keyword[2:]
            if flag_name in value_keywords.values():
                tail_options[0:0] = [f"--{flag_name}", value]
                index -= 2
                continue
        if keyword in value_keywords:
            tail_options[0:0] = [f"--{value_keywords[keyword]}", value]
            index -= 2
            continue
        break
    positionals = args[: index + 1]
    return [*positionals, *tail_options]


def _keyword_name(name: str, token: str) -> str:
    lowered = str(token or "").strip().lower()
    if lowered.startswith("--"):
        lowered = lowered[2:]
    if lowered in _VALUE_KEYWORDS.get(name, {}):
        return lowered
    return lowered
