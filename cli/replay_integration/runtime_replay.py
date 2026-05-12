from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence

from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    ToolEvent,
    compose_turn_events_from_response_items,
    default_response_items,
)
from cli.agent_cli.providers.adapters.openai_responses import (
    extract_responses_message_items,
    extract_responses_output_text,
)
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy

from .replay_client import ReplayExhaustedError
from .schema import ReplayCassette, ReplayRound, ReplayToolCall
from .tool_replay import ReplayToolExecutor


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: List[str] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _to_object(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{str(key): _to_object(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_to_object(item) for item in value]
    return value


def recorded_user_prompt(round_item: ReplayRound) -> str:
    for item in reversed(list(round_item.request.get("input") or [])):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        role = str(item.get("role") or "").strip()
        if item_type == "message" and role == "user":
            return _content_text(item.get("content"))
    return ""


def _tool_calls_for_round(cassette: ReplayCassette, round_index: int) -> List[ReplayToolCall]:
    return [
        item
        for item in list(cassette.tool_calls or [])
        if int(item.round_index or 0) == int(round_index)
    ]


class RuntimeReplayMismatchError(RuntimeError):
    pass


@dataclass
class RuntimeReplayPlanner:
    cassette: ReplayCassette
    require_user_text_match: bool = True
    require_prompt_cache_key_match: bool = True

    def __post_init__(self) -> None:
        self._cursor = 0

    def reset(self) -> None:
        self._cursor = 0

    def remaining_rounds(self) -> Sequence[ReplayRound]:
        return list(self.cassette.rounds[self._cursor :])

    def public_summary(self) -> Dict[str, Any]:
        session = self.cassette.manifest.session
        return {
            "configured": True,
            "provider_name": str(session.provider or "replay"),
            "model_key": str(session.model or "replay"),
            "planner_kind": "runtime_replay",
            "wire_api": "replay",
            "model": str(session.model or "replay"),
            "base_url": "replay://runtime",
            "reasoning_effort": None,
            "source": "replay_cassette",
            "config_path": None,
            "auth_path": None,
        }

    def _match_round(
        self,
        *,
        user_text: str,
        prompt_cache_key: str | None,
    ) -> ReplayRound:
        if self._cursor >= len(self.cassette.rounds):
            raise ReplayExhaustedError("runtime replay cassette has no remaining rounds")

        round_item = self.cassette.rounds[self._cursor]
        expected_text = recorded_user_prompt(round_item)
        actual_text = str(user_text or "").strip()
        if self.require_user_text_match and expected_text and expected_text != actual_text:
            raise RuntimeReplayMismatchError(
                f"runtime replay prompt mismatch for round {round_item.index}: "
                f"expected {expected_text!r}, got {actual_text!r}"
            )

        expected_cache_key = (
            str(round_item.request.get("prompt_cache_key") or "").strip()
            or str(self.cassette.manifest.session.prompt_cache_key or "").strip()
            or str(self.cassette.manifest.session.thread_id or "").strip()
        )
        actual_cache_key = str(prompt_cache_key or "").strip()
        if (
            self.require_prompt_cache_key_match
            and expected_cache_key
            and actual_cache_key
            and expected_cache_key != actual_cache_key
        ):
            raise RuntimeReplayMismatchError(
                f"runtime replay prompt_cache_key mismatch for round {round_item.index}: "
                f"expected {expected_cache_key!r}, got {actual_cache_key!r}"
            )
        return round_item

    @staticmethod
    def _tool_result(
        tool_executor: Any,
        command_text: str,
    ) -> CommandExecutionResult:
        structured_runner = getattr(tool_executor, "run_structured", None)
        if callable(structured_runner):
            return structured_runner(command_text)
        raw_assistant_text, raw_events = tool_executor(command_text)
        return CommandExecutionResult(
            assistant_text=str(raw_assistant_text or ""),
            tool_events=list(raw_events or []),
            item_events=[],
        )

    def plan(
        self,
        user_text: str,
        history: List[Dict[str, str]],
        *,
        tool_executor: Optional[Any] = None,
        attachments: Optional[List[Any]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
        prompt_cache_key: Optional[str] = None,
        turn_event_callback: Optional[Any] = None,
    ) -> AgentIntent:
        del history, attachments, input_items, turn_event_callback
        round_item = self._match_round(user_text=user_text, prompt_cache_key=prompt_cache_key)

        round_tool_calls = _tool_calls_for_round(self.cassette, round_item.index)
        normalized_executor = tool_executor or ReplayToolExecutor(round_tool_calls)
        tool_events: List[ToolEvent] = []
        item_events: List[Dict[str, Any]] = []
        for tool_call in round_tool_calls:
            result = self._tool_result(normalized_executor, tool_call.command_text)
            tool_events.extend(list(result.tool_events or []))
            item_events.extend([dict(item) for item in list(result.item_events or []) if isinstance(item, dict)])

        response_object = _to_object(round_item.response)
        response_items = extract_responses_message_items(response_object)
        assistant_text = extract_responses_output_text(response_object)
        if not response_items and assistant_text:
            response_items = default_response_items(assistant_text=assistant_text)
        turn_events = compose_turn_events_from_response_items(
            assistant_text=assistant_text,
            response_items=response_items,
            executed_item_events=item_events,
        )

        self._cursor += 1
        return AgentIntent(
            assistant_text=assistant_text,
            response_items=response_items,
            tool_events=tool_events,
            turn_events=turn_events,
            status_hint="tool" if tool_events else "assistant",
        )


def build_runtime_for_replay(
    cassette: ReplayCassette,
    *,
    cwd: str | None = None,
    thread_id: str | None = None,
    runtime_policy: RuntimePolicy | None = None,
) -> AgentCliRuntime:
    runtime = AgentCliRuntime(
        thread_store=None,
        runtime_policy=runtime_policy or RuntimePolicy.normalized(approval_policy="never"),
    )
    runtime_cwd = (
        str(cwd or "").strip()
        or str(cassette.manifest.environment_snapshot.get("cwd") or "").strip()
        or str(cassette.manifest.session.cwd or "").strip()
        or str(runtime.cwd)
    )
    runtime.set_cwd(runtime_cwd)
    replay_thread_id = (
        str(thread_id or "").strip()
        or str(cassette.manifest.session.prompt_cache_key or "").strip()
        or str(cassette.manifest.session.thread_id or "").strip()
    )
    if replay_thread_id:
        runtime.thread_id = replay_thread_id
    planner = RuntimeReplayPlanner(cassette)
    planner_override = getattr(runtime.agent, "set_planner_override", None)
    if callable(planner_override):
        planner_override(planner, managed=False)
    else:
        runtime.agent._planner = planner
        runtime.agent._planner_managed = False
        runtime.agent._planner_error = None
        runtime.agent._planner_runtime_error = None
        runtime.agent._planner_runtime_error_diagnostics = None
    runtime._structured_tool_executor = ReplayToolExecutor(cassette)
    return runtime
