from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_services import (
    expert_review_execution_result_helpers_runtime as _result_helpers,
)
from cli.agent_cli.runtime_services import (
    expert_review_execution_reviewer_helpers_runtime as _reviewer_helpers,
)
from cli.agent_cli.runtime_services import (
    expert_review_execution_runtime_access_helpers_runtime as _runtime_access_helpers,
)
from cli.agent_cli.runtime_services import (
    expert_review_execution_value_helpers_runtime as _value_helpers,
)
from cli.agent_cli.runtime_services.expert_review_result_runtime import (
    EXPERT_REVIEW_ERROR_NO_ELIGIBLE_PROVIDER,
    EXPERT_REVIEW_ERROR_NO_REVIEWER_CANDIDATE,
    EXPERT_REVIEW_ERROR_UNAVAILABLE,
    expert_review_reviewer_identity,
)


_DEFAULT_SCOPE = "current_task"
_DEFAULT_MAX_FINDINGS = 5


def _normalized_text(value: Any) -> str:
    return _value_helpers.normalized_text(value)


def _normalized_choice(value: Any, *, allowed: tuple[str, ...], default: str) -> str:
    return _value_helpers.normalized_choice(
        value,
        allowed=allowed,
        default=default,
        normalized_text_fn=_normalized_text,
    )


def _sequence_items(value: Any) -> list[Any]:
    return _value_helpers.sequence_items(value)


def _normalized_string_list(
    value: Any,
    *,
    allowed: tuple[str, ...] | None = None,
) -> list[str]:
    return _value_helpers.normalized_string_list(
        value,
        allowed=allowed,
        sequence_items_fn=_sequence_items,
        normalized_text_fn=_normalized_text,
    )


def _normalized_scope(value: Any) -> str:
    return _value_helpers.normalized_scope(
        value,
        default=_DEFAULT_SCOPE,
        normalized_choice_fn=_normalized_choice,
    )


def _normalized_max_findings(value: Any) -> int:
    return _value_helpers.normalized_max_findings(value, default=_DEFAULT_MAX_FINDINGS)


def _elapsed_ms(started_at: float) -> int:
    return _value_helpers.elapsed_ms(started_at)


def _provider_status(runtime: Any) -> dict[str, Any]:
    return _runtime_access_helpers.provider_status(runtime)


def _provider_status_text(runtime: Any, key: str) -> str:
    return _runtime_access_helpers.provider_status_text(
        runtime,
        key,
        provider_status_fn=_provider_status,
        normalized_text_fn=_normalized_text,
    )


def _provider_public_name(runtime: Any, gate_payload: Mapping[str, Any]) -> str:
    return _runtime_access_helpers.provider_public_name(
        runtime,
        gate_payload,
        provider_status_text_fn=_provider_status_text,
        normalized_text_fn=_normalized_text,
    )


def _provider_review_gate(runtime: Any) -> dict[str, Any]:
    return _runtime_access_helpers.provider_review_gate(
        runtime,
        provider_status_fn=_provider_status,
    )


def _available_provider_items(runtime: Any) -> list[dict[str, Any]]:
    return _runtime_access_helpers.available_provider_items(runtime)


def _runtime_state_snapshot(runtime: Any) -> dict[str, Any]:
    return _runtime_access_helpers.runtime_state_snapshot(runtime)


def _selection_failure_error_code(selection: Mapping[str, Any]) -> str:
    return _reviewer_helpers.selection_failure_error_code(
        selection,
        normalized_text_fn=_normalized_text,
        no_eligible_provider_error=EXPERT_REVIEW_ERROR_NO_ELIGIBLE_PROVIDER,
        no_reviewer_candidate_error=EXPERT_REVIEW_ERROR_NO_REVIEWER_CANDIDATE,
        unavailable_error=EXPERT_REVIEW_ERROR_UNAVAILABLE,
    )


def _selection_failure_detail(selection: Mapping[str, Any]) -> str:
    return _reviewer_helpers.selection_failure_detail(
        selection,
        normalized_text_fn=_normalized_text,
        unavailable_error=EXPERT_REVIEW_ERROR_UNAVAILABLE,
    )


def _candidate_provider_selector(candidate: Mapping[str, Any]) -> str | None:
    return _reviewer_helpers.candidate_provider_selector(
        candidate,
        normalized_text_fn=_normalized_text,
    )


def _candidate_model_selector(candidate: Mapping[str, Any]) -> str | None:
    return _reviewer_helpers.candidate_model_selector(
        candidate,
        normalized_text_fn=_normalized_text,
    )


def _candidate_provider_display(candidate: Mapping[str, Any]) -> str:
    return _reviewer_helpers.candidate_provider_display(
        candidate,
        normalized_text_fn=_normalized_text,
    )


def _candidate_model_display(candidate: Mapping[str, Any]) -> str:
    return _reviewer_helpers.candidate_model_display(
        candidate,
        normalized_text_fn=_normalized_text,
    )


def _candidate_reviewer_reasoning_strategy(candidate: Mapping[str, Any]) -> str:
    return _reviewer_helpers.candidate_reviewer_reasoning_strategy(
        candidate,
        normalized_text_fn=_normalized_text,
    )


def _candidate_reviewer_reasoning_effort(candidate: Mapping[str, Any]) -> str | None:
    return _reviewer_helpers.candidate_reviewer_reasoning_effort(
        candidate,
        normalized_text_fn=_normalized_text,
    )


def _candidate_reviewer_reasoning_mode(candidate: Mapping[str, Any]) -> str:
    return _reviewer_helpers.candidate_reviewer_reasoning_mode(
        candidate,
        normalized_text_fn=_normalized_text,
    )


def _candidate_reviewer_capability_policy(candidate: Mapping[str, Any]) -> str:
    return _reviewer_helpers.candidate_reviewer_capability_policy(
        candidate,
        normalized_text_fn=_normalized_text,
    )


def _candidate_reviewer_capability_source(candidate: Mapping[str, Any]) -> str:
    return _reviewer_helpers.candidate_reviewer_capability_source(
        candidate,
        normalized_text_fn=_normalized_text,
    )


def _resolved_reviewer_provider(candidate: Mapping[str, Any], resolution: Any) -> str:
    return _reviewer_helpers.resolved_reviewer_provider(
        candidate,
        resolution,
        candidate_provider_display_fn=_candidate_provider_display,
        normalized_text_fn=_normalized_text,
    )


def _resolved_reviewer_model(candidate: Mapping[str, Any], resolution: Any) -> str:
    return _reviewer_helpers.resolved_reviewer_model(
        candidate,
        resolution,
        candidate_model_display_fn=_candidate_model_display,
        normalized_text_fn=_normalized_text,
    )


def _reviewer_task_text(prompt_bundle: Mapping[str, Any]) -> str:
    return _reviewer_helpers.reviewer_task_text(
        prompt_bundle,
        normalized_text_fn=_normalized_text,
    )


def _wait_timeout_ms(resolution: Any) -> int | None:
    return _runtime_access_helpers.wait_timeout_ms(resolution)


def _first_tool_payload(result: CommandExecutionResult) -> dict[str, Any]:
    return _runtime_access_helpers.first_tool_payload(result)


def _reviewer_output_text(wait_result: CommandExecutionResult, wait_payload: Mapping[str, Any]) -> str:
    return _runtime_access_helpers.reviewer_output_text(
        wait_result,
        wait_payload,
        normalized_text_fn=_normalized_text,
    )


def _wait_failure_detail(wait_result: CommandExecutionResult, wait_payload: Mapping[str, Any]) -> str:
    return _runtime_access_helpers.wait_failure_detail(
        wait_result,
        wait_payload,
        normalized_text_fn=_normalized_text,
    )


def _expert_review_tool_payload(
    *,
    result: Mapping[str, Any],
    request_payload: Mapping[str, Any],
    gate_payload: Mapping[str, Any],
    selection: Mapping[str, Any],
    child_agent_id: str,
) -> dict[str, Any]:
    return _result_helpers.expert_review_tool_payload(
        result=result,
        request_payload=request_payload,
        gate_payload=gate_payload,
        selection=selection,
        child_agent_id=child_agent_id,
        candidate_provider_display_fn=_candidate_provider_display,
        candidate_model_display_fn=_candidate_model_display,
        candidate_model_selector_fn=_candidate_model_selector,
        normalized_text_fn=_normalized_text,
    )


def _expert_review_assistant_text(result: Mapping[str, Any]) -> str:
    return _result_helpers.expert_review_assistant_text(
        result,
        normalized_text_fn=_normalized_text,
        reviewer_identity_fn=expert_review_reviewer_identity,
    )


def _expert_review_command_result(
    *,
    result: Mapping[str, Any],
    request_payload: Mapping[str, Any],
    gate_payload: Mapping[str, Any],
    selection: Mapping[str, Any],
    item_events: Sequence[Mapping[str, Any]],
    child_agent_id: str = "",
) -> CommandExecutionResult:
    return _result_helpers.expert_review_command_result(
        result=result,
        request_payload=request_payload,
        gate_payload=gate_payload,
        selection=selection,
        item_events=item_events,
        child_agent_id=child_agent_id,
        expert_review_tool_payload_fn=_expert_review_tool_payload,
        normalized_text_fn=_normalized_text,
        expert_review_assistant_text_fn=_expert_review_assistant_text,
    )
