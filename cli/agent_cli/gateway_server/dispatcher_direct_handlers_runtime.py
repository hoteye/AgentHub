from __future__ import annotations

from cli.agent_cli import approval_contract_runtime

from typing import Any


JsonMap = dict[str, Any]


def legacy_methods(legacy_only_methods: set[str], legacy_method_aliases: dict[str, str]) -> list[str]:
    return sorted(legacy_only_methods | set(legacy_method_aliases))


def connect_initialize_payload(
    *,
    protocol_version: str,
    version: str,
    capabilities: JsonMap,
) -> JsonMap:
    return {
        "protocolVersion": protocol_version,
        "serverInfo": {
            "name": "agenthub_gateway_dispatcher",
            "version": version,
        },
        **capabilities,
    }


def health_get_payload(provider_status: JsonMap) -> JsonMap:
    return {
        "status": "ok",
        "runtime": {
            "providerLabel": provider_status.get("provider_label") or "-",
            "platformFamily": provider_status.get("platform_family") or "-",
            "platformOs": provider_status.get("platform_os") or "-",
            "shellKind": provider_status.get("shell_kind") or "-",
        },
    }


def health_probes_payload(snapshot: JsonMap) -> JsonMap:
    return {
        "status": "ok",
        "probes": {
            "runtime": {"ok": True},
            "gatewayStateStore": {
                "ok": True,
                "events": len(snapshot.get("events") or []),
                "workflowRuns": len(snapshot.get("workflow_runs") or []),
                "approvalTickets": len(snapshot.get("approval_tickets") or []),
            },
        },
    }


def log_sources_payload(sources: JsonMap) -> list[JsonMap]:
    return [
        {
            "key": key,
            "label": meta["label"],
            "path": str(meta["path"]),
        }
        for key, meta in sources.items()
    ]


def empty_logs_tail_payload() -> JsonMap:
    return {
        "source": "",
        "label": "No logs available",
        "path": None,
        "lines": [],
        "text": "",
        "lineCount": 0,
        "truncated": False,
        "availableSources": [],
    }


def logs_tail_payload(
    *,
    selected_source: str,
    source_meta: JsonMap,
    lines: list[str],
    truncated: bool,
    available_sources: list[JsonMap],
) -> JsonMap:
    return {
        "source": selected_source,
        "label": source_meta["label"],
        "path": str(source_meta["path"]),
        "lines": lines,
        "text": "\n".join(lines),
        "lineCount": len(lines),
        "truncated": truncated,
        "availableSources": available_sources,
    }


def gateway_event_kwargs(params: JsonMap, *, first_text_fn: Any) -> JsonMap:
    return {
        "event_type": first_text_fn(params, "eventType", "event_type"),
        "source_kind": first_text_fn(params, "sourceKind", "source_kind"),
        "source_id": first_text_fn(params, "sourceId", "source_id"),
        "payload": params.get("payload"),
        "metadata": params.get("metadata"),
        "connector_key": first_text_fn(params, "connectorKey", "connector_key") or None,
        "plugin_name": first_text_fn(params, "pluginName", "plugin_name") or None,
        "tenant_id": first_text_fn(params, "tenantId", "tenant_id") or None,
        "occurred_at": first_text_fn(params, "occurredAt", "occurred_at") or None,
        "received_at": first_text_fn(params, "receivedAt", "received_at") or None,
        "trace_id": first_text_fn(params, "traceId", "trace_id") or None,
        "correlation_id": first_text_fn(params, "correlationId", "correlation_id") or None,
        "causation_id": first_text_fn(params, "causationId", "causation_id") or None,
        "event_id": first_text_fn(params, "eventId", "event_id") or None,
    }


def gateway_state_payload(snapshot: JsonMap, *, gateway_item_to_dict_fn: Any) -> JsonMap:
    diagnostics = dict(snapshot.get("diagnostics") or {})
    return {
        "events": [gateway_item_to_dict_fn(item) for item in snapshot["events"]],
        "workflowRuns": [gateway_item_to_dict_fn(item) for item in snapshot["workflow_runs"]],
        "actionRequests": [gateway_item_to_dict_fn(item) for item in snapshot["action_requests"]],
        "approvalTickets": [gateway_item_to_dict_fn(item) for item in snapshot["approval_tickets"]],
        "auditRecords": [gateway_item_to_dict_fn(item) for item in snapshot["audit_records"]],
        "diagnostics": {
            "workflowDiagnostics": list(diagnostics.get("workflow_diagnostics") or []),
            "approvalDiagnostics": list(diagnostics.get("approval_diagnostics") or []),
        },
    }


def gateway_events_list_payload(result: JsonMap) -> JsonMap:
    return {"events": result.get("events") or []}


def gateway_workflows_list_payload(result: JsonMap) -> JsonMap:
    return {
        "workflowRuns": result.get("workflowRuns") or [],
        "actionRequests": result.get("actionRequests") or [],
        "diagnostics": dict(result.get("diagnostics") or {}),
    }


def normalize_approval_decision(decision: str) -> str:
    try:
        return str(approval_contract_runtime.normalize_approval_decision(decision).get("type") or "")
    except ValueError:
        return ""


def verification_payload(*, header_name: str, prefix: str) -> JsonMap:
    return {
        "verified": True,
        "headerName": header_name,
        "prefix": prefix,
    }
