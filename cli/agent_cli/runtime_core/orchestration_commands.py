from __future__ import annotations

from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import (
    orchestration_commands_parse_runtime as orchestration_parse_runtime,
)
from cli.agent_cli.runtime_core import (
    orchestration_commands_visible_child_runtime as visible_child_runtime,
)
from cli.agent_cli.runtime_core.orchestration_commands_helpers_runtime import (
    _preview_request_orchestration,
    _run_orchestration_confirmation,
)
from cli.agent_cli.runtime_core.orchestration_commands_helpers_runtime_text import (
    _child_tab_send_text,
    _child_tab_spawn_text,
    _child_task_wait_text,
    _orchestrate_confirmation_text,
    _orchestrate_continue_text,
    _orchestrate_created_text,
    _orchestrate_dispatch_text,
    _orchestrate_progress_text,
    _orchestrate_review_text,
    _orchestration_preview_request_text,
)


def handle_orchestration_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
) -> tuple[str, list[Any]] | CommandExecutionResult | None:
    if name == "__request_orchestration":
        try:
            request = _parse_request_orchestration_payload(arg_text)
        except ValueError as exc:
            return (str(exc), [])
        if bool(request.get("confirmation_required")) and callable(
            getattr(runtime, "request_user_input_handler", None)
        ):
            payload = _run_orchestration_confirmation(
                runtime,
                str(request.get("source_text") or ""),
                initial_planning_adjustments=dict(request.get("planning_adjustments") or {}),
            )
            return _command_result(_orchestrate_confirmation_text(payload))
        payload = _preview_request_orchestration(runtime, request)
        return _command_result(_orchestration_preview_request_text(payload))
    if name == "__spawn_child_tab":
        try:
            payload = _run_spawn_child_tab(runtime, arg_text)
        except ValueError as exc:
            return _tool_error_result("spawn_child_tab", str(exc))
        return _tool_result("spawn_child_tab", _child_tab_spawn_text(payload), payload)
    if name == "__send_child_tab":
        try:
            payload = _run_send_child_tab(runtime, arg_text)
        except ValueError as exc:
            return _tool_error_result("send_child_tab", str(exc))
        return _tool_result("send_child_tab", _child_tab_send_text(payload), payload)
    if name == "__wait_child_tasks":
        try:
            payload = _run_wait_child_tasks(runtime, arg_text)
        except ValueError as exc:
            return _tool_error_result("wait_child_tasks", str(exc))
        return _tool_result("wait_child_tasks", _child_task_wait_text(payload), payload)
    if name == "orchestrate":
        task_text = str(arg_text or "").strip()
        if not task_text:
            return ("Usage: /orchestrate <task text or taskbook markdown>", [])
        try:
            payload = runtime.create_orchestration_run(task_text)
        except ValueError as exc:
            return (str(exc), [])
        return _command_result(_orchestrate_created_text(payload))
    if name == "orchestrate_confirm":
        task_text = str(arg_text or "").strip()
        if not task_text:
            return ("Usage: /orchestrate_confirm <task text or taskbook markdown>", [])
        try:
            payload = _run_orchestration_confirmation(runtime, task_text)
        except ValueError as exc:
            return (str(exc), [])
        return _command_result(_orchestrate_confirmation_text(payload))
    if name == "orchestrate_dispatch":
        run_id = str(arg_text or "").strip()
        if not run_id:
            return ("Usage: /orchestrate_dispatch <run_id>", [])
        try:
            payload = runtime.dispatch_orchestration_run(run_id)
        except ValueError as exc:
            return (str(exc), [])
        return _command_result(_orchestrate_dispatch_text(payload))
    if name == "orchestrate_progress":
        run_id = str(arg_text or "").strip()
        if not run_id:
            return ("Usage: /orchestrate_progress <run_id>", [])
        try:
            payload = runtime.progress_orchestration_run(run_id)
        except ValueError as exc:
            return (str(exc), [])
        return _command_result(_orchestrate_progress_text(payload))
    if name == "orchestrate_continue":
        parse_args = getattr(runtime, "_parse_args", None)
        if not callable(parse_args):
            return (
                "Usage: /orchestrate_continue <run_id> [max-passes <n>] [dispatch-ready <true|false>]",
                [],
            )
        run_id, options = _parse_orchestration_continue_args(runtime, arg_text)
        if not run_id:
            return (
                "Usage: /orchestrate_continue <run_id> [max-passes <n>] [dispatch-ready <true|false>]",
                [],
            )
        try:
            max_passes = max(1, int(options.get("max-passes") or 8))
        except (TypeError, ValueError):
            return ("invalid max-passes for orchestrate_continue", [])
        dispatch_ready = _bool_option(options.get("dispatch-ready"), default=True)
        try:
            payload = runtime.continue_orchestration_run(
                run_id,
                max_passes=max_passes,
                dispatch_ready=dispatch_ready,
            )
        except ValueError as exc:
            return (str(exc), [])
        return _command_result(_orchestrate_continue_text(payload))
    if name == "orchestrate_apply":
        run_id, card_id = _parse_orchestration_review_args(runtime, arg_text)
        if not run_id or not card_id:
            return ("Usage: /orchestrate_apply <run_id> <card_id>", [])
        try:
            payload = runtime.apply_orchestration_card(run_id, card_id)
        except ValueError as exc:
            return (str(exc), [])
        return _command_result(_orchestrate_review_text(payload, applied=True))
    if name == "orchestrate_reject":
        run_id, card_id = _parse_orchestration_review_args(runtime, arg_text)
        if not run_id or not card_id:
            return ("Usage: /orchestrate_reject <run_id> <card_id>", [])
        try:
            payload = runtime.reject_orchestration_card(run_id, card_id)
        except ValueError as exc:
            return (str(exc), [])
        return _command_result(_orchestrate_review_text(payload, applied=False))
    return None


def _parse_request_orchestration_payload(arg_text: str) -> dict[str, Any]:
    return orchestration_parse_runtime.parse_request_orchestration_payload(arg_text)


def _parse_json_payload(arg_text: str, *, command_name: str) -> dict[str, Any]:
    return orchestration_parse_runtime.parse_json_object_payload(
        arg_text,
        command_name=command_name,
    )


def _run_spawn_child_tab(runtime: Any, arg_text: str) -> dict[str, Any]:
    request = _parse_json_payload(arg_text, command_name="__spawn_child_tab")
    return visible_child_runtime._run_spawn_child_tab_request(runtime, request)


def _run_send_child_tab(runtime: Any, arg_text: str) -> dict[str, Any]:
    request = _parse_json_payload(arg_text, command_name="__send_child_tab")
    return visible_child_runtime._run_send_child_tab_request(runtime, request)


def _run_wait_child_tasks(runtime: Any, arg_text: str) -> dict[str, Any]:
    request = _parse_json_payload(arg_text, command_name="__wait_child_tasks")
    return visible_child_runtime._run_wait_child_tasks_request(runtime, request)


def _parse_orchestration_review_args(runtime: Any, arg_text: str) -> tuple[str, str]:
    return orchestration_parse_runtime.parse_orchestration_review_args(runtime, arg_text)


def _parse_orchestration_continue_args(runtime: Any, arg_text: str) -> tuple[str, dict[str, Any]]:
    return orchestration_parse_runtime.parse_orchestration_continue_args(runtime, arg_text)


def _bool_option(value: Any, *, default: bool) -> bool:
    return orchestration_parse_runtime.bool_option(value, default=default)


def _command_result(text: str) -> CommandExecutionResult:
    return CommandExecutionResult(
        assistant_text=text,
        command_display_text=text,
    )


def _tool_result(tool_name: str, text: str, payload: dict[str, Any]) -> CommandExecutionResult:
    return CommandExecutionResult(
        assistant_text=text,
        command_display_text=text.splitlines()[0] if text else tool_name,
        tool_events=[
            ToolEvent(
                name=tool_name,
                ok=True,
                summary=text.splitlines()[0] if text else f"{tool_name} completed",
                payload=dict(payload),
            )
        ],
    )


def _tool_error_result(tool_name: str, error: str) -> CommandExecutionResult:
    text = f"{tool_name} failed: {error}"
    return CommandExecutionResult(
        assistant_text=text,
        command_display_text=text,
        tool_events=[
            ToolEvent(
                name=tool_name,
                ok=False,
                summary=f"{tool_name} failed",
                payload={"error": error},
            )
        ],
    )
