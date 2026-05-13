from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha1
from typing import Any

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.gateway_core import ActionRequest, ApprovalTicket, create_audit_record
from cli.agent_cli.models import ActivityEvent, ToolEvent
from cli.agent_cli.runtime_kernels.codex_sidecar import approval_response_runtime
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject, JsonRpcServerRequest
from cli.agent_cli.runtime_services import approval_resolution_helpers_runtime

CODEX_SIDECAR_CONNECTOR_KEY = "codex_sidecar"
CODEX_SIDECAR_PLUGIN_NAME = "codex_sidecar"
CODEX_COMMAND_APPROVAL_ACTION_TYPE = "codex_sidecar.command_execution"
CODEX_FILE_CHANGE_APPROVAL_ACTION_TYPE = "codex_sidecar.file_change"
CODEX_PERMISSION_APPROVAL_ACTION_TYPE = "codex_sidecar.permissions"
CODEX_COMMAND_APPROVAL_METHOD = "item/commandExecution/requestApproval"
CODEX_FILE_CHANGE_APPROVAL_METHOD = "item/fileChange/requestApproval"
CODEX_PERMISSION_APPROVAL_METHOD = "item/permissions/requestApproval"


def is_command_approval_request(request: JsonRpcServerRequest) -> bool:
    return str(request.method or "").strip() == CODEX_COMMAND_APPROVAL_METHOD


def is_supported_approval_request(request: JsonRpcServerRequest) -> bool:
    return str(request.method or "").strip() in {
        CODEX_COMMAND_APPROVAL_METHOD,
        CODEX_FILE_CHANGE_APPROVAL_METHOD,
        CODEX_PERMISSION_APPROVAL_METHOD,
    }


def approval_id_for_request(request: JsonRpcServerRequest) -> str:
    params = dict(request.params or {})
    raw_approval_id = str(params.get("approvalId") or params.get("approval_id") or "").strip()
    if raw_approval_id:
        return raw_approval_id
    thread_id = str(params.get("threadId") or params.get("thread_id") or "").strip()
    turn_id = str(params.get("turnId") or params.get("turn_id") or "").strip()
    item_id = str(params.get("itemId") or params.get("item_id") or "").strip()
    digest = sha1(f"{thread_id}|{turn_id}|{item_id}|{request.request_id}".encode()).hexdigest()[:12]
    return f"codex_approval_{digest}"


def activity_for_approval(
    request: JsonRpcServerRequest,
    *,
    approval_id: str,
    available_decisions: list[dict[str, Any]],
) -> ActivityEvent:
    params = dict(request.params or {})
    command = str(params.get("command") or "").strip()
    reason = str(params.get("reason") or "").strip()
    kind = _approval_kind_for_request(request)
    detail_lines = [approval_id]
    if command:
        detail_lines.append(f"command={command}")
    if kind == "file_change" and params.get("grantRoot"):
        detail_lines.append(f"grantRoot={params.get('grantRoot')}")
    if kind == "permissions" and params.get("permissions"):
        detail_lines.append("permissions requested")
    if reason:
        detail_lines.append(f"reason={reason}")
    return ActivityEvent(
        title=_approval_activity_title(kind),
        status="info",
        detail="\n".join(detail_lines),
        kind="approval",
        code=_approval_activity_code(kind),
        params={
            "approval_id": approval_id,
            "command": command or None,
            "reason": reason or None,
            "available_decisions": available_decisions,
            "source": "codex_sidecar",
            "method": request.method,
            "request_id": request.request_id,
            "approval_kind": kind,
        },
    )


def activity_for_command_approval(
    request: JsonRpcServerRequest,
    *,
    approval_id: str,
    available_decisions: list[dict[str, Any]],
) -> ActivityEvent:
    return activity_for_approval(
        request,
        approval_id=approval_id,
        available_decisions=available_decisions,
    )


def register_command_approval(runtime: Any, request: JsonRpcServerRequest) -> ToolEvent:
    return register_approval(runtime, request)


def register_approval(runtime: Any, request: JsonRpcServerRequest) -> ToolEvent:
    _ensure_gateway_store(runtime)
    params = dict(request.params or {})
    approval_id = approval_id_for_request(request)
    existing_ticket = runtime.gateway_state_store.get_approval_ticket(approval_id)
    if existing_ticket is not None:
        return _approval_tool_event(existing_ticket, params)
    now = _utc_now_text()
    thread_id = str(params.get("threadId") or "").strip()
    turn_id = str(params.get("turnId") or "").strip()
    item_id = str(params.get("itemId") or "").strip()
    kind = _approval_kind_for_request(request)
    action_request = ActionRequest(
        action_id=f"codex_action_{_digest(approval_id, thread_id, turn_id, item_id)}",
        action_type=_approval_action_type(kind),
        connector_key=CODEX_SIDECAR_CONNECTOR_KEY,
        plugin_name=CODEX_SIDECAR_PLUGIN_NAME,
        trace_id=f"codex_sidecar_{_digest(thread_id, turn_id, item_id, approval_id)}",
        requested_at=now,
        requested_by="codex_sidecar",
        approval_required=True,
        action_family=kind,
        action_class="runtime",
        approval_policy=None,
        audit_stage="approval",
        payload=_action_payload_from_request(request, approval_id=approval_id),
        metadata={
            "source": "codex_sidecar",
            "method": request.method,
            "request_id": request.request_id,
            "thread_id": thread_id,
            "turn_id": turn_id,
            "item_id": item_id,
            "approval_kind": kind,
        },
    )
    available_decisions = _available_decisions_from_request(request)
    ticket = ApprovalTicket(
        approval_id=approval_id,
        action_id=action_request.action_id,
        trace_id=action_request.trace_id,
        status="pending",
        requested_at=now,
        requested_by="codex_sidecar",
        reason=str(params.get("reason") or f"Codex sidecar requested {kind} approval").strip(),
        summary=_approval_summary(kind),
        available_decisions=available_decisions,
        grant_root=str(params.get("grantRoot") or "").strip() or None,
        metadata={
            "source": "codex_sidecar",
            "method": request.method,
            "request_id": request.request_id,
            "thread_id": thread_id,
            "turn_id": turn_id,
            "item_id": item_id,
            "approval_kind": kind,
        },
    )
    runtime.save_gateway_action_request(action_request)
    runtime.save_gateway_approval_ticket(ticket)
    runtime.append_gateway_audit_record(
        create_audit_record(
            trace_id=action_request.trace_id,
            stage="approval",
            status="pending",
            summary=ticket.summary,
            action_id=action_request.action_id,
            approval_id=ticket.approval_id,
            details={
                "reason": ticket.reason,
                "command": action_request.payload.get("command"),
                "approval_kind": kind,
            },
            metadata={"source": "codex_sidecar"},
        )
    )
    return _approval_tool_event(ticket, params)


def decide_command_approval(
    runtime: Any,
    approval_id: str,
    *,
    decision: Any,
    decided_by: str,
    decision_note: str = "",
) -> dict[str, Any]:
    return decide_approval(
        runtime,
        approval_id,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )


def decide_approval(
    runtime: Any,
    approval_id: str,
    *,
    decision: Any,
    decided_by: str,
    decision_note: str = "",
) -> dict[str, Any]:
    approval_ticket, action_request = approval_resolution_helpers_runtime.pending_approval_context(
        runtime, approval_id
    )
    normalized_decision = approval_contract_runtime.merge_available_decision(
        available_decisions=getattr(approval_ticket, "available_decisions", None),
        decision=decision,
        fallback_proposed_rule=(
            dict(getattr(approval_ticket, "proposed_rule", {}) or {})
            if isinstance(getattr(approval_ticket, "proposed_rule", None), dict)
            else None
        ),
    )
    updated_ticket = approval_resolution_helpers_runtime.decided_approval_ticket(
        approval_ticket,
        decision=normalized_decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )
    runtime.save_gateway_approval_ticket(updated_ticket)
    runtime.append_gateway_audit_record(
        create_audit_record(
            trace_id=updated_ticket.trace_id,
            stage="approval",
            status=updated_ticket.status,
            summary=f"{updated_ticket.status} Codex sidecar approval",
            action_id=updated_ticket.action_id,
            approval_id=updated_ticket.approval_id,
            details={
                "decision_type": updated_ticket.decision_type,
                "decision_note": updated_ticket.decision_note,
            },
            metadata={"source": "codex_sidecar"},
        )
    )
    response = approval_resolution_helpers_runtime.approval_resolution_response(
        updated_ticket,
        action_request,
        None,
        [],
        payload_updates={
            "source": "codex_sidecar",
            "command": dict(action_request.payload or {}).get("command"),
        },
    )
    response["codex_sidecar_response"] = approval_response_for_decision(
        normalized_decision,
        action_request=action_request,
    )
    return response


def command_approval_response_for_decision(decision: Any) -> JsonObject:
    return approval_response_for_decision(decision)


def approval_response_for_decision(
    decision: Any,
    *,
    action_request: ActionRequest | None = None,
) -> JsonObject:
    return approval_response_runtime.approval_response_for_decision(
        decision,
        action_request=action_request,
    )


def _available_decisions_from_request(request: JsonRpcServerRequest) -> list[dict[str, Any]]:
    params = dict(request.params or {})
    raw = params.get("availableDecisions") or params.get("available_decisions")
    if raw:
        normalized = approval_contract_runtime.normalize_available_decisions(raw)
        if normalized:
            return normalized
    proposed_rule = params.get("proposedExecpolicyAmendment") or params.get(
        "proposed_execpolicy_amendment"
    )
    if str(request.method or "").strip() == CODEX_COMMAND_APPROVAL_METHOD:
        return approval_contract_runtime.shell_available_decisions(
            dict(proposed_rule) if isinstance(proposed_rule, dict) else None
        )
    if str(request.method or "").strip() == CODEX_FILE_CHANGE_APPROVAL_METHOD:
        return approval_contract_runtime.patch_available_decisions(
            grant_root=str(params.get("grantRoot") or "").strip() or None
        )
    return approval_contract_runtime.shell_available_decisions(
        dict(proposed_rule) if isinstance(proposed_rule, dict) else None
    )


def _action_payload_from_request(
    request: JsonRpcServerRequest,
    *,
    approval_id: str,
) -> dict[str, Any]:
    params = dict(request.params or {})
    return {
        "approval_id": approval_id,
        "request_id": request.request_id,
        "method": request.method,
        "thread_id": str(params.get("threadId") or "").strip(),
        "turn_id": str(params.get("turnId") or "").strip(),
        "item_id": str(params.get("itemId") or "").strip(),
        "command": str(params.get("command") or "").strip(),
        "cwd": str(params.get("cwd") or "").strip() or None,
        "reason": str(params.get("reason") or "").strip() or None,
        "command_actions": (
            list(params.get("commandActions") or [])
            if isinstance(params.get("commandActions"), list)
            else []
        ),
        "grant_root": str(params.get("grantRoot") or "").strip() or None,
        "permissions": (
            params.get("permissions") if isinstance(params.get("permissions"), dict) else None
        ),
        "changes": params.get("changes") if isinstance(params.get("changes"), list) else [],
        "additional_permissions": params.get("additionalPermissions")
        or params.get("additional_permissions"),
        "proposed_execpolicy_amendment": params.get("proposedExecpolicyAmendment")
        or params.get("proposed_execpolicy_amendment"),
        "proposed_network_policy_amendments": params.get("proposedNetworkPolicyAmendments")
        or params.get("proposed_network_policy_amendments"),
    }


def _approval_tool_event(ticket: ApprovalTicket, params: dict[str, Any]) -> ToolEvent:
    kind = str((ticket.metadata or {}).get("approval_kind") or "command_execution")
    event_name = "shell_approval_requested"
    if kind != "command_execution":
        event_name = f"{kind}_approval_requested"
    return ToolEvent(
        name=event_name,
        ok=True,
        summary=f"codex sidecar {kind} approval requested {ticket.approval_id}",
        payload={
            "ok": True,
            "approval_id": ticket.approval_id,
            "status": ticket.status,
            "summary": ticket.summary,
            "reason": ticket.reason,
            "command": str(params.get("command") or "").strip(),
            "cwd": str(params.get("cwd") or "").strip() or None,
            "available_decisions": list(ticket.available_decisions or []),
            "source": "codex_sidecar",
            "approval_kind": kind,
        },
    )


def _ensure_gateway_store(runtime: Any) -> None:
    if getattr(runtime, "gateway_state_store", None) is not None:
        return
    from cli.agent_cli.gateway_core import InMemoryGatewayStateStore

    runtime.gateway_state_store = InMemoryGatewayStateStore()


def _utc_now_text() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _digest(*parts: object) -> str:
    return sha1("|".join(str(part or "") for part in parts).encode()).hexdigest()[:12]


def _approval_kind_for_request(request: JsonRpcServerRequest) -> str:
    method = str(request.method or "").strip()
    if method == CODEX_FILE_CHANGE_APPROVAL_METHOD:
        return "file_change"
    if method == CODEX_PERMISSION_APPROVAL_METHOD:
        return "permissions"
    return "command_execution"


def _approval_action_type(kind: str) -> str:
    if kind == "file_change":
        return CODEX_FILE_CHANGE_APPROVAL_ACTION_TYPE
    if kind == "permissions":
        return CODEX_PERMISSION_APPROVAL_ACTION_TYPE
    return CODEX_COMMAND_APPROVAL_ACTION_TYPE


def _approval_summary(kind: str) -> str:
    if kind == "file_change":
        return "Approve Codex sidecar file changes"
    if kind == "permissions":
        return "Approve Codex sidecar permissions"
    return "Approve Codex sidecar command"


def _approval_activity_title(kind: str) -> str:
    if kind == "file_change":
        return "Requested file change approval"
    if kind == "permissions":
        return "Requested permissions approval"
    return "Requested shell approval"


def _approval_activity_code(kind: str) -> str:
    if kind == "file_change":
        return "approval.request.file_change"
    if kind == "permissions":
        return "approval.request.permissions"
    return "approval.request.shell"


_codex_execpolicy_amendment_from_rule = (
    approval_response_runtime.codex_execpolicy_amendment_from_rule
)
_permission_response_for_decision = approval_response_runtime.permission_response_for_decision
