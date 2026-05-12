from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.ui.status_controller_operator_helpers_runtime import (
    OPERATOR_AGGREGATE_COMMANDS,
    OPERATOR_COMMANDS,
    OPERATOR_EVIDENCE_KEYS,
    OPERATOR_HINT_KEYS,
    OPERATOR_PAYLOAD_KEYS,
    OPERATOR_STATUS_KEYS,
    OPERATOR_TEXT_COMMANDS,
    boolish_status,
    key_value_lines,
    merged_operator_key_values,
    normalized_count,
    normalized_status,
    operator_command_name,
    operator_evidence_from_status_sources,
    operator_evidence_snapshot,
    operator_payload_contains_status,
    operator_primary_state,
    operator_primary_state_from_mapping,
    operator_review_evidence_state,
    operator_review_evidence_state_from_mapping,
    operator_review_state,
    operator_review_state_from_mapping,
    operator_status_from_mapping,
    operator_status_from_text,
    policy_entries,
    policy_surface_hint,
    status_text,
    tool_label,
)
from cli.agent_cli.ui import context_window_status_runtime


def _operator_status_sources_from_response(
    response: Any,
    *,
    operator_command_name_fn: Callable[[Any], str],
    key_value_lines_fn: Callable[[Any], dict[str, str]],
    operator_status_from_mapping_fn: Callable[[dict[str, Any]], dict[str, str]],
    operator_status_from_text_fn: Callable[[dict[str, str]], dict[str, str]],
) -> tuple[str, Any, dict[str, str], dict[str, str], dict[str, str]]:
    command_name = operator_command_name_fn(getattr(response, "user_text", ""))
    raw_assistant_text = getattr(
        response, "_ui_operator_raw_assistant_text", getattr(response, "assistant_text", "")
    )
    text_payload = key_value_lines_fn(raw_assistant_text)
    structured_status: dict[str, str] = {}
    for event in reversed(list(getattr(response, "tool_events", []) or [])):
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict):
            continue
        event_name = str(getattr(event, "name", "") or "").strip()
        if event_name not in OPERATOR_COMMANDS and not operator_payload_contains_status(payload):
            continue
        structured_status.update(operator_status_from_mapping_fn(payload))
        summary = str(getattr(event, "summary", "") or "").strip()
        if (
            summary
            and structured_status.get("summary", "-") == "-"
            and text_payload.get("summary", "-") in {"", "-"}
        ):
            structured_status["summary"] = summary
        break
    text_status = operator_status_from_text_fn(text_payload) if command_name in OPERATOR_COMMANDS else {}
    merged_status = (
        {
            key: value
            for key, value in merged_operator_key_values(structured_status, text_status).items()
            if key in OPERATOR_STATUS_KEYS and value not in {"", "-"}
        }
        if command_name in OPERATOR_COMMANDS
        else dict(structured_status)
    )
    return command_name, raw_assistant_text, text_payload, structured_status, merged_status


def operator_evidence_from_response(
    response: Any,
    *,
    operator_command_name_fn: Callable[[Any], str],
    key_value_lines_fn: Callable[[Any], dict[str, str]],
    operator_status_from_mapping_fn: Callable[[dict[str, Any]], dict[str, str]],
    operator_status_from_text_fn: Callable[[dict[str, str]], dict[str, str]],
) -> dict[str, str]:
    command_name, _, text_payload, structured_status, merged_status = _operator_status_sources_from_response(
        response,
        operator_command_name_fn=operator_command_name_fn,
        key_value_lines_fn=key_value_lines_fn,
        operator_status_from_mapping_fn=operator_status_from_mapping_fn,
        operator_status_from_text_fn=operator_status_from_text_fn,
    )
    return operator_evidence_from_status_sources(
        structured_values=structured_status,
        text_values=operator_status_from_text_fn(text_payload) if command_name in OPERATOR_COMMANDS else {},
        merged_values=merged_status,
    )


def status_from_response(
    response: Any,
    *,
    operator_status_from_response_fn: Callable[[Any], dict[str, str]],
) -> dict[str, str]:
    base_status = {
        str(key): str(value)
        for key, value in dict(getattr(response, "status", {}) or {}).items()
        if value is not None
    }
    operator_status = {key: "-" for key in OPERATOR_STATUS_KEYS}
    operator_status.update({key: "-" for key in OPERATOR_HINT_KEYS})
    operator_status.update({key: "-" for key in OPERATOR_EVIDENCE_KEYS})
    operator_status.update(operator_status_from_response_fn(response))
    base_status.update(operator_status)
    base_status.update(
        context_window_status_runtime.context_usage_status_from_response(
            response,
            current_status=base_status,
        )
    )
    return base_status


def operator_status_from_response(
    response: Any,
    *,
    operator_command_name_fn: Callable[[Any], str],
    key_value_lines_fn: Callable[[Any], dict[str, str]],
    operator_status_from_mapping_fn: Callable[[dict[str, Any]], dict[str, str]],
    operator_status_from_text_fn: Callable[[dict[str, str]], dict[str, str]],
    operator_hint_from_command_fn: Callable[[str, dict[str, str], Any], str],
) -> dict[str, str]:
    (
        command_name,
        raw_assistant_text,
        text_payload,
        structured_status,
        merged_status,
    ) = _operator_status_sources_from_response(
        response,
        operator_command_name_fn=operator_command_name_fn,
        key_value_lines_fn=key_value_lines_fn,
        operator_status_from_mapping_fn=operator_status_from_mapping_fn,
        operator_status_from_text_fn=operator_status_from_text_fn,
    )
    extracted = dict(merged_status)
    if command_name in OPERATOR_TEXT_COMMANDS:
        hint = operator_hint_from_command_fn(
            command_name,
            merged_operator_key_values(extracted, text_payload),
            raw_assistant_text,
        )
        if hint:
            extracted["operator_hint_text"] = hint
    text_status = operator_status_from_text_fn(text_payload) if command_name in OPERATOR_COMMANDS else {}
    extracted.update(
        operator_evidence_from_status_sources(
            structured_values=structured_status,
            text_values=text_status,
            merged_values=merged_status,
        )
    )
    return extracted
