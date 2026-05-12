from __future__ import annotations

from collections.abc import Callable
from typing import Any


def build_request_scope(
    *,
    gateway_request_scope_fn: Callable[..., Any],
    request_id: str,
    action: str,
    payload: dict[str, Any],
) -> Any:
    normalized_action = str(action or "").strip()
    request_payload = dict(payload or {})
    return gateway_request_scope_fn(
        request_id=request_id,
        method=f"gui.{normalized_action or 'unknown'}",
        ingress_kind="gui_bridge",
        actor_id=str(request_payload.get("actor_id") or "gui.operator"),
        trace_id=str(request_payload.get("trace_id") or "").strip() or None,
        correlation_id=str(request_payload.get("correlation_id") or request_id).strip() or None,
        client_id="gui_http_server",
        auth={"role": "operator", "authenticated": True},
        metadata={"action": normalized_action},
    )


def dispatch_action(
    *,
    runtime: Any,
    action: str,
    request_id: str,
    payload: dict[str, Any],
    browser: Any,
    proxy: Any,
    gateway_dispatch_fn: Callable[..., dict[str, Any]],
    task_run_fn: Callable[..., dict[str, Any]],
    shell_run_fn: Callable[..., dict[str, Any]],
    task_stop_fn: Callable[..., dict[str, Any]],
    chat_send_fn: Callable[..., dict[str, Any]],
    thread_list_fn: Callable[..., dict[str, Any]],
    thread_resume_fn: Callable[..., dict[str, Any]],
    browser_workflow_action_fn: Callable[..., dict[str, Any]],
    browser_action_fn: Callable[..., dict[str, Any]],
    approval_list_fn: Callable[..., dict[str, Any]],
    approval_resolve_fn: Callable[..., dict[str, Any]],
    audit_list_fn: Callable[..., dict[str, Any]],
    plugin_list_fn: Callable[..., dict[str, Any]],
    connector_list_fn: Callable[..., dict[str, Any]],
    plugin_enable_fn: Callable[..., dict[str, Any]],
    plugin_disable_fn: Callable[..., dict[str, Any]],
    plugin_reload_fn: Callable[..., dict[str, Any]],
    settings_get_fn: Callable[..., dict[str, Any]],
    settings_update_fn: Callable[..., dict[str, Any]],
    error_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    normalized_action = str(action or "").strip()
    request_payload = dict(payload or {})
    if normalized_action in gateway_dispatch_actions():
        return gateway_dispatch_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "task.run":
        return task_run_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "shell.run":
        return shell_run_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "task.stop":
        return task_stop_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "chat.send":
        return chat_send_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "thread.list":
        return thread_list_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "thread.resume":
        return thread_resume_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action.startswith(("browser.workflow.", "browser.playbook.")):
        return browser_workflow_action_fn(
            runtime,
            browser,
            proxy,
            request_id=request_id,
            action=normalized_action,
            payload=request_payload,
        )
    if normalized_action.startswith("browser."):
        return browser_action_fn(
            browser,
            proxy,
            request_id=request_id,
            action=normalized_action,
            payload=request_payload,
        )
    if normalized_action == "approval.list":
        return approval_list_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "approval.resolve":
        return approval_resolve_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "audit.list":
        return audit_list_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "plugin.list":
        return plugin_list_fn(runtime, request_id=request_id, action=normalized_action)
    if normalized_action == "connector.list":
        return connector_list_fn(runtime, request_id=request_id, action=normalized_action)
    if normalized_action == "plugin.enable":
        return plugin_enable_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "plugin.disable":
        return plugin_disable_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "plugin.reload":
        return plugin_reload_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    if normalized_action == "settings.get":
        return settings_get_fn(runtime, request_id=request_id, action=normalized_action)
    if normalized_action == "settings.update":
        return settings_update_fn(
            runtime, request_id=request_id, action=normalized_action, payload=request_payload
        )
    return error_fn(
        request_id=request_id,
        action=normalized_action,
        code=f"{normalized_action}.unsupported",
        message=f"unsupported gui bridge action: {normalized_action}",
    )


def gateway_dispatch_actions() -> set[str]:
    return {
        "connect.initialize",
        "connect.capabilities",
        "connect.ping",
        "nodes.list",
        "config.validate",
        "config.apply",
        "config.restart.report",
        "health.get",
        "health.probes",
        "logs.tail",
        "gateway.state.get",
        "gateway.events.list",
        "gateway.workflows.list",
        "gateway.trace.timeline",
        "workflows.list",
        "workflows.get",
        "workflows.resume",
        "approvals.list",
        "approvals.get",
        "approvals.resolve",
        "browser.proxy",
    }
