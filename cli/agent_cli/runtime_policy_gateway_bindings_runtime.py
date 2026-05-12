from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli import (
    runtime_policy_gateway_bindings_facade_runtime as bindings_facade_runtime_service,
)
from cli.agent_cli import runtime_runtime
from cli.agent_cli import runtime_summary_runtime as runtime_summary_runtime_service
from cli.agent_cli.runtime_services import approval_runtime as approval_runtime_service


def bind_runtime_policy_gateway_methods(
    runtime_cls: Any,
    *,
    cli_version: str,
    local_approval_connector_key: str,
    local_approval_plugin_name: str,
    local_patch_approval_reason: str,
    local_background_teammate_approval_reason: str,
    slash_command_specs_fn: Callable[..., Any],
    match_slash_commands_fn: Callable[..., Any],
    autocomplete_slash_command_fn: Callable[..., Any],
    github_action_artifact_refs_fn: Callable[..., Any],
    find_github_workflow_run_fn: Callable[..., Any],
) -> None:
    def describe_thread(
        self: Any,
        thread: dict[str, Any] | None = None,
        *,
        thread_id: str | None = None,
        status: str | None = None,
        turns: list[dict[str, Any]] | None = None,
        metadata_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return runtime_summary_runtime_service.describe_thread(
            self,
            thread=thread,
            thread_id=thread_id,
            status=status,
            turns=turns,
            metadata_overrides=metadata_overrides,
            cli_version=cli_version,
        )

    def request_patch_approval(self: Any, patch_text: str, *, requested_by: str = "cli"):
        return approval_runtime_service.request_patch_approval(
            self,
            patch_text,
            requested_by=requested_by,
            connector_key=local_approval_connector_key,
            plugin_name=local_approval_plugin_name,
            approval_reason=local_patch_approval_reason,
        )

    def request_background_teammate_approval(
        self: Any,
        task: str,
        *,
        requested_by: str = "cli",
        provider: str = "",
        model: str = "",
        reasoning_effort: str = "",
        task_cwd: str | None = None,
        queue_cwd: str | None = None,
        approval_policy: str = "never",
        sandbox_mode: str = "workspace-write",
        allowed_paths: list[str] | None = None,
        blocked_paths: list[str] | None = None,
        timeout_seconds: float | None = None,
    ):
        return approval_runtime_service.request_background_teammate_approval(
            self,
            task,
            requested_by=requested_by,
            provider=provider,
            model=model,
            reasoning_effort=reasoning_effort,
            task_cwd=task_cwd,
            queue_cwd=queue_cwd,
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            allowed_paths=allowed_paths,
            blocked_paths=blocked_paths,
            timeout_seconds=timeout_seconds,
            connector_key=local_approval_connector_key,
            plugin_name=local_approval_plugin_name,
            approval_reason=local_background_teammate_approval_reason,
        )

    def decide_approval(
        self: Any,
        approval_id: str,
        *,
        approved: bool | None = None,
        decision: Any = None,
        decided_by: str,
        decision_note: str = "",
    ) -> dict[str, Any]:
        return runtime_runtime.decide_approval(
            approval_id=approval_id,
            approved=approved,
            decision=decision,
            decided_by=decided_by,
            decision_note=decision_note,
            get_approval_ticket_fn=self.gateway_state_store.get_approval_ticket,
            get_action_request_fn=self.gateway_state_store.get_action_request,
            decide_patch_approval_fn=self._decide_patch_approval,
            decide_shell_approval_fn=self._decide_shell_approval,
            decide_background_teammate_approval_fn=self._decide_background_teammate_approval,
            decide_gateway_approval_fn=self.decide_gateway_approval,
            local_approval_connector_key=local_approval_connector_key,
            local_approval_plugin_name=local_approval_plugin_name,
        )

    def decide_gateway_approval(
        self: Any,
        approval_id: str,
        *,
        approved: bool | None = None,
        decision: Any = None,
        decided_by: str,
        decision_note: str = "",
    ) -> dict[str, Any]:
        return approval_runtime_service.decide_gateway_approval(
            self,
            approval_id,
            approved=approved,
            decision=decision,
            decided_by=decided_by,
            decision_note=decision_note,
            github_action_artifact_refs_fn=github_action_artifact_refs_fn,
            find_github_workflow_run_fn=find_github_workflow_run_fn,
        )

    def slash_command_catalog(self: Any) -> list[dict[str, str]]:
        plugin_manager = getattr(self.tools, "_plugin_manager", None)
        return runtime_summary_runtime_service.slash_command_catalog_rows(
            plugin_manager=plugin_manager,
            slash_command_specs_fn=slash_command_specs_fn,
            locale=getattr(self, "presentation_locale", None),
        )

    def slash_command_matches(self: Any, prefix: str) -> list[dict[str, str]]:
        plugin_manager = getattr(self.tools, "_plugin_manager", None)
        return runtime_summary_runtime_service.slash_command_match_rows(
            prefix=prefix,
            plugin_manager=plugin_manager,
            match_slash_commands_fn=match_slash_commands_fn,
            locale=getattr(self, "presentation_locale", None),
        )

    def slash_command_completion(self: Any, prefix: str) -> str | None:
        return autocomplete_slash_command_fn(
            prefix, plugin_manager=getattr(self.tools, "_plugin_manager", None)
        )

    runtime_cls.runtime_policy_status = bindings_facade_runtime_service.runtime_policy_status
    runtime_cls.response_runtime_snapshot = (
        bindings_facade_runtime_service.response_runtime_snapshot
    )
    runtime_cls.describe_thread = describe_thread
    runtime_cls.configure_runtime_policy = bindings_facade_runtime_service.configure_runtime_policy
    runtime_cls.web_access_allowed = bindings_facade_runtime_service.web_access_allowed
    runtime_cls.web_search_enabled = bindings_facade_runtime_service.web_search_enabled
    runtime_cls.patch_requires_approval = bindings_facade_runtime_service.patch_requires_approval
    runtime_cls.workspace_is_read_only = bindings_facade_runtime_service.workspace_is_read_only
    runtime_cls.approval_status = bindings_facade_runtime_service.approval_status
    runtime_cls.gateway_registry = bindings_facade_runtime_service.gateway_registry
    runtime_cls.current_gateway_request_scope = (
        bindings_facade_runtime_service.current_gateway_request_scope
    )
    runtime_cls.gateway_broadcast_since = bindings_facade_runtime_service.gateway_broadcast_since
    runtime_cls.subscribe_gateway_broadcast = (
        bindings_facade_runtime_service.subscribe_gateway_broadcast
    )
    runtime_cls.unsubscribe_gateway_broadcast = (
        bindings_facade_runtime_service.unsubscribe_gateway_broadcast
    )
    runtime_cls._broadcast_gateway_state = bindings_facade_runtime_service._broadcast_gateway_state
    runtime_cls.save_gateway_event = bindings_facade_runtime_service.save_gateway_event
    runtime_cls.save_gateway_workflow_run = (
        bindings_facade_runtime_service.save_gateway_workflow_run
    )
    runtime_cls.save_gateway_action_request = (
        bindings_facade_runtime_service.save_gateway_action_request
    )
    runtime_cls.save_gateway_approval_ticket = (
        bindings_facade_runtime_service.save_gateway_approval_ticket
    )
    runtime_cls.append_gateway_audit_record = (
        bindings_facade_runtime_service.append_gateway_audit_record
    )
    runtime_cls.route_gateway_event = bindings_facade_runtime_service.route_gateway_event
    runtime_cls._workflow_handler_registration = (
        bindings_facade_runtime_service._workflow_handler_registration
    )
    runtime_cls._invoke_workflow_handler = bindings_facade_runtime_service._invoke_workflow_handler
    runtime_cls.dispatch_gateway_event = bindings_facade_runtime_service.dispatch_gateway_event
    runtime_cls.gateway_state_snapshot = bindings_facade_runtime_service.gateway_state_snapshot
    runtime_cls.list_approval_tickets = bindings_facade_runtime_service.list_approval_tickets
    runtime_cls.update_workflow_run_state = (
        bindings_facade_runtime_service.update_workflow_run_state
    )
    runtime_cls.list_approval_diagnostics = (
        bindings_facade_runtime_service.list_approval_diagnostics
    )
    runtime_cls.request_patch_approval = request_patch_approval
    runtime_cls.approvals_event = bindings_facade_runtime_service.approvals_event
    runtime_cls.request_background_teammate_approval = request_background_teammate_approval
    runtime_cls.decide_approval = decide_approval
    runtime_cls.request_gateway_action = bindings_facade_runtime_service.request_gateway_action
    runtime_cls.execute_gateway_action_now = (
        bindings_facade_runtime_service.execute_gateway_action_now
    )
    runtime_cls.record_gateway_action_denied = (
        bindings_facade_runtime_service.record_gateway_action_denied
    )
    runtime_cls._default_browser_action_executor = (
        bindings_facade_runtime_service._default_browser_action_executor
    )
    runtime_cls._execute_browser_gateway_action = (
        bindings_facade_runtime_service._execute_browser_gateway_action
    )
    runtime_cls._approval_diagnostic = bindings_facade_runtime_service._approval_diagnostic
    runtime_cls._workflow_diagnostic = bindings_facade_runtime_service._workflow_diagnostic
    runtime_cls._build_gateway_diagnostics = (
        bindings_facade_runtime_service._build_gateway_diagnostics
    )
    runtime_cls._decide_patch_approval = bindings_facade_runtime_service._decide_patch_approval
    runtime_cls._decide_shell_approval = bindings_facade_runtime_service._decide_shell_approval
    runtime_cls._decide_background_teammate_approval = (
        bindings_facade_runtime_service._decide_background_teammate_approval
    )
    runtime_cls.decide_gateway_approval = decide_gateway_approval
    runtime_cls.slash_command_catalog = slash_command_catalog
    runtime_cls.slash_command_matches = slash_command_matches
    runtime_cls.slash_command_completion = slash_command_completion
