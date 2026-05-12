from __future__ import annotations

import inspect
from typing import Any, Callable, Dict

from cli.agent_cli import runtime_codex_headless_contract_runtime as codex_headless_contract_runtime_service
from cli.agent_cli.models import CommandExecutionResult, ToolEvent, shell_tool_call_item_events
from cli.agent_cli.runtime_core import shell_command_handlers_pure_helpers_runtime
from cli.agent_cli.runtime_core import shell_command_handlers_runtime


def canonical_exec_output_text(payload: Dict[str, Any]) -> str:
    return shell_command_handlers_runtime.canonical_exec_output_text(payload)


def canonical_command_tool_event(name: str, payload: Dict[str, Any], *, command: str) -> ToolEvent:
    return shell_command_handlers_runtime.canonical_command_tool_event(
        name,
        payload,
        command=command,
        tool_event_cls=ToolEvent,
        canonical_exec_output_text_fn=canonical_exec_output_text,
    )


def codex_read_only_exec_failure_result(
    *,
    request: shell_command_handlers_pure_helpers_runtime.ExecCommandRequest,
    policy_payload: Dict[str, Any],
) -> CommandExecutionResult:
    payload: Dict[str, Any] = shell_command_handlers_pure_helpers_runtime.shell_contract_payload(
        {
            "ok": False,
            "command": request.command,
            "status": "failed",
            "allowed": False,
            "exit_code": 1,
            "returncode": 1,
        },
        shell_override=request.shell_override,
        resolved_shell=request.shell,
    )
    payload.update(policy_payload)
    payload.pop("output_text", None)
    stderr_text = (
        codex_headless_contract_runtime_service.codex_noninteractive_read_only_exec_stderr(
            command=request.command,
            shell=request.shell,
        )
    )
    payload["ok"] = False
    payload["status"] = "failed"
    payload["exit_code"] = 1
    payload["returncode"] = 1
    payload["stderr"] = stderr_text
    payload["error"] = stderr_text
    payload["function_call_output"] = canonical_exec_output_text(payload)
    payload["function_call_output_model_visible"] = True
    event = canonical_command_tool_event("exec_command", payload, command=request.command)
    return CommandExecutionResult(
        assistant_text=canonical_exec_output_text(payload),
        tool_events=[event],
        item_events=shell_tool_call_item_events(event, command=request.command),
    )


def exec_command_arguments(
    *,
    request: shell_command_handlers_pure_helpers_runtime.ExecCommandRequest,
    resolved_shell: str | None,
    compact_arguments: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> dict[str, Any]:
    return shell_command_handlers_runtime.exec_command_arguments(
        command=request.command,
        workdir=request.workdir,
        shell=request.shell,
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
        compact_arguments=compact_arguments,
    )


def request_shell_approval_for_exec(runtime: Any, command: str, **kwargs: Any) -> ToolEvent:
    request_shell_approval = runtime.request_shell_approval
    signature = inspect.signature(request_shell_approval)
    accepts_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if accepts_var_kwargs:
        return request_shell_approval(command, **kwargs)
    accepted_kwargs = {
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    }
    return request_shell_approval(
        command,
        **{key: value for key, value in kwargs.items() if key in accepted_kwargs},
    )
