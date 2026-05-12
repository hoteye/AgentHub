from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli import __version__
from cli.agent_cli.gateway_server.access_posture_contract import build_access_posture_summary


CONTROL_UI_BOOTSTRAP_CONFIG_PATH = "/__agenthub/control-ui-config.json"


def _provider_status(runtime: Any) -> dict[str, Any]:
    agent = getattr(runtime, "agent", None)
    provider_status = getattr(agent, "provider_status", None)
    if callable(provider_status):
        return dict(provider_status() or {})
    return {}


def build_control_ui_bootstrap(
    runtime: Any,
    *,
    base_path: str = "/gui",
) -> Dict[str, Any]:
    from cli.agent_cli.gateway_server.dispatcher import gateway_dispatcher_methods

    provider_status = _provider_status(runtime)
    return {
        "basePath": str(base_path.rstrip("/") or "/gui"),
        "assistantName": "AgentHub",
        "assistantAvatar": "",
        "assistantAgentId": "agenthub",
        "serverVersion": __version__,
        "providerLabel": str(provider_status.get("provider_label") or ""),
        "gateway": {
            "methods": list(gateway_dispatcher_methods()),
            "streams": ["gateway_events", "workflow_runs", "approvals", "audit"],
        },
    }


def build_control_ui_state_snapshot(
    runtime: Any,
    *,
    limit: int = 20,
) -> Dict[str, Any]:
    safe_limit = max(1, int(limit))
    snapshot = dict(getattr(runtime, "gateway_state_snapshot")(limit=safe_limit) or {})
    gateway_registry_getter = getattr(runtime, "gateway_registry", None)
    registry = gateway_registry_getter() if callable(gateway_registry_getter) else None
    connectors = []
    if registry is not None:
        connectors = [item.to_dict() if hasattr(item, "to_dict") else dict(item or {}) for item in registry.list_connectors()]
    runtime_policy_status = getattr(runtime, "runtime_policy_status", None)
    approval_status = getattr(runtime, "approval_status", None)
    access_posture = build_access_posture_summary(runtime)
    diagnostics = dict(snapshot.get("diagnostics") or {})
    diagnostics.setdefault("access_posture", access_posture)
    diagnostics.setdefault("pairing_summary", dict(access_posture.get("pairing") or {}))
    return {
        "health": {
            "status": "ok",
            "provider": _provider_status(runtime),
        },
        "runtimePolicy": runtime_policy_status() if callable(runtime_policy_status) else {},
        "approvalStatus": approval_status() if callable(approval_status) else {},
        "events": [item.to_dict() if hasattr(item, "to_dict") else dict(item or {}) for item in snapshot.get("events") or []],
        "workflowRuns": [
            item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
            for item in snapshot.get("workflow_runs") or []
        ],
        "actionRequests": [
            item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
            for item in snapshot.get("action_requests") or []
        ],
        "approvalTickets": [
            item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
            for item in snapshot.get("approval_tickets") or []
        ],
        "auditRecords": [
            item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
            for item in snapshot.get("audit_records") or []
        ],
        "diagnostics": diagnostics,
        "accessPosture": access_posture,
        "connectors": connectors,
    }


__all__ = [
    "CONTROL_UI_BOOTSTRAP_CONFIG_PATH",
    "build_control_ui_bootstrap",
    "build_control_ui_state_snapshot",
]
