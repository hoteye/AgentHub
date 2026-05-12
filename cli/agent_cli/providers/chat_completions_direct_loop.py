from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import AgentIntent, ToolEvent, default_response_items


class ChatCompletionsDirectLoopMixin:
    def _run_direct_planning_loop(
        self,
        *,
        started_at: float,
        user_text: str,
        messages: List[Dict[str, Any]],
        tool_executor,
        executed_events: List[ToolEvent],
        executed_item_events: List[Dict[str, Any]],
        initial_model_ms: int,
        tool_execution_ms: int,
        synthesis_model_ms: int,
        planning_rounds: int,
        synthesis_rounds: int,
        planning_trace: List[Dict[str, Any]],
        synthesis_trace: List[Dict[str, Any]],
        perf_counter_fn: Callable[[], float],
        tool_specs_builder,
        command_builder,
    ) -> Dict[str, Any]:
        final_text = ""
        response_items = []
        for _ in range(6):
            request_kwargs: Dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
                "stream": False,
            }
            if self.supports_tools:
                request_kwargs["tools"] = tool_specs_builder(
                    self.config,
                    self.host_platform,
                    plugin_manager_factory=self.plugin_manager_factory,
                )
                request_kwargs["tool_choice"] = "auto"
            extra_body = self._request_extra_body()
            if extra_body:
                request_kwargs["extra_body"] = extra_body
            try:
                request_started_at = perf_counter_fn()
                response = self._chat_completion_create(
                    timeout=self.model_timeout,
                    **request_kwargs,
                )
                request_elapsed_ms = int((perf_counter_fn() - request_started_at) * 1000)
                initial_model_ms += request_elapsed_ms
                planning_rounds += 1
            except Exception:
                break
            choice = response.choices[0]
            message = choice.message
            content_text = self._message_content_text(getattr(message, "content", ""))
            tool_calls = list(getattr(message, "tool_calls", []) or [])
            answer_preview = self._sanitize_final_answer_text(content_text)
            planning_trace.append(
                {
                    "round": planning_rounds,
                    "model_ms": request_elapsed_ms,
                    "tool_calls": [
                        str(getattr(getattr(tool_call, "function", None), "name", "")).strip()
                        for tool_call in tool_calls
                        if str(getattr(getattr(tool_call, "function", None), "name", "")).strip()
                    ],
                    "tool_call_count": len(tool_calls),
                    "answered": bool(not tool_calls and answer_preview),
                    "answer_preview": answer_preview[:120] if not tool_calls and answer_preview else "",
                }
            )
            messages.append(self._assistant_message_dict(message, content_text=content_text, tool_calls=tool_calls))

            if not tool_calls:
                final_text = answer_preview
                response_items = default_response_items(assistant_text=final_text)
                break

            if tool_executor is None:
                first_call = tool_calls[0]
                arguments = self._parse_tool_arguments(getattr(getattr(first_call, "function", None), "arguments", "{}"))
                command_text = command_builder(
                    str(getattr(getattr(first_call, "function", None), "name", "")),
                    arguments,
                    self.host_platform,
                    plugin_manager_factory=self.plugin_manager_factory,
                )
                return {
                    "immediate_intent": AgentIntent(
                        assistant_text=content_text or "已生成工具调用，准备执行。",
                        command_text=command_text,
                        status_hint="tool" if command_text else "llm",
                        timings={
                            "initial_model_ms": initial_model_ms,
                            "tool_execution_ms": tool_execution_ms,
                            "synthesis_model_ms": synthesis_model_ms,
                            "total_ms": int((perf_counter_fn() - started_at) * 1000),
                            "planning_rounds": planning_rounds,
                            "synthesis_rounds": synthesis_rounds,
                            "planning_trace": planning_trace,
                            "synthesis_trace": synthesis_trace,
                            "tool_call_count": len(executed_events),
                        },
                    )
                }

            batch_results, batch_elapsed_ms = self._execute_tool_call_batch(tool_calls, tool_executor=tool_executor)
            tool_execution_ms += batch_elapsed_ms
            for result in batch_results:
                executed_events.extend(result["events"])
                executed_item_events.extend(
                    self._rebase_item_events(
                        list(result.get("item_events") or []),
                        start_index=self._next_item_index(executed_item_events),
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "content": json.dumps(result["payload"], ensure_ascii=False),
                    }
                )

        return {
            "immediate_intent": None,
            "final_text": final_text,
            "response_items": response_items,
            "initial_model_ms": initial_model_ms,
            "tool_execution_ms": tool_execution_ms,
            "planning_rounds": planning_rounds,
            "planning_trace": planning_trace,
        }
