from __future__ import annotations

from typing import Any, Callable


def action_execute_request_payload(
    params: dict[str, Any],
    *,
    first_text_fn: Callable[..., str],
) -> dict[str, Any]:
    request_payload = params.get("request")
    if request_payload is not None:
        if not isinstance(request_payload, dict):
            raise ValueError("params.request must be an object when provided")
        normalized_request = dict(request_payload)
        normalized_request.setdefault(
            "request_id",
            first_text_fn(normalized_request, "requestId", "request_id") or None,
        )
        normalized_request.setdefault(
            "correlation_id",
            first_text_fn(normalized_request, "correlationId", "correlation_id") or None,
        )
        normalized_request.setdefault(
            "actor_id",
            first_text_fn(normalized_request, "actorId", "actor_id") or None,
        )
        normalized_request.setdefault(
            "run_id",
            first_text_fn(normalized_request, "runId", "run_id")
            or first_text_fn(params, "runId", "run_id")
            or None,
        )
        normalized_request.setdefault(
            "agent_id",
            first_text_fn(normalized_request, "agentId", "agent_id")
            or first_text_fn(params, "agentId", "agent_id")
            or None,
        )
        return normalized_request

    action = params.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("params.action must be a non-empty string")
    request_parameters = params.get("parameters")
    if request_parameters is not None and not isinstance(request_parameters, dict):
        raise ValueError("params.parameters must be an object when provided")
    return {
        "action": action.strip(),
        "parameters": dict(request_parameters or {}),
        "request_id": first_text_fn(params, "requestId", "request_id") or None,
        "correlation_id": first_text_fn(params, "correlationId", "correlation_id") or None,
        "actor_id": first_text_fn(params, "actorId", "actor_id") or None,
        "run_id": first_text_fn(params, "runId", "run_id") or None,
        "agent_id": first_text_fn(params, "agentId", "agent_id") or None,
    }


__all__ = ["action_execute_request_payload"]
