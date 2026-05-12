from __future__ import annotations

from typing import Any

from cli.agent_cli.gateway_api import gui_bridge_action_runtime as gui_bridge_action_runtime_service
from cli.agent_cli.gateway_api import gui_bridge_api_runtime as gui_bridge_api_runtime_service
from cli.agent_cli.gateway_api.gui_bridge_browser import (
    approval_list as _approval_list_handler,
)
from cli.agent_cli.gateway_api.gui_bridge_browser import (
    approval_resolve as _approval_resolve_handler,
)
from cli.agent_cli.gateway_api.gui_bridge_browser import (
    browser_action as _browser_action_handler,
)
from cli.agent_cli.gateway_api.gui_bridge_browser import (
    browser_workflow_action as _browser_workflow_action_handler,
)
from cli.agent_cli.gateway_server.dispatcher import dispatch_gateway_method
from cli.agent_cli.gateway_server.request_scope import (
    gateway_request_scope,
    get_gateway_request_scope,
    with_gateway_request_scope,
)
from shared.web_automation.client import BrowserClient
from shared.web_automation.proxy import BrowserProxyExecutor


def gui_bridge_success(
    *,
    request_id: str,
    action: str,
    data: Any,
) -> dict[str, Any]:
    return {
        "protocol_version": "v1",
        "request_id": str(request_id),
        "action": str(action),
        "ok": True,
        "data": data,
        "error": None,
    }


def gui_bridge_error(
    *,
    request_id: str,
    action: str,
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "protocol_version": "v1",
        "request_id": str(request_id),
        "action": str(action),
        "ok": False,
        "data": None,
        "error": {
            "code": str(code),
            "message": str(message),
            "detail": dict(detail or {}),
            "retryable": bool(retryable),
        },
    }


def dispatch_gui_bridge_action(
    runtime,
    *,
    action: str,
    payload: dict[str, Any] | None = None,
    request_id: str = "req_gui_bridge",
    browser_client: BrowserClient | None = None,
    browser_proxy: BrowserProxyExecutor | None = None,
) -> dict[str, Any]:
    normalized_action = str(action or "").strip()
    request_payload = dict(payload or {})
    browser = browser_client or BrowserClient()
    proxy = browser_proxy or BrowserProxyExecutor()
    scope = gui_bridge_api_runtime_service.build_request_scope(
        gateway_request_scope_fn=gateway_request_scope,
        request_id=request_id,
        action=normalized_action,
        payload=request_payload,
    )

    def _run() -> dict[str, Any]:
        return gui_bridge_api_runtime_service.dispatch_action(
            runtime=runtime,
            action=normalized_action,
            request_id=request_id,
            payload=request_payload,
            browser=browser,
            proxy=proxy,
            gateway_dispatch_fn=_gateway_dispatch,
            task_run_fn=_task_run,
            shell_run_fn=_shell_run,
            task_stop_fn=_task_stop,
            chat_send_fn=_chat_send,
            thread_list_fn=_thread_list,
            thread_resume_fn=_thread_resume,
            browser_workflow_action_fn=_browser_workflow_action,
            browser_action_fn=_browser_action,
            approval_list_fn=_approval_list,
            approval_resolve_fn=_approval_resolve,
            audit_list_fn=_audit_list,
            plugin_list_fn=_plugin_list,
            connector_list_fn=_connector_list,
            plugin_enable_fn=_plugin_enable,
            plugin_disable_fn=_plugin_disable,
            plugin_reload_fn=_plugin_reload,
            settings_get_fn=_settings_get,
            settings_update_fn=_settings_update,
            error_fn=gui_bridge_error,
        )

    try:
        return with_gateway_request_scope(scope, _run)
    except Exception as exc:
        return gui_bridge_error(
            request_id=request_id,
            action=normalized_action,
            code=f"{normalized_action}.failed",
            message=str(exc),
        )


def _task_run(runtime, *, request_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.task_run(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
        error=gui_bridge_error,
    )


def _shell_run(runtime, *, request_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.shell_run(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
        error=gui_bridge_error,
    )


def _task_stop(runtime, *, request_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.task_stop(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
        error=gui_bridge_error,
    )


def _chat_send(runtime, *, request_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.chat_send(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
        error=gui_bridge_error,
    )


def _thread_list(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.thread_list(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
    )


def _thread_resume(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.thread_resume(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
        error=gui_bridge_error,
    )


def _gateway_dispatch(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.gateway_dispatch(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        dispatch_gateway_method_fn=dispatch_gateway_method,
        success=gui_bridge_success,
        error=gui_bridge_error,
    )


def _browser_workflow_action(
    runtime,
    browser: BrowserClient,
    proxy: BrowserProxyExecutor,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return _browser_workflow_action_handler(
        runtime,
        browser,
        proxy,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
        error=gui_bridge_error,
        get_gateway_request_scope_fn=get_gateway_request_scope,
    )


def _browser_action(
    browser: BrowserClient,
    proxy: BrowserProxyExecutor,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return _browser_action_handler(
        browser,
        proxy,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
        error=gui_bridge_error,
    )


def _approval_list(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return _approval_list_handler(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
    )


def _approval_resolve(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return _approval_resolve_handler(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
        error=gui_bridge_error,
    )


def _audit_list(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.audit_list(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
    )


def _plugin_list(runtime, *, request_id: str, action: str) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.plugin_list(
        runtime,
        request_id=request_id,
        action=action,
        success=gui_bridge_success,
    )


def _connector_list(runtime, *, request_id: str, action: str) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.connector_list(
        runtime,
        request_id=request_id,
        action=action,
        dispatch_gateway_method_fn=dispatch_gateway_method,
        success=gui_bridge_success,
    )


def _settings_get(runtime, *, request_id: str, action: str) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.settings_get(
        runtime,
        request_id=request_id,
        action=action,
        success=gui_bridge_success,
    )


def _plugin_enable(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return _plugin_mutation(
        runtime, request_id=request_id, action=action, payload=payload, operation="enable"
    )


def _plugin_disable(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return _plugin_mutation(
        runtime, request_id=request_id, action=action, payload=payload, operation="disable"
    )


def _plugin_reload(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return _plugin_mutation(
        runtime, request_id=request_id, action=action, payload=payload, operation="reload"
    )


def _plugin_mutation(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.plugin_mutation(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        operation=operation,
        success=gui_bridge_success,
        error=gui_bridge_error,
    )


def _settings_update(
    runtime, *, request_id: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return gui_bridge_action_runtime_service.settings_update(
        runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        success=gui_bridge_success,
    )
