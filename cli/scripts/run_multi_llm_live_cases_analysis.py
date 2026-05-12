from __future__ import annotations

import statistics
from typing import Any

from cli.agent_cli.runtime import AgentCliRuntime

from cli.scripts.run_multi_llm_live_cases_catalog import (
    CI_REUSE_RECOMMENDED_COMMANDS,
    LiveCase,
)


def _failure_category(errors: list[str], case_result: dict[str, Any]) -> str:
    del case_result
    error_set = {str(item or "").strip() for item in list(errors or []) if str(item or "").strip()}
    if not error_set:
        return "none"
    if "bootstrap_failure" in error_set:
        return "bootstrap_failure"
    if "case_execution_failure" in error_set:
        return "case_execution_failure"
    if "assistant_text_missing" in error_set:
        return "empty_response"
    if "missing_provider_trace_request" in error_set:
        return "missing_trace_request"
    if "missing_spawn_agent_event" in error_set:
        return "missing_spawn_event"
    return ",".join(sorted(error_set))


def _report_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total_cases = len(cases)
    passed_count = sum(1 for item in cases if bool(item.get("passed")))
    failed_count = total_cases - passed_count
    phase_counts: dict[str, int] = {}
    failure_categories: dict[str, int] = {}
    wall_values: list[int] = []
    for item in cases:
        phase = str(item.get("phase") or "").strip() or "unknown"
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        category = str(item.get("failure_category") or "").strip() or "none"
        failure_categories[category] = failure_categories.get(category, 0) + 1
        wall_ms = int(item.get("case_wall_ms") or 0)
        if wall_ms > 0:
            wall_values.append(wall_ms)
    return {
        "total_cases": total_cases,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "pass_rate": round(passed_count / total_cases, 4) if total_cases else 0.0,
        "phase_counts": phase_counts,
        "failure_categories": failure_categories,
        "avg_case_wall_ms": round(statistics.mean(wall_values), 1) if wall_values else None,
    }


def _ci_reuse_block(
    *,
    profile: str,
    strict: bool,
    selected_case_names: list[str],
    summary: dict[str, Any],
) -> dict[str, Any]:
    normalized_profile = str(profile or "all").strip() or "all"
    recommended = CI_REUSE_RECOMMENDED_COMMANDS.get(normalized_profile, "")
    failed_count = int(summary.get("failed_count") or 0)
    ci_gate_passed = failed_count == 0 if strict else True
    return {
        "profile": normalized_profile,
        "strict": bool(strict),
        "selected_case_names": list(selected_case_names),
        "recommended_command": str(recommended),
        "ci_gate_passed": bool(ci_gate_passed),
    }


def _valid_trace_request(case_result: dict[str, Any]) -> bool:
    requests = list((case_result.get("llm_trace") or {}).get("requests") or [])
    for item in requests:
        if not isinstance(item, dict):
            continue
        if str(item.get("provider_name") or "").strip() and str(item.get("model") or "").strip():
            return True
    return False


def _status_items(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _append_orchestration_expectation_errors(
    case: LiveCase,
    case_result: dict[str, Any],
    errors: list[str],
) -> None:
    expected_decision = str(case.expected_orchestration_decision or "").strip()
    expected_stay_local_reason = str(case.expected_stay_local_reason or "").strip()
    expected_counterexamples = [str(item or "").strip() for item in case.expected_stay_local_counterexamples if str(item or "").strip()]
    if not expected_decision and not expected_stay_local_reason and not expected_counterexamples:
        return
    status = case_result.get("runtime_provider_status") or {}
    if not isinstance(status, dict):
        status = {}
    observed_decision = str(status.get("orchestration_decision") or "").strip()
    if expected_decision:
        if not observed_decision:
            errors.append("missing_orchestration_decision")
        elif observed_decision != expected_decision:
            errors.append("orchestration_decision_mismatch")
    if expected_stay_local_reason:
        observed_reason = str(status.get("orchestration_stay_local_reason") or "").strip()
        if observed_reason != expected_stay_local_reason:
            errors.append("stay_local_reason_mismatch")
    if expected_counterexamples:
        observed_counterexamples = _status_items(status.get("orchestration_stay_local_counterexamples"))
        if observed_counterexamples != expected_counterexamples:
            errors.append("stay_local_counterexamples_mismatch")


def _validation_errors(case: LiveCase, case_result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    assistant_text = str(case_result.get("assistant_text") or "").strip()
    if not assistant_text or assistant_text == "模型未返回内容。":
        errors.append("assistant_text_missing")

    tool_event_names = {
        str(name or "").strip()
        for name in list(case_result.get("tool_event_names") or [])
        if str(name or "").strip()
    }
    expected_spawn_agent = case.expected_spawn_agent
    if expected_spawn_agent is False and "spawn_agent" in tool_event_names:
        errors.append("unexpected_spawn_agent_event")
    elif expected_spawn_agent is True and "spawn_agent" not in tool_event_names:
        errors.append("missing_spawn_agent_event")

    if case.phase in {"tool_followup", "final_synthesis"}:
        _append_orchestration_expectation_errors(case, case_result, errors)
        if not _valid_trace_request(case_result):
            errors.append("missing_provider_trace_request")
        return errors

    if case.phase == "orchestrate_background_teammate":
        run_id = str(case_result.get("orchestration_run_id") or "").strip()
        if not run_id:
            errors.append("missing_orchestration_run_id")
        if case_result.get("orchestration_dispatched") is not True:
            errors.append("missing_orchestration_dispatch")
        dispatch_refs = [str(item or "").strip() for item in list(case_result.get("orchestration_dispatch_refs") or []) if str(item or "").strip()]
        if not dispatch_refs:
            errors.append("missing_orchestration_dispatch_ref")
        elif not any(":background_task:bg_teammate" in item for item in dispatch_refs):
            errors.append("orchestration_dispatch_not_teammate_background")
        if case_result.get("orchestration_progressed") is not True:
            errors.append("missing_orchestration_progress")
        _append_orchestration_expectation_errors(case, case_result, errors)
        return errors

    if case.phase != "spawn_agent":
        _append_orchestration_expectation_errors(case, case_result, errors)
        return errors

    if case.expected_spawn_agent is None and "spawn_agent" not in tool_event_names:
        errors.append("missing_spawn_agent_event")
    if not str(case_result.get("delegated_provider_name") or "").strip():
        errors.append("missing_delegated_provider")
    if not str(case_result.get("delegated_model") or "").strip():
        errors.append("missing_delegated_model")
    if not str(case_result.get("delegated_source") or "").strip():
        errors.append("missing_delegated_source")
    expected_source = str(case.expected_delegated_source or "").strip()
    if expected_source and str(case_result.get("delegated_source") or "").strip() != expected_source:
        errors.append("delegated_source_mismatch")
    if str(case.role or "").strip() and str(case_result.get("delegated_role") or "").strip() != str(case.role).strip():
        errors.append("delegated_role_mismatch")

    expected_mode = str(case.expected_delegation_mode or (case.spawn_overrides or {}).get("mode") or "").strip()
    if expected_mode and str(case_result.get("delegation_mode") or "").strip() != expected_mode:
        errors.append("delegation_mode_mismatch")
    expected_task_shape = str(case.expected_task_shape or (case.spawn_overrides or {}).get("task_shape") or "").strip()
    if expected_task_shape and str(case_result.get("delegated_task_shape") or "").strip() != expected_task_shape:
        errors.append("delegated_task_shape_mismatch")
    expected_wait_required = case.expected_wait_required
    if expected_wait_required is None and "wait_required" in dict(case.spawn_overrides or {}):
        expected_wait_required = (case.spawn_overrides or {}).get("wait_required")
    if expected_wait_required is not None:
        if case_result.get("delegated_wait_required") is not expected_wait_required:
            errors.append("delegated_wait_required_mismatch")
    expected_background_priority = str(case.expected_background_priority or "").strip()
    if expected_background_priority and str(case_result.get("delegated_background_priority") or "").strip() != expected_background_priority:
        errors.append("delegated_background_priority_mismatch")

    if case.wait_timeout_ms > 0:
        if "wait_agent" not in tool_event_names:
            errors.append("missing_wait_agent_event")
        if case.wait_required is True:
            if str(case_result.get("wait_status") or "").strip() != "completed":
                errors.append("wait_status_not_completed")
            if case_result.get("wait_result_ready") is not True:
                errors.append("wait_result_not_ready")
            if case_result.get("wait_adopted") is not True:
                errors.append("wait_result_not_adopted")

    _append_orchestration_expectation_errors(case, case_result, errors)
    return errors


def _runtime_provider_status(runtime: AgentCliRuntime | None) -> dict[str, Any]:
    if runtime is None:
        return {}
    try:
        return dict(runtime.agent.provider_status() or {})
    except Exception as exc:
        return {
            "provider_ready": "false",
            "error": str(exc),
        }


def _failed_case_result(
    case: LiveCase,
    *,
    error_code: str,
    error_message: str,
    runtime_provider_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": case.name,
        "phase": case.phase,
        "prompt": case.prompt,
        "commands": list(case.commands),
        "setup_results": [],
        "assistant_text": "用例执行失败。",
        "tool_event_summaries": [],
        "tool_event_names": [],
        "delegated_agent_id": "",
        "delegated_async": None,
        "delegated_role": "",
        "delegation_reason": "",
        "delegation_mode": "",
        "delegated_wait_required": None,
        "delegated_task_shape": "",
        "delegated_background_priority": "",
        "delegated_parallel_group": "",
        "delegated_provider_name": "",
        "delegated_model": "",
        "delegated_source": "",
        "wait_assistant_text": "",
        "wait_tool_event_names": [],
        "wait_status": "",
        "wait_decision": "",
        "wait_result_ready": None,
        "wait_adopted": None,
        "orchestration_run_id": "",
        "orchestration_created": False,
        "orchestration_dispatched": False,
        "orchestration_progressed": False,
        "orchestration_dispatch_refs": [],
        "orchestration_selected_cards": [],
        "orchestration_dispatched_cards": [],
        "orchestration_status": "",
        "orchestration_phase": "",
        "orchestration_progress_status": "",
        "orchestration_progress_phase": "",
        "case_wall_ms": 0,
        "llm_trace": {"stages": [], "requests": []},
        "log_dir": "",
        "runtime_provider_status": dict(runtime_provider_status or {}),
        "fatal_error": {
            "code": str(error_code),
            "message": str(error_message),
        },
        "validation_errors": [str(error_code)],
        "__fatal_error__": True,
    }
