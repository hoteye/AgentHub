from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

from cli.agent_cli.core.turn_engine import ToolExecutionResult
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.models import AgentIntent, ToolEvent


class ChatCompletionsTurnEngineMixin:
    def _planning_intent_with_turn_engine(
        self,
        *,
        user_text: str,
        messages: List[Dict[str, Any]],
        tool_executor,
    ) -> AgentIntent:
        session_cls = getattr(self, "_turn_engine_session_cls")
        turn_engine_cls = getattr(self, "_turn_engine_cls")
        tool_specs_builder = getattr(self, "_turn_engine_tool_specs_builder")
        command_builder = getattr(self, "_turn_engine_command_builder")
        perf_counter_fn = getattr(self, "_turn_engine_perf_counter_fn")

        session = session_cls(
            client=self.client,
            create_fn=lambda **kwargs: self._chat_completion_create(timeout=self.model_timeout, **kwargs),
            model=self.config.model,
            tool_specs=tool_specs_builder(
                self.config,
                self.host_platform,
                plugin_manager_factory=self.plugin_manager_factory or PluginManager,
            ),
            supports_tools=self.supports_tools,
            supports_developer_role=(
                (self.config.planner_kind or "").strip().lower() not in {"deepseek_chat", "deepseek_reasoner"}
                and str(self.config.provider_name or "").strip().lower() != "glm"
            ),
            supports_parallel_tool_calls=self.supports_parallel_tool_calls,
            tool_choice="auto",
            extra_body=self._request_extra_body() or None,
            supports_reasoning=self.supports_reasoning,
            reasoning_output_field=self.reasoning_output_field,
            interaction_profile=str(getattr(self, "interaction_profile", "") or "").strip(),
            turn_protocol_policy=str(getattr(self, "turn_protocol_policy", "") or "").strip(),
        )

        def _tool_batch_runner(tool_calls: List[Any]) -> Tuple[List[ToolExecutionResult], int]:
            scripted_calls = [
                SimpleNamespace(
                    id=call.call_id,
                    function=SimpleNamespace(
                        name=call.name,
                        arguments=json.dumps(call.arguments or {}, ensure_ascii=False),
                    ),
                )
                for call in tool_calls
            ]
            batch_results, batch_elapsed_ms = self._execute_tool_call_batch(
                scripted_calls,
                tool_executor=tool_executor,
            )
            return (
                [
                    ToolExecutionResult(
                        call_id=str(result["tool_call_id"]),
                        command_text=str((result.get("payload") or {}).get("command_text") or "") or None,
                        assistant_text=str((result.get("payload") or {}).get("assistant_text") or ""),
                        events=list(result.get("events") or []),
                        item_events=[dict(item) for item in list(result.get("item_events") or []) if isinstance(item, dict)],
                        elapsed_ms=int(result.get("elapsed_ms") or 0),
                    )
                    for result in batch_results
                ],
                batch_elapsed_ms,
            )

        def _followup_handler(_: str, executed_events: List[ToolEvent]) -> AgentIntent:
            return AgentIntent(
                assistant_text="",
                command_text=None,
                status_hint="tool",
                tool_events=list(executed_events),
            )

        engine = turn_engine_cls(
            session,
            tool_executor=tool_executor,
            command_builder=lambda name, arguments: command_builder(
                name,
                arguments,
                self.host_platform,
                plugin_manager_factory=self.plugin_manager_factory,
            ),
            followup_handler=_followup_handler,
            tool_batch_runner=_tool_batch_runner,
            fallback_on_empty_output=False,
            perf_counter_fn=perf_counter_fn,
        )
        run_started_at = perf_counter_fn()
        try:
            return engine.run(user_text=user_text, initial_input=messages)
        except Exception:
            elapsed_ms = max(0, int((perf_counter_fn() - run_started_at) * 1000))
            return AgentIntent(
                assistant_text="",
                command_text=None,
                status_hint="llm",
                tool_events=[],
                timings={
                    "initial_model_ms": 0,
                    "tool_execution_ms": 0,
                    "synthesis_model_ms": 0,
                    "total_ms": elapsed_ms,
                    "planning_rounds": 0,
                    "synthesis_rounds": 0,
                    "planning_trace": [],
                    "synthesis_trace": [],
                    "tool_call_count": 0,
                },
            )
