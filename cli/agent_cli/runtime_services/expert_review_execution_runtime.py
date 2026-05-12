from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_services.expert_review_execution_helpers_runtime import (
    _available_provider_items,
    _elapsed_ms,
    _expert_review_command_result,
    _first_tool_payload,
    _provider_public_name,
    _provider_review_gate,
    _provider_status_text,
    _reviewer_output_text,
    _reviewer_task_text,
    _runtime_state_snapshot,
    _selection_failure_detail,
    _selection_failure_error_code,
    _wait_failure_detail,
    _wait_timeout_ms,
)
from cli.agent_cli.runtime_services.expert_review_execution_normalization_helpers_runtime import (
    parse_expert_review_request_payload,
)
from cli.agent_cli.runtime_services.expert_review_execution_projection_helpers_runtime import (
    build_execution_failure_result_and_event,
    build_parsed_review_result_event,
    build_review_running_event,
)
from cli.agent_cli.runtime_services.expert_review_execution_pure_helpers_runtime import (
    resolved_reviewer_execution_metadata,
    selected_reviewer_execution_metadata,
)
from cli.agent_cli.runtime_services.expert_review_packet_runtime import (
    build_expert_review_packet,
)
from cli.agent_cli.runtime_services.expert_review_parse_runtime import (
    parse_expert_review_output,
)
from cli.agent_cli.runtime_services.expert_review_prompt_runtime import (
    build_expert_review_reviewer_prompt,
)
from cli.agent_cli.runtime_services.expert_review_result_runtime import (
    EXPERT_REVIEW_ERROR_DELEGATE_FAILED,
    EXPERT_REVIEW_ERROR_PACKET_BUILD_FAILED,
    EXPERT_REVIEW_ERROR_PARSE_FAILED,
    EXPERT_REVIEW_FOCUS_AREAS,
    EXPERT_REVIEW_STRICTNESS_LEVELS,
    build_expert_review_failure_result,
    expert_review_reviewer_identity,
)
from cli.agent_cli.runtime_services.expert_review_selector_runtime import (
    select_expert_review_reviewer,
)
from cli.agent_cli.runtime_services.expert_review_turn_events_runtime import (
    build_expert_review_completed_turn_event,
    build_expert_review_failed_turn_event,
    build_expert_review_requested_turn_event,
    build_expert_review_running_turn_event,
)


_DEFAULT_SCOPE = "current_task"
_DEFAULT_STRICTNESS = "medium"
_DEFAULT_MAX_FINDINGS = 5
_EXPERT_REVIEW_ROLE = "subagent"
_EXPERT_REVIEW_DELEGATION_REASON = "expert_review"
_EXPERT_REVIEW_DELEGATION_MODE = "background"
_EXPERT_REVIEW_TASK_SHAPE = "read_only"
_EXPERT_REVIEW_ITEM_ID = "expert_review_item"
_EXPECTED_DELEGATE_EXCEPTIONS = (RuntimeError, ValueError, TimeoutError, ConnectionError)
_EXPECTED_PACKET_BUILD_EXCEPTIONS = (RuntimeError, ValueError)


def parse_expert_review_command_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return parse_expert_review_request_payload(
        payload,
        default_strictness=_DEFAULT_STRICTNESS,
        focus_areas=EXPERT_REVIEW_FOCUS_AREAS,
        strictness_levels=EXPERT_REVIEW_STRICTNESS_LEVELS,
    )


def run_expert_review(
    runtime: Any,
    *,
    task: str,
    scope: Any = _DEFAULT_SCOPE,
    focus: Sequence[Any] | Any = None,
    artifact_paths: Sequence[Any] | Any = None,
    max_findings: Any = _DEFAULT_MAX_FINDINGS,
    strictness: Any = _DEFAULT_STRICTNESS,
    item_id: str = _EXPERT_REVIEW_ITEM_ID,
    call_id: str = "",
) -> CommandExecutionResult:
    request_payload = parse_expert_review_command_payload(
        {
            "task": task,
            "scope": scope,
            "focus": focus,
            "artifact_paths": artifact_paths,
            "max_findings": max_findings,
            "strictness": strictness,
        }
    )
    item_events = [
        build_expert_review_requested_turn_event(
            item_id=item_id,
            call_id=call_id,
            **request_payload,
        )
    ]

    started_at = time.monotonic()
    gate_payload = _provider_review_gate(runtime)
    provider_items = _available_provider_items(runtime)
    selection = select_expert_review_reviewer(
        provider_items,
        review_gate=gate_payload,
        active_provider_name=_provider_status_text(runtime, "provider_name"),
        active_provider_public_name=_provider_public_name(runtime, gate_payload),
    )
    if not bool(selection.get("selected")):
        failure, failure_event = build_execution_failure_result_and_event(
            request_payload=request_payload,
            item_id=item_id,
            call_id=call_id,
            error_code=_selection_failure_error_code(selection),
            detail=_selection_failure_detail(selection),
            review_elapsed_ms=_elapsed_ms(started_at),
            selection_reason=str(selection.get("selection_reason") or ""),
            failure_result_builder=build_expert_review_failure_result,
            failed_event_builder=build_expert_review_failed_turn_event,
        )
        item_events.append(failure_event)
        return _expert_review_command_result(
            result=failure,
            request_payload=request_payload,
            gate_payload=gate_payload,
            selection=selection,
            item_events=item_events,
        )

    selected_reviewer = selected_reviewer_execution_metadata(selection)
    resolution = None
    try:
        resolution = runtime.agent.resolve_delegate_execution(
            _EXPERT_REVIEW_ROLE,
            **selected_reviewer.delegate_resolution_kwargs(),
        )
    except _EXPECTED_DELEGATE_EXCEPTIONS as exc:
        failure, failure_event = build_execution_failure_result_and_event(
            request_payload=request_payload,
            item_id=item_id,
            call_id=call_id,
            error_code=EXPERT_REVIEW_ERROR_DELEGATE_FAILED,
            detail=str(exc),
            review_elapsed_ms=_elapsed_ms(started_at),
            reviewer_metadata=selected_reviewer,
            stage="delegate",
            failure_result_builder=build_expert_review_failure_result,
            failed_event_builder=build_expert_review_failed_turn_event,
        )
        item_events.append(failure_event)
        return _expert_review_command_result(
            result=failure,
            request_payload=request_payload,
            gate_payload=gate_payload,
            selection=selection,
            item_events=item_events,
        )

    resolved_reviewer = resolved_reviewer_execution_metadata(selection, resolution)
    item_events.append(
        build_review_running_event(
            request_payload=request_payload,
            item_id=item_id,
            call_id=call_id,
            reviewer_metadata=resolved_reviewer,
            running_event_builder=build_expert_review_running_turn_event,
        )
    )

    try:
        packet = build_expert_review_packet(
            task=request_payload["task"],
            thread_turns=list(getattr(runtime, "history_turns", []) or []),
            runtime_state=_runtime_state_snapshot(runtime),
            scope=request_payload["scope"],
            focus=request_payload["focus"],
            artifact_paths=request_payload["artifact_paths"],
            max_findings=request_payload["max_findings"],
            strictness=request_payload["strictness"],
        )
        prompt_bundle = build_expert_review_reviewer_prompt(packet, policy=resolved_reviewer.prompt_policy())
    except _EXPECTED_PACKET_BUILD_EXCEPTIONS as exc:
        failure, failure_event = build_execution_failure_result_and_event(
            request_payload=request_payload,
            item_id=item_id,
            call_id=call_id,
            error_code=EXPERT_REVIEW_ERROR_PACKET_BUILD_FAILED,
            detail=str(exc),
            review_elapsed_ms=_elapsed_ms(started_at),
            reviewer_metadata=resolved_reviewer,
            stage="packet_build",
            failure_result_builder=build_expert_review_failure_result,
            failed_event_builder=build_expert_review_failed_turn_event,
        )
        item_events.append(failure_event)
        return _expert_review_command_result(
            result=failure,
            request_payload=request_payload,
            gate_payload=gate_payload,
            selection=selection,
            item_events=item_events,
        )

    child_agent_id = ""
    try:
        spawn_result = runtime.spawn_agent_result(
            **resolved_reviewer.spawn_request_kwargs(
                task=_reviewer_task_text(prompt_bundle),
                role=_EXPERT_REVIEW_ROLE,
                reason=_EXPERT_REVIEW_DELEGATION_REASON,
                mode=_EXPERT_REVIEW_DELEGATION_MODE,
                task_shape=_EXPERT_REVIEW_TASK_SHAPE,
            )
        )
        spawn_payload = _first_tool_payload(spawn_result)
        child_agent_id = str(spawn_payload.get("agent_id") or "").strip()
        if not child_agent_id:
            raise RuntimeError("expert_review delegated spawn did not return an agent_id")
        wait_result = runtime.wait_agent_result(
            child_agent_id,
            timeout_ms=_wait_timeout_ms(resolution),
            reason="wait_for_child_result",
        )
    except _EXPECTED_DELEGATE_EXCEPTIONS as exc:
        failure, failure_event = build_execution_failure_result_and_event(
            request_payload=request_payload,
            item_id=item_id,
            call_id=call_id,
            error_code=EXPERT_REVIEW_ERROR_DELEGATE_FAILED,
            detail=str(exc),
            review_elapsed_ms=_elapsed_ms(started_at),
            reviewer_metadata=resolved_reviewer,
            stage="delegate",
            failure_result_builder=build_expert_review_failure_result,
            failed_event_builder=build_expert_review_failed_turn_event,
        )
        item_events.append(failure_event)
        return _expert_review_command_result(
            result=failure,
            request_payload=request_payload,
            gate_payload=gate_payload,
            selection=selection,
            item_events=item_events,
            child_agent_id=child_agent_id,
        )

    wait_payload = _first_tool_payload(wait_result)
    wait_status = str(wait_payload.get("status") or "").strip().lower()
    review_elapsed_ms = _elapsed_ms(started_at)
    if wait_status != "completed":
        wait_failure_detail = _wait_failure_detail(wait_result, wait_payload)
        failure, failure_event = build_execution_failure_result_and_event(
            request_payload=request_payload,
            item_id=item_id,
            call_id=call_id,
            error_code=EXPERT_REVIEW_ERROR_DELEGATE_FAILED,
            detail=wait_failure_detail,
            review_elapsed_ms=review_elapsed_ms,
            reviewer_metadata=resolved_reviewer,
            stage="delegate",
            failure_result_builder=build_expert_review_failure_result,
            failed_event_builder=build_expert_review_failed_turn_event,
        )
        item_events.append(failure_event)
        return _expert_review_command_result(
            result=failure,
            request_payload=request_payload,
            gate_payload=gate_payload,
            selection=selection,
            item_events=item_events,
            child_agent_id=child_agent_id,
        )

    reviewer_output = _reviewer_output_text(wait_result, wait_payload)
    parsed_result = parse_expert_review_output(
        reviewer_output,
        **resolved_reviewer.parse_result_kwargs(
            scope=request_payload["scope"],
            focus=request_payload["focus"],
            strictness=request_payload["strictness"],
            review_elapsed_ms=review_elapsed_ms,
        ),
    )
    item_events.append(
        build_parsed_review_result_event(
            parsed_result=parsed_result,
            request_payload=request_payload,
            item_id=item_id,
            call_id=call_id,
            reviewer_metadata=resolved_reviewer,
            review_elapsed_ms=review_elapsed_ms,
            wait_failure_detail=_wait_failure_detail(wait_result, wait_payload),
            default_parse_error_code=EXPERT_REVIEW_ERROR_PARSE_FAILED,
            reviewer_identity_fn=expert_review_reviewer_identity,
            completed_event_builder=build_expert_review_completed_turn_event,
            failed_event_builder=build_expert_review_failed_turn_event,
        )
    )
    return _expert_review_command_result(
        result=parsed_result,
        request_payload=request_payload,
        gate_payload=gate_payload,
        selection=selection,
        item_events=item_events,
        child_agent_id=child_agent_id,
    )
__all__ = [
    "parse_expert_review_command_payload",
    "run_expert_review",
]
