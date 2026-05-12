from __future__ import annotations

from collections.abc import Callable, Sequence
from os.path import commonprefix
from typing import Any

from cli.agent_cli.ui import slash_completion_projection_helpers_runtime as _projection_helpers
from cli.agent_cli.ui import slash_completion_pure_helpers_runtime as _pure_helpers

_SUBMIT_AFTER_APPLY_TRUE_VALUES = {"1", "true", "yes", "on"}


def match_local_slash_commands(
    prefix: str,
    *,
    local_slash_specs: list[dict[str, str]],
) -> list[dict[str, str]]:
    token = str(prefix or "").strip().lower().lstrip("/")
    if not token:
        return local_slash_specs
    startswith_matches = [
        spec
        for spec in local_slash_specs
        if str(spec.get("name") or "").strip().lower().startswith(token)
    ]
    if startswith_matches:
        return startswith_matches
    return [
        spec for spec in local_slash_specs if token in str(spec.get("name") or "").strip().lower()
    ]


def complete_local_slash_command(
    prefix: str,
    *,
    local_slash_specs: list[dict[str, str]],
) -> str | None:
    token = str(prefix or "").strip().lower().lstrip("/")
    matches = match_local_slash_commands(token, local_slash_specs=local_slash_specs)
    if not matches:
        return None
    if len(matches) == 1:
        return f"/{matches[0]['name']} "
    names = [
        str(item.get("name") or "").strip()
        for item in matches
        if str(item.get("name") or "").strip()
    ]
    shared_prefix = commonprefix(names)
    if shared_prefix and len(shared_prefix) > len(token):
        return f"/{shared_prefix}"
    if any(name == token for name in names):
        return f"/{token} "
    return None


def _filtered_slash_candidates(
    candidates: Sequence[dict[str, str]],
    *,
    token_query: str,
    completed_tokens: tuple[str, ...],
) -> list[dict[str, str]]:
    used_values = set(completed_tokens)
    filtered: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        usage = str(candidate.get("usage") or "").strip()
        replacement = str(candidate.get("replacement") or usage).strip()
        if not usage or not replacement:
            continue
        dedupe_key = str(candidate.get("name") or replacement).strip()
        if usage in used_values or (usage and f"--{usage}" in used_values):
            continue
        if token_query and token_query not in usage.lower():
            continue
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        filtered.append(candidate)
    return filtered


def _project_slash_argument_match_item(
    candidate: dict[str, str],
    *,
    command_name: str,
    replace_start: int,
    replace_end: int,
    slash_completion_replacement: Callable[..., tuple[str, int]],
) -> dict[str, str]:
    usage = str(candidate.get("usage") or "").strip()
    description = str(candidate.get("description") or "").strip()
    replacement = str(candidate.get("replacement") or usage).strip()
    if not replacement.endswith(" "):
        replacement += " "
    insert_text, cursor_pos = slash_completion_replacement(
        replace_start=replace_start,
        replace_end=replace_end,
        replacement=replacement,
    )
    item = {
        "name": str(
            candidate.get("name") or f"{command_name}:{replacement.strip().replace(' ', ':')}"
        ).strip(),
        "usage": usage,
        "description": description,
        "insert_text": insert_text,
        "cursor_pos": str(cursor_pos),
        "completion_mode": "slash_arg",
    }
    if (
        str(candidate.get("submit_after_apply") or "").strip().lower()
        in _SUBMIT_AFTER_APPLY_TRUE_VALUES
    ):
        item["submit_after_apply"] = "true"
    if (
        str(candidate.get("continue_completion") or "").strip().lower()
        in _SUBMIT_AFTER_APPLY_TRUE_VALUES
    ):
        item["continue_completion"] = "true"
    return item


def slash_argument_matches(
    context: Any,
    *,
    runtime: Any,
    slash_command_spec_getter: Callable[[str], dict[str, str] | None],
    slash_completion_replacement: Callable[..., tuple[str, int]],
    browser_actions: Sequence[str],
    reasoning_efforts: Sequence[str],
    approval_statuses: Sequence[str],
    locale: str | None = None,
) -> list[dict[str, str]]:
    command_name = str(context.command_name or "").strip()
    if not command_name:
        return []
    completed_tokens = _pure_helpers.completed_arg_tokens(context)
    pending_flag = _projection_helpers.slash_pending_flag(command_name, completed_tokens)
    candidates: list[dict[str, str]] = []
    if pending_flag is not None:
        submit_after_apply = _projection_helpers.slash_submit_after_apply(
            command_name, pending_flag=pending_flag
        )
        candidates.extend(
            _pure_helpers.slash_candidate(
                item,
                _projection_helpers.slash_value_candidate_description(
                    pending_flag,
                    locale=locale,
                ),
                submit_after_apply=submit_after_apply,
                name=f"{command_name}:{pending_flag}:{item}",
            )
            for item in _projection_helpers.slash_flag_value_candidates(
                command_name,
                pending_flag,
                reasoning_efforts=reasoning_efforts,
                approval_statuses=approval_statuses,
            )
        )
    else:
        candidates.extend(
            _projection_helpers.slash_positional_candidates(
                command_name,
                completed_tokens,
                runtime=runtime,
                browser_actions=browser_actions,
                reasoning_efforts=reasoning_efforts,
                locale=locale,
            )
        )
        candidates.extend(
            _projection_helpers.slash_flag_candidates(
                command_name,
                slash_command_spec_getter=slash_command_spec_getter,
                locale=locale,
            )
        )

    token_query = str(context.current_token or "").strip().lower()
    filtered = _filtered_slash_candidates(
        candidates,
        token_query=token_query,
        completed_tokens=completed_tokens,
    )
    return [
        _project_slash_argument_match_item(
            candidate,
            command_name=command_name,
            replace_start=context.replace_start,
            replace_end=context.replace_end,
            slash_completion_replacement=slash_completion_replacement,
        )
        for candidate in filtered
    ]
