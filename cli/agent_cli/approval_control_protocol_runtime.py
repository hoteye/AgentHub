from __future__ import annotations

from typing import Any

from cli.agent_cli import approval_contract_runtime

CONTROL_REQUEST_TYPE = "control_request"
CONTROL_RESPONSE_TYPE = "control_response"
CAN_USE_TOOL_SUBTYPE = "can_use_tool"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _tool_name_for_approval_payload(event_name: str, payload: dict[str, Any]) -> str:
    if event_name == "shell_approval_requested":
        return "Bash"
    if event_name == "patch_approval_requested":
        return (
            _text(payload.get("source_tool_name"))
            or _text(payload.get("function_call_name"))
            or (
                "Write"
                if _text(payload.get("request_kind")) == "structured_write"
                else (
                    "Edit"
                    if _text(payload.get("request_kind")) == "structured_edit"
                    else "apply_patch"
                )
            )
        )
    return (
        _text(payload.get("function_call_name")) or _text(payload.get("action_type")) or event_name
    )


def _tool_input_for_approval_payload(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_name == "shell_approval_requested":
        result: dict[str, Any] = {"command": _text(payload.get("command"))}
        description = _text(payload.get("description")) or _text(payload.get("justification"))
        if description:
            result["description"] = description
        return {key: value for key, value in result.items() if value not in ("", None, {}, [])}
    arguments = _dict(payload.get("function_call_arguments"))
    if arguments:
        return arguments
    if event_name == "patch_approval_requested":
        patch = _text(payload.get("patch")) or _text(payload.get("patch_text"))
        if patch:
            return {"patch": patch}
    return {
        key: value
        for key, value in dict(payload).items()
        if key
        not in {
            "approval_id",
            "available_decisions",
            "continuation",
            "ok",
            "status",
        }
        and value not in ("", None, {}, [])
    }


def control_request_for_tool_event(tool_event: Any) -> dict[str, Any] | None:
    event_name = _text(getattr(tool_event, "name", ""))
    if event_name not in {
        "shell_approval_requested",
        "patch_approval_requested",
        "background_teammate_approval_requested",
    }:
        return None
    payload = _dict(getattr(tool_event, "payload", None))
    approval_id = _text(payload.get("approval_id"))
    if not approval_id:
        return None
    request: dict[str, Any] = {
        "subtype": CAN_USE_TOOL_SUBTYPE,
        "tool_name": _tool_name_for_approval_payload(event_name, payload),
        "input": _tool_input_for_approval_payload(event_name, payload),
        "tool_use_id": _text(payload.get("provider_call_id")) or approval_id,
    }
    reason = _text(payload.get("reason"))
    summary = _text(payload.get("summary")) or _text(getattr(tool_event, "summary", ""))
    if reason:
        request["decision_reason"] = reason
    if summary:
        request["description"] = summary
    blocked_path = _text(payload.get("blocked_path"))
    if blocked_path:
        request["blocked_path"] = blocked_path
    return {
        "type": CONTROL_REQUEST_TYPE,
        "request_id": approval_id,
        "request": request,
    }


def control_requests_for_tool_events(tool_events: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in list(tool_events or []):
        request = control_request_for_tool_event(event)
        if request is None:
            continue
        request_id = _text(request.get("request_id"))
        if request_id and request_id in seen:
            continue
        if request_id:
            seen.add(request_id)
        result.append(request)
    return result


def decision_to_permission_response(
    decision: Any,
    *,
    tool_use_id: str | None = None,
    message: str = "",
) -> dict[str, Any]:
    normalized = approval_contract_runtime.normalize_approval_decision(decision)
    decision_type = _text(normalized.get("type"))
    if approval_contract_runtime.is_approval_accepting(normalized):
        response: dict[str, Any] = {
            "behavior": "allow",
            "updatedInput": {},
            "decisionClassification": (
                "user_permanent"
                if decision_type
                in {
                    approval_contract_runtime.APPROVAL_DECISION_ACCEPT_FOR_SESSION,
                    approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT,
                }
                else "user_temporary"
            ),
        }
    else:
        response = {
            "behavior": "deny",
            "message": message or "Permission denied by user.",
            "decisionClassification": "user_reject",
        }
        if decision_type == approval_contract_runtime.APPROVAL_DECISION_CANCEL:
            response["interrupt"] = True
    if tool_use_id:
        response["toolUseID"] = str(tool_use_id)
    response["agenthub_decision"] = decision_type
    return response


def control_response_for_decision(
    *,
    approval_id: str,
    decision: Any,
    request_id: str | None = None,
    tool_use_id: str | None = None,
    message: str = "",
) -> dict[str, Any]:
    normalized_request_id = _text(request_id) or _text(approval_id)
    return {
        "type": CONTROL_RESPONSE_TYPE,
        "response": {
            "subtype": "success",
            "request_id": normalized_request_id,
            "response": decision_to_permission_response(
                decision,
                tool_use_id=tool_use_id,
                message=message,
            ),
        },
    }


def request_id_from_control_response(message: Any) -> str | None:
    if not isinstance(message, dict) or message.get("type") != CONTROL_RESPONSE_TYPE:
        return None
    response = _dict(message.get("response"))
    request_id = _text(response.get("request_id"))
    return request_id or None


def approval_decision_from_control_response(message: Any) -> dict[str, str]:
    if not isinstance(message, dict) or message.get("type") != CONTROL_RESPONSE_TYPE:
        raise ValueError("request.type must be control_response")
    response = _dict(message.get("response"))
    subtype = _text(response.get("subtype"))
    request_id = _text(response.get("request_id"))
    if not request_id:
        raise ValueError("control_response.response.request_id must be set")
    if subtype == "error":
        return {
            "approval_id": request_id,
            "decision": approval_contract_runtime.APPROVAL_DECISION_DECLINE,
            "decision_note": _text(response.get("error")) or "control_response error",
        }
    if subtype != "success":
        raise ValueError("control_response.response.subtype must be success or error")
    body = _dict(response.get("response"))
    exact_decision = _text(body.get("agenthub_decision") or body.get("agenthubDecision"))
    if exact_decision:
        normalized_exact = approval_contract_runtime.normalize_approval_decision(exact_decision)
        return {
            "approval_id": _text(body.get("approval_id")) or request_id,
            "decision": _text(normalized_exact.get("type")),
            "decision_note": _text(body.get("message")),
        }
    behavior = _text(body.get("behavior")).lower()
    classification = _text(body.get("decisionClassification")).lower()
    if behavior == "allow":
        decision = (
            approval_contract_runtime.APPROVAL_DECISION_ACCEPT_FOR_SESSION
            if classification == "user_permanent"
            else approval_contract_runtime.APPROVAL_DECISION_ACCEPT
        )
    elif behavior == "deny":
        decision = (
            approval_contract_runtime.APPROVAL_DECISION_CANCEL
            if bool(body.get("interrupt"))
            else approval_contract_runtime.APPROVAL_DECISION_DECLINE
        )
    else:
        raise ValueError("control_response.response.response.behavior must be allow or deny")
    return {
        "approval_id": _text(body.get("approval_id")) or request_id,
        "decision": decision,
        "decision_note": _text(body.get("message")),
    }


__all__ = [
    "CAN_USE_TOOL_SUBTYPE",
    "CONTROL_REQUEST_TYPE",
    "CONTROL_RESPONSE_TYPE",
    "approval_decision_from_control_response",
    "control_request_for_tool_event",
    "control_requests_for_tool_events",
    "control_response_for_decision",
    "decision_to_permission_response",
    "request_id_from_control_response",
]
