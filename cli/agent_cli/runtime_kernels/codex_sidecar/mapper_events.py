from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.mapper_normalization import (
    _field,
    _mapping,
    _text,
    _thread_id_from_payload,
    _turn_id_from_payload,
)


def _turn_error_message(turn: dict[str, Any]) -> str:
    error = _mapping(turn.get("error"))
    return _text(
        _field(error, "message", "errorMessage")
        or _field(error, "additionalDetails", "additional_details")
    )


def _turn_event_metadata(params: dict[str, Any]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    thread_id = _thread_id_from_payload(params)
    turn_id = _turn_id_from_payload(params)
    if thread_id:
        metadata["thread_id"] = thread_id
    if turn_id:
        metadata["turn_id"] = turn_id
    return metadata
