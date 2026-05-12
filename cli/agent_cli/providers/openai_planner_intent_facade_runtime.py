from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.models import AgentIntent
from cli.agent_cli.providers import openai_planner_intent_runtime as openai_planner_intent_runtime_helpers


def history_for_conversation(
    planner: Any,
    history: List[Dict[str, str]],
    *,
    input_items: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    return openai_planner_intent_runtime_helpers.history_for_conversation(
        history,
        input_items=input_items,
        input_items_have_assistant_turn_fn=planner._input_items_have_assistant_turn,
    )


def synthetic_recovery_allowed(planner: Any) -> bool:
    return openai_planner_intent_runtime_helpers.synthetic_recovery_allowed(
        reference_parity_enabled=planner.reference_parity_enabled
    )


def assert_synthetic_recovery_allowed(planner: Any, path_name: str) -> None:
    openai_planner_intent_runtime_helpers.assert_synthetic_recovery_allowed(
        reference_parity_enabled=planner.reference_parity_enabled,
        path_name=path_name,
    )


def normalize_command_text(planner: Any, command_text: Optional[str]) -> Optional[str]:
    return openai_planner_intent_runtime_helpers.normalize_command_text(
        command_text,
        followup_command_pattern=planner._FOLLOWUP_COMMAND_PATTERN,
        normalize_shell_command_fn=planner.host_platform.normalize_shell_command,
    )


def extract_command_text(planner: Any, raw_text: str) -> Optional[str]:
    return openai_planner_intent_runtime_helpers.extract_command_text(
        raw_text,
        command_pattern=planner._COMMAND_PATTERN,
        normalize_command_text_fn=planner._normalize_command_text,
    )


def intent_from_raw_text(
    planner: Any,
    raw_text: str,
    *,
    allow_command_pattern_fallback: bool = True,
) -> AgentIntent:
    return openai_planner_intent_runtime_helpers.intent_from_raw_text(
        raw_text,
        allow_command_pattern_fallback=allow_command_pattern_fallback,
        extract_json_payload_fn=planner._extract_json_payload,
        normalize_command_text_fn=planner._normalize_command_text,
        extract_command_text_fn=planner._extract_command_text,
        command_pattern=planner._COMMAND_PATTERN,
    )
