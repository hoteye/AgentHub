from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cli.agent_cli.ui.transcript_history import TranscriptEntry


def structured_payload(entry: TranscriptEntry) -> dict[str, Any] | None:
    payload = entry.structured
    return payload if isinstance(payload, dict) else None


def payload_name(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    return str(payload.get("name") or "").strip().lower()


def payload_state(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    return str(payload.get("state") or "").strip().lower()


def payload_title(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    return str(payload.get("title") or "").strip()


def payload_output(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    return str(payload.get("output") or "").strip()


def payload_group_key(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    return str(payload.get("group_key") or "").strip().lower()


def payload_summary(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    return str(payload.get("summary") or "").strip()


def payload_input(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    input_payload = payload.get("input")
    return dict(input_payload) if isinstance(input_payload, dict) else {}


def payload_metadata(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    metadata = payload.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def payload_code(payload: dict[str, Any] | None) -> str:
    metadata = payload_metadata(payload)
    code = str(metadata.get("code") or "").strip().lower()
    if code:
        return code
    return payload_name(payload)


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def first_summary_line(text: str) -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return str(text or "").strip()


def payload_command_text(payload: dict[str, Any] | None) -> str:
    input_payload = payload_input(payload)
    for key in ("display_command", "command"):
        text = str(input_payload.get(key) or "").strip()
        if text:
            return text
    command_lines = string_list(input_payload.get("command_lines"))
    lines = [line.strip() for line in command_lines if line.strip()]
    return "\n".join(lines)


def payload_exploration_details(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    details = payload_input(payload).get("details")
    if not isinstance(details, list):
        return []
    return [dict(detail) for detail in details if isinstance(detail, dict)]
