from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.resume_support import apply_runtime_resume_request
from cli.agent_cli.runtime_core import (
    thread_commands_agent_runtime,
    thread_commands_target_runtime,
    thread_commands_text_runtime,
)
from cli.agent_cli.runtime_core.command_usage import (
    _spawn_agent_usage_text,
)
from cli.agent_cli.slash_parser import SlashInvocation, slash_keyword_map, slash_switch_set

CommandHandlerResult = tuple[str, list[ToolEvent]] | CommandExecutionResult | None


def _slash_parsed_args(
    slash_invocation: SlashInvocation | None,
) -> tuple[list[str], dict[str, Any]] | None:
    if slash_invocation is None:
        return None
    options: dict[str, Any] = dict(slash_keyword_map(slash_invocation))
    for switch_name in slash_switch_set(slash_invocation):
        options[switch_name] = True
    return [str(item) for item in slash_invocation.positionals], options


def handle_thread_and_agent_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
    parse_json_tool_arg: Callable[[str], dict[str, Any]],
    int_option: Callable[..., int | None],
    bool_option: Callable[..., bool],
    decode_raw_text_arg: Callable[[str], str],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandHandlerResult:
    if name == "threads":
        slash_args = _slash_parsed_args(slash_invocation)
        if slash_args is not None:
            _, options = slash_args
        else:
            _, options = runtime._parse_args(arg_text)
        try:
            limit = int_option(options.get("limit"), default=20) or 20
        except ValueError as exc:
            return (str(exc), [])
        return (thread_commands_text_runtime.threads_text(runtime, limit=max(1, limit)), [])
    if name == "resume":
        thread_id = str(decode_raw_text_arg(arg_text) or "").strip()
        if not thread_id:
            return ("Usage: /resume <thread_id>", [])
        try:
            payload = apply_runtime_resume_request(runtime, thread_id=thread_id) or {}
        except Exception as exc:
            return (f"resume failed: {exc}", [])
        return (thread_commands_text_runtime.resume_payload_text(runtime, dict(payload or {})), [])
    if name == "resume_last":
        if str(arg_text or "").strip():
            return ("Usage: /resume_last", [])
        try:
            payload = apply_runtime_resume_request(runtime, resume_last=True) or {}
        except Exception as exc:
            return (f"resume failed: {exc}", [])
        return (thread_commands_text_runtime.resume_payload_text(runtime, dict(payload or {})), [])
    if name == "resume_path":
        rollout_path = str(decode_raw_text_arg(arg_text) or "").strip()
        if not rollout_path:
            return ("Usage: /resume_path <rollout_path>", [])
        try:
            payload = apply_runtime_resume_request(runtime, rollout_path=rollout_path) or {}
        except Exception as exc:
            return (f"resume failed: {exc}", [])
        return (thread_commands_text_runtime.resume_payload_text(runtime, dict(payload or {})), [])
    if name in {"exit", "quit"}:
        if str(arg_text or "").strip():
            return (f"Usage: /{name}", [])
        payload = thread_commands_text_runtime.exit_payload(runtime)
        return single_event_result(
            thread_commands_text_runtime.exit_payload_text(runtime),
            ToolEvent(
                name="app_exit_requested",
                ok=True,
                summary="exit requested",
                payload=payload,
            ),
            arguments={},
            tool_name="app_exit_requested",
        )
    if name == "close":
        if str(arg_text or "").strip():
            return ("Usage: /close", [])
        return single_event_result(
            "Tab close requested.",
            ToolEvent(
                name="tab_close_requested",
                ok=True,
                summary="close current tab",
                payload={},
            ),
            arguments={},
            tool_name="tab_close_requested",
        )
    if name == "preview":
        action = str(decode_raw_text_arg(arg_text) or "").strip().lower() or "toggle"
        if action not in {"open", "close", "toggle", "status"}:
            return ("Usage: /preview [open|close|toggle|status]", [])
        return single_event_result(
            f"Preview {action} requested.",
            ToolEvent(
                name="preview_control_requested",
                ok=True,
                summary=f"preview {action}",
                payload={"action": action},
            ),
            arguments={"action": action},
            tool_name="preview_control_requested",
        )
    if name == "spawn_agent":
        payload = thread_commands_agent_runtime.parse_spawn_agent_payload(
            arg_text=arg_text,
            parse_json_tool_arg=parse_json_tool_arg,
            decode_raw_text_arg=decode_raw_text_arg,
            bool_option=bool_option,
        )
        if payload is None:
            return text_only_result(_spawn_agent_usage_text())
        parse_error = str(payload.get("error") or "").strip() if isinstance(payload, dict) else ""
        if parse_error:
            return error_result(
                error_event(
                    "spawn_agent",
                    "spawn_agent parse failed",
                    error=parse_error,
                ),
            )
        if not payload:
            return error_result(
                error_event(
                    "spawn_agent",
                    "spawn_agent parse failed",
                    error="failed to parse function arguments: expected non-empty task",
                ),
            )
        task_text = str(payload["task"])
        role_name = str(payload["role"])
        arguments = thread_commands_agent_runtime.spawn_agent_arguments(payload)
        runner = getattr(runtime, "spawn_agent_result", None)
        if not callable(runner):
            return error_result(
                error_event(
                    "spawn_agent",
                    "spawn_agent unavailable",
                    error="spawn_agent runtime is unavailable",
                ),
                arguments=arguments,
            )
        try:
            structured = runner(
                **thread_commands_agent_runtime._filter_runner_kwargs(
                    runner,
                    {
                        "task": task_text,
                        "role": role_name,
                        "model": payload.get("model"),
                        "provider": payload.get("provider"),
                        "reasoning_effort": payload.get("reasoning_effort"),
                        "timeout": payload.get("timeout"),
                        "async_mode": payload.get("async_mode"),
                        "reason": payload.get("reason"),
                        "mode": payload.get("mode"),
                        "wait_required": payload.get("wait_required"),
                        "task_shape": payload.get("task_shape"),
                        "subagent_type": payload.get("subagent_type"),
                        "input_items": payload.get("input_items"),
                        "fork_context": payload.get("fork_context"),
                        "codex_collab_payload": bool(payload.get("codex_collab_payload")),
                    },
                )
            )
        except Exception as exc:
            return error_result(
                error_event(
                    "spawn_agent",
                    "spawn_agent failed",
                    error=str(exc),
                    role=role_name,
                    task=task_text,
                ),
                arguments=arguments,
            )
        if isinstance(structured, CommandExecutionResult):
            return structured
        return single_event_result(
            str(task_text),
            ToolEvent(
                name="spawn_agent",
                ok=True,
                summary="spawn_agent completed",
                payload={"ok": True, "role": role_name, "task": task_text},
            ),
            arguments=arguments,
            tool_name="spawn_agent",
            prefer_result_text=True,
        )
    target_result = thread_commands_target_runtime.handle_target_command(
        runtime,
        name=name,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        int_option=int_option,
        bool_option=bool_option,
        text_only_result=text_only_result,
        error_result=error_result,
        error_event=error_event,
        slash_invocation=slash_invocation,
    )
    if target_result is not None:
        return target_result
    return None
