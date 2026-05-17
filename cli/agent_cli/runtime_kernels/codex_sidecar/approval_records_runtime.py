from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha1
from typing import Any

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.gateway_core import (
    ActionRequest,
    ApprovalTicket,
    AuditRecord,
    create_audit_record,
)
from cli.agent_cli.models import ActivityEvent, ToolEvent
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonRpcServerRequest

CODEX_SIDECAR_CONNECTOR_KEY = "codex_sidecar"
CODEX_SIDECAR_PLUGIN_NAME = "codex_sidecar"
CODEX_COMMAND_APPROVAL_ACTION_TYPE = "codex_sidecar.command_execution"
CODEX_FILE_CHANGE_APPROVAL_ACTION_TYPE = "codex_sidecar.file_change"
CODEX_PERMISSION_APPROVAL_ACTION_TYPE = "codex_sidecar.permissions"
CODEX_COMMAND_APPROVAL_METHOD = "item/commandExecution/requestApproval"
CODEX_FILE_CHANGE_APPROVAL_METHOD = "item/fileChange/requestApproval"
CODEX_PERMISSION_APPROVAL_METHOD = "item/permissions/requestApproval"
CODEX_APPROVAL_METHODS = frozenset(
    {
        CODEX_COMMAND_APPROVAL_METHOD,
        CODEX_FILE_CHANGE_APPROVAL_METHOD,
        CODEX_PERMISSION_APPROVAL_METHOD,
    }
)


@dataclass(frozen=True, slots=True)
class ApprovalRegistrationRecords:
    approval_id: str
    params: dict[str, Any]
    kind: str
    action_request: ActionRequest
    ticket: ApprovalTicket


def is_command_approval_request(request: JsonRpcServerRequest) -> bool:
    return str(request.method or "").strip() == CODEX_COMMAND_APPROVAL_METHOD


def is_supported_approval_request(request: JsonRpcServerRequest) -> bool:
    return str(request.method or "").strip() in CODEX_APPROVAL_METHODS


def approval_id_for_request(request: JsonRpcServerRequest) -> str:
    params = dict(request.params or {})
    raw_approval_id = str(params.get("approvalId") or params.get("approval_id") or "").strip()
    if raw_approval_id:
        return raw_approval_id
    thread_id = str(params.get("threadId") or params.get("thread_id") or "").strip()
    turn_id = str(params.get("turnId") or params.get("turn_id") or "").strip()
    item_id = str(params.get("itemId") or params.get("item_id") or "").strip()
    request_digest = sha1(
        f"{thread_id}|{turn_id}|{item_id}|{request.request_id}".encode()
    ).hexdigest()[:12]
    return f"codex_approval_{request_digest}"


def activity_for_approval(
    request: JsonRpcServerRequest,
    *,
    approval_id: str,
    available_decisions: list[dict[str, Any]],
) -> ActivityEvent:
    params = dict(request.params or {})
    command = str(params.get("command") or "").strip()
    reason = str(params.get("reason") or "").strip()
    kind = approval_kind_for_request(request)
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
        title=approval_activity_title(kind),
        status="info",
        detail="\n".join(detail_lines),
        kind="approval",
        code=approval_activity_code(kind),
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


def approval_registration_records(
    request: JsonRpcServerRequest,
    *,
    approval_id: str | None = None,
) -> ApprovalRegistrationRecords:
    params = dict(request.params or {})
    resolved_approval_id = approval_id or approval_id_for_request(request)
    now = utc_now_text()
    thread_id = str(params.get("threadId") or "").strip()
    turn_id = str(params.get("turnId") or "").strip()
    item_id = str(params.get("itemId") or "").strip()
    kind = approval_kind_for_request(request)
    metadata = approval_metadata_from_request(
        request,
        kind=kind,
        thread_id=thread_id,
        turn_id=turn_id,
        item_id=item_id,
    )
    action_request = ActionRequest(
        action_id=f"codex_action_{digest(resolved_approval_id, thread_id, turn_id, item_id)}",
        action_type=approval_action_type(kind),
        connector_key=CODEX_SIDECAR_CONNECTOR_KEY,
        plugin_name=CODEX_SIDECAR_PLUGIN_NAME,
        trace_id=f"codex_sidecar_{digest(thread_id, turn_id, item_id, resolved_approval_id)}",
        requested_at=now,
        requested_by="codex_sidecar",
        approval_required=True,
        action_family=kind,
        action_class="runtime",
        approval_policy=None,
        audit_stage="approval",
        payload=action_payload_from_request(request, approval_id=resolved_approval_id),
        metadata=dict(metadata),
    )
    available_decisions = available_decisions_from_request(request)
    ticket = ApprovalTicket(
        approval_id=resolved_approval_id,
        action_id=action_request.action_id,
        trace_id=action_request.trace_id,
        status="pending",
        requested_at=now,
        requested_by="codex_sidecar",
        reason=str(params.get("reason") or f"Codex sidecar requested {kind} approval").strip(),
        summary=approval_summary(kind),
        available_decisions=available_decisions,
        grant_root=str(params.get("grantRoot") or "").strip() or None,
        metadata=dict(metadata),
    )
    return ApprovalRegistrationRecords(
        approval_id=resolved_approval_id,
        params=params,
        kind=kind,
        action_request=action_request,
        ticket=ticket,
    )


def available_decisions_from_request(request: JsonRpcServerRequest) -> list[dict[str, Any]]:
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


def action_payload_from_request(
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


def approval_tool_event(ticket: ApprovalTicket, params: dict[str, Any]) -> ToolEvent:
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


def pending_approval_audit_record(
    action_request: ActionRequest,
    ticket: ApprovalTicket,
    *,
    kind: str,
) -> AuditRecord:
    return create_audit_record(
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


def decided_approval_audit_record(ticket: ApprovalTicket) -> AuditRecord:
    return create_audit_record(
        trace_id=ticket.trace_id,
        stage="approval",
        status=ticket.status,
        summary=f"{ticket.status} Codex sidecar approval",
        action_id=ticket.action_id,
        approval_id=ticket.approval_id,
        details={
            "decision_type": ticket.decision_type,
            "decision_note": ticket.decision_note,
        },
        metadata={"source": "codex_sidecar"},
    )


def approval_resolution_payload_updates(action_request: ActionRequest) -> dict[str, Any]:
    return {
        "source": "codex_sidecar",
        "command": dict(action_request.payload or {}).get("command"),
    }


def approval_metadata_from_request(
    request: JsonRpcServerRequest,
    *,
    kind: str,
    thread_id: str,
    turn_id: str,
    item_id: str,
) -> dict[str, Any]:
    return {
        "source": "codex_sidecar",
        "method": request.method,
        "request_id": request.request_id,
        "thread_id": thread_id,
        "turn_id": turn_id,
        "item_id": item_id,
        "approval_kind": kind,
    }


def utc_now_text() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def digest(*parts: object) -> str:
    return sha1("|".join(str(part or "") for part in parts).encode()).hexdigest()[:12]


def approval_kind_for_request(request: JsonRpcServerRequest) -> str:
    method = str(request.method or "").strip()
    if method == CODEX_FILE_CHANGE_APPROVAL_METHOD:
        return "file_change"
    if method == CODEX_PERMISSION_APPROVAL_METHOD:
        return "permissions"
    return "command_execution"


def approval_action_type(kind: str) -> str:
    if kind == "file_change":
        return CODEX_FILE_CHANGE_APPROVAL_ACTION_TYPE
    if kind == "permissions":
        return CODEX_PERMISSION_APPROVAL_ACTION_TYPE
    return CODEX_COMMAND_APPROVAL_ACTION_TYPE


def approval_summary(kind: str) -> str:
    if kind == "file_change":
        return "Approve Codex sidecar file changes"
    if kind == "permissions":
        return "Approve Codex sidecar permissions"
    return "Approve Codex sidecar command"


def approval_activity_title(kind: str) -> str:
    if kind == "file_change":
        return "Requested file change approval"
    if kind == "permissions":
        return "Requested permissions approval"
    return "Requested shell approval"


def approval_activity_code(kind: str) -> str:
    if kind == "file_change":
        return "approval.request.file_change"
    if kind == "permissions":
        return "approval.request.permissions"
    return "approval.request.shell"
