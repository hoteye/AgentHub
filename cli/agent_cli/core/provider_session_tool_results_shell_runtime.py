from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.models import (
    FunctionCallOutputPayload,
    ToolEvent,
    function_call_output_payload_from_text_segments,
)
from cli.agent_cli.core.provider_session_tool_results_shell_apply_patch_helpers_runtime import (
    codex_apply_patch_explicit_output,
    codex_apply_patch_warning_item,
    inline_apply_patch_text,
    shell_codex_passthrough_explicit_output,
)
from cli.agent_cli.core.provider_session_tool_results_shell_status_helpers_runtime import (
    shell_background_line,
    shell_codex_background_line,
    shell_codex_fallback_line,
    shell_codex_normalized_explicit_output,
    shell_codex_status_line,
    shell_exit_code,
    shell_exit_code_from_payload,
    shell_explicit_fallback_text,
    shell_failure_line,
    shell_running_status,
    shell_stderr_text,
    shell_stdout_text,
    shell_summary_text,
    tool_event_is_shell_like,
    tool_event_provider_type,
    tool_result_projection_policy,
)


def tool_event_provider_raw_item(tool_event: ToolEvent | None) -> Dict[str, Any]:
    if tool_event is None:
        return {}
    payload = dict(tool_event.payload or {})
    raw_item = payload.get("provider_raw_item")
    if isinstance(raw_item, dict):
        return dict(raw_item)
    return {}


def shell_output_block(tool_event: ToolEvent | None) -> Dict[str, Any]:
    payload = dict(getattr(tool_event, "payload", {}) or {})
    block: Dict[str, Any] = {}
    stdout = payload.get("stdout")
    stderr = payload.get("stderr")
    aggregated_output = payload.get("aggregated_output")
    if stdout is None and stderr is None and aggregated_output is not None:
        stdout = aggregated_output
    if stdout is not None:
        block["stdout"] = str(stdout)
    if stderr is not None:
        block["stderr"] = str(stderr)

    outcome: Dict[str, Any] = {}
    if payload.get("timed_out"):
        outcome["type"] = "timeout"
    elif payload.get("interrupted"):
        outcome["type"] = "interrupted"
    else:
        outcome["type"] = "exit"
        exit_code = payload.get("exit_code", payload.get("returncode"))
        if exit_code is None and tool_event is not None:
            exit_code = 0 if bool(tool_event.ok) else 1
        try:
            outcome["exit_code"] = int(exit_code)
        except (TypeError, ValueError):
            pass
    if outcome:
        block["outcome"] = outcome
    return block


def shell_tool_result_payload(
    command_text: Optional[str],
    assistant_text: str,
    events: List[ToolEvent],
    *,
    tool_result_projection_policy: str = "",
) -> FunctionCallOutputPayload | None:
    last_event = events[-1] if events else None
    if not tool_event_is_shell_like(last_event):
        return None
    normalized_policy = tool_result_projection_policy.strip().lower()
    payload = dict(last_event.payload or {}) if last_event is not None else {}
    if normalized_policy == "codex_like":
        explicit_output = str(payload.get("function_call_output") or "").strip()
        if explicit_output:
            success = bool(last_event.ok) if last_event is not None else None
            if (
                bool(payload.get("inline_apply_patch_intercepted"))
                or inline_apply_patch_text(command_text)
                or inline_apply_patch_text(payload.get("command"))
            ):
                return FunctionCallOutputPayload.from_output(
                    codex_apply_patch_explicit_output(
                        explicit_output=explicit_output,
                        payload=payload,
                        tool_event=last_event,
                    ),
                    success=success,
                )
            if shell_codex_passthrough_explicit_output(
                command_text=command_text,
                payload=payload,
                explicit_output=explicit_output,
            ):
                return FunctionCallOutputPayload.from_output(explicit_output, success=success)
            return FunctionCallOutputPayload.from_output(
                shell_codex_normalized_explicit_output(
                    explicit_output=explicit_output,
                    payload=payload,
                ),
                success=success,
            )
    parts: List[str] = []
    stdout_text = shell_stdout_text(payload)
    stderr_text = shell_stderr_text(payload)
    if stdout_text:
        parts.append(stdout_text)
    if stderr_text:
        parts.append(stderr_text)
    if shell_running_status(payload):
        if normalized_policy == "codex_like":
            parts.append(shell_codex_background_line(payload))
        else:
            parts.append(shell_background_line(payload))
    elif last_event is not None:
        if normalized_policy == "codex_like":
            status_line = shell_codex_status_line(tool_event=last_event, payload=payload, stderr_text=stderr_text)
            if status_line:
                parts.append(status_line)
        else:
            failure_line = shell_failure_line(tool_event=last_event, payload=payload)
            if failure_line:
                parts.append(failure_line)
    if not parts:
        fallback = shell_explicit_fallback_text(
            command_text=command_text,
            assistant_text=assistant_text,
            tool_event=last_event,
            payload=payload,
            projection_policy=normalized_policy,
        )
        if fallback:
            parts.append(fallback)
    success = bool(last_event.ok) if last_event is not None else None
    return function_call_output_payload_from_text_segments(parts, success=success)


def shell_tool_result_items(
    *,
    call_id: str,
    events: List[ToolEvent],
) -> List[Dict[str, Any]]:
    last_event = events[-1] if events else None
    provider_item_type = tool_event_provider_type(last_event)
    output_item_type = "local_shell_call_output" if provider_item_type == "local_shell_call" else "shell_call_output"
    raw_item = tool_event_provider_raw_item(last_event)
    item: Dict[str, Any] = {
        "type": output_item_type,
        "call_id": call_id,
        "output": [shell_output_block(last_event)],
    }
    action = dict(raw_item.get("action") or {}) if isinstance(raw_item.get("action"), dict) else {}
    max_output_length = raw_item.get("max_output_length", action.get("max_output_length"))
    if max_output_length is None and last_event is not None:
        payload = dict(last_event.payload or {})
        max_output_length = payload.get("max_output_length", payload.get("max_output_chars"))
    if max_output_length is not None:
        try:
            item["max_output_length"] = int(max_output_length)
        except (TypeError, ValueError):
            item["max_output_length"] = max_output_length
    status = ""
    if last_event is not None:
        status = str((last_event.payload or {}).get("status") or "").strip()
    if status:
        item["status"] = status
    return [item]
