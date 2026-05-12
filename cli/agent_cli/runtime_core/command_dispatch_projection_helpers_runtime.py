from __future__ import annotations

from typing import Callable

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.models import ToolEvent

from .command_dispatch_pure_helpers_runtime import (
    failed_tool_output_text,
    successful_command_tool_output_text,
)


def tool_result_fallback_text(
    events: list[ToolEvent],
    *,
    tool_event_is_soft_failure_fn: Callable[[ToolEvent], bool],
) -> str:
    if not events:
        return ""
    last_event = events[-1]
    payload = last_event.payload or {}

    if last_event.name == "command_parse" and not last_event.ok:
        error_text = str(payload.get("error") or last_event.summary or "").strip()
        return f"命令解析失败: {error_text}" if error_text else "命令解析失败。"

    if not last_event.ok and not tool_event_is_soft_failure_fn(last_event):
        return failed_tool_output_text(payload, summary=str(last_event.summary or ""))

    if tool_event_is_soft_failure_fn(last_event):
        return str(payload.get("text") or last_event.summary or "").strip()

    if last_event.name in {"exec_command", "write_stdin"}:
        return successful_command_tool_output_text(payload, summary=str(last_event.summary or ""))

    if last_event.name == "web_fetch":
        title = str(payload.get("title") or "").strip()
        final_url = str(payload.get("final_url") or payload.get("url") or "").strip()
        if title and final_url:
            return f"已读取网页：{title}\n{final_url}"
        if title:
            return f"已读取网页：{title}"
        if final_url:
            return f"已读取网页：{final_url}"
        return "已读取网页。"

    if last_event.name == "file_read":
        path_text = str(payload.get("path") or "").strip()
        return f"已读取文件：{path_text}" if path_text else ""

    if last_event.name == "file_search":
        query_text = str(payload.get("query") or "").strip()
        if query_text:
            return (
                f"已执行兼容命令 /file_search：{query_text}\n"
                "建议优先使用 grep_files（文件发现）+ read_file/file_read（按行读取）。"
            )
        return "已执行兼容命令 /file_search；建议优先使用 grep_files。"

    if last_event.name == "file_list":
        path_text = str(payload.get("path") or ".").strip() or "."
        return (
            f"已执行兼容命令 /file_list（path={path_text}）。\n"
            "建议优先使用 list_dir（目录分页与深度遍历）。"
        )

    if last_event.name == "apply_patch":
        file_count = int(payload.get("file_count") or 0)
        return f"已修改 {file_count} 个文件。" if file_count else "已应用补丁。"

    if last_event.name == "patch_approval_requested":
        approval_id = str(payload.get("approval_id") or "").strip()
        commands = approval_contract_runtime.approval_option_commands(
            approval_id,
            payload.get("available_decisions"),
        )
        if approval_id:
            return (
                f"已提交补丁审批：{approval_id}\n"
                + "\n".join(commands or [f"/approve {approval_id}", f"/reject {approval_id}"])
            )
        return "已提交补丁审批。"

    if last_event.name == "shell_approval_requested":
        approval_id = str(payload.get("approval_id") or "").strip()
        command = str(payload.get("command") or "").strip()
        commands = approval_contract_runtime.approval_option_commands(
            approval_id,
            payload.get("available_decisions"),
        )
        if approval_id and command:
            return (
                f"已提交命令审批：{approval_id}\n"
                + "\n".join(commands or [f"/approve {approval_id}", f"/reject {approval_id}"])
                + "\n"
                f"{command}"
            )
        if approval_id:
            return (
                f"已提交命令审批：{approval_id}\n"
                + "\n".join(commands or [f"/approve {approval_id}", f"/reject {approval_id}"])
            )
        return "已提交命令审批。"

    if last_event.name == "background_teammate_approval_requested":
        summary_text = str(payload.get("summary_text") or "").strip()
        if summary_text:
            return summary_text
        approval_id = str(payload.get("approval_id") or "").strip()
        commands = approval_contract_runtime.approval_option_commands(
            approval_id,
            payload.get("available_decisions"),
        )
        if approval_id:
            return (
                f"已提交后台 teammate 审批：{approval_id}\n"
                + "\n".join(commands or [f"/approve {approval_id}", f"/reject {approval_id}"])
            )
        return "已提交后台 teammate 审批。"

    if last_event.name == "approval_decision":
        approval_id = str(payload.get("approval_id") or "").strip()
        status = str(payload.get("status") or "").strip()
        if approval_id and status:
            return f"审批 {approval_id} 已{status}。"
        return ""

    if last_event.name == "background_teammate_submitted":
        summary_text = str(payload.get("summary_text") or "").strip()
        if summary_text:
            return summary_text
        task_id = str(payload.get("task_id") or "").strip()
        status = str(payload.get("status") or "").strip()
        if task_id and status:
            return f"background teammate submitted\n" f"task_id={task_id}\n" f"status={status}"
        return "background teammate submitted"

    if last_event.name in {"web_search", "open", "click", "find"}:
        return ""

    return str(last_event.summary or "").strip()
