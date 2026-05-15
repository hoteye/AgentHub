from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core import (
    shell_command_handlers_pure_helpers_runtime as exec_parse_runtime,
)
from cli.agent_cli.runtime_core import shell_command_handlers_runtime as shell_command_runtime
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    bool_option as _structured_bool_option,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    int_option as _structured_int_option,
)


@dataclass
class ToolExecutionResult:
    call_id: str
    command_text: str | None
    assistant_text: str
    events: list[ToolEvent]
    item_events: list[dict[str, Any]]
    elapsed_ms: int
    pre_emitted_item_events: list[dict[str, Any]] | None = None


def tool_call_preamble_text(tool_name: str, arguments: dict[str, Any]) -> str:
    normalized_tool_name = str(tool_name or "").strip()
    if normalized_tool_name in {"list_dir", "file_list"}:
        path_text = str(arguments.get("dir_path") or arguments.get("path") or ".").strip() or "."
        return (
            "我先查看当前目录内容。"
            if path_text in {".", "./"}
            else f"我先查看 {path_text} 的目录内容。"
        )
    if normalized_tool_name in {"read_file", "file_read"}:
        path_text = str(arguments.get("file_path") or arguments.get("path") or "").strip()
        return f"我先读取 {path_text} 的内容。" if path_text else "我先读取相关文件内容。"
    if normalized_tool_name in {"file_search", "grep_files"}:
        query_text = str(arguments.get("query") or arguments.get("pattern") or "").strip()
        return f"我先在仓库里搜索 {query_text}。" if query_text else "我先在仓库里搜索相关内容。"
    if normalized_tool_name in {"exec_command", "shell", "write_stdin"}:
        return "我先运行一个命令检查一下。"
    if normalized_tool_name in {"web_search", "web_fetch", "open", "click", "find", "browser"}:
        return "我先做一步网页检查。"
    return "我先检查一下相关内容。"


def synthetic_agent_message_event(*, item_id: str, text: str) -> dict[str, Any]:
    return {
        "type": "item.completed",
        "item": {
            "id": str(item_id or ""),
            "type": "agent_message",
            "text": str(text or "").strip(),
        },
    }


def annotate_tool_events_with_provider_call(
    *,
    tool_events: list[ToolEvent],
    provider_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    execution_tool: str = "",
    provider_item_type: str = "",
    provider_raw_item: dict[str, Any] | None = None,
) -> list[ToolEvent]:
    annotated: list[ToolEvent] = []
    for tool_event in list(tool_events or []):
        payload = dict(tool_event.payload or {})
        if provider_call_id:
            payload.setdefault("provider_call_id", provider_call_id)
        if tool_name:
            payload.setdefault("function_call_name", tool_name)
        if execution_tool:
            payload.setdefault("planner_execution_tool", str(execution_tool))
        if provider_item_type:
            payload.setdefault("provider_tool_type", str(provider_item_type))
        if provider_raw_item:
            payload.setdefault("provider_raw_item", dict(provider_raw_item or {}))
        payload.setdefault("function_call_arguments", dict(arguments or {}))
        annotated.append(
            ToolEvent(
                name=str(tool_event.name or ""),
                ok=bool(tool_event.ok),
                summary=str(tool_event.summary or ""),
                payload=payload,
            )
        )
    return annotated


def _unmapped_tool_call_result(
    call: Any,
    *,
    elapsed_ms: int,
) -> ToolExecutionResult | None:
    call_id = str(getattr(call, "call_id", "") or "").strip()
    if not call_id:
        return None
    call_name = str(getattr(call, "name", "") or "").strip() or "unknown_tool"
    arguments = dict(getattr(call, "arguments", {}) or {})
    provider_item_type = str(getattr(call, "item_type", "") or "").strip()
    provider_raw_item = dict(getattr(call, "raw_item", {}) or {})
    message = (
        f"Tool call {call_name} could not be executed because AgentHub has no "
        "command mapping for the provided tool name or arguments."
    )
    event = ToolEvent(
        name=call_name,
        ok=False,
        summary=message,
        payload={
            "provider_call_id": call_id,
            "function_call_name": call_name,
            "function_call_arguments": arguments,
            "provider_tool_type": provider_item_type,
            "provider_raw_item": provider_raw_item,
            "error": message,
            "function_call_output": message,
            "function_call_output_model_visible": True,
        },
    )
    return ToolExecutionResult(
        call_id=call_id,
        command_text=None,
        assistant_text=message,
        events=[event],
        item_events=[
            {
                "type": "item.completed",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": message,
                    "success": False,
                },
            }
        ],
        elapsed_ms=elapsed_ms,
    )


def _provisional_shell_metadata(
    engine: Any,
    *,
    command_text: str,
) -> dict[str, Any]:
    if not str(command_text or "").strip().startswith("/exec_command"):
        return {}
    runtime = getattr(getattr(engine, "tool_executor", None), "runtime_owner", None)
    if runtime is None:
        return {}
    try:
        inputs = exec_parse_runtime.parse_exec_command_inputs(
            runtime=runtime,
            arg_text=_exec_command_arg_text(command_text),
            slash_invocation=None,
            normalize_shell_option_fn=shell_command_runtime.normalize_shell_option,
        )
        request = exec_parse_runtime.resolve_exec_command_request(
            inputs,
            bool_option=_structured_bool_option,
            int_option=_structured_int_option,
        )
    except Exception:
        return {}
    resolved_shell = _resolve_runtime_shell(runtime, request.shell)
    metadata: dict[str, Any] = {"login": request.login}
    if request.shell:
        metadata["shell"] = request.shell
    if resolved_shell:
        metadata["resolved_shell"] = resolved_shell
        metadata.setdefault("shell", resolved_shell)
    return metadata


def _exec_command_arg_text(command_text: str) -> str:
    text = str(command_text or "").strip()
    if text.startswith("/exec_command"):
        return text[len("/exec_command") :].strip()
    return text


def _resolve_runtime_shell(runtime: Any, shell: str | None) -> str | None:
    host_platform = getattr(runtime, "_host_platform", None)
    if callable(host_platform):
        try:
            platform = host_platform()
            resolved = platform.resolve_shell_program(shell)
            if resolved:
                return str(resolved)
        except Exception:
            pass
    normalizer = getattr(runtime, "_normalize_shell_override", None)
    if callable(normalizer):
        try:
            resolved = normalizer(shell)
            if resolved:
                return str(resolved)
        except Exception:
            pass
    return str(shell or "").strip() or None
