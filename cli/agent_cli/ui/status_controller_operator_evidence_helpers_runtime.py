from __future__ import annotations

from typing import Any

from cli.agent_cli.ui import status_controller_operator_projection_helpers_runtime as _projection_helpers


OPERATOR_PAYLOAD_KEYS = _projection_helpers.OPERATOR_PAYLOAD_KEYS
OPERATOR_STATUS_KEYS = _projection_helpers.OPERATOR_STATUS_KEYS
_OPERATOR_ARTIFACT_STATUS_KEYS = _projection_helpers._OPERATOR_ARTIFACT_STATUS_KEYS
_OPERATOR_EVIDENCE_STATE_KEYS = _projection_helpers._OPERATOR_EVIDENCE_STATE_KEYS
_OPERATOR_EVIDENCE_SUBJECT_KEYS = _projection_helpers._OPERATOR_EVIDENCE_SUBJECT_KEYS
merged_operator_key_values = _projection_helpers.merged_operator_key_values
normalized_status = _projection_helpers.normalized_status
operator_primary_state_from_mapping = _projection_helpers.operator_primary_state_from_mapping
operator_review_evidence_state_from_mapping = _projection_helpers.operator_review_evidence_state_from_mapping
status_text = _projection_helpers.status_text


def operator_evidence_snapshot(values: dict[str, Any]) -> dict[str, str]:
    mapping = merged_operator_key_values(values)
    snapshot: dict[str, str] = {}
    task_id = str(mapping.get("task_id") or "").strip()
    agent_id = str(mapping.get("agent_id") or "").strip()
    role = str(mapping.get("role") or "").strip()
    if task_id not in {"", "-"}:
        snapshot["operator_evidence_subject_kind"] = "task"
        snapshot["operator_evidence_subject_id"] = task_id
    elif agent_id not in {"", "-"}:
        snapshot["operator_evidence_subject_kind"] = "agent"
        snapshot["operator_evidence_subject_id"] = agent_id
    elif role not in {"", "-"}:
        snapshot["operator_evidence_subject_kind"] = "role"
        snapshot["operator_evidence_subject_id"] = role
    lifecycle_state = normalized_status(operator_primary_state_from_mapping(mapping))
    if lifecycle_state:
        snapshot["operator_evidence_lifecycle_state"] = lifecycle_state
    review_state = operator_review_evidence_state_from_mapping(mapping)
    if review_state:
        snapshot["operator_evidence_review_state"] = review_state
    return snapshot


def _operator_evidence_signature(
    snapshot: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(str(snapshot.get(key) or "").strip() for key in keys)


def _operator_evidence_signature_present(signature: tuple[str, ...]) -> bool:
    return any(part not in {"", "-"} for part in signature)


def _operator_evidence_source(
    *,
    structured_snapshot: dict[str, str],
    text_snapshot: dict[str, str],
    merged_snapshot: dict[str, str],
    keys: tuple[str, ...],
) -> str:
    merged_signature = _operator_evidence_signature(merged_snapshot, keys=keys)
    if not _operator_evidence_signature_present(merged_signature):
        return ""
    structured_signature = _operator_evidence_signature(structured_snapshot, keys=keys)
    text_signature = _operator_evidence_signature(text_snapshot, keys=keys)
    structured_matches = (
        _operator_evidence_signature_present(structured_signature)
        and structured_signature == merged_signature
    )
    text_matches = _operator_evidence_signature_present(text_signature) and text_signature == merged_signature
    if structured_matches:
        return "structured"
    if text_matches:
        return "text"
    if _operator_evidence_signature_present(structured_signature) and _operator_evidence_signature_present(
        text_signature
    ):
        return "mixed"
    if _operator_evidence_signature_present(structured_signature):
        return "structured"
    if _operator_evidence_signature_present(text_signature):
        return "text"
    return ""


def operator_evidence_from_status_sources(
    *,
    structured_values: dict[str, Any],
    text_values: dict[str, Any],
    merged_values: dict[str, Any],
) -> dict[str, str]:
    structured_snapshot = operator_evidence_snapshot(structured_values)
    text_snapshot = operator_evidence_snapshot(text_values)
    merged_snapshot = operator_evidence_snapshot(merged_values)
    state_source = _operator_evidence_source(
        structured_snapshot=structured_snapshot,
        text_snapshot=text_snapshot,
        merged_snapshot=merged_snapshot,
        keys=_OPERATOR_EVIDENCE_STATE_KEYS,
    )
    if state_source:
        merged_snapshot["operator_evidence_state_source"] = state_source
    subject_source = _operator_evidence_source(
        structured_snapshot=structured_snapshot,
        text_snapshot=text_snapshot,
        merged_snapshot=merged_snapshot,
        keys=_OPERATOR_EVIDENCE_SUBJECT_KEYS,
    )
    if subject_source:
        merged_snapshot["operator_evidence_subject_source"] = subject_source
    return merged_snapshot


def operator_status_from_mapping(payload: dict[str, Any]) -> dict[str, str]:
    extracted: dict[str, str] = {}
    for key in OPERATOR_STATUS_KEYS:
        if key in payload:
            extracted[key] = status_text(payload.get(key))
    artifact = payload.get("artifact")
    if isinstance(artifact, dict):
        for key in _OPERATOR_ARTIFACT_STATUS_KEYS:
            if key in artifact and extracted.get(key, "-") == "-":
                extracted[key] = status_text(artifact.get(key))
    result = payload.get("result")
    if isinstance(result, dict):
        for key in OPERATOR_STATUS_KEYS:
            if key in result and extracted.get(key, "-") == "-":
                extracted[key] = status_text(result.get(key))
        result_artifact = result.get("artifact")
        if isinstance(result_artifact, dict):
            for key in _OPERATOR_ARTIFACT_STATUS_KEYS:
                if key in result_artifact and extracted.get(key, "-") == "-":
                    extracted[key] = status_text(result_artifact.get(key))
    extracted.update(operator_evidence_snapshot(extracted))
    return extracted


def operator_payload_contains_status(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    extracted = operator_status_from_mapping(payload)
    return any(extracted.get(key, "-") not in {"", "-"} for key in OPERATOR_PAYLOAD_KEYS)
