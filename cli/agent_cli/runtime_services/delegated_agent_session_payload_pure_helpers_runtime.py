from __future__ import annotations

from typing import Any


_ASYNC_STARTED_TERMINAL_COMPLETION_STATES = {"ready_to_adopt", "awaiting_join", "adopted"}


def normalized_optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def normalized_optional_text(value: Any) -> str:
    return str(value or "").strip()


def resolved_subagent_protocol_ids(metadata: dict[str, Any]) -> dict[str, str]:
    context = metadata.get("context")
    context_map = context if isinstance(context, dict) else {}

    def pick(*keys: str) -> str:
        for key in keys:
            top = normalized_optional_text(metadata.get(key))
            if top:
                return top
            nested = normalized_optional_text(context_map.get(key))
            if nested:
                return nested
        return ""

    return {
        "run_id": pick("run_id"),
        "parent_run_id": pick("parent_run_id"),
        "thread_id": pick("thread_id"),
    }


def resolved_delegation_metadata(
    metadata: dict[str, Any] | None,
    *,
    role: str,
    effective_async_mode: bool,
) -> dict[str, Any]:
    resolved = dict(metadata or {})
    normalized_role = str(role or "").strip().lower() or "subagent"
    resolved_mode = "background" if effective_async_mode else "sync"
    normalized_wait_required = None
    if "wait_required" in resolved:
        normalized_wait_required = normalized_optional_bool(resolved.get("wait_required"))
    resolved["delegation_mode"] = resolved_mode
    if resolved_mode == "sync":
        resolved["wait_required"] = False
    elif normalized_wait_required is None:
        resolved["wait_required"] = False if normalized_role == "teammate" else False
    else:
        resolved["wait_required"] = normalized_wait_required
    return resolved


def normalize_async_started_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    completion_state = str(normalized.get("completion_state") or "").strip().lower()
    if completion_state not in _ASYNC_STARTED_TERMINAL_COMPLETION_STATES:
        return normalized
    normalized["result_ready"] = False
    normalized["adopted"] = False
    normalized["status"] = "queued"
    normalized["completion_state"] = "pending"
    normalized["result_state"] = "pending"
    normalized["adoption_expectation"] = "continue_main_thread_or_wait"
    result_contract = dict(normalized.get("result_contract") or {})
    if result_contract:
        result_contract["status"] = "queued"
        result_contract["completion_state"] = "pending"
        result_contract["next_action"] = "continue_main_thread_or_wait"
        artifact = dict(result_contract.get("artifact") or {})
        if not artifact or str(artifact.get("kind") or "").strip().lower() in {"pending", "empty", "text"}:
            result_contract["artifact"] = {"kind": "pending"}
        confidence = str(result_contract.get("confidence") or "").strip().lower()
        if not confidence or confidence != "pending":
            result_contract["confidence"] = "pending"
        summary = str(result_contract.get("summary") or "").strip()
        if not summary or "completed" in summary.lower():
            result_contract["summary"] = "delegated task queued"
        normalized["result_contract"] = result_contract
    return normalized
