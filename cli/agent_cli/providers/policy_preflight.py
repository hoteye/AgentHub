from __future__ import annotations

import re
import shlex
from typing import Any, Callable, Dict, List, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent

PolicyToolExecutor = Callable[[str], Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def _quote_arg(value: Any) -> str:
    return shlex.quote(str(value))


class PolicyPreflightMixin:
    def _execute_policy_preflight(
        self,
        user_text: str,
        executed_events: List[ToolEvent],
        executed_item_events: List[Dict[str, Any]],
        tool_executor: PolicyToolExecutor,
    ) -> Tuple[List[ToolEvent], List[Dict[str, Any]]]:
        new_events: List[ToolEvent] = []
        new_item_events: List[Dict[str, Any]] = []
        search_queries = self._policy_query_plan(user_text)
        summary_question = self._policy_is_summary_question(user_text)
        max_searches = 1 if summary_question else 4
        seen_queries = {
            re.sub(r"\s+", " ", str((event.payload or {}).get("query") or "").strip()).lower()
            for event in executed_events
            if event.name == "policy_doc_search" and str((event.payload or {}).get("query") or "").strip()
        }

        for query in search_queries:
            if len(
                [
                    event
                    for event in [*executed_events, *new_events]
                    if event.name == "policy_doc_search"
                ]
            ) >= max_searches:
                break
            normalized_query = re.sub(r"\s+", " ", str(query or "").strip()).lower()
            if not normalized_query or normalized_query in seen_queries:
                continue
            seen_queries.add(normalized_query)
            command_text = f"/policy_doc_search {_quote_arg(query)} --limit 5"
            try:
                execution = self._run_tool_executor_structured(tool_executor, command_text)
                events = list(execution.tool_events or [])
                rebased = self._rebase_item_events(
                    [dict(item) for item in list(execution.item_events or []) if isinstance(item, dict)],
                    start_index=self._next_item_index([*executed_item_events, *new_item_events]),
                )
                new_item_events.extend(rebased)
            except Exception as exc:
                events = [
                    ToolEvent(
                        name="policy_doc_search",
                        ok=False,
                        summary=f"policy preflight search failed: {exc}",
                        payload={"ok": False, "query": query, "command_text": command_text},
                    )
                ]
            new_events.extend(events)

            combined_events = [*executed_events, *new_events]
            effective_blocks = self._policy_effective_evidence(user_text, self._policy_evidence_blocks(combined_events))
            if effective_blocks:
                top_block = effective_blocks[0]
                if (
                    not bool(top_block.get("is_noise_candidate"))
                    and str(top_block.get("doc_group") or "") in {"governance_base", "direct_rule"}
                    and self._policy_search_hit_is_specific(query, top_block)
                ):
                    break

        combined_events = [*executed_events, *new_events]
        effective_blocks = self._policy_effective_evidence_v2(user_text, self._policy_evidence_blocks(combined_events))
        readable_doc_keys = {
            (
                str(block.get("doc_id") or "").strip(),
                str(block.get("title") or "").strip(),
            )
            for block in effective_blocks
            if str(block.get("text") or "").strip()
        }

        read_targets: List[Dict[str, Any]] = []
        for block in effective_blocks:
            if bool(block.get("is_noise_candidate")):
                continue
            if str(block.get("doc_group") or "") not in {"governance_base", "direct_rule"}:
                continue
            key = (str(block.get("doc_id") or "").strip(), str(block.get("title") or "").strip())
            if key in readable_doc_keys:
                continue
            read_targets.append(block)
            if len(read_targets) >= (1 if summary_question else 3):
                break

        for block in read_targets:
            doc_id = str(block.get("doc_id") or "").strip()
            path = str(block.get("path") or "").strip()
            if not doc_id and not path:
                continue
            command_text = "/policy_doc_read"
            if doc_id:
                command_text += f" --doc-id {_quote_arg(doc_id)}"
            if path:
                command_text += f" --path {_quote_arg(path)}"
            command_text += " --max-chars 6000"
            try:
                execution = self._run_tool_executor_structured(tool_executor, command_text)
                events = list(execution.tool_events or [])
                rebased = self._rebase_item_events(
                    [dict(item) for item in list(execution.item_events or []) if isinstance(item, dict)],
                    start_index=self._next_item_index([*executed_item_events, *new_item_events]),
                )
                new_item_events.extend(rebased)
            except Exception as exc:
                events = [
                    ToolEvent(
                        name="policy_doc_read",
                        ok=False,
                        summary=f"policy preflight read failed: {exc}",
                        payload={
                            "ok": False,
                            "doc_id": doc_id,
                            "path": path,
                            "command_text": command_text,
                        },
                    )
                ]
            new_events.extend(events)

        return new_events, new_item_events

    def _is_policy_grounded_turn(self, user_text: str, executed_events: List[ToolEvent]) -> bool:
        del user_text
        return any(event.name in {"policy_doc_search", "policy_doc_read"} for event in executed_events)
