from __future__ import annotations

import concurrent.futures
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    tool_events_include_approval_requests,
    tool_events_include_interrupt,
    tool_events_to_turn_events,
)
from cli.agent_cli.providers.planner_postprocessing import generic_tool_event_summary_lines
from cli.agent_cli.providers.tool_calls import (
    command_for_tool_call as _command_for_tool_call_impl,
    tool_result_payload as _tool_result_payload_impl,
)
from cli.agent_cli.providers.tool_turn_events import ToolTurnEventsMixin

ToolLoopExecutor = Callable[[str], Tuple[str, List[ToolEvent]] | CommandExecutionResult]

_PARALLEL_SAFE_TOOL_NAMES = frozenset(
    {
        "grep_files",
        "read_file",
        "list_dir",
        "file_list",
        "file_search",
        "file_read",
        "web_search",
        "web_fetch",
        "browser",
    }
)


class ToolExecutionLoopMixin(ToolTurnEventsMixin):
    @staticmethod
    def _tool_event_summary_lines(events: List[ToolEvent]) -> List[str]:
        return generic_tool_event_summary_lines(events)

    def _tool_supports_parallel_calls(self, tool_name: str) -> bool:
        return self.supports_parallel_tool_calls and str(tool_name or "").strip() in _PARALLEL_SAFE_TOOL_NAMES

    @staticmethod
    def _run_tool_executor_structured(
        tool_executor: ToolLoopExecutor,
        command_text: str,
    ) -> CommandExecutionResult:
        structured_runner = getattr(tool_executor, "run_structured", None)
        if callable(structured_runner):
            structured = structured_runner(command_text)
            if isinstance(structured, CommandExecutionResult):
                return structured
        raw_result = tool_executor(command_text)
        if isinstance(raw_result, CommandExecutionResult):
            return raw_result
        assistant_text, events = raw_result
        item_events, _ = tool_events_to_turn_events(list(events or []), start_index=0)
        return CommandExecutionResult(
            assistant_text=assistant_text,
            tool_events=list(events or []),
            item_events=item_events,
        )

    def _execute_tool_call(
        self,
        *,
        tool_call: Any,
        tool_name: str,
        command_text: Optional[str],
        tool_executor: ToolLoopExecutor,
    ) -> Dict[str, Any]:
        started_at = time.perf_counter()
        if not command_text:
            payload = {
                "ok": False,
                "command_text": None,
                "assistant_text": f"unsupported tool call: {tool_name}",
                "events": [],
            }
            return {
                "tool_call_id": str(getattr(tool_call, "id", "")),
                "payload": payload,
                "events": [],
                "item_events": [],
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            }
        execution = self._run_tool_executor_structured(tool_executor, command_text)
        assistant_text = execution.assistant_text
        events = list(execution.tool_events or [])
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        for event in list(events):
            payload = event.payload if isinstance(event.payload, dict) else {}
            payload.setdefault("planner_elapsed_ms", elapsed_ms)
            event.payload = payload
        item_events = self._normalized_execution_events(execution)
        tool_result_payload = getattr(self, "_tool_loop_tool_result_payload", _tool_result_payload_impl)
        payload = tool_result_payload(command_text, assistant_text, events)
        payload["elapsed_ms"] = elapsed_ms
        return {
            "tool_call_id": str(getattr(tool_call, "id", "")),
            "payload": payload,
            "events": list(events),
            "item_events": item_events,
            "elapsed_ms": elapsed_ms,
        }

    def _execute_tool_call_batch(
        self,
        tool_calls: List[Any],
        *,
        tool_executor: ToolLoopExecutor,
    ) -> Tuple[List[Dict[str, Any]], int]:
        batch_started_at = time.perf_counter()
        prepared_calls: List[Dict[str, Any]] = []
        command_builder = getattr(self, "_tool_loop_command_for_tool_call", None)
        for tool_call in tool_calls:
            function = getattr(tool_call, "function", None)
            tool_name = str(getattr(function, "name", ""))
            arguments = self._parse_tool_arguments(getattr(function, "arguments", "{}"))
            if callable(command_builder):
                command_text = command_builder(
                    tool_name,
                    arguments,
                    self.host_platform,
                    plugin_manager_factory=self.plugin_manager_factory,
                )
            else:
                command_text = _command_for_tool_call_impl(
                    tool_name,
                    arguments,
                    self.host_platform,
                    plugin_manager_factory=self.plugin_manager_factory,
                )
            prepared_calls.append(
                {
                    "tool_call": tool_call,
                    "tool_name": tool_name,
                    "command_text": command_text,
                    "parallel": bool(command_text) and self._tool_supports_parallel_calls(tool_name),
                }
            )

        results: List[Dict[str, Any]] = []
        next_item_index = 0
        index = 0
        while index < len(prepared_calls):
            current = prepared_calls[index]
            if not current["parallel"]:
                result = self._execute_tool_call(
                    tool_call=current["tool_call"],
                    tool_name=current["tool_name"],
                    command_text=current["command_text"],
                    tool_executor=tool_executor,
                )
                rebased_item_events = self._rebase_item_events(
                    list(result.get("item_events") or []),
                    start_index=next_item_index,
                )
                next_item_index = self._next_item_index(rebased_item_events)
                result["item_events"] = rebased_item_events
                results.append(result)
                if tool_events_include_interrupt(result.get("events") or []) or tool_events_include_approval_requests(
                    result.get("events") or []
                ):
                    return results, int((time.perf_counter() - batch_started_at) * 1000)
                index += 1
                continue

            batch: List[Dict[str, Any]] = []
            while index < len(prepared_calls) and prepared_calls[index]["parallel"]:
                batch.append(prepared_calls[index])
                index += 1

            if len(batch) == 1:
                current = batch[0]
                result = self._execute_tool_call(
                    tool_call=current["tool_call"],
                    tool_name=current["tool_name"],
                    command_text=current["command_text"],
                    tool_executor=tool_executor,
                )
                rebased_item_events = self._rebase_item_events(
                    list(result.get("item_events") or []),
                    start_index=next_item_index,
                )
                next_item_index = self._next_item_index(rebased_item_events)
                result["item_events"] = rebased_item_events
                results.append(result)
                if tool_events_include_interrupt(result.get("events") or []) or tool_events_include_approval_requests(
                    result.get("events") or []
                ):
                    return results, int((time.perf_counter() - batch_started_at) * 1000)
                continue

            max_workers = min(len(batch), 4)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        self._execute_tool_call,
                        tool_call=item["tool_call"],
                        tool_name=item["tool_name"],
                        command_text=item["command_text"],
                        tool_executor=tool_executor,
                    )
                    for item in batch
                ]
                for future in futures:
                    result = future.result()
                    rebased_item_events = self._rebase_item_events(
                        list(result.get("item_events") or []),
                        start_index=next_item_index,
                    )
                    next_item_index = self._next_item_index(rebased_item_events)
                    result["item_events"] = rebased_item_events
                    results.append(result)

        return results, int((time.perf_counter() - batch_started_at) * 1000)
