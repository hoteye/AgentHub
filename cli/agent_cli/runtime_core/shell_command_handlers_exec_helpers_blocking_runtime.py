from __future__ import annotations

import re
from typing import Any, Callable

from cli.agent_cli.models import CommandExecutionResult, FunctionCallOutputPayload
from cli.agent_cli.runtime_core.tool_call_context_runtime import current_provider_tool_call_id


def active_run_text(runtime: Any) -> str:
    return str(
        getattr(runtime, "_active_run_text", "")
        or getattr(runtime, "_active_run_label", "")
        or ""
    ).strip()


def user_explicitly_forbids_tool(user_text: str, tool_name: str) -> bool:
    normalized_text = str(user_text or "").strip()
    normalized_tool = str(tool_name or "").strip()
    if not normalized_text or not normalized_tool:
        return False
    escaped_tool = re.escape(normalized_tool)
    wrapped_tool = rf"[`\"']?{escaped_tool}[`\"']?"
    patterns = (
        rf"\bdo\s+not\s+use\s+{wrapped_tool}\b",
        rf"\bdon['’]t\s+use\s+{wrapped_tool}\b",
        rf"\bmust\s+not\s+use\s+{wrapped_tool}\b",
        rf"\bshould\s+not\s+use\s+{wrapped_tool}\b",
        rf"\bwithout\s+using\s+{wrapped_tool}\b",
        rf"\bavoid\s+using\s+{wrapped_tool}\b",
        rf"(不要|别|禁止|不能|不可)\s*(使用|用)?\s*{wrapped_tool}",
    )
    return any(re.search(pattern, normalized_text, flags=re.IGNORECASE) for pattern in patterns)


def blocked_exec_command_refusal_text(
    command_text: str,
    *,
    looks_like_inline_apply_patch: Callable[[str], bool],
) -> str:
    if looks_like_inline_apply_patch(command_text):
        return (
            "I can’t do that because the only file-editing path available in this session is "
            "exec_command, and you explicitly told me not to use it."
        )
    return "I can’t do that because you explicitly told me not to use exec_command."


def blocked_exec_command_item_events(refusal_text: str) -> list[dict[str, Any]]:
    call_id = current_provider_tool_call_id()
    if not call_id:
        return []
    payload = FunctionCallOutputPayload.from_output(refusal_text, success=False)
    return [
        {
            "type": "item.completed",
            "item": {
                "id": "item_0",
                "type": "function_call_output",
                "call_id": call_id,
                "output": payload.wire_value(),
                "success": payload.success,
            },
        }
    ]


def blocked_exec_command_result(
    runtime: Any,
    *,
    command_text: str,
    looks_like_inline_apply_patch: Callable[[str], bool],
    tool_trace: Callable[..., None],
) -> CommandExecutionResult | None:
    user_text = active_run_text(runtime)
    if not user_explicitly_forbids_tool(user_text, "exec_command"):
        return None
    refusal_text = blocked_exec_command_refusal_text(
        command_text,
        looks_like_inline_apply_patch=looks_like_inline_apply_patch,
    )
    tool_trace(
        "tool.exec_command.blocked_by_user_instruction",
        command=command_text,
        user_text=user_text,
    )
    return CommandExecutionResult(
        assistant_text=refusal_text,
        tool_events=[],
        item_events=blocked_exec_command_item_events(refusal_text),
    )
