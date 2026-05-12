from __future__ import annotations

from typing import Any, Callable, Mapping

from . import runtime_normalization_helpers_runtime as normalization_helpers_runtime
from . import runtime_pure_helpers_runtime as pure_helpers_runtime


def projected_tool_contracts(
    payload: Mapping[str, Any],
    *,
    project_tool_descriptors_fn: Callable[[Mapping[str, Any]], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    contracts = [
        normalization_helpers_runtime.normalized_projected_tool_contract(item)
        for item in project_tool_descriptors_fn(payload)
    ]
    contracts.sort(key=lambda item: item["name"])
    return contracts


def projected_tool_contract_map(
    payload: Mapping[str, Any],
    *,
    project_tool_descriptors_fn: Callable[[Mapping[str, Any]], list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    return {
        item["name"]: item
        for item in projected_tool_contracts(
            payload,
            project_tool_descriptors_fn=project_tool_descriptors_fn,
        )
    }


def approval_request_observability(contract: Mapping[str, Any]) -> dict[str, Any]:
    observability = normalization_helpers_runtime.normalized_observability_contract(
        contract.get("observability"),
        name=str(contract.get("name") or ""),
        server_name=str(contract.get("server_name") or ""),
        remote_name=str(contract.get("remote_name") or ""),
    )
    reason_codes = dict(observability.get("reason_codes") or {})
    return {
        "schema_version": int(observability.get("schema_version") or 1),
        "reason_code": str(
            reason_codes.get("pending") or normalization_helpers_runtime.OBSERVABILITY_REASON_CODES["pending"]
        ),
        "decision_trace": ["approval.requested", "approval.pending"],
        "latency_bucket_field": str(
            observability.get("latency_bucket_field") or normalization_helpers_runtime.OBSERVABILITY_LATENCY_BUCKET_FIELD
        ),
        "latency_bucket": "pending",
        "reason_codes": reason_codes,
        "tool_snapshot": dict(observability.get("tool_snapshot") or {}),
    }


def call_observability(
    result: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    latency_ms: int,
) -> dict[str, Any]:
    observability = normalization_helpers_runtime.normalized_observability_contract(
        contract.get("observability"),
        name=str(contract.get("name") or ""),
        server_name=str(contract.get("server_name") or ""),
        remote_name=str(contract.get("remote_name") or ""),
    )
    reason_codes = dict(observability.get("reason_codes") or {})
    outcome = pure_helpers_runtime.call_decision_outcome(result)
    reason_code = str(
        reason_codes.get(outcome)
        or reason_codes.get("rejected")
        or normalization_helpers_runtime.OBSERVABILITY_REASON_CODES["rejected"]
    )
    return {
        "schema_version": int(observability.get("schema_version") or 1),
        "decision_outcome": outcome,
        "reason_code": reason_code,
        "decision_trace": ["approval.requested", f"approval.{outcome}", "action.executed"],
        "latency_bucket_field": str(
            observability.get("latency_bucket_field") or normalization_helpers_runtime.OBSERVABILITY_LATENCY_BUCKET_FIELD
        ),
        "latency_ms": int(latency_ms),
        "latency_bucket": pure_helpers_runtime.call_latency_bucket(int(latency_ms)),
        "reason_codes": reason_codes,
        "tool_snapshot": dict(observability.get("tool_snapshot") or {}),
    }


def projected_tool_approval_request_payload(
    contract: Mapping[str, Any],
    *,
    arguments: Mapping[str, Any] | None = None,
    requested_by: str = "mcp.runtime",
    approval_summary: str = "",
    approval_reason: str = "",
) -> dict[str, Any]:
    target_name = str(contract.get("name") or "").strip()
    server_name = str(contract.get("server_name") or "").strip()
    request_observability = approval_request_observability(contract)
    approval = pure_helpers_runtime.approval_metadata(contract)
    return {
        "action_type": "mcp.tool.call",
        "connector_key": pure_helpers_runtime.connector_key(server_name),
        "plugin_name": "mcp_runtime",
        "requested_by": str(requested_by or "mcp.runtime"),
        "request_payload": {
            "action": "mcp.tool.call",
            "projected_name": target_name,
            "arguments": dict(arguments or {}),
            "tool_contract": dict(contract),
            "observability": dict(request_observability),
        },
        "approval_summary": str(approval_summary or "").strip() or f"Approve MCP tool call {target_name}",
        "approval_reason": str(approval_reason or "").strip() or f"MCP tool call requires approval: {target_name}",
        "metadata": {
            "tool_contract": dict(contract),
            "approval": approval,
            "observability": dict(request_observability),
        },
    }


def apply_projected_tool_call_projection(
    result: dict[str, Any],
    *,
    contract: Mapping[str, Any],
    latency_ms: int,
) -> dict[str, Any]:
    result["tool_contract"] = dict(contract)
    result["approval"] = pure_helpers_runtime.approval_metadata(contract)
    result["observability"] = call_observability(
        result,
        contract=contract,
        latency_ms=latency_ms,
    )
    return result
