from __future__ import annotations

from typing import Any, Callable
from importlib import import_module

from cli.agent_cli import __version__
from cli.agent_cli.gateway_api.approvals_api import approval_decision_result_to_camel_case
from cli.agent_cli.gateway_api.webhook_api import (
    build_webhook_event,
    parse_webhook_body,
    verify_webhook_signature,
)
from cli.agent_cli.gateway_core import create_audit_record, create_gateway_event
from cli.agent_cli.gateway_protocol import PROTOCOL_VERSION
from cli.agent_cli.gateway_server import admin_dispatchers
from cli.agent_cli.gateway_server.access_posture_contract import build_access_posture_summary
from cli.agent_cli.gateway_server import dispatcher_direct_handlers_runtime
from cli.agent_cli.gateway_server import dispatcher_direct_handlers_helper_runtime
from cli.agent_cli.gateway_server import dispatcher_direct_handlers_methods_helpers as dispatcher_direct_handlers_methods_helpers_service
from cli.agent_cli.gateway_server.dispatcher_runtime_payloads import (
    available_log_sources as _available_log_sources,
    capabilities_payload as _capabilities_payload,
    nodes_inventory_payload as _nodes_inventory_payload,
    runtime_registry_payload as _runtime_registry_payload,
    tail_text_lines as _tail_text_lines,
)
from cli.agent_cli.gateway_server.request_parsing import (
    first_int as _first_int,
    first_text as _first_text,
    resolve_gateway_auth_context as _resolve_gateway_auth_context,
)
from cli.agent_cli.gateway_server.response_builders import (
    gateway_dispatch_result_payload as _gateway_dispatch_result_payload,
    gateway_item_to_dict as _gateway_item_to_dict,
    sorted_trace_timeline as _sorted_trace_timeline,
    workflow_resume_eligible as _workflow_resume_eligible,
)
from cli.agent_cli.gateway_server.workflow_handlers import (
    WorkflowHandlerDeps,
    build_workflow_handler_family,
)
from cli.agent_cli.gateway_server.method_registry import GatewayServerMethodRegistry
from cli.agent_cli.gateway_server.dispatcher_direct_handlers_common import (
    GatewayDispatchResult,
    _failure,
    _success,
)
from cli.agent_cli.runtime_services import approval_continuation_runtime

JsonMap = dict[str, Any]

_LEGACY_METHOD_ALIASES: dict[str, str] = {
    "gateway/state": "gateway.state.get",
    "approval/list": "approvals.list",
    "approval/decide": "approvals.resolve",
    "browser/proxy": "browser.proxy",
}
_LEGACY_ONLY_METHODS = {
    "gateway/dispatch",
    "gateway/webhook",
}

_gateway_method_registry: GatewayServerMethodRegistry | None = None


def configure_gateway_method_registry(registry: GatewayServerMethodRegistry) -> None:
    global _gateway_method_registry
    _gateway_method_registry = registry


def gateway_method_registry() -> GatewayServerMethodRegistry:
    if _gateway_method_registry is None:
        raise RuntimeError("gateway_method_registry has not been configured")
    return _gateway_method_registry


def _handle_connect_initialize(**kwargs: Any) -> JsonMap:
    runtime = kwargs["runtime"]
    auth = _resolve_gateway_auth_context(kwargs.get("client_info"))
    capabilities_inputs = dispatcher_direct_handlers_helper_runtime.capabilities_inputs(
        registry_items=gateway_method_registry().list(),
        legacy_methods=dispatcher_direct_handlers_runtime.legacy_methods(_LEGACY_ONLY_METHODS, _LEGACY_METHOD_ALIASES),
    )
    capabilities = _capabilities_payload(
        runtime=runtime,
        auth=auth,
        method_entries=capabilities_inputs["method_entries"],
        legacy_methods=capabilities_inputs["legacy_methods"],
    )
    return _success(
        dispatcher_direct_handlers_runtime.connect_initialize_payload(
            protocol_version=PROTOCOL_VERSION,
            version=__version__,
            capabilities=capabilities,
        )
    )


def _handle_connect_capabilities(**kwargs: Any) -> JsonMap:
    runtime = kwargs["runtime"]
    auth = _resolve_gateway_auth_context(kwargs.get("client_info"))
    capabilities_inputs = dispatcher_direct_handlers_helper_runtime.capabilities_inputs(
        registry_items=gateway_method_registry().list(),
        legacy_methods=dispatcher_direct_handlers_runtime.legacy_methods(_LEGACY_ONLY_METHODS, _LEGACY_METHOD_ALIASES),
    )
    return _success(
        _capabilities_payload(
            runtime=runtime,
            auth=auth,
            method_entries=capabilities_inputs["method_entries"],
            legacy_methods=capabilities_inputs["legacy_methods"],
        )
    )


def _handle_connect_ping(**kwargs: Any) -> JsonMap:
    return _success({"ok": True, "protocolVersion": PROTOCOL_VERSION})


def _handle_access_posture_get(**kwargs: Any) -> JsonMap:
    runtime = kwargs["runtime"]
    auth = _resolve_gateway_auth_context(kwargs.get("client_info"))
    return _success(build_access_posture_summary(runtime, auth=auth))


def _handle_nodes_list(**kwargs: Any) -> JsonMap:
    return dispatcher_direct_handlers_methods_helpers_service.handle_nodes_list(
        kwargs,
        resolve_gateway_auth_context_fn=_resolve_gateway_auth_context,
        first_int_fn=_first_int,
        build_access_posture_summary_fn=build_access_posture_summary,
        runtime_registry_payload_fn=_runtime_registry_payload,
        nodes_inventory_payload_fn=_nodes_inventory_payload,
        success_fn=_success,
    )


def _handle_config_validate(**kwargs: Any) -> JsonMap:
    runtime = kwargs["runtime"]
    params = kwargs["params"]
    return _success(
        admin_dispatchers.config_validation_payload(
            runtime=runtime,
            params=params,
            runtime_registry_payload_fn=_runtime_registry_payload,
        )
    )


def _handle_config_apply(**kwargs: Any) -> JsonMap:
    runtime = kwargs["runtime"]
    params = kwargs["params"]
    return _success(
        admin_dispatchers.config_apply_result(
            runtime=runtime,
            params=params,
            runtime_registry_payload_fn=_runtime_registry_payload,
        )
    )


def _handle_config_restart_report(**kwargs: Any) -> JsonMap:
    runtime = kwargs["runtime"]
    params = kwargs["params"]
    return _success(
        admin_dispatchers.config_restart_report(
            runtime=runtime,
            params=params,
            runtime_registry_payload_fn=_runtime_registry_payload,
        )
    )


def _handle_health_get(**kwargs: Any) -> JsonMap:
    runtime = kwargs["runtime"]
    provider_status = dict(runtime.agent.provider_status() or {})
    return _success(dispatcher_direct_handlers_runtime.health_get_payload(provider_status))


def _handle_health_probes(**kwargs: Any) -> JsonMap:
    runtime = kwargs["runtime"]
    snapshot = runtime.gateway_state_snapshot(limit=5)
    return _success(dispatcher_direct_handlers_runtime.health_probes_payload(snapshot))


def _handle_logs_tail(**kwargs: Any) -> JsonMap:
    return dispatcher_direct_handlers_methods_helpers_service.handle_logs_tail(
        kwargs,
        available_log_sources_fn=_available_log_sources,
        normalized_logs_tail_request_fn=dispatcher_direct_handlers_helper_runtime.normalized_logs_tail_request,
        first_int_fn=_first_int,
        first_text_fn=_first_text,
        failure_fn=_failure,
        success_fn=_success,
        empty_logs_tail_payload_fn=dispatcher_direct_handlers_runtime.empty_logs_tail_payload,
        tail_text_lines_fn=_tail_text_lines,
        logs_tail_payload_fn=dispatcher_direct_handlers_runtime.logs_tail_payload,
        log_sources_payload_fn=dispatcher_direct_handlers_runtime.log_sources_payload,
    )


def _handle_gateway_dispatch(**kwargs: Any) -> JsonMap:
    return dispatcher_direct_handlers_methods_helpers_service.handle_gateway_dispatch(
        kwargs,
        validated_gateway_dispatch_event_kwargs_fn=dispatcher_direct_handlers_helper_runtime.validated_gateway_dispatch_event_kwargs,
        first_text_fn=_first_text,
        gateway_event_kwargs_fn=dispatcher_direct_handlers_runtime.gateway_event_kwargs,
        create_gateway_event_fn=create_gateway_event,
        gateway_dispatch_result_payload_fn=_gateway_dispatch_result_payload,
        failure_fn=_failure,
        success_fn=_success,
    )


def _handle_gateway_webhook(**kwargs: Any) -> JsonMap:
    return dispatcher_direct_handlers_methods_helpers_service.handle_gateway_webhook(
        kwargs,
        validated_gateway_webhook_request_fn=dispatcher_direct_handlers_helper_runtime.validated_gateway_webhook_request,
        first_text_fn=_first_text,
        verify_webhook_request_fn=dispatcher_direct_handlers_helper_runtime.verify_webhook_request,
        verify_webhook_signature_fn=verify_webhook_signature,
        verification_payload_fn=dispatcher_direct_handlers_runtime.verification_payload,
        webhook_event_payload_fn=dispatcher_direct_handlers_helper_runtime.webhook_event_payload,
        parse_webhook_body_fn=parse_webhook_body,
        build_webhook_event_fn=build_webhook_event,
        gateway_dispatch_response_fn=dispatcher_direct_handlers_helper_runtime.gateway_dispatch_response,
        gateway_dispatch_result_payload_fn=_gateway_dispatch_result_payload,
        failure_fn=_failure,
        success_fn=_success,
    )


def _handle_gateway_state_get(**kwargs: Any) -> JsonMap:
    return dispatcher_direct_handlers_methods_helpers_service.handle_gateway_state_get(
        kwargs,
        gateway_state_payload_fn=dispatcher_direct_handlers_runtime.gateway_state_payload,
        gateway_item_to_dict_fn=_gateway_item_to_dict,
        success_fn=_success,
    )


def _handle_gateway_events_list(**kwargs: Any) -> JsonMap:
    return dispatcher_direct_handlers_methods_helpers_service.handle_gateway_events_list(
        kwargs,
        handle_gateway_state_get_fn=_handle_gateway_state_get,
        gateway_events_list_payload_fn=dispatcher_direct_handlers_runtime.gateway_events_list_payload,
        success_fn=_success,
    )


def _handle_gateway_workflows_list(**kwargs: Any) -> JsonMap:
    return dispatcher_direct_handlers_methods_helpers_service.handle_gateway_workflows_list(
        kwargs,
        handle_gateway_state_get_fn=_handle_gateway_state_get,
        gateway_workflows_list_payload_fn=dispatcher_direct_handlers_runtime.gateway_workflows_list_payload,
        success_fn=_success,
    )


def _handle_approvals_resolve(**kwargs: Any) -> JsonMap:
    return dispatcher_direct_handlers_methods_helpers_service.handle_approvals_resolve(
        kwargs,
        approvals_resolve_request_fn=dispatcher_direct_handlers_helper_runtime.approvals_resolve_request,
        first_text_fn=_first_text,
        normalize_approval_decision_fn=dispatcher_direct_handlers_runtime.normalize_approval_decision,
        failure_fn=_failure,
        approval_decision_result_to_camel_case_fn=approval_decision_result_to_camel_case,
        gateway_dispatch_result_cls=GatewayDispatchResult,
        resume_after_approval_fn=approval_continuation_runtime.resume_after_approval,
        persist_continuation_result_fn=approval_continuation_runtime.persist_continuation_result,
    )


def _handle_browser_proxy(**kwargs: Any) -> JsonMap:
    return dispatcher_direct_handlers_methods_helpers_service.handle_browser_proxy(
        kwargs,
        browser_proxy_request_json_fn=dispatcher_direct_handlers_helper_runtime.browser_proxy_request_json,
        run_browser_proxy_command_fn=_run_browser_proxy_command,
        browser_proxy_result_fn=dispatcher_direct_handlers_helper_runtime.browser_proxy_result,
        failure_fn=_failure,
        success_fn=_success,
    )


def _run_browser_proxy_command(payload: dict[str, Any]) -> JsonMap:
    dispatcher_module = import_module("cli.agent_cli.gateway_server.dispatcher")
    return dispatcher_module.run_browser_proxy_command(payload)


def build_workflow_trace_approval_handlers() -> Any:
    return build_workflow_handler_family(
        WorkflowHandlerDeps(
            first_int=_first_int,
            first_text=_first_text,
            gateway_item_to_dict=_gateway_item_to_dict,
            sorted_trace_timeline=_sorted_trace_timeline,
            workflow_resume_eligible=_workflow_resume_eligible,
            create_audit_record=create_audit_record,
            success=_success,
            failure=_failure,
            handle_gateway_state_get=_handle_gateway_state_get,
        )
    )


_DIRECT_HANDLERS: dict[str, Callable[..., JsonMap]] = {
    "connect.initialize": _handle_connect_initialize,
    "connect.capabilities": _handle_connect_capabilities,
    "connect.ping": _handle_connect_ping,
    "access.posture.get": _handle_access_posture_get,
    "nodes.list": _handle_nodes_list,
    "config.validate": _handle_config_validate,
    "config.apply": _handle_config_apply,
    "config.restart.report": _handle_config_restart_report,
    "health.get": _handle_health_get,
    "health.probes": _handle_health_probes,
    "logs.tail": _handle_logs_tail,
    "gateway/dispatch": _handle_gateway_dispatch,
    "gateway/webhook": _handle_gateway_webhook,
    "gateway.state.get": _handle_gateway_state_get,
    "gateway.events.list": _handle_gateway_events_list,
    "gateway.workflows.list": _handle_gateway_workflows_list,
    "approvals.resolve": _handle_approvals_resolve,
    "browser.proxy": _handle_browser_proxy,
}
