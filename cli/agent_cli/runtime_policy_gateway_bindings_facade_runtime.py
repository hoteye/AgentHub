from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli import runtime_codex_headless_contract_runtime as codex_headless_contract_runtime_service
from cli.agent_cli import (
    runtime_policy_gateway_bindings_helpers_runtime as runtime_policy_gateway_bindings_helpers_runtime_service,
)
from cli.agent_cli import runtime_runtime
from cli.agent_cli import runtime_summary_runtime as runtime_summary_runtime_service
from cli.agent_cli.models import ToolEvent


def runtime_policy_status(self: Any) -> Dict[str, str]:
    status = self.runtime_policy.to_status()
    effective_policy = codex_headless_contract_runtime_service.effective_model_runtime_policy(
        self,
        approval_policy=status.get("approval_policy"),
        sandbox_mode=status.get("sandbox_mode"),
    )
    status["approval_policy"] = str(effective_policy.get("approval_policy") or "")
    status["sandbox_mode"] = str(effective_policy.get("sandbox_mode") or "")
    return status


def response_runtime_snapshot(self: Any) -> Dict[str, Any]:
    return runtime_summary_runtime_service.response_runtime_snapshot(self)


def configure_runtime_policy(
    self: Any,
    *,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    web_search_mode: str | None = None,
    network_access_enabled: str | bool | None = None,
) -> Dict[str, str]:
    self.runtime_policy, status = runtime_runtime.configure_runtime_policy_state(
        runtime_policy=self.runtime_policy,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=web_search_mode,
        network_access_enabled=network_access_enabled,
        agent_runtime_policy_setter=getattr(self.agent, "set_runtime_policy_overrides", None),
    )
    return status


def web_access_allowed(self: Any) -> bool:
    return bool(self.runtime_policy.network_access_enabled)


def web_search_enabled(self: Any) -> bool:
    return self.runtime_policy.web_search_mode != "disabled" and self.web_access_allowed()


def patch_requires_approval(self: Any) -> bool:
    return self.runtime_policy.approval_policy != "never"


def workspace_is_read_only(self: Any) -> bool:
    return self.runtime_policy.sandbox_mode == "read-only"


def approval_status(self: Any) -> Dict[str, str]:
    return runtime_summary_runtime_service.approval_status(
        list_approval_tickets_fn=self.list_approval_tickets,
    )


gateway_registry = runtime_policy_gateway_bindings_helpers_runtime_service.gateway_registry
current_gateway_request_scope = (
    runtime_policy_gateway_bindings_helpers_runtime_service.current_gateway_request_scope
)
gateway_broadcast_since = (
    runtime_policy_gateway_bindings_helpers_runtime_service.gateway_broadcast_since
)
subscribe_gateway_broadcast = (
    runtime_policy_gateway_bindings_helpers_runtime_service.subscribe_gateway_broadcast
)
unsubscribe_gateway_broadcast = (
    runtime_policy_gateway_bindings_helpers_runtime_service.unsubscribe_gateway_broadcast
)
_broadcast_gateway_state = (
    runtime_policy_gateway_bindings_helpers_runtime_service._broadcast_gateway_state
)
save_gateway_event = runtime_policy_gateway_bindings_helpers_runtime_service.save_gateway_event
save_gateway_workflow_run = (
    runtime_policy_gateway_bindings_helpers_runtime_service.save_gateway_workflow_run
)
save_gateway_action_request = (
    runtime_policy_gateway_bindings_helpers_runtime_service.save_gateway_action_request
)
save_gateway_approval_ticket = (
    runtime_policy_gateway_bindings_helpers_runtime_service.save_gateway_approval_ticket
)
append_gateway_audit_record = (
    runtime_policy_gateway_bindings_helpers_runtime_service.append_gateway_audit_record
)
route_gateway_event = runtime_policy_gateway_bindings_helpers_runtime_service.route_gateway_event
_workflow_handler_registration = (
    runtime_policy_gateway_bindings_helpers_runtime_service._workflow_handler_registration
)
_invoke_workflow_handler = (
    runtime_policy_gateway_bindings_helpers_runtime_service._invoke_workflow_handler
)
dispatch_gateway_event = (
    runtime_policy_gateway_bindings_helpers_runtime_service.dispatch_gateway_event
)
gateway_state_snapshot = (
    runtime_policy_gateway_bindings_helpers_runtime_service.gateway_state_snapshot
)
list_approval_tickets = (
    runtime_policy_gateway_bindings_helpers_runtime_service.list_approval_tickets
)
update_workflow_run_state = (
    runtime_policy_gateway_bindings_helpers_runtime_service.update_workflow_run_state
)
list_approval_diagnostics = (
    runtime_policy_gateway_bindings_helpers_runtime_service.list_approval_diagnostics
)


def approvals_event(self: Any, *, limit: int = 20, status: str | None = None) -> ToolEvent:
    tickets = self.list_approval_tickets(limit=limit, status=status)
    rows = runtime_runtime.approval_list_rows(
        tickets=tickets,
        get_action_request_fn=self.gateway_state_store.get_action_request,
    )
    return runtime_runtime.approval_list_event(
        rows=rows,
        status=status,
        tool_event_factory=ToolEvent,
    )


request_gateway_action = (
    runtime_policy_gateway_bindings_helpers_runtime_service.request_gateway_action
)
execute_gateway_action_now = (
    runtime_policy_gateway_bindings_helpers_runtime_service.execute_gateway_action_now
)
record_gateway_action_denied = (
    runtime_policy_gateway_bindings_helpers_runtime_service.record_gateway_action_denied
)
_default_browser_action_executor = (
    runtime_policy_gateway_bindings_helpers_runtime_service._default_browser_action_executor
)
_execute_browser_gateway_action = (
    runtime_policy_gateway_bindings_helpers_runtime_service._execute_browser_gateway_action
)
_approval_diagnostic = runtime_policy_gateway_bindings_helpers_runtime_service._approval_diagnostic
_workflow_diagnostic = runtime_policy_gateway_bindings_helpers_runtime_service._workflow_diagnostic
_build_gateway_diagnostics = (
    runtime_policy_gateway_bindings_helpers_runtime_service._build_gateway_diagnostics
)
_decide_patch_approval = (
    runtime_policy_gateway_bindings_helpers_runtime_service._decide_patch_approval
)
_decide_shell_approval = (
    runtime_policy_gateway_bindings_helpers_runtime_service._decide_shell_approval
)
_decide_background_teammate_approval = (
    runtime_policy_gateway_bindings_helpers_runtime_service._decide_background_teammate_approval
)
