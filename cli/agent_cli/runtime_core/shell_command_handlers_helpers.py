from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.models import CommandExecutionResult, ToolEvent, shell_tool_call_item_events
from cli.agent_cli.runtime_core import shell_command_handlers_runtime
from cli.agent_cli.runtime_core.command_usage import _command_usage_text
from cli.agent_cli.slash_parser import SlashInvocation, slash_keyword_map, slash_switch_set


def _slash_parsed_args(
    slash_invocation: SlashInvocation | None,
) -> tuple[list[str], dict[str, Any]] | None:
    if slash_invocation is None:
        return None
    options: dict[str, Any] = dict(slash_keyword_map(slash_invocation))
    for switch_name in slash_switch_set(slash_invocation):
        options[switch_name] = True
    return [str(item) for item in slash_invocation.positionals], options


def _preview_text(value: Any, *, max_chars: int = 240) -> str:
    return shell_command_handlers_runtime.preview_text(value, max_chars=max_chars)


def _tool_trace(stage: str, **payload: Any) -> None:
    if not timeline_debug_enabled():
        return
    log_timeline(stage, **json_ready(payload))


def _tool_event_trace_payload(
    event: ToolEvent,
    *,
    compact_arguments: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    return shell_command_handlers_runtime.tool_event_trace_payload(
        event,
        compact_arguments=compact_arguments,
        preview_text_fn=_preview_text,
    )


def _canonical_exec_output_text(payload: dict[str, Any]) -> str:
    return shell_command_handlers_runtime.canonical_exec_output_text(payload)


def _canonical_command_tool_event(name: str, payload: dict[str, Any], *, command: str) -> ToolEvent:
    return shell_command_handlers_runtime.canonical_command_tool_event(
        name,
        payload,
        command=command,
        tool_event_cls=ToolEvent,
        canonical_exec_output_text_fn=_canonical_exec_output_text,
    )


def _call_write_stdin_result(
    result_getter: Callable[..., CommandExecutionResult],
    session_id: str,
    chars: str,
    *,
    yield_time_ms: int | None,
    max_output_tokens: int | None,
) -> CommandExecutionResult:
    max_output_chars = shell_command_handlers_runtime.max_output_chars_for_tokens(max_output_tokens)
    kwargs: dict[str, Any] = {"yield_time_ms": yield_time_ms}
    try:
        parameters = inspect.signature(result_getter).parameters
    except (TypeError, ValueError):
        parameters = {}
    supports_max_output_chars = not parameters or any(
        name == "max_output_chars" or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for name, parameter in parameters.items()
    )
    if supports_max_output_chars:
        kwargs["max_output_chars"] = max_output_chars
    return result_getter(session_id, chars, **kwargs)


def handle_write_stdin_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: SlashInvocation | None,
    compact_arguments: Callable[[dict[str, Any]], dict[str, Any]],
    int_option: Callable[..., int | None],
    error_event: Callable[..., ToolEvent],
    error_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
) -> CommandExecutionResult | None:
    slash_args = _slash_parsed_args(slash_invocation)
    if slash_args is not None:
        positionals, options = slash_args
    else:
        positionals, options = runtime._parse_args(arg_text)
    if not positionals:
        return text_only_result(
            _command_usage_text("write_stdin")
            or "Usage: /write_stdin <session_id> [chars] [yield-time-ms <n>] [max-output-tokens <n>]"
        )
    session_id = str(positionals[0] or "").strip()
    chars = " ".join(positionals[1:]) if len(positionals) > 1 else ""
    _tool_trace(
        "tool.write_stdin.parsed",
        raw_arg_text=str(arg_text or ""),
        positionals=[str(item or "") for item in positionals],
        parsed_session_id=session_id,
        parsed_session_id_length=len(session_id),
        chars_preview=_preview_text(chars),
    )
    try:
        yield_time_ms = int_option(options.get("yield-time-ms"), default=250)
        max_output_tokens = int_option(options.get("max-output-tokens"))
    except ValueError as exc:
        _tool_trace(
            "tool.write_stdin.parse_failed",
            session_id=session_id,
            chars_preview=_preview_text(chars),
            error=str(exc),
        )
        return error_result(
            error_event(
                "write_stdin", "write_stdin parse failed", error=str(exc), session_id=session_id
            ),
            arguments={"session_id": session_id},
        )
    _tool_trace(
        "tool.write_stdin.started",
        session_id=session_id,
        chars_preview=_preview_text(chars),
        yield_time_ms=yield_time_ms,
        max_output_tokens=max_output_tokens,
    )
    result_getter = getattr(runtime, "write_shell_stdin_result", None)
    if not callable(result_getter):
        _tool_trace(
            "tool.write_stdin.unsupported",
            session_id=session_id,
            chars_preview=_preview_text(chars),
            error="interactive shell unsupported",
        )
        return error_result(
            error_event(
                "write_stdin",
                "write_stdin unsupported",
                error="interactive shell unsupported",
                session_id=session_id,
            ),
            arguments={"session_id": session_id, "chars": chars},
        )
    structured = _call_write_stdin_result(
        result_getter,
        session_id,
        chars,
        yield_time_ms=yield_time_ms,
        max_output_tokens=max_output_tokens,
    )
    payload = dict((structured.tool_events[0].payload if structured.tool_events else {}) or {})
    payload.setdefault("session_id", session_id)
    payload.setdefault("max_output_tokens", max_output_tokens)
    event = _canonical_command_tool_event(
        "write_stdin",
        payload,
        command=str(payload.get("command") or ""),
    )
    _tool_trace(
        "tool.write_stdin.completed",
        chars_preview=_preview_text(chars),
        **_tool_event_trace_payload(event, compact_arguments=compact_arguments),
    )
    return CommandExecutionResult(
        assistant_text=_canonical_exec_output_text(payload),
        tool_events=[event],
        item_events=shell_tool_call_item_events(event, command=str(payload.get("command") or "")),
    )
