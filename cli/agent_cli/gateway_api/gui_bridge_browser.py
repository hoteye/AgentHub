from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.gateway_api import (
    gui_bridge_browser_request_runtime as gui_bridge_browser_request_runtime_service,
    gui_bridge_browser_workflow_runtime as gui_bridge_browser_workflow_runtime_service,
)
from shared.web_automation.client import BrowserClient
from shared.web_automation.proxy import BrowserProxyExecutor

_BROWSER_WORKFLOW_PLUGIN = "easyclaw_browser"
_BROWSER_WORKFLOW_CONNECTOR = "gui_browser"


def browser_workflow_action(
    runtime: Any,
    browser: BrowserClient,
    proxy: BrowserProxyExecutor,
    *,
    request_id: str,
    action: str,
    payload: Dict[str, Any],
    success: Callable[..., Dict[str, Any]],
    error: Callable[..., Dict[str, Any]],
    get_gateway_request_scope_fn: Callable[[], Any],
) -> Dict[str, Any]:
    workflow_name = action.split(".", 2)[2] if action.count(".") >= 2 else ""
    if workflow_name == "verify":
        return gui_bridge_browser_workflow_runtime_service.browser_workflow_verify(
            runtime,
            request_id=request_id,
            action=action,
            payload=payload,
            success=success,
            browser_request=_browser_request_from_gui_payload(payload, default_action="snapshot"),
            browser_workflow_plugin=_BROWSER_WORKFLOW_PLUGIN,
            browser_workflow_connector=_BROWSER_WORKFLOW_CONNECTOR,
            get_gateway_request_scope_fn=get_gateway_request_scope_fn,
        )
    if workflow_name == "mutate":
        browser_request = _browser_request_from_gui_payload(payload, default_action="act")
        return gui_bridge_browser_workflow_runtime_service.browser_workflow_mutate(
            runtime,
            request_id=request_id,
            action=action,
            payload=payload,
            success=success,
            browser_request=browser_request,
            action_type=gui_bridge_browser_request_runtime_service.browser_action_type_from_request(
                browser_request
            ),
            browser_workflow_plugin=_BROWSER_WORKFLOW_PLUGIN,
            browser_workflow_connector=_BROWSER_WORKFLOW_CONNECTOR,
            get_gateway_request_scope_fn=get_gateway_request_scope_fn,
        )
    return error(
        request_id=request_id,
        action=action,
        code=f"{action}.unsupported",
        message=f"unsupported browser workflow action: {action}",
    )


def browser_action(
    browser: BrowserClient,
    proxy: BrowserProxyExecutor,
    *,
    request_id: str,
    action: str,
    payload: Dict[str, Any],
    success: Callable[..., Dict[str, Any]],
    error: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    command = action.split(".", 1)[1]
    if command == "proxy":
        result = proxy.run(**gui_bridge_browser_request_runtime_service.browser_proxy_params(payload))
        return success(request_id=request_id, action=action, data=result)
    result = browser.perform(
        **gui_bridge_browser_request_runtime_service.browser_client_params(payload, command=command)
    )
    if bool(result.get("ok")):
        return success(request_id=request_id, action=action, data=result)
    return error(
        request_id=request_id,
        action=action,
        code=f"{action}.failed",
        message=str(result.get("error") or result.get("message") or "browser action failed"),
        detail=result,
    )


def approval_list(
    runtime: Any,
    *,
    request_id: str,
    action: str,
    payload: Dict[str, Any],
    success: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    limit = max(1, int(payload.get("limit") or 20))
    status = str(payload.get("status") or "pending").strip() or None
    tickets = runtime.list_approval_tickets(limit=limit, status=status)
    diagnostics_getter = getattr(runtime, "list_approval_diagnostics", None)
    diagnostics = diagnostics_getter(limit=limit, status=status) if callable(diagnostics_getter) else []
    return success(request_id=request_id, action=action, data=gui_bridge_browser_workflow_runtime_service.approval_list_data(tickets=tickets, diagnostics=diagnostics))


def approval_resolve(
    runtime: Any,
    *,
    request_id: str,
    action: str,
    payload: Dict[str, Any],
    success: Callable[..., Dict[str, Any]],
    error: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    approval_id = str(payload.get("approval_id") or "").strip()
    raw_decision = payload.get("decision")
    try:
        normalized_decision = approval_contract_runtime.normalize_approval_decision(raw_decision)
    except ValueError:
        normalized_decision = None
    if not approval_id or normalized_decision is None:
        return error(
            request_id=request_id,
            action=action,
            code="approval.resolve.invalid_payload",
            message="approval_id and a supported decision are required",
        )
    result = runtime.decide_approval(
        approval_id,
        decision=normalized_decision,
        decided_by=str(payload.get("decided_by") or "easyclaw-gui"),
        decision_note=str(payload.get("decision_note") or ""),
    )
    return success(
        request_id=request_id,
        action=action,
        data=gui_bridge_browser_workflow_runtime_service.approval_resolve_data(
            approval_id=approval_id,
            decision=str(normalized_decision.get("type") or ""),
            result=result,
        ),
    )


def _browser_request_from_gui_payload(
    payload: Dict[str, Any],
    *,
    default_action: str,
) -> Dict[str, Any]:
    return gui_bridge_browser_request_runtime_service.browser_request_from_gui_payload(
        payload,
        default_action=default_action,
    )
