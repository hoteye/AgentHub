from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from cli.agent_cli.models import CommandExecutionResult, ToolEvent

from .schema import ReplayCassette, ReplayToolCall


def _normalize_command_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


@dataclass(frozen=True)
class _CanonicalCommand:
    command: str
    workdir: str = ""


def _parse_shell_wrapped_command(value: str | None) -> _CanonicalCommand | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parts = shlex.split(text)
    except ValueError:
        return None
    for index, token in enumerate(parts[:-1]):
        if token in {"-lc", "-c", "-Command"} and index + 1 < len(parts):
            command = _normalize_command_text(parts[index + 1])
            if command:
                return _CanonicalCommand(command=command)
    return None


def _parse_slash_exec_command(value: str | None) -> _CanonicalCommand | None:
    text = str(value or "").strip()
    if not text.startswith("/exec_command"):
        return None
    try:
        parts = shlex.split(text)
    except ValueError:
        return None
    if len(parts) < 2:
        return None
    command = _normalize_command_text(parts[1])
    if not command:
        return None
    workdir = ""
    index = 2
    while index < len(parts):
        token = parts[index]
        if token == "--workdir" and index + 1 < len(parts):
            workdir = str(parts[index + 1] or "").strip()
            index += 2
            continue
        index += 1
    return _CanonicalCommand(command=command, workdir=workdir)


def _canonical_command(value: str | None) -> _CanonicalCommand | None:
    slash_exec = _parse_slash_exec_command(value)
    if slash_exec is not None:
        return slash_exec
    shell_wrapped = _parse_shell_wrapped_command(value)
    if shell_wrapped is not None:
        return shell_wrapped
    normalized = _normalize_command_text(value)
    if not normalized:
        return None
    return _CanonicalCommand(command=normalized)


def _commands_equivalent(expected: str | None, actual: str | None) -> bool:
    normalized_expected = _normalize_command_text(expected)
    normalized_actual = _normalize_command_text(actual)
    if normalized_expected and normalized_expected == normalized_actual:
        return True
    expected_command = _canonical_command(expected)
    actual_command = _canonical_command(actual)
    if expected_command is None or actual_command is None:
        return False
    if expected_command.command != actual_command.command:
        return False
    if (
        expected_command.workdir
        and actual_command.workdir
        and expected_command.workdir != actual_command.workdir
    ):
        return False
    return True


def _tool_output_text(tool_call: ReplayToolCall) -> str:
    if tool_call.output_items:
        output = tool_call.output_items[0].get("output")
        if isinstance(output, str):
            return output
        if output is not None:
            return json.dumps(output, ensure_ascii=False)
    for event in reversed(list(tool_call.tool_events or [])):
        item = event.get("item") if isinstance(event, dict) else None
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "command_execution":
            continue
        return str(item.get("aggregated_output") or "").strip()
    return ""


def _tool_success(tool_call: ReplayToolCall) -> bool:
    if tool_call.output_items:
        success = tool_call.output_items[0].get("success")
        if isinstance(success, bool):
            return success
    for event in reversed(list(tool_call.tool_events or [])):
        item = event.get("item") if isinstance(event, dict) else None
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "command_execution":
            continue
        try:
            return int(item.get("exit_code")) == 0
        except (TypeError, ValueError):
            break
    return True


def _tool_event(tool_call: ReplayToolCall) -> ToolEvent:
    output = None
    success = None
    if tool_call.output_items:
        output = tool_call.output_items[0].get("output")
        item_success = tool_call.output_items[0].get("success")
        if isinstance(item_success, bool):
            success = item_success

    text = _tool_output_text(tool_call)
    ok = _tool_success(tool_call) if success is None else success
    payload: Dict[str, Any] = {
        "call_id": tool_call.call_id,
        "command": tool_call.command_text,
    }
    if output is not None:
        payload["function_call_output"] = output
    elif text:
        payload["function_call_output"] = text
    if text:
        payload["stdout"] = text
    return ToolEvent(
        name=tool_call.tool_name or "tool",
        ok=bool(ok),
        summary=text or tool_call.command_text or tool_call.tool_name or "replayed tool output",
        payload=payload,
    )


class ReplayToolMismatchError(RuntimeError):
    pass


@dataclass
class ReplayToolMatch:
    tool_call: ReplayToolCall


class ReplayToolExecutor:
    def __init__(self, source: ReplayCassette | Sequence[ReplayToolCall]) -> None:
        if isinstance(source, ReplayCassette):
            self._tool_calls = list(source.tool_calls or [])
        else:
            self._tool_calls = list(source or [])
        self._cursor = 0

    def reset(self) -> None:
        self._cursor = 0

    def remaining_tool_calls(self) -> Sequence[ReplayToolCall]:
        return list(self._tool_calls[self._cursor :])

    def _match(self, command_text: str) -> ReplayToolMatch:
        if self._cursor >= len(self._tool_calls):
            raise ReplayToolMismatchError("replay tool cassette has no remaining tool calls")

        expected = self._tool_calls[self._cursor]
        normalized_expected = _normalize_command_text(expected.command_text)
        normalized_actual = _normalize_command_text(command_text)
        if normalized_expected and not _commands_equivalent(expected.command_text, command_text):
            raise ReplayToolMismatchError(
                "replay tool mismatch: "
                f"expected {expected.command_text!r}, got {command_text!r}"
            )
        self._cursor += 1
        return ReplayToolMatch(tool_call=expected)

    def run_structured(self, command_text: str) -> CommandExecutionResult:
        match = self._match(command_text)
        tool_call = match.tool_call
        tool_event = _tool_event(tool_call)
        output_text = _tool_output_text(tool_call)
        return CommandExecutionResult(
            assistant_text=output_text,
            tool_events=[tool_event],
            item_events=[dict(item) for item in list(tool_call.tool_events or []) if isinstance(item, dict)],
        )

    def __call__(self, command_text: str) -> tuple[str, List[ToolEvent]]:
        result = self.run_structured(command_text)
        return result.assistant_text, result.tool_events
