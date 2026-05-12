from __future__ import annotations

from typing import Any, Mapping

from . import runtime_pure_helpers_runtime as pure_helpers_runtime

OBSERVABILITY_REASON_CODES = {
    "pending": "approval.pending",
    "approved": "approval.approved",
    "rejected": "approval.rejected",
    "timed_out": "approval.timed_out",
    "expired": "approval.expired",
}
OBSERVABILITY_DECISION_TRACE_TEMPLATE = [
    "approval.requested",
    "approval.decided",
    "action.executed",
]
OBSERVABILITY_TOOL_SNAPSHOT_FIELDS = [
    "projected_name",
    "server_name",
    "remote_name",
    "connector_key",
    "approval_scope",
]
OBSERVABILITY_LATENCY_BUCKET_FIELD = "approval_latency_bucket"


def default_observability_contract(*, name: str, server_name: str, remote_name: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "decision_trace_template": list(OBSERVABILITY_DECISION_TRACE_TEMPLATE),
        "reason_codes": dict(OBSERVABILITY_REASON_CODES),
        "latency_bucket_field": OBSERVABILITY_LATENCY_BUCKET_FIELD,
        "tool_snapshot_fields": list(OBSERVABILITY_TOOL_SNAPSHOT_FIELDS),
        "tool_snapshot": {
            "projected_name": name,
            "server_name": server_name,
            "remote_name": remote_name,
            "connector_key": pure_helpers_runtime.connector_key(server_name),
            "approval_scope": pure_helpers_runtime.approval_scope(server_name),
        },
    }


def normalized_observability_contract(
    observability: Any,
    *,
    name: str,
    server_name: str,
    remote_name: str,
) -> dict[str, Any]:
    base = default_observability_contract(
        name=name,
        server_name=server_name,
        remote_name=remote_name,
    )
    if not isinstance(observability, Mapping):
        return base
    normalized = dict(base)
    normalized.update(dict(observability))
    reason_codes = observability.get("reason_codes")
    if isinstance(reason_codes, Mapping):
        merged_reason_codes = dict(base["reason_codes"])
        merged_reason_codes.update(
            {
                str(key): str(value)
                for key, value in dict(reason_codes).items()
                if str(key).strip() and str(value).strip()
            }
        )
        normalized["reason_codes"] = merged_reason_codes
    trace_template = observability.get("decision_trace_template")
    if isinstance(trace_template, list):
        normalized["decision_trace_template"] = [str(item) for item in trace_template if str(item).strip()] or list(
            base["decision_trace_template"]
        )
    snapshot_fields = observability.get("tool_snapshot_fields")
    if isinstance(snapshot_fields, list):
        normalized["tool_snapshot_fields"] = [str(item) for item in snapshot_fields if str(item).strip()] or list(
            base["tool_snapshot_fields"]
        )
    tool_snapshot = observability.get("tool_snapshot")
    if isinstance(tool_snapshot, Mapping):
        merged_snapshot = dict(base["tool_snapshot"])
        merged_snapshot.update(dict(tool_snapshot))
        normalized["tool_snapshot"] = merged_snapshot
    return normalized


def normalized_projected_tool_contract(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    name = str(descriptor.get("name") or "").strip()
    server_name = str(descriptor.get("server_name") or "").strip()
    remote_name = str(descriptor.get("remote_name") or "").strip()
    return {
        "name": name,
        "type": str(descriptor.get("type") or "mcp_tool"),
        "tool_family": str(descriptor.get("tool_family") or "mcp_remote"),
        "source": str(descriptor.get("source") or "mcp"),
        "server_name": server_name,
        "remote_name": remote_name,
        "requires_confirmation": bool(descriptor.get("requires_confirmation", True)),
        "mutates_ui": bool(descriptor.get("mutates_ui", False)),
        "approval_required": bool(descriptor.get("approval_required", True)),
        "approval_family": str(descriptor.get("approval_family") or "mcp_tool_call"),
        "approval_scope": str(descriptor.get("approval_scope") or pure_helpers_runtime.approval_scope(server_name)),
        "observability": normalized_observability_contract(
            descriptor.get("observability"),
            name=name,
            server_name=server_name,
            remote_name=remote_name,
        ),
    }
