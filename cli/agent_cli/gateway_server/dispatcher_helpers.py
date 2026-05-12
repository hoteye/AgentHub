from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from cli.agent_cli.tools_core.registry import runtime_registry_app_connector_entries, runtime_registry_mcp_server_entries

JsonMap = dict[str, Any]


def runtime_registry_payload(runtime: Any) -> JsonMap:
    tools = getattr(runtime, "tools", None)
    getter = getattr(tools, "capabilities", None)
    payload = getter() if callable(getter) else {}
    capabilities = dict(payload) if isinstance(payload, dict) else {}
    plugin_manager = getattr(tools, "_plugin_manager", None)
    mcp_servers = runtime_registry_mcp_server_entries(
        plugin_manager,
        runtime_capabilities=capabilities,
    )
    app_connectors = runtime_registry_app_connector_entries(
        plugin_manager,
        runtime_capabilities=capabilities,
    )
    return {
        "workspaceTrust": str(capabilities.get("workspace_trust") or "trusted"),
        "mcpServers": list(mcp_servers),
        "appConnectors": list(app_connectors),
        "toolCount": int(capabilities.get("count") or 0),
        "source": "tools.capabilities" if bool(capabilities) else "runtime",
    }


def available_log_sources(runtime: Any) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    gateway_state_store = getattr(runtime, "gateway_state_store", None)
    base_dir = getattr(gateway_state_store, "base_dir", None)
    if base_dir:
        gateway_root = Path(base_dir)
        for key, filename, label in (
            ("gateway.events", "events.jsonl", "Gateway Events"),
            ("gateway.workflow_runs", "workflow_runs.jsonl", "Gateway Workflow Runs"),
            ("gateway.action_requests", "action_requests.jsonl", "Gateway Action Requests"),
            ("gateway.approval_tickets", "approval_tickets.jsonl", "Gateway Approval Tickets"),
            ("gateway.audit_records", "audit_records.jsonl", "Gateway Audit Records"),
        ):
            candidate = gateway_root / filename
            if candidate.exists():
                sources[key] = {"label": label, "path": candidate}
    thread_store = getattr(runtime, "thread_store", None)
    if thread_store is not None:
        active_thread_id = getattr(thread_store, "get_active_thread_id", None)
        get_thread = getattr(thread_store, "get_thread", None)
        thread_id = active_thread_id() if callable(active_thread_id) else None
        record = get_thread(thread_id) if callable(get_thread) and thread_id else None
        rollout_path = Path(str((record or {}).get("rollout_path") or "")).expanduser() if record else None
        if rollout_path and rollout_path.exists():
            sources["thread.active_rollout"] = {"label": "Active Thread Rollout", "path": rollout_path}
    return sources


def tail_text_lines(path: Path, *, limit: int) -> tuple[list[str], bool]:
    recent: deque[str] = deque(maxlen=max(1, int(limit)))
    total = 0
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            total += 1
            recent.append(raw_line.rstrip("\n"))
    return list(recent), total > len(recent)
