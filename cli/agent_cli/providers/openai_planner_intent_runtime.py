from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Pattern

from cli.agent_cli.models import AgentIntent
from cli.agent_cli.providers import openai_planner_synthesis as openai_planner_synthesis_helpers


def history_for_conversation(
    history: List[Dict[str, str]],
    *,
    input_items: Optional[List[Dict[str, Any]]] = None,
    input_items_have_assistant_turn_fn: Callable[[Optional[List[Dict[str, Any]]]], bool],
) -> List[Dict[str, str]]:
    # Structured turn items are the canonical conversation carrier once assistant turns exist.
    if input_items_have_assistant_turn_fn(input_items):
        return []
    return list(history or [])


def synthetic_recovery_allowed(*, reference_parity_enabled: bool) -> bool:
    return not reference_parity_enabled


def assert_synthetic_recovery_allowed(*, reference_parity_enabled: bool, path_name: str) -> None:
    if synthetic_recovery_allowed(reference_parity_enabled=reference_parity_enabled):
        return
    raise RuntimeError(f"{path_name} is disabled when reference parity is enabled")


def normalize_command_text(
    command_text: Optional[str],
    *,
    followup_command_pattern: Pattern[str],
    normalize_shell_command_fn: Callable[[str], str],
) -> Optional[str]:
    return openai_planner_synthesis_helpers.normalize_command_text(
        command_text,
        followup_command_pattern=followup_command_pattern,
        normalize_shell_command_fn=normalize_shell_command_fn,
    )


def extract_command_text(
    raw_text: str,
    *,
    command_pattern: Pattern[str],
    normalize_command_text_fn: Callable[[Optional[str]], Optional[str]],
) -> Optional[str]:
    return openai_planner_synthesis_helpers.extract_command_text(
        raw_text,
        command_pattern=command_pattern,
        normalize_command_text_fn=normalize_command_text_fn,
    )


def intent_from_raw_text(
    raw_text: str,
    *,
    allow_command_pattern_fallback: bool = True,
    extract_json_payload_fn: Callable[[str], Optional[Dict[str, Any]]],
    normalize_command_text_fn: Callable[[Optional[str]], Optional[str]],
    extract_command_text_fn: Callable[[str], Optional[str]],
    command_pattern: Pattern[str],
) -> AgentIntent:
    return openai_planner_synthesis_helpers.intent_from_raw_text(
        raw_text,
        allow_command_pattern_fallback=allow_command_pattern_fallback,
        extract_json_payload_fn=extract_json_payload_fn,
        normalize_command_text_fn=normalize_command_text_fn,
        extract_command_text_fn=extract_command_text_fn,
        command_pattern=command_pattern,
    )
