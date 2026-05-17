from __future__ import annotations

from typing import Any

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.gateway_core import ActionRequest
from cli.agent_cli.models import ActivityEvent, ToolEvent
from cli.agent_cli.runtime_kernels.codex_sidecar import (
    approval_records_runtime,
    approval_response_runtime,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject, JsonRpcServerRequest
from cli.agent_cli.runtime_services import approval_resolution_helpers_runtime

CODEX_SIDECAR_CONNECTOR_KEY = approval_records_runtime.CODEX_SIDECAR_CONNECTOR_KEY
CODEX_SIDECAR_PLUGIN_NAME = approval_records_runtime.CODEX_SIDECAR_PLUGIN_NAME
CODEX_COMMAND_APPROVAL_ACTION_TYPE = approval_records_runtime.CODEX_COMMAND_APPROVAL_ACTION_TYPE
CODEX_FILE_CHANGE_APPROVAL_ACTION_TYPE = (
    approval_records_runtime.CODEX_FILE_CHANGE_APPROVAL_ACTION_TYPE
)
CODEX_PERMISSION_APPROVAL_ACTION_TYPE = (
    approval_records_runtime.CODEX_PERMISSION_APPROVAL_ACTION_TYPE
)
CODEX_COMMAND_APPROVAL_METHOD = approval_records_runtime.CODEX_COMMAND_APPROVAL_METHOD
CODEX_FILE_CHANGE_APPROVAL_METHOD = approval_records_runtime.CODEX_FILE_CHANGE_APPROVAL_METHOD
CODEX_PERMISSION_APPROVAL_METHOD = approval_records_runtime.CODEX_PERMISSION_APPROVAL_METHOD


def is_command_approval_request(request: JsonRpcServerRequest) -> bool:
    return approval_records_runtime.is_command_approval_request(request)


def is_supported_approval_request(request: JsonRpcServerRequest) -> bool:
    return approval_records_runtime.is_supported_approval_request(request)


def approval_id_for_request(request: JsonRpcServerRequest) -> str:
    return approval_records_runtime.approval_id_for_request(request)


def activity_for_approval(
    request: JsonRpcServerRequest,
    *,
    approval_id: str,
    available_decisions: list[dict[str, Any]],
) -> ActivityEvent:
    return approval_records_runtime.activity_for_approval(
        request,
        approval_id=approval_id,
        available_decisions=available_decisions,
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
    approval_id = approval_id_for_request(request)
    existing_ticket = runtime.gateway_state_store.get_approval_ticket(approval_id)
    if existing_ticket is not None:
        return approval_records_runtime.approval_tool_event(
            existing_ticket,
            dict(request.params or {}),
        )
    records = approval_records_runtime.approval_registration_records(
        request,
        approval_id=approval_id,
    )
    runtime.save_gateway_action_request(records.action_request)
    runtime.save_gateway_approval_ticket(records.ticket)
    runtime.append_gateway_audit_record(
        approval_records_runtime.pending_approval_audit_record(
            records.action_request,
            records.ticket,
            kind=records.kind,
        )
    )
    return approval_records_runtime.approval_tool_event(records.ticket, records.params)


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
        approval_records_runtime.decided_approval_audit_record(updated_ticket)
    )
    response = approval_resolution_helpers_runtime.approval_resolution_response(
        updated_ticket,
        action_request,
        None,
        [],
        payload_updates=approval_records_runtime.approval_resolution_payload_updates(
            action_request
        ),
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


def _ensure_gateway_store(runtime: Any) -> None:
    if getattr(runtime, "gateway_state_store", None) is not None:
        return
    from cli.agent_cli.gateway_core import InMemoryGatewayStateStore

    runtime.gateway_state_store = InMemoryGatewayStateStore()


_available_decisions_from_request = approval_records_runtime.available_decisions_from_request
_action_payload_from_request = approval_records_runtime.action_payload_from_request
_approval_tool_event = approval_records_runtime.approval_tool_event
_utc_now_text = approval_records_runtime.utc_now_text
_digest = approval_records_runtime.digest
_approval_kind_for_request = approval_records_runtime.approval_kind_for_request
_approval_action_type = approval_records_runtime.approval_action_type
_approval_summary = approval_records_runtime.approval_summary
_approval_activity_title = approval_records_runtime.approval_activity_title
_approval_activity_code = approval_records_runtime.approval_activity_code
_codex_execpolicy_amendment_from_rule = (
    approval_response_runtime.codex_execpolicy_amendment_from_rule
)
_permission_response_for_decision = approval_response_runtime.permission_response_for_decision
