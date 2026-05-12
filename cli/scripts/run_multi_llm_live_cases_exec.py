from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from cli.agent_cli.models import AgentIntent, ToolEvent
from cli.agent_cli.providers.anthropic_claude_helpers import AnthropicMessagesSession, build_anthropic_client
from cli.agent_cli.runtime import AgentCliRuntime
from cli.scripts.run_multi_llm_live_cases_catalog import LiveCase
from cli.scripts.run_multi_llm_live_cases_exec_projection_helpers import _delegation_view, _route_view
from cli.scripts.run_multi_llm_live_cases_exec_route_helpers import (
    _anthropic_route_intent as _anthropic_route_intent_impl,
    _chat_completion_route_intent,
    _generic_tool_synthesis_prompt,
    _planner_case_intent as _planner_case_intent_impl,
)
from cli.scripts.run_multi_llm_live_cases_exec_tool_helpers import (
    RuntimeToolExecutor,
    _command_text,
    _line_items,
    _line_value,
    _run_setup_command,
    _run_tool_command,
    _spawn_agent_command,
    _wait_agent_command,
)
from cli.scripts.run_multi_llm_live_cases_exec_trace_helpers import _extract_llm_trace


def _anthropic_route_intent(
    planner: Any,
    *,
    route_name: str,
    user_text: str,
    executed_events: list[ToolEvent],
    executed_item_events: list[dict[str, Any]] | None = None,
) -> AgentIntent:
    return _anthropic_route_intent_impl(
        planner,
        route_name=route_name,
        user_text=user_text,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        anthropic_session_cls=AnthropicMessagesSession,
        anthropic_client_builder=build_anthropic_client,
    )


def _planner_case_intent(
    planner: Any,
    *,
    route_name: str,
    user_text: str,
    executed_events: list[ToolEvent],
    tool_executor: RuntimeToolExecutor | None = None,
    executed_item_events: list[dict[str, Any]] | None = None,
) -> AgentIntent:
    return _planner_case_intent_impl(
        planner,
        route_name=route_name,
        user_text=user_text,
        executed_events=executed_events,
        tool_executor=tool_executor,
        executed_item_events=executed_item_events,
        anthropic_session_cls=AnthropicMessagesSession,
        anthropic_client_builder=build_anthropic_client,
    )


def _run_case(
    planner: Any,
    executor: RuntimeToolExecutor,
    runtime: AgentCliRuntime,
    *,
    case: LiveCase,
    workspace_root: str,
    log_root: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    case_log_dir = log_root / case.name
    if case_log_dir.exists():
        shutil.rmtree(case_log_dir)
    case_log_dir.mkdir(parents=True, exist_ok=True)

    previous_log_dir = os.environ.get("AGENTHUB_DEBUG_LOG_DIR")
    os.environ["AGENTHUB_DEBUG_LOG_DIR"] = str(case_log_dir)
    try:
        executed_events: list[ToolEvent] = []
        setup_results: list[dict[str, Any]] = []
        wait_assistant_text = ""
        wait_tool_event_names: list[str] = []
        wait_payload: dict[str, Any] = {}
        orchestration_run_id = ""
        orchestration_created = False
        orchestration_dispatched = False
        orchestration_progressed = False
        orchestration_dispatch_refs: list[str] = []
        orchestration_selected_cards: list[str] = []
        orchestration_dispatched_cards: list[str] = []
        orchestration_status = ""
        orchestration_phase = ""
        orchestration_progress_status = ""
        orchestration_progress_phase = ""
        for command_text in case.setup_commands:
            setup_result = _run_setup_command(
                executor,
                command_text=command_text,
            )
            setup_results.append(
                {
                    "command": command_text,
                    "assistant_text": str(setup_result.assistant_text or ""),
                    "tool_event_names": [str(event.name or "") for event in list(setup_result.tool_events or [])],
                    "tool_event_summaries": [str(event.summary or "") for event in list(setup_result.tool_events or [])],
                }
            )
        for command in case.commands:
            executed_events.extend(
                _run_tool_command(
                    executor,
                    command=command,
                    workdir=workspace_root,
                )
            )
        if case.phase == "tool_followup":
            intent = _planner_case_intent(
                planner,
                route_name="tool_followup",
                user_text=case.prompt,
                executed_events=executed_events,
                tool_executor=executor,
            )
        elif case.phase == "final_synthesis":
            intent = _planner_case_intent(
                planner,
                route_name="final_synthesis",
                user_text=case.prompt,
                executed_events=executed_events,
            )
            intent_assistant_text = str(intent.assistant_text or "")
            intent_tool_events = list(intent.tool_events or executed_events)
        elif case.phase == "spawn_agent":
            result = executor.run_structured(_spawn_agent_command(case))
            intent_assistant_text = str(result.assistant_text or "")
            intent_tool_events = list(result.tool_events or [])
            if case.wait_timeout_ms > 0:
                spawned_payload = dict(intent_tool_events[-1].payload or {}) if intent_tool_events else {}
                agent_id = str(spawned_payload.get("agent_id") or "").strip()
                if not agent_id:
                    raise RuntimeError(f"spawn_agent case {case.name} did not return agent_id")
                wait_result = executor.run_structured(
                    _wait_agent_command(
                        agent_id,
                        timeout_ms=case.wait_timeout_ms,
                        reason=case.wait_reason,
                        wait_required=case.wait_required,
                    )
                )
                wait_assistant_text = str(wait_result.assistant_text or "")
                if wait_assistant_text.strip():
                    intent_assistant_text = wait_assistant_text
                wait_tool_event_names = [str(event.name or "") for event in list(wait_result.tool_events or [])]
                if wait_result.tool_events:
                    wait_payload = dict(wait_result.tool_events[-1].payload or {})
                intent_tool_events.extend(list(wait_result.tool_events or []))
        elif case.phase == "orchestrate_background_teammate":
            create_result = executor.run_structured(f"/orchestrate {case.prompt}")
            create_text = str(create_result.assistant_text or "")
            orchestration_run_id = _line_value(create_text, "run_id")
            orchestration_created = "orchestration run created" in create_text
            if not orchestration_run_id:
                raise RuntimeError(f"orchestrate case {case.name} did not return run_id")
            dispatch_result = executor.run_structured(f"/orchestrate_dispatch {orchestration_run_id}")
            dispatch_text = str(dispatch_result.assistant_text or "")
            orchestration_dispatched = "orchestration dispatch submitted" in dispatch_text
            orchestration_dispatch_refs = _line_items(dispatch_text, "dispatch_refs")
            orchestration_selected_cards = _line_items(dispatch_text, "selected_cards")
            orchestration_dispatched_cards = _line_items(dispatch_text, "dispatched_cards")
            orchestration_status = _line_value(dispatch_text, "status")
            orchestration_phase = _line_value(dispatch_text, "current_phase")

            progress_result = executor.run_structured(f"/orchestrate_progress {orchestration_run_id}")
            progress_text = str(progress_result.assistant_text or "")
            orchestration_progressed = "orchestration progress updated" in progress_text
            orchestration_progress_status = _line_value(progress_text, "status")
            orchestration_progress_phase = _line_value(progress_text, "current_phase")

            intent_assistant_text = progress_text
            intent_tool_events = list(create_result.tool_events or []) + list(dispatch_result.tool_events or []) + list(progress_result.tool_events or [])
        else:
            raise RuntimeError(f"unsupported case phase: {case.phase}")
        if case.phase not in {"spawn_agent", "orchestrate_background_teammate"}:
            intent_assistant_text = str(intent.assistant_text or "")
            intent_tool_events = list(intent.tool_events or executed_events)
    finally:
        if previous_log_dir is None:
            os.environ.pop("AGENTHUB_DEBUG_LOG_DIR", None)
        else:
            os.environ["AGENTHUB_DEBUG_LOG_DIR"] = previous_log_dir

    trace = _extract_llm_trace(case_log_dir)
    delegated_payload = {}
    if case.phase == "spawn_agent" and intent_tool_events:
        for event in list(intent_tool_events or []):
            if str(event.name or "").strip() == "spawn_agent":
                delegated_payload = dict(event.payload or {})
                break
    return {
        "name": case.name,
        "phase": case.phase,
        "prompt": case.prompt,
        "commands": list(case.commands),
        "setup_results": setup_results,
        "assistant_text": intent_assistant_text,
        "tool_event_summaries": [str(event.summary or "") for event in intent_tool_events],
        "tool_event_names": [str(event.name or "") for event in intent_tool_events],
        "delegated_agent_id": str(delegated_payload.get("agent_id") or ""),
        "delegated_async": delegated_payload.get("async"),
        "delegated_role": str(delegated_payload.get("role") or ""),
        "delegation_reason": str(delegated_payload.get("delegation_reason") or ""),
        "delegation_mode": str(delegated_payload.get("delegation_mode") or ""),
        "delegated_wait_required": delegated_payload.get("wait_required"),
        "delegated_task_shape": str(delegated_payload.get("task_shape") or ""),
        "delegated_background_priority": str(delegated_payload.get("background_priority") or ""),
        "delegated_parallel_group": str(delegated_payload.get("parallel_group") or ""),
        "delegated_provider_name": str(delegated_payload.get("provider_name") or ""),
        "delegated_model": str(delegated_payload.get("model") or ""),
        "delegated_source": str(delegated_payload.get("source") or ""),
        "wait_assistant_text": wait_assistant_text,
        "wait_tool_event_names": wait_tool_event_names,
        "wait_status": str(wait_payload.get("status") or ""),
        "wait_decision": str(wait_payload.get("wait_decision") or ""),
        "wait_result_ready": wait_payload.get("result_ready"),
        "wait_adopted": wait_payload.get("adopted"),
        "orchestration_run_id": orchestration_run_id,
        "orchestration_created": orchestration_created,
        "orchestration_dispatched": orchestration_dispatched,
        "orchestration_progressed": orchestration_progressed,
        "orchestration_dispatch_refs": orchestration_dispatch_refs,
        "orchestration_selected_cards": orchestration_selected_cards,
        "orchestration_dispatched_cards": orchestration_dispatched_cards,
        "orchestration_status": orchestration_status,
        "orchestration_phase": orchestration_phase,
        "orchestration_progress_status": orchestration_progress_status,
        "orchestration_progress_phase": orchestration_progress_phase,
        "case_wall_ms": int((time.perf_counter() - started) * 1000),
        "llm_trace": trace,
        "log_dir": str(case_log_dir),
        "runtime_provider_status": dict(runtime.agent.provider_status() or {}),
    }
