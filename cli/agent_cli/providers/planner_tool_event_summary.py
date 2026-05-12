from __future__ import annotations

from typing import Any, Dict, List, Sequence

from cli.agent_cli.models import ToolEvent, tool_event_is_soft_failure


def _trim_text(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _short_success_output(payload: Dict[str, Any], *, limit: int = 800) -> str:
    for key in ("stdout", "aggregated_output", "output_text", "text"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value if len(value) <= limit else ""
    function_call_output = str(payload.get("function_call_output") or "").strip()
    if function_call_output.startswith("Process exited with code 0\nOutput:\n"):
        function_call_output = function_call_output.split("Output:\n", 1)[1].strip()
    text = str(function_call_output or "").strip()
    if len(text) > limit:
        return ""
    return text


def generic_tool_event_summary_lines(events: Sequence[ToolEvent]) -> List[str]:
    lines: List[str] = []
    for event in list(events or [])[-6:]:
        payload = event.payload or {}
        status_text = "ok" if event.ok else ("no_match" if tool_event_is_soft_failure(event) else "failed")
        line = f"- {event.name}: {status_text}"
        if event.name == "grep_files":
            pattern = str(payload.get("pattern") or "").strip()
            search_path = str(payload.get("path") or "").strip()
            top_path = str(((payload.get("paths") or [None])[0]) or "").strip()
            if pattern:
                line += f" | pattern={pattern}"
            if search_path:
                line += f" | path={search_path}"
            if top_path:
                line += f" | top_path={top_path}"
            else:
                line += f" | {event.summary}"
            lines.append(line)
            continue
        if event.name == "read_file":
            file_path = str(payload.get("file_path") or payload.get("path") or "").strip()
            excerpt_lines = list(payload.get("excerpt_lines") or [])
            top_excerpt = ""
            if excerpt_lines and isinstance(excerpt_lines[0], dict):
                line_no = int(excerpt_lines[0].get("line") or 0)
                line_text = _trim_text(excerpt_lines[0].get("text"), limit=120)
                if line_text:
                    top_excerpt = f"L{line_no}: {line_text}" if line_no > 0 else line_text
            if file_path:
                line += f" | path={file_path}"
            if top_excerpt:
                line += f" | excerpt={top_excerpt}"
            else:
                line += f" | {event.summary}"
            lines.append(line)
            continue
        if event.name == "list_dir":
            dir_path = str(payload.get("dir_path") or payload.get("path") or "").strip()
            entries = list(payload.get("entries") or [])
            top_entry = ""
            if entries and isinstance(entries[0], dict):
                top_kind = str(entries[0].get("kind") or "").strip()
                top_path = str(entries[0].get("path") or "").strip()
                if top_path:
                    top_entry = f"[{top_kind}] {top_path}" if top_kind else top_path
            if dir_path:
                line += f" | path={dir_path}"
            if top_entry:
                line += f" | first_entry={top_entry}"
            else:
                line += f" | {event.summary}"
            lines.append(line)
            continue
        if event.name == "web_search":
            query = str(payload.get("query") or "").strip()
            if query:
                line += f" | query={query}"
            top_result = (payload.get("results") or [None])[0] or {}
            top_title = str(top_result.get("title") or "").strip()
            top_url = str(top_result.get("url") or "").strip()
            if top_title:
                line += f" | top_title={top_title}"
            if top_url:
                line += f" | top_url={top_url}"
            lines.append(line)
            continue
        if event.name == "web_fetch":
            url = str(payload.get("final_url") or payload.get("url") or "").strip()
            title = str(payload.get("title") or "").strip()
            if url:
                line += f" | url={url}"
            if title:
                line += f" | title={title}"
            lines.append(line)
            continue
        line += f" | {event.summary}"
        detail_parts: List[str] = []
        for key in ("conversation_name", "summary_text", "draft_text", "draft_reply", "reason", "stdout", "stderr"):
            value = str(payload.get(key) or "").strip()
            if not value:
                continue
            if key in {"stdout", "stderr"}:
                value = value[:200]
            detail_parts.append(f"{key}={value}")
            if len(detail_parts) >= 2:
                break
        if detail_parts:
            line += " | " + " ; ".join(detail_parts)
        lines.append(line)
    return lines


def structured_tool_fallback_text(executed_events: Sequence[ToolEvent]) -> str:
    # Avoid import-time cycle between providers and runtime_core.command_dispatch.
    from cli.agent_cli.runtime_core.command_dispatch import tool_result_fallback_text

    events = list(executed_events or [])
    if not events:
        return "模型未返回内容。"
    last_event = events[-1]
    payload = dict(last_event.payload or {})
    if bool(last_event.ok) and str(last_event.name or "").strip() in {"exec_command", "write_stdin", "shell"}:
        command_text = _trim_text(payload.get("command"), limit=160)
        output_text = _short_success_output(payload)
        lines: List[str] = ["工具已执行完成，但回答阶段未产出可展示内容。"]
        if command_text:
            lines.append(f"最后一个命令：`{command_text}`")
        if output_text:
            lines.append(f"工具输出：\n{output_text}")
        return "\n".join(lines)
    fallback_text = tool_result_fallback_text(events)
    if fallback_text:
        return fallback_text
    if not last_event.ok:
        return str(payload.get("error") or last_event.summary or "工具调用失败").strip()
    return "工具调用已完成，但回答阶段未产出可展示内容。"
