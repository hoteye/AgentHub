from __future__ import annotations

from typing import Any, Callable


def required_payload_text(payload: dict[str, Any]) -> str:
    return str(payload.get("text") or "").strip()


def payload_limit(payload: dict[str, Any], *, default: int) -> int:
    return max(1, int(payload.get("limit") or default))


def payload_trace_id(payload: dict[str, Any]) -> str:
    return str(payload.get("trace_id") or "").strip()


def thread_list_payload(
    threads: list[dict[str, Any]],
    *,
    loaded_thread_id: str | None,
    active_thread_id: str | None,
    describe_thread_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return {
        "threads": [
            describe_thread_fn(
                item,
                status="idle" if str(item.get("thread_id") or "") == str(loaded_thread_id or "") else "not_loaded",
                turns=[],
            )
            for item in threads
        ],
        "active_thread_id": str(active_thread_id or "") or None,
    }


def resume_diagnostics(*, thread: dict[str, Any], thread_id: str, resumed: dict[str, Any]) -> dict[str, Any]:
    return {
        "selected_source": str(resumed.get("resume_source") or "thread_id"),
        "selected_thread_id": str(thread.get("thread_id") or thread_id),
        "selected_path": thread.get("path"),
        "precedence": ["history", "path", "thread_id"],
        "requested": {
            "thread_id": thread_id,
            "path": None,
            "history_count": 0,
        },
        "ignored_sources": [],
    }


def thread_resume_payload(
    *,
    resumed: dict[str, Any],
    thread: dict[str, Any],
    thread_id: str,
    thread_history_turn_payload_fn: Callable[[dict[str, Any]], dict[str, Any]],
    runtime_snapshot: dict[str, Any],
) -> dict[str, Any]:
    history = list(resumed.get("history") or [])
    turns = list(resumed.get("turns") or [])
    return {
        "thread": thread,
        "history": [
            {
                "role": str(item.get("role") or ""),
                "content": str(item.get("content") or ""),
            }
            for item in history
            if isinstance(item, dict)
        ],
        "turns": [
            thread_history_turn_payload_fn(item)
            for item in turns
            if isinstance(item, dict)
        ],
        "state": dict(resumed.get("state") or {}),
        "resume_diagnostics": resume_diagnostics(thread=thread, thread_id=thread_id, resumed=resumed),
        "runtime": runtime_snapshot,
    }


def normalize_gateway_action_payload(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    bridge_aliases = {
        "approvals.resolve": {
            "decision": {
                "approved": "approve",
                "rejected": "reject",
            }
        }
    }
    canonical_payload = dict(payload or {})
    if action in bridge_aliases:
        decision_map = bridge_aliases[action].get("decision", {})
        decision_value = str(canonical_payload.get("decision") or "").strip().lower()
        if decision_value in decision_map:
            canonical_payload["decision"] = decision_map[decision_value]
    return canonical_payload


def gateway_error_detail(result: Any) -> dict[str, Any]:
    detail = dict(result.error_data or {})
    detail.setdefault("http_code", int(result.error_code or -32000))
    return detail


def audit_records_payload(snapshot: dict[str, Any], *, trace_id: str) -> dict[str, Any]:
    records = []
    for item in snapshot.get("audit_records") or []:
        if trace_id and str(getattr(item, "trace_id", "") or "") != trace_id:
            continue
        records.append(
            {
                "trace_id": getattr(item, "trace_id", ""),
                "stage": getattr(item, "stage", ""),
                "status": getattr(item, "status", ""),
                "summary": getattr(item, "summary", ""),
                "action_id": getattr(item, "action_id", None),
                "approval_id": getattr(item, "approval_id", None),
                "details": dict(getattr(item, "details", {}) or {}),
                "metadata": dict(getattr(item, "metadata", {}) or {}),
            }
        )
    return {"records": records}


def plugin_list_payload(plugins: list[Any], *, normalize_plugin_summary_fn) -> dict[str, Any]:
    return {
        "plugins": [
            normalize_plugin_summary_fn(item)
            for item in plugins
        ]
    }


def connector_routed_payload(routed_payload: dict[str, Any], *, runtime_policy_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "connectors": [dict(item) for item in list(routed_payload.get("connectors") or []) if isinstance(item, dict)],
        "runtimeRegistry": dict(routed_payload.get("runtimeRegistry") or {}),
        "runtimePolicy": dict(routed_payload.get("runtimePolicy") or {}) or runtime_policy_status,
    }


def plugin_state_map(plugins: list[dict[str, Any]]) -> dict[str, bool]:
    return {item["plugin_id"]: bool(item.get("enabled")) for item in plugins}


def connector_fallback_payload(
    *,
    registry: Any,
    approval_policy: str,
    plugin_state: dict[str, bool],
    plugin_manager_entries: list[dict[str, Any]],
    gateway_connector_contract_item_fn,
    app_connector_contract_item_fn,
) -> dict[str, Any]:
    connectors = []
    seen_connector_keys: set[str] = set()
    for item in registry.list_connectors():
        plugin_name = str(getattr(item, "plugin_name", "") or "").strip()
        connector_item = gateway_connector_contract_item_fn(
            item,
            approval_policy=approval_policy,
            plugin_enabled=plugin_state.get(plugin_name, True),
        )
        if connector_item is None:
            continue
        connector_key = str(connector_item.get("connector_key") or connector_item.get("connector_id") or "").strip()
        if not connector_key:
            continue
        seen_connector_keys.add(connector_key)
        connectors.append(dict(connector_item))
    for item in plugin_manager_entries:
        plugin_name = str(item.get("plugin_name") or item.get("pluginName") or "").strip()
        connector_item = app_connector_contract_item_fn(
            item,
            approval_policy=approval_policy,
            plugin_enabled=plugin_state.get(plugin_name, True),
        )
        if connector_item is None:
            continue
        connector_key = str(connector_item.get("connector_key") or connector_item.get("connector_id") or "").strip()
        if not connector_key or connector_key in seen_connector_keys:
            continue
        seen_connector_keys.add(connector_key)
        connectors.append(dict(connector_item))
    return {"connectors": connectors}


def plugin_mutation_result_payload(
    *,
    payload_map: dict[str, Any],
    plugins: list[dict[str, Any]],
    plugin_name: str,
    operation: str,
) -> dict[str, Any]:
    selected_plugin = None
    if plugin_name:
        selected_plugin = next((item for item in plugins if item["plugin_id"] == plugin_name), None)
    if selected_plugin is None and payload_map.get("plugin_name"):
        selected_plugin = {
            "plugin_id": str(payload_map.get("plugin_name") or ""),
            "title": str(payload_map.get("plugin_name") or ""),
            "enabled": bool(payload_map.get("enabled")),
            "health": "ready" if bool(payload_map.get("ok")) and bool(payload_map.get("enabled", True)) else "warning",
        }
    return {
        "accepted": True,
        "plugin": selected_plugin,
        "plugins": plugins,
        "operation": operation,
    }
