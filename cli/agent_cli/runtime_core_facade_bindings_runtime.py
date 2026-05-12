from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.models import AgentIntent, CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import (
    execute_agent_intent as core_execute_agent_intent,
    execute_agent_intent_result as core_execute_agent_intent_result,
    parse_args,
    plan_step_names,
    run_command_text as core_run_command_text,
    run_command_text_result as core_run_command_text_result,
    single_event as core_single_event,
    split_command,
    try_execute_local_plan as core_try_execute_local_plan,
)
from cli.agent_cli.runtime_services import approval_runtime as approval_runtime_service
from cli.agent_cli.runtime_services import gateway_runtime as gateway_runtime_service
from workers.actions import ActionResult

from cli.agent_cli import runtime_runtime


def bind_runtime_core_facade_methods(
    runtime_cls: Any,
    *,
    local_plan_disabled_note: str,
) -> None:
    @staticmethod
    def _filter_handler_kwargs(handler: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        return gateway_runtime_service.filter_handler_kwargs(handler, kwargs)

    @staticmethod
    def _normalized_workflow_result(raw_result: Any) -> Dict[str, Any]:
        return gateway_runtime_service.normalized_workflow_result(raw_result)

    @staticmethod
    def _string_list(value: Any) -> List[str]:
        return gateway_runtime_service.string_list(value)

    @staticmethod
    def _workflow_result_details(workflow_run: Any) -> Dict[str, Any]:
        return gateway_runtime_service.workflow_result_details(workflow_run)

    @staticmethod
    def _merge_context(existing: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        return gateway_runtime_service.merge_context(existing, updates)

    @staticmethod
    def _normalize_action_result(value: Any, *, default_action: str) -> ActionResult:
        return approval_runtime_service.normalize_action_result(
            value,
            default_action=default_action,
        )

    @staticmethod
    def _browser_request_from_action_request(action_request: Any) -> Dict[str, Any]:
        return approval_runtime_service.browser_request_from_action_request(action_request)

    @staticmethod
    def _browser_profile_prefers_local_execution(profile: Any) -> bool:
        return approval_runtime_service.browser_profile_prefers_local_execution(profile)

    @staticmethod
    def _browser_artifact_refs(value: Any) -> List[str]:
        return approval_runtime_service.browser_artifact_refs(value)

    @staticmethod
    def _action_request_details(action_request: Any) -> Dict[str, Any]:
        return approval_runtime_service.action_request_details(action_request)

    @staticmethod
    def _recommendation_item(action_request: Any) -> Dict[str, Any]:
        return gateway_runtime_service.recommendation_item(action_request)

    @staticmethod
    def _execution_diagnostic(audit_record: Any | None) -> Dict[str, Any]:
        return gateway_runtime_service.execution_diagnostic(audit_record)

    @staticmethod
    def _gateway_item_payload(item: Any) -> Dict[str, Any]:
        return approval_runtime_service.gateway_item_payload(item)

    def _approval_decision_turn_events(
        self: Any,
        *,
        approval_ticket: Any,
        action_request: Any,
        action_result: Any,
        item_index_start: int = 0,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return approval_runtime_service.approval_decision_turn_events(
            approval_ticket,
            action_request,
            action_result,
            item_index_start=item_index_start,
        )

    def _run_command_text(self: Any, text: str) -> Tuple[str, List[ToolEvent]]:
        return core_run_command_text(self, text)

    def _run_command_text_result(self: Any, text: str) -> CommandExecutionResult:
        return core_run_command_text_result(self, text)

    @staticmethod
    def _split_command(text: str) -> Tuple[str, str]:
        return split_command(text)

    @staticmethod
    def _parse_args(arg_text: str) -> Tuple[List[str], Dict[str, Any]]:
        return parse_args(arg_text)

    @staticmethod
    def _single_event(prefix: str, event: ToolEvent) -> Tuple[str, List[ToolEvent]]:
        return core_single_event(prefix, event)

    def _execute_agent_intent(self: Any, intent: AgentIntent) -> Tuple[str, List[ToolEvent]]:
        return core_execute_agent_intent(self, intent)

    def _execute_agent_intent_result(self: Any, intent: AgentIntent) -> CommandExecutionResult:
        return core_execute_agent_intent_result(self, intent)

    def _build_local_plan(self: Any, text: str) -> Dict[str, Any]:
        del text
        return runtime_runtime.build_local_plan(local_plan_disabled_note=local_plan_disabled_note)

    @staticmethod
    def _plan_step_names(plan: Dict[str, Any]) -> List[str]:
        return plan_step_names(plan)

    def _should_try_local_plan(self: Any, text: str) -> bool:
        _, self.last_plan, self._last_plan_text, allowed = runtime_runtime.local_plan_state_update(
            text=text,
            last_plan=self.last_plan,
            last_plan_text=self._last_plan_text,
            build_local_plan_fn=self._build_local_plan,
            preview=False,
        )
        return allowed

    def _preview_local_plan(self: Any, text: str) -> Dict[str, Any]:
        payload, self.last_plan, self._last_plan_text, _ = runtime_runtime.local_plan_state_update(
            text=text,
            last_plan=self.last_plan,
            last_plan_text=self._last_plan_text,
            build_local_plan_fn=self._build_local_plan,
            preview=True,
        )
        return payload

    def _implicit_local_plan_allowed(self: Any) -> bool:
        return False

    def _stateful_local_plan_allowed(self: Any, text: str) -> bool:
        del text
        return False

    def _provider_ready_local_plan_allowed(self: Any, text: str) -> bool:
        del text
        return False

    def _try_execute_local_plan(self: Any, text: str) -> Optional[Tuple[str, List[ToolEvent]]]:
        return core_try_execute_local_plan(self, text)

    runtime_cls._filter_handler_kwargs = _filter_handler_kwargs
    runtime_cls._normalized_workflow_result = _normalized_workflow_result
    runtime_cls._string_list = _string_list
    runtime_cls._workflow_result_details = _workflow_result_details
    runtime_cls._merge_context = _merge_context
    runtime_cls._normalize_action_result = _normalize_action_result
    runtime_cls._browser_request_from_action_request = _browser_request_from_action_request
    runtime_cls._browser_profile_prefers_local_execution = _browser_profile_prefers_local_execution
    runtime_cls._browser_artifact_refs = _browser_artifact_refs
    runtime_cls._action_request_details = _action_request_details
    runtime_cls._recommendation_item = _recommendation_item
    runtime_cls._execution_diagnostic = _execution_diagnostic
    runtime_cls._gateway_item_payload = _gateway_item_payload
    runtime_cls._approval_decision_turn_events = _approval_decision_turn_events
    runtime_cls._run_command_text = _run_command_text
    runtime_cls._run_command_text_result = _run_command_text_result
    runtime_cls._split_command = _split_command
    runtime_cls._parse_args = _parse_args
    runtime_cls._single_event = _single_event
    runtime_cls._execute_agent_intent = _execute_agent_intent
    runtime_cls._execute_agent_intent_result = _execute_agent_intent_result
    runtime_cls._build_local_plan = _build_local_plan
    runtime_cls._plan_step_names = _plan_step_names
    runtime_cls._should_try_local_plan = _should_try_local_plan
    runtime_cls._preview_local_plan = _preview_local_plan
    runtime_cls._implicit_local_plan_allowed = _implicit_local_plan_allowed
    runtime_cls._stateful_local_plan_allowed = _stateful_local_plan_allowed
    runtime_cls._provider_ready_local_plan_allowed = _provider_ready_local_plan_allowed
    runtime_cls._try_execute_local_plan = _try_execute_local_plan
