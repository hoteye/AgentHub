from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import (
    AgentIntent,
    PromptAttachment,
    ResponseInputItem,
    ToolEvent,
    default_response_items,
)
from cli.agent_cli.providers.openai_client import call_with_provider_retries


class ChatCompletionsFinalizeMixin:
    def _finalize_chat_plan(
        self,
        *,
        started_at: float,
        user_text: str,
        attachments: list[PromptAttachment] | None,
        tool_executor,
        executed_events: list[ToolEvent],
        executed_item_events: list[dict[str, Any]],
        final_text: str,
        policy_question: bool,
        policy_summary_question: bool,
        policy_query_plan: list[str],
        initial_model_ms: int,
        tool_execution_ms: int,
        synthesis_model_ms: int,
        planning_rounds: int,
        synthesis_rounds: int,
        planning_trace: list[dict[str, Any]],
        synthesis_trace: list[dict[str, Any]],
        response_items: list[ResponseInputItem],
        turn_engine_turn_events: list[dict[str, Any]],
        turn_engine_item_event_count: int,
        perf_counter_fn: Callable[[], float],
    ) -> AgentIntent:
        policy_turn = self._is_policy_grounded_turn(user_text, executed_events)
        raw_evidence_blocks = self._policy_evidence_blocks(executed_events) if policy_turn else []
        evidence_blocks = (
            self._policy_effective_evidence_v2(user_text, raw_evidence_blocks)
            if raw_evidence_blocks
            else []
        )
        if (
            tool_executor is not None
            and policy_question
            and (
                not raw_evidence_blocks
                or not self._policy_has_readable_normative_evidence(evidence_blocks)
            )
        ):
            preflight_events, preflight_item_events = self._execute_policy_preflight(
                user_text,
                executed_events,
                executed_item_events,
                tool_executor,
            )
            if preflight_events:
                executed_events.extend(preflight_events)
                executed_item_events.extend(preflight_item_events)
                policy_turn = self._is_policy_grounded_turn(user_text, executed_events)
                raw_evidence_blocks = (
                    self._policy_evidence_blocks(executed_events) if policy_turn else []
                )
                evidence_blocks = (
                    self._policy_effective_evidence_v2(user_text, raw_evidence_blocks)
                    if raw_evidence_blocks
                    else []
                )
        evidence_profile = (
            self._policy_evidence_profile_v2(evidence_blocks, raw_evidence_blocks)
            if evidence_blocks
            else {}
        )
        summary_fast_path = False
        if not final_text and policy_summary_question and evidence_blocks:
            final_text = self._policy_summary_fast_answer_v2(evidence_blocks)
            summary_fast_path = bool(final_text)
        if policy_turn and executed_events and not raw_evidence_blocks:
            final_text = self._policy_no_evidence_fallback_text_v2(user_text, executed_events)
        unsupported_claims = (
            []
            if summary_fast_path
            else (
                self._unsupported_policy_claims(final_text, evidence_blocks)
                if final_text and evidence_blocks
                else []
            )
        )
        answer_contradictions = (
            self._policy_answer_contradictions_v2(user_text, final_text, evidence_blocks)
            if final_text and evidence_blocks and not summary_fast_path
            else []
        )
        coverage_issues = (
            self._policy_answer_coverage_issues_v2(final_text, evidence_profile)
            if final_text and evidence_profile and not summary_fast_path
            else []
        )
        coverage_issues = [*coverage_issues, *answer_contradictions]

        should_run_synthesis = bool(executed_events) and (
            (policy_turn and (not final_text or unsupported_claims or coverage_issues))
            or ((not policy_turn) and not final_text)
        )
        if should_run_synthesis:
            prior_final_text = final_text
            prior_unsupported_claims = list(unsupported_claims)
            prior_coverage_issues = list(coverage_issues)
            try:
                synthesis_kwargs: dict[str, Any] = {
                    "model": self.config.model,
                    "messages": self._synthesis_messages(
                        user_text=user_text,
                        executed_events=executed_events,
                        executed_item_events=executed_item_events,
                        attachments=attachments,
                    ),
                    "stream": False,
                }
                extra_body = self._request_extra_body()
                if extra_body:
                    synthesis_kwargs["extra_body"] = extra_body
                synthesis_started_at = perf_counter_fn()
                synthesis_response = call_with_provider_retries(
                    lambda: self._chat_completion_create(
                        timeout=self.model_timeout,
                        **synthesis_kwargs,
                    )
                )
                synthesis_elapsed_ms = int((perf_counter_fn() - synthesis_started_at) * 1000)
                synthesis_model_ms += synthesis_elapsed_ms
                synthesis_rounds += 1
                synthesis_choice = synthesis_response.choices[0]
                synthesis_message = synthesis_choice.message
                synthesized_text = self._sanitize_final_answer_text(
                    self._message_content_text(getattr(synthesis_message, "content", ""))
                )
                synthesis_trace.append(
                    {
                        "round": synthesis_rounds,
                        "model_ms": synthesis_elapsed_ms,
                        "answered": bool(synthesized_text),
                        "answer_preview": synthesized_text[:120] if synthesized_text else "",
                    }
                )
                if synthesized_text:
                    final_text = synthesized_text
                    response_items = default_response_items(assistant_text=synthesized_text)
                elif prior_final_text:
                    final_text = prior_final_text
                if evidence_blocks:
                    unsupported_claims = (
                        self._unsupported_policy_claims(final_text, evidence_blocks)
                        if final_text
                        else prior_unsupported_claims
                    )
                    coverage_issues = []
                    if final_text:
                        coverage_issues.extend(
                            self._policy_answer_coverage_issues_v2(final_text, evidence_profile)
                        )
                        coverage_issues.extend(
                            self._policy_answer_contradictions_v2(
                                user_text, final_text, evidence_blocks
                            )
                        )
                    else:
                        coverage_issues = prior_coverage_issues
            except Exception:
                final_text = prior_final_text
                unsupported_claims = prior_unsupported_claims
                coverage_issues = prior_coverage_issues

        if evidence_blocks and (not final_text or unsupported_claims or coverage_issues):
            if coverage_issues:
                final_text = self._policy_coverage_fallback_text_v2(
                    user_text,
                    evidence_blocks,
                    evidence_profile,
                    unsupported_claims=unsupported_claims,
                    coverage_issues=coverage_issues,
                )
            else:
                final_text = self._policy_grounded_fallback_text_v2(
                    user_text,
                    evidence_blocks,
                    evidence_profile,
                    unsupported_claims=unsupported_claims,
                )

        if not final_text:
            final_text = (
                self._structured_tool_fallback_text(user_text, executed_events)
                if executed_events
                else "模型未返回内容。"
            )
        final_text = self._sanitize_final_answer_text(final_text)
        if not response_items:
            response_items = default_response_items(assistant_text=final_text)
        activity_events = self._policy_activity_events_v2(
            user_text=user_text,
            query_plan=policy_query_plan,
            executed_events=executed_events,
            evidence_blocks=evidence_blocks,
            evidence_profile=evidence_profile,
            final_text=final_text,
            unsupported_claims=unsupported_claims,
            coverage_issues=coverage_issues,
        )
        activity_events = [
            *self._native_web_search_activity_events(
                user_text=user_text, executed_events=executed_events
            ),
            *activity_events,
        ]
        existing_turn_events: list[dict[str, Any]] = list(turn_engine_turn_events)
        if existing_turn_events and turn_engine_item_event_count != len(executed_item_events):
            existing_turn_events = []
        timings = {
            "initial_model_ms": initial_model_ms,
            "tool_execution_ms": tool_execution_ms,
            "synthesis_model_ms": synthesis_model_ms,
            "total_ms": int((perf_counter_fn() - started_at) * 1000),
            "planning_rounds": planning_rounds,
            "synthesis_rounds": synthesis_rounds,
            "planning_trace": planning_trace,
            "synthesis_trace": synthesis_trace,
            "tool_call_count": len(executed_events),
        }

        return AgentIntent(
            assistant_text=final_text,
            response_items=response_items,
            command_text=None,
            status_hint="tool" if executed_events else "llm",
            tool_events=executed_events,
            turn_events=self._canonical_turn_events(
                assistant_text=final_text,
                response_items=response_items,
                executed_item_events=executed_item_events,
                existing_turn_events=existing_turn_events,
            ),
            activity_events=activity_events,
            timings=timings,
        )
