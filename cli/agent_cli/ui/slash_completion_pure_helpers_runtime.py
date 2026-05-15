from __future__ import annotations

import re
from typing import Any

from cli.agent_cli.ui import (
    slash_completion_provider_model_runtime as _provider_model_runtime,
)

_candidate_matches_current = _provider_model_runtime._candidate_matches_current
_normalized_token_set = _provider_model_runtime._normalized_token_set
_ordered_non_empty_tokens = _provider_model_runtime._ordered_non_empty_tokens
_token_variants = _provider_model_runtime._token_variants
available_model_items = _provider_model_runtime.available_model_items
available_model_names = _provider_model_runtime.available_model_names
available_provider_names = _provider_model_runtime.available_provider_names
current_model_tokens = _provider_model_runtime.current_model_tokens
current_provider_name = _provider_model_runtime.current_provider_name
current_provider_tokens = _provider_model_runtime.current_provider_tokens
current_reasoning_effort_tokens = _provider_model_runtime.current_reasoning_effort_tokens
current_slash_arg_selection_index = _provider_model_runtime.current_slash_arg_selection_index
default_reasoning_effort_tokens_for_model = (
    _provider_model_runtime.default_reasoning_effort_tokens_for_model
)
model_availability_hint = _provider_model_runtime.model_availability_hint
model_name_matches_current = _provider_model_runtime.model_name_matches_current
reasoning_effort_names_for_model = _provider_model_runtime.reasoning_effort_names_for_model

SELECTION_WRITE_SCOPES = ("user", "session", "project")


def slash_candidate(
    usage: str,
    description: str,
    *,
    replacement: str | None = None,
    submit_after_apply: bool = False,
    continue_completion: bool = False,
    name: str | None = None,
    description_key: str | None = None,
    command: str | None = None,
) -> dict[str, str]:
    item = {
        "usage": str(usage or "").strip(),
        "replacement": str(replacement if replacement is not None else usage or "").strip(),
        "description": str(description or "").strip(),
    }
    if name:
        item["name"] = str(name)
    if description_key:
        item["description_key"] = str(description_key)
    if command:
        item["command"] = str(command)
    if submit_after_apply:
        item["submit_after_apply"] = "true"
    if continue_completion:
        item["continue_completion"] = "true"
    return item


def selection_scope_action_candidates(command_name: str, value: str) -> list[dict[str, str]]:
    return selection_scope_action_candidates_with_metadata(command_name, value)


def selection_scope_action_candidates_with_metadata(
    command_name: str,
    value: str,
    *,
    availability_hint: str | None = None,
) -> list[dict[str, str]]:
    normalized_command = str(command_name or "").strip().lower()
    normalized_value = str(value or "").strip()
    normalized_hint = str(availability_hint or "").strip()

    def _model_description(text: str) -> str:
        if not normalized_hint:
            return text
        return f"{normalized_hint}; {text}"

    if not normalized_value:
        return []
    if normalized_command == "provider":
        return [
            slash_candidate(
                normalized_value,
                "switch provider and save as user default",
                replacement=normalized_value,
                submit_after_apply=True,
                name=f"provider:{normalized_value}",
                description_key="slash.arg.provider.switch_save_user",
            ),
        ]
    if normalized_command == "model":
        return [
            slash_candidate(
                normalized_value,
                _model_description("switch model and save as user default"),
                replacement=normalized_value,
                continue_completion=True,
                name=f"model:{normalized_value}",
                description_key="slash.arg.model.switch_save_user",
            ),
        ]
    return []


def usage_flag_names(usage: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for flag in re.findall(r"--[A-Za-z0-9-]+", str(usage or "")):
        if flag in seen:
            continue
        seen.add(flag)
        ordered.append(flag)
    return ordered


def completed_arg_tokens(context: Any) -> tuple[str, ...]:
    if context.mode != "slash_arg":
        return ()
    if context.ends_with_space:
        return tuple(context.arg_tokens)
    if not context.arg_tokens:
        return ()
    return tuple(context.arg_tokens[:-1])
