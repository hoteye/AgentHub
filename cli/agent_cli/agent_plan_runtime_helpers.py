from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli import agent_plan_facade_runtime, agent_plan_runtime
from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent
from cli.agent_cli.providers import availability_runtime as availability_runtime_service
from cli.agent_cli.runtime_core.local_routing import extract_first_url, looks_like_live_web_query


def plan_with_provider_and_fallback(
    agent: Any,
    text: str,
    *,
    history: list[dict[str, str]] | None = None,
    tool_executor: Callable[[str], tuple[str, list[ToolEvent]]] | None = None,
    attachments: list[PromptAttachment] | None = None,
    input_items: list[dict[str, Any]] | None = None,
    prompt_cache_key: str | None = None,
    turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
    provider_session_id: str | None = None,
    provider_turn_id: str | None = None,
    provider_sandbox_mode: str | None = None,
    initial_previous_response_id: str | None = None,
) -> AgentIntent:
    normalized = (text or "").strip().lower()
    if not normalized and not input_items:
        return AgentIntent(assistant_text="请输入命令或问题。")

    shell_alias_intent = agent_plan_runtime.host_shell_alias_intent(
        text,
        normalized,
        host_platform=agent.host_platform,
    )
    if shell_alias_intent is not None:
        return agent._intent_with_protocol_path(
            shell_alias_intent,
            kind="host_short_circuit_shell_alias",
            source="host",
            provider_used=False,
            parity_evaluable=False,
            reason="explicit_shell_alias",
        )

    if agent._planner is None:
        ensure_planner_loaded = getattr(agent, "_ensure_planner_loaded", None)
        if callable(ensure_planner_loaded):
            ensure_planner_loaded()

    if agent._planner is not None:
        planner_started_at = time.perf_counter()
        try:
            planner_kwargs = agent_plan_runtime.planner_call_kwargs(
                agent._planner,
                filter_callable_kwargs=agent._filter_callable_kwargs,
                tool_executor=tool_executor,
                attachments=attachments,
                input_items=input_items,
                prompt_cache_key=prompt_cache_key,
                turn_event_callback=turn_event_callback,
                provider_session_id=provider_session_id,
                provider_turn_id=provider_turn_id,
                provider_sandbox_mode=provider_sandbox_mode,
                initial_previous_response_id=initial_previous_response_id,
            )
            intent = agent._planner.plan(text, history or [], **planner_kwargs)
            agent._planner_runtime_error = None
            agent._planner_runtime_error_diagnostics = None
            success_diagnostics = dict(intent.timings or {})
            success_diagnostics.setdefault(
                "observed_elapsed_ms", int((time.perf_counter() - planner_started_at) * 1000)
            )
            availability_runtime_service.mark_provider_success(
                agent,
                planner=agent._planner,
                diagnostics=success_diagnostics,
            )
            return agent._intent_with_protocol_path(
                intent,
                kind=(
                    "provider_replay_loop"
                    if agent._planner_is_replay_runtime()
                    else "provider_loop"
                ),
                source="provider",
                provider_used=True,
                parity_evaluable=True,
                reason="planner_execution",
            )
        except Exception as exc:
            agent._planner_runtime_error = f"{type(exc).__name__}: {exc}"
            diagnostics = getattr(exc, "agenthub_provider_diagnostics", None)
            failure_diagnostics = dict(diagnostics or {}) if isinstance(diagnostics, dict) else {}
            failure_diagnostics.setdefault(
                "observed_elapsed_ms", int((time.perf_counter() - planner_started_at) * 1000)
            )
            agent._planner_runtime_error_diagnostics = failure_diagnostics or None
            availability_runtime_service.mark_provider_failure(
                agent,
                planner=agent._planner,
                exc=exc,
                diagnostics=failure_diagnostics,
            )
            if timeline_debug_enabled():
                log_timeline(
                    "agent.plan.provider_exception",
                    error_type=type(exc).__name__,
                    error_text=str(exc),
                    provider_ready=agent._planner is not None,
                )

    explicit_url = extract_first_url(text)
    live_web_query = looks_like_live_web_query(text)
    if live_web_query or explicit_url:
        fallback_intent = agent._live_web_fallback_intent(text, tool_executor=tool_executor)
        if fallback_intent is not None:
            runtime_error = str(agent._planner_runtime_error or "").strip()
            if runtime_error:
                diagnostic_lines: list[str] = []
                diagnostic_builder = getattr(agent, "_planner_runtime_error_diagnostic_lines", None)
                if callable(diagnostic_builder):
                    try:
                        diagnostic_lines = [
                            str(line).strip()
                            for line in list(diagnostic_builder() or [])
                            if str(line).strip()
                        ]
                    except Exception:
                        diagnostic_lines = []

                protocol_diagnostics = dict(
                    getattr(fallback_intent, "protocol_diagnostics", {}) or {}
                )
                protocol_diagnostics["provider_runtime_error"] = runtime_error
                if diagnostic_lines:
                    protocol_diagnostics["provider_runtime_error_diagnostics"] = diagnostic_lines
                fallback_intent.protocol_diagnostics = protocol_diagnostics

                commentary_lines = []
                existing_commentary = str(
                    getattr(fallback_intent, "commentary_text", "") or ""
                ).strip()
                if existing_commentary:
                    commentary_lines.append(existing_commentary)
                commentary_lines.append("主 provider 本轮失败，已切换到 live_web_fallback。")
                commentary_lines.append(f"provider_error={runtime_error}")
                if diagnostic_lines:
                    commentary_lines.extend(diagnostic_lines)
                fallback_intent.commentary_text = "\n".join(commentary_lines)
            return agent_plan_facade_runtime.intent_with_protocol_path(
                fallback_intent,
                kind="host_short_circuit_live_web_fallback",
                source="host",
                provider_used=False,
                parity_evaluable=False,
                reason="live_web_fallback",
                intent_with_protocol_path_fn=agent._intent_with_protocol_path,
            )

    shell_intent = agent._match_shell_intent(text, normalized)
    if shell_intent is not None:
        return agent._intent_with_protocol_path(
            shell_intent,
            kind="host_short_circuit_shell_intent",
            source="host",
            provider_used=False,
            parity_evaluable=False,
            reason="rule_based_shell_intent",
        )

    if agent._planner_error is not None or agent._planner_runtime_error is not None:
        if timeline_debug_enabled():
            log_timeline(
                "agent.plan.degraded_fallback",
                planner_error=agent._planner_error,
                planner_runtime_error=agent._planner_runtime_error,
            )
        return agent_plan_facade_runtime.degraded_fallback_intent(
            planner_fallback_text=agent._planner_fallback_text(),
            intent_with_protocol_path_fn=agent._intent_with_protocol_path,
        )

    return agent_plan_facade_runtime.no_provider_intent(
        intent_with_protocol_path_fn=agent._intent_with_protocol_path,
    )
