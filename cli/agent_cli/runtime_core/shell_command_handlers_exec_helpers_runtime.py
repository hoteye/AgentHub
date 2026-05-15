from __future__ import annotations

from collections.abc import Callable
from typing import Any

import cli.agent_cli.runtime_core.shell_command_handlers_exec_policy_runtime as exec_policy_runtime
from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    generic_tool_call_item_events,
    shell_tool_call_item_events,
)
from cli.agent_cli.runtime_action_policy_runtime import evaluate_exec_command_action_policy
from cli.agent_cli.runtime_core import (
    shell_command_handlers_exec_helpers_apply_patch_runtime,
    shell_command_handlers_exec_helpers_execution_runtime,
    shell_command_handlers_pure_helpers_runtime,
    shell_command_handlers_runtime,
)
from cli.agent_cli.runtime_core.command_usage import _command_usage_text
from cli.agent_cli.runtime_services import command_policy_runtime
from cli.agent_cli.slash_parser import SlashInvocation

_active_run_text = exec_policy_runtime._active_run_text
_user_explicitly_forbids_tool = exec_policy_runtime._user_explicitly_forbids_tool
_blocked_exec_command_refusal_text = exec_policy_runtime._blocked_exec_command_refusal_text
_blocked_exec_command_item_events = exec_policy_runtime._blocked_exec_command_item_events
_blocked_exec_command_result = exec_policy_runtime._blocked_exec_command_result
_codex_read_only_exec_failure_result = exec_policy_runtime._codex_read_only_exec_failure_result
_request_shell_approval_for_exec = exec_policy_runtime._request_shell_approval_for_exec


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
    return shell_command_handlers_exec_helpers_execution_runtime.canonical_exec_output_text(payload)


def _command_looks_like_inline_apply_patch(command_text: str) -> bool:
    return shell_command_handlers_exec_helpers_apply_patch_runtime.command_looks_like_inline_apply_patch(
        command_text
    )


def _inline_apply_patch_text(command_text: str) -> str:
    return shell_command_handlers_exec_helpers_apply_patch_runtime.inline_apply_patch_text(
        command_text
    )


def _inline_apply_patch_workspace_root(runtime: Any, *, workdir: str | None):
    return (
        shell_command_handlers_exec_helpers_apply_patch_runtime.inline_apply_patch_workspace_root(
            runtime,
            workdir=workdir,
        )
    )


def _codex_apply_patch_exec_output(success_text: str) -> str:
    return shell_command_handlers_exec_helpers_apply_patch_runtime.codex_apply_patch_exec_output(
        success_text
    )


def _inline_apply_patch_exec_result(
    runtime: Any,
    *,
    request: shell_command_handlers_pure_helpers_runtime.ExecCommandRequest,
    compact_arguments: Callable[[dict[str, Any]], dict[str, Any]],
    approval_request_text: Callable[[str, ToolEvent], str],
) -> CommandExecutionResult | None:
    return shell_command_handlers_exec_helpers_apply_patch_runtime.inline_apply_patch_exec_result(
        runtime,
        request=request,
        compact_arguments=compact_arguments,
        approval_request_text=approval_request_text,
        canonical_command_tool_event=_canonical_command_tool_event,
        tool_trace=_tool_trace,
    )


def _canonical_command_tool_event(name: str, payload: dict[str, Any], *, command: str) -> ToolEvent:
    return shell_command_handlers_exec_helpers_execution_runtime.canonical_command_tool_event(
        name,
        payload,
        command=command,
    )


def _exec_command_arguments(
    *,
    request: shell_command_handlers_pure_helpers_runtime.ExecCommandRequest,
    resolved_shell: str | None,
    compact_arguments: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    return shell_command_handlers_exec_helpers_execution_runtime.exec_command_arguments(
        request=request,
        resolved_shell=resolved_shell,
        compact_arguments=compact_arguments,
    )


def handle_exec_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: SlashInvocation | None,
    compact_arguments: Callable[[dict[str, Any]], dict[str, Any]],
    int_option: Callable[..., int | None],
    bool_option: Callable[..., bool],
    error_event: Callable[..., ToolEvent],
    error_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    approval_request_text: Callable[[str, ToolEvent], str],
) -> CommandExecutionResult:
    inputs = shell_command_handlers_pure_helpers_runtime.parse_exec_command_inputs(
        runtime=runtime,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        normalize_shell_option_fn=shell_command_handlers_runtime.normalize_shell_option,
    )
    if not inputs.command:
        return text_only_result(
            _command_usage_text("exec_command")
            or "Usage: /exec_command <cmd> [workdir <dir>] [shell <path>] [tty] [login <true|false>] [yield-time-ms <n>] [timeout-ms <n>] [max-output-tokens <n>]"
        )
    try:
        request = shell_command_handlers_pure_helpers_runtime.resolve_exec_command_request(
            inputs,
            bool_option=bool_option,
            int_option=int_option,
        )
    except ValueError as exc:
        _tool_trace(
            "tool.exec_command.parse_failed",
            command=inputs.command,
            raw_arg_text=str(arg_text or ""),
            error=str(exc),
        )
        return error_result(
            error_event("exec_command", "exec_command parse failed", error=str(exc)),
            arguments={"cmd": inputs.command},
        )
    _tool_trace(
        "tool.exec_command.started",
        command=request.command,
        workdir=request.workdir,
        shell=request.shell,
        shell_override=request.shell_override,
        resolved_shell=request.shell,
        tty=request.tty,
        login=request.login,
        yield_time_ms=request.yield_time_ms,
        timeout_ms=request.timeout_ms,
        max_output_tokens=request.max_output_tokens,
        sandbox_permissions=request.sandbox_permissions,
        justification=request.justification,
        prefix_rule=list(request.prefix_rule) if request.prefix_rule is not None else None,
        additional_permissions=request.additional_permissions,
    )
    blocked_result = _blocked_exec_command_result(runtime, command_text=request.command)
    if blocked_result is not None:
        return blocked_result
    inline_apply_patch_result = _inline_apply_patch_exec_result(
        runtime,
        request=request,
        compact_arguments=compact_arguments,
        approval_request_text=approval_request_text,
    )
    if inline_apply_patch_result is not None:
        return inline_apply_patch_result
    function_call_arguments = _exec_command_arguments(
        request=request,
        resolved_shell=request.shell,
        compact_arguments=compact_arguments,
    )
    policy_state = evaluate_exec_command_action_policy(
        runtime,
        request.command,
        workdir=request.workdir,
        sandbox_permissions=request.sandbox_permissions,
        additional_permissions=request.additional_permissions,
    )
    policy_payload = dict(policy_state["payload"] or {})
    requirement_name = str(
        (policy_state["action_policy_payload"] or {}).get("requirement") or ""
    ).strip()
    if requirement_name == "forbidden":
        if (
            bool(policy_payload.get("codex_noninteractive_headless"))
            and str(policy_payload.get("reason_code") or "").strip()
            == "exec.read_only.forbidden.no_approval"
        ):
            return _codex_read_only_exec_failure_result(
                request=request,
                policy_payload=policy_payload,
            )
        payload: dict[str, Any] = (
            shell_command_handlers_pure_helpers_runtime.shell_contract_payload(
                {"command": request.command, "status": "policy_denied", "allowed": False},
                shell_override=request.shell_override,
                resolved_shell=request.shell,
            )
        )
        payload.update(policy_payload)
        return error_result(
            error_event(
                "exec_command",
                "exec_command denied by exec policy",
                error=str(
                    policy_payload.get("reason_text") or "exec_command denied by exec policy"
                ),
                **payload,
            ),
            arguments=function_call_arguments,
            tool_name="exec_command",
        )
    if requirement_name == "needs_approval":
        approval_cached = approval_contract_runtime.shell_approval_is_cached(
            runtime,
            command=request.command,
            cwd=request.workdir,
            exec_mode="exec_once",
            login=request.login,
            tty=request.tty,
            shell=request.shell,
            sandbox_permissions=request.sandbox_permissions,
            additional_permissions=request.additional_permissions,
        )
        if not approval_cached:
            event = _request_shell_approval_for_exec(
                runtime,
                request.command,
                exec_mode="exec_once",
                cwd=request.workdir,
                login=request.login,
                tty=request.tty,
                shell=request.shell,
                max_output_chars=shell_command_handlers_runtime.max_output_chars_for_tokens(
                    request.max_output_tokens
                ),
                sandbox_permissions=request.sandbox_permissions,
                justification=request.justification,
                prefix_rule=list(request.prefix_rule) if request.prefix_rule is not None else None,
                additional_permissions=request.additional_permissions,
                policy_payload=policy_payload,
            )
            event.payload.update(policy_payload)
            event = shell_command_handlers_pure_helpers_runtime.enrich_tool_event_shell_contract(
                event,
                shell_override=request.shell_override,
                resolved_shell=request.shell,
            )
            _tool_trace(
                "tool.exec_command.approval_requested",
                **_tool_event_trace_payload(event, compact_arguments=compact_arguments),
            )
            return CommandExecutionResult(
                assistant_text=approval_request_text("Request shell approval.", event),
                tool_events=[event],
                item_events=generic_tool_call_item_events(
                    tool_name="exec_command",
                    arguments=function_call_arguments,
                    ok=bool(event.ok),
                    summary=str(event.summary or ""),
                    structured_content=dict(event.payload or {}),
                ),
            )
        policy_payload.update(
            {
                "approval_cache_hit": True,
                "policy_decision": "allowed",
                "policy_decision_reason": "approval_cached",
            }
        )
    try:
        session = runtime.start_shell_session(
            request.command,
            cwd=request.workdir,
            login=request.login,
            tty=request.tty,
            shell=request.shell,
            max_output_chars=shell_command_handlers_runtime.max_output_chars_for_tokens(
                request.max_output_tokens
            ),
        )
    except Exception as exc:
        summary = (
            "exec_command denied by policy"
            if isinstance(exc, command_policy_runtime.CommandPolicyError)
            else "exec_command failed"
        )
        payload: dict[str, Any] = (
            shell_command_handlers_pure_helpers_runtime.shell_contract_payload(
                {"command": request.command},
                shell_override=request.shell_override,
                resolved_shell=request.shell,
            )
        )
        if isinstance(exc, command_policy_runtime.CommandPolicyError):
            payload.update(dict(exc.payload or {}))
        _tool_trace(
            "tool.exec_command.failed",
            command=request.command,
            workdir=request.workdir,
            shell=request.shell,
            shell_override=request.shell_override,
            resolved_shell=request.shell,
            tty=request.tty,
            login=request.login,
            error=str(exc),
        )
        return error_result(
            error_event("exec_command", summary, error=str(exc), **payload),
            arguments={"cmd": request.command},
        )
    resolved_shell = shell_command_handlers_pure_helpers_runtime.resolved_shell_value(
        session.get("shell"), request.shell
    )
    _tool_trace(
        "tool.exec_command.session_started",
        command=request.command,
        workdir=request.workdir,
        shell=resolved_shell,
        shell_override=request.shell_override,
        resolved_shell=resolved_shell,
        tty=request.tty,
        login=request.login,
        session_id=session.get("session_id"),
        process_id=session.get("process_id"),
        call_id=session.get("call_id"),
    )
    session_id = str(session.get("session_id") or "").strip()
    poll_result = runtime.write_shell_stdin_result(
        session_id,
        "",
        yield_time_ms=request.yield_time_ms,
        allow_extended_empty_poll=True,
    )
    function_call_arguments = _exec_command_arguments(
        request=request,
        resolved_shell=resolved_shell,
        compact_arguments=compact_arguments,
    )
    payload = shell_command_handlers_runtime.exec_command_poll_payload(
        poll_payload=dict(
            (poll_result.tool_events[0].payload if poll_result.tool_events else {}) or {}
        ),
        command=request.command,
        session_id=session_id,
        call_id=session.get("call_id"),
        process_id=session.get("process_id"),
        workdir=request.workdir,
        shell=resolved_shell,
        shell_override=request.shell_override,
        resolved_shell=resolved_shell,
        tty=request.tty,
        login=request.login,
        yield_time_ms=request.yield_time_ms,
        timeout_ms=request.timeout_ms,
        max_output_tokens=request.max_output_tokens,
        sandbox_permissions=request.sandbox_permissions,
        justification=request.justification,
        prefix_rule=request.prefix_rule,
        additional_permissions=request.additional_permissions,
        function_call_arguments=function_call_arguments,
    )
    payload.update(policy_payload)
    event = _canonical_command_tool_event("exec_command", payload, command=request.command)
    _tool_trace(
        "tool.exec_command.completed",
        **_tool_event_trace_payload(event, compact_arguments=compact_arguments),
    )
    return CommandExecutionResult(
        assistant_text=_canonical_exec_output_text(payload),
        tool_events=[event],
        item_events=shell_tool_call_item_events(event, command=request.command),
    )
