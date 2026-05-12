from __future__ import annotations

import shlex
from typing import Any

from cli.agent_cli.runtime_core import (
    provider_commands_parsing_helpers_runtime as provider_parsing_helpers_runtime,
)
from cli.agent_cli.slash_parser import SlashInvocation, slash_keyword_map, slash_switch_set
from cli.agent_cli.slash_surface import compat_normalize_arg_tokens

_SELECTION_WRITE_SCOPES = {"session", "user", "project"}


def slash_invocation_inputs(
    slash_invocation: SlashInvocation | None,
) -> tuple[list[str], list[str], dict[str, Any], list[str]] | None:
    return provider_parsing_helpers_runtime.slash_invocation_inputs(
        slash_invocation,
        slash_keyword_map_fn=slash_keyword_map,
        slash_switch_set_fn=slash_switch_set,
    )


def model_inputs_from_source(
    runtime: Any,
    *,
    command_name: str = "model",
    arg_text: str,
    slash_invocation: SlashInvocation | None,
) -> tuple[list[str], dict[str, Any], list[str]]:
    return provider_parsing_helpers_runtime.model_inputs_from_source(
        runtime,
        command_name=command_name,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        compat_normalize_arg_tokens_fn=compat_normalize_arg_tokens,
        parse_generic_args_fn=provider_parsing_helpers_runtime.parse_generic_args,
    )


def parse_provider_selection_inputs(
    arg_text: str,
    *,
    slash_inputs: tuple[list[str], list[str], dict[str, Any], list[str]] | None,
) -> dict[str, Any]:
    if slash_inputs is not None:
        raw_tokens, provider_positionals, options, extras = slash_inputs
        return {
            "raw_tokens": list(raw_tokens or []),
            "provider_positionals": [
                normalized
                for token in list(provider_positionals or [])
                if (normalized := str(token or "").strip())
            ],
            "verbose": bool(options.get("verbose")),
            "probe_requested": bool(options.get("probe")),
            "write_scope": str(options.get("write") or "user").strip().lower() or "user",
            "missing_write_value": extras_include_any(extras, {"--write", "write"}),
        }
    try:
        raw_tokens = shlex.split(str(arg_text or "").strip(), posix=True)
    except ValueError:
        raw_tokens = [segment for segment in str(arg_text or "").split() if segment]
    verbose = False
    probe_requested = False
    write_scope = "user"
    provider_positionals: list[str] = []
    missing_write_value = False
    index = 0
    while index < len(raw_tokens):
        normalized = str(raw_tokens[index] or "").strip()
        if normalized in {"--verbose", "-v"}:
            verbose = True
            index += 1
            continue
        if normalized == "--probe":
            probe_requested = True
            index += 1
            continue
        if normalized == "--write":
            if index + 1 >= len(raw_tokens):
                missing_write_value = True
                break
            write_scope = str(raw_tokens[index + 1] or "").strip().lower() or "user"
            index += 2
            continue
        if normalized:
            provider_positionals.append(normalized)
        index += 1
    return {
        "raw_tokens": raw_tokens,
        "provider_positionals": provider_positionals,
        "verbose": verbose,
        "probe_requested": probe_requested,
        "write_scope": write_scope,
        "missing_write_value": missing_write_value,
    }


def extras_include_any(extras: list[str], tokens: set[str]) -> bool:
    return any(str(token or "").strip() in tokens for token in list(extras or []))


def normalized_selection_write_scope(value: Any, *, default: str = "user") -> str:
    return provider_parsing_helpers_runtime.normalized_selection_write_scope(
        value,
        default=default,
        valid_scopes=_SELECTION_WRITE_SCOPES,
    )


def selection_write_path(status: dict[str, Any], *, write_scope: str) -> str:
    return provider_parsing_helpers_runtime.selection_write_path(
        status,
        write_scope=write_scope,
    )


def selection_write_scopes() -> set[str]:
    return set(_SELECTION_WRITE_SCOPES)


def switch_provider_with_fallback(
    runtime: Any,
    provider_name: str,
    *,
    write_scope: str,
) -> dict[str, Any]:
    try:
        return runtime.agent.switch_provider(provider_name, write_scope=write_scope)
    except TypeError:
        try:
            return runtime.agent.switch_provider(provider_name, persist=write_scope != "session")
        except TypeError:
            return runtime.agent.switch_provider(provider_name)


def configure_model_selection_with_fallback(
    runtime: Any,
    *,
    model_selector: str | None,
    reasoning_effort: str | None,
    write_scope: str,
) -> dict[str, Any]:
    try:
        return runtime.configure_model_selection(
            model=model_selector,
            reasoning_effort=reasoning_effort,
            write_scope=write_scope,
        )
    except TypeError:
        try:
            return runtime.configure_model_selection(
                model=model_selector,
                reasoning_effort=reasoning_effort,
                persist=write_scope != "session",
            )
        except TypeError:
            return runtime.configure_model_selection(
                model=model_selector,
                reasoning_effort=reasoning_effort,
            )


def available_models_with_fallback(runtime: Any, provider_filter: str | None) -> list[dict[str, Any]]:
    try:
        return list(runtime.agent.available_models(provider_filter, include_hidden=False) or [])
    except TypeError:
        return list(runtime.agent.available_models(provider_filter) or [])


def session_overrides(agent: Any, getter_name: str) -> Any:
    getter = getattr(agent, getter_name, None)
    return getter() if callable(getter) else {}


__all__ = [
    "available_models_with_fallback",
    "configure_model_selection_with_fallback",
    "extras_include_any",
    "model_inputs_from_source",
    "normalized_selection_write_scope",
    "parse_provider_selection_inputs",
    "selection_write_path",
    "selection_write_scopes",
    "session_overrides",
    "slash_invocation_inputs",
    "switch_provider_with_fallback",
]
