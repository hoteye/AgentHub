from __future__ import annotations

from typing import List, Optional

from cli.agent_cli.command_execution_summary_runtime import (
    command_activity_params,
    command_display_text_from_mapping,
)
from cli.agent_cli.models import ActivityEvent, ToolEvent, tool_event_is_soft_failure
from cli.agent_cli.runtime_core.event_detail_rendering import (
    activity_detail_for_event as _activity_detail_for_event,
    detail_for_event as _detail_for_event,
)
from cli.agent_cli.runtime_core.tool_event_rendering import (
    append_elapsed_detail as _append_elapsed_detail,
    browser_activity_repr as _browser_activity_repr,
)


def _web_search_backend_variant(payload: dict) -> str:
    route = payload.get("web_search_route") or {}
    route_backend_kind = str(route.get("effective_backend_kind") or route.get("selected_backend_kind") or "").strip().lower()
    route_backend_id = str(route.get("effective_backend_id") or route.get("selected_backend_id") or "").strip().lower()
    execution_path = str(route.get("execution_path") or "").strip().lower()
    engine = str(payload.get("engine") or "").strip().lower()

    if (
        route_backend_kind == "provider_native"
        or route_backend_id.startswith("provider_native_")
        or execution_path in {"openai_responses_native", "anthropic_native", "glm_native"}
        or ("native_web_search" in engine and not engine.startswith("local_"))
    ):
        return "native"
    if (
        route_backend_kind in {"local", "local_fallback"}
        or route_backend_id.startswith("local_")
        or execution_path == "local_fallback"
        or engine.startswith("local_")
    ):
        return "local"
    return ""


def _web_search_activity_title(event: ToolEvent) -> str:
    variant = _web_search_backend_variant(event.payload or {})
    if variant == "native":
        return "Native web search" if event.ok else "Native web search failed"
    if variant == "local":
        return "Local web search" if event.ok else "Local web search failed"
    return "Searched the web" if event.ok else "Web search failed"


def activity_events_for_tool_event(
    event: ToolEvent,
    *,
    selected_conversation: Optional[str] = None,
) -> List[ActivityEvent]:
    payload = event.payload or {}
    title = ""
    detail = activity_detail_for_event(event)
    status = "success" if event.ok else ("info" if tool_event_is_soft_failure(event) else "error")
    kind = "tool"
    code = ""
    params = dict(payload or {})
    if event.name == "interrupted":
        title = "Execution interrupted"
        status = "info"
        kind = "interrupt"
        code = "interrupt.completed"
        params = {"reason": str(payload.get("reason") or "user_interrupt")}
    elif event.name in {"shell", "exec_command", "write_stdin"}:
        command = str(payload.get("command") or event.summary or "command").strip()
        display_command = (
            command_display_text_from_mapping({"command": command, **dict(payload or {})}, single_line=True)
            or command
        )
        if payload.get("interrupted"):
            title = f"Interrupted {display_command}"
            status = "info"
        else:
            title = ("Ran " if event.ok else "Command failed: ") + display_command
        kind = "command"
        code = "command.run"
        params = command_activity_params(
            {"command": command, **dict(payload or {})},
            extra_params={
                "returncode": payload.get("returncode"),
                "interrupted": bool(payload.get("interrupted")),
                "timed_out": bool(payload.get("timed_out")),
                "duration_ms": payload.get("duration_ms"),
            },
        )
    elif event.name == "apply_patch":
        request_kind = str(payload.get("request_kind") or "").strip().lower()
        source_tool_name = str(payload.get("source_tool_name") or payload.get("function_call_name") or "").strip()
        if request_kind == "structured_write" and source_tool_name == "Write":
            change = ((payload.get("changes") or [{}])[0] if isinstance(payload.get("changes"), list) and payload.get("changes") else {})
            write_mode = str((change or {}).get("write_mode") or "").strip().lower()
            if event.ok:
                title = "Created file" if write_mode == "create" else "Overwrote file"
            else:
                title = "Write failed"
        elif request_kind == "structured_edit" and source_tool_name == "Edit":
            title = "Edited file" if event.ok else "Edit failed"
        else:
            title = "Applied patch" if event.ok else "Patch apply failed"
        code = "patch.apply"
        params = {
            "file_count": payload.get("file_count"),
            "added_count": payload.get("added_count"),
            "updated_count": payload.get("updated_count"),
            "deleted_count": payload.get("deleted_count"),
            "moved_count": payload.get("moved_count"),
            "source_tool_name": source_tool_name,
            "request_kind": payload.get("request_kind"),
        }
    elif event.name == "patch_approval_requested":
        title = "Requested patch approval" if event.ok else "Patch approval request failed"
        code = "approval.request.patch"
        params = {
            "approval_id": payload.get("approval_id"),
            "file_count": payload.get("file_count"),
        }
    elif event.name == "shell_approval_requested":
        title = "Requested shell approval" if event.ok else "Shell approval request failed"
        code = "approval.request.shell"
        params = {
            "approval_id": payload.get("approval_id"),
            "command": payload.get("command"),
            "timeout_sec": payload.get("timeout_sec"),
        }
    elif event.name == "background_teammate_approval_requested":
        title = "Requested background teammate approval" if event.ok else "Background teammate approval request failed"
        code = "approval.request.action"
        params = {
            "approval_id": payload.get("approval_id"),
            "summary": payload.get("summary"),
            "task": payload.get("task"),
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "sandbox_mode": payload.get("sandbox_mode"),
            "timeout_seconds": payload.get("timeout_seconds"),
            "task_type": payload.get("task_type") or "background_teammate",
        }
    elif event.name == "approval_list":
        title = "Listed approvals" if event.ok else "Approval listing failed"
        code = "approval.list"
        params = {
            "count": payload.get("count"),
            "status": payload.get("status"),
        }
    elif event.name == "approval_decision":
        status_text = str(payload.get("status") or "").strip().lower()
        if status_text == "approved":
            action_type = str(payload.get("action_type") or "")
            if action_type == "apply_patch":
                title = "Approved patch"
                code = "approval.decision.patch"
            elif action_type == "shell_command":
                title = "Approved command"
                code = "approval.decision.command"
            else:
                title = "Approved action"
                code = "approval.decision.action"
        elif status_text == "rejected":
            action_type = str(payload.get("action_type") or "")
            if action_type == "apply_patch":
                title = "Rejected patch"
                code = "approval.decision.patch"
            elif action_type == "shell_command":
                title = "Rejected command"
                code = "approval.decision.command"
            else:
                title = "Rejected action"
                code = "approval.decision.action"
        else:
            title = "Decided approval" if event.ok else "Approval decision failed"
            code = "approval.decision"
        params = {
            "approval_id": payload.get("approval_id"),
            "status": payload.get("status"),
            "decision_type": payload.get("decision_type"),
            "action_type": payload.get("action_type"),
            "command": payload.get("command"),
            "continuation_status": (payload.get("continuation") or {}).get("continuation_status")
            if isinstance(payload.get("continuation"), dict)
            else None,
            "continuation_attempted": (payload.get("continuation") or {}).get("continuation_attempted")
            if isinstance(payload.get("continuation"), dict)
            else None,
        }
    elif event.name == "glob_files":
        title = "Matched files" if (event.ok or tool_event_is_soft_failure(event)) else "File glob failed"
        code = "dir.search"
        params = {
            "pattern": payload.get("pattern"),
            "path": payload.get("path") or ".",
            "count": payload.get("count"),
        }
    elif event.name == "list_dir":
        title = "Listed directory" if (event.ok or tool_event_is_soft_failure(event)) else "Directory listing failed"
        code = "dir.list"
        params = {"dir_path": payload.get("dir_path") or ".", "path": payload.get("dir_path") or ".", "count": payload.get("count")}
    elif event.name == "grep_files":
        title = "Searched file paths" if (event.ok or tool_event_is_soft_failure(event)) else "File path search failed"
        code = "dir.search"
        params = {"pattern": payload.get("pattern"), "path": payload.get("path") or ".", "count": payload.get("count")}
    elif event.name == "read_file":
        title = "Read file" if (event.ok or tool_event_is_soft_failure(event)) else "File read failed"
        code = "file.read"
        params = {"file_path": payload.get("file_path") or payload.get("path"), "path": payload.get("path") or payload.get("file_path")}
    elif event.name == "file_list":
        title = "Listed files" if (event.ok or tool_event_is_soft_failure(event)) else "File listing failed"
        code = "file.list"
        params = {"path": payload.get("path"), "count": payload.get("count")}
    elif event.name == "file_search":
        title = "Searched files" if (event.ok or tool_event_is_soft_failure(event)) else "File search failed"
        code = "file.search"
        params = {"query": payload.get("query"), "path": payload.get("path"), "count": payload.get("count")}
    elif event.name == "file_read":
        title = "Read file" if (event.ok or tool_event_is_soft_failure(event)) else "File read failed"
        code = "file.read"
        params = {"path": payload.get("path")}
    elif event.name == "list_conversations":
        title = "Listed visible conversations" if event.ok else "Failed to list visible conversations"
        code = "conversation.list"
        params = {"count": payload.get("count"), "selected": (payload.get("selected") or {}).get("name")}
    elif event.name == "select_conversation":
        target = (
            (payload.get("selected_after") or {}).get("name")
            or (payload.get("target") or {}).get("name")
            or payload.get("selected_conversation")
            or "conversation"
        )
        title = f"Selected {target}" if event.ok else f"Failed to select {target}"
        code = "conversation.select"
        params = {"target": target}
    elif event.name == "read_recent_messages":
        name = payload.get("conversation_name") or selected_conversation or "current conversation"
        title = f"Read recent messages from {name}" if event.ok else f"Failed to read messages from {name}"
        code = "conversation.read_recent"
        params = {"conversation_name": name}
    elif event.name == "summarize_conversation":
        name = payload.get("conversation_name") or selected_conversation or "current conversation"
        title = f"Summarized {name}" if event.ok else f"Failed to summarize {name}"
        code = "conversation.summarize"
        params = {"conversation_name": name}
    elif event.name == "draft_reply":
        name = payload.get("conversation_name") or selected_conversation or "current conversation"
        title = f"Drafted reply for {name}" if event.ok else f"Failed to draft reply for {name}"
        code = "conversation.draft_reply"
        params = {"conversation_name": name}
    elif event.name == "prepare_send":
        name = payload.get("conversation_name") or selected_conversation or "current conversation"
        title = f"Prepared reply for {name}" if event.ok else f"Prepare-send blocked for {name}"
        code = "conversation.prepare_send"
        params = {"conversation_name": name}
    elif event.name == "send_reply":
        name = payload.get("conversation_name") or selected_conversation or "current conversation"
        title = f"Sent reply to {name}" if event.ok else f"Send blocked for {name}"
        code = "conversation.send_reply"
        params = {"conversation_name": name}
    elif event.name == "download_and_understand_office_attachments":
        title = "Analyzed visible attachments" if event.ok else "Failed to analyze visible attachments"
        code = "office.attachments.analyze"
    elif event.name == "office_run":
        skill = payload.get("skill_name") or payload.get("skill") or "office skill"
        title = f"Ran {skill}" if event.ok else f"Failed to run {skill}"
        code = "office.skill.run"
        params = {"skill_name": skill}
    elif event.name == "office_skills":
        title = "Listed office skills" if event.ok else "Failed to list office skills"
        code = "office.skills.list"
    elif event.name == "web_search":
        title = _web_search_activity_title(event)
        kind = "web"
        code = "web.search"
        params = {
            "query": payload.get("query"),
            "count": payload.get("count"),
            "backend": _web_search_backend_variant(payload),
            "web_search_outcome": payload.get("web_search_outcome"),
            "search_dispatched": payload.get("search_dispatched"),
            "search_results_received": payload.get("search_results_received"),
        }
    elif event.name == "view_image":
        title = "Viewed image" if event.ok else "View image failed"
        code = "image.view"
        params = {"path": payload.get("path"), "format": payload.get("format"), "size_bytes": payload.get("size_bytes")}
    elif event.name == "web_fetch":
        title = "Fetched webpage" if event.ok else "Webpage fetch failed"
        kind = "web"
        code = "web.fetch"
    elif event.name == "open":
        title = "Opened webpage" if event.ok else "Open webpage failed"
        kind = "web"
        code = "web.open"
    elif event.name == "click":
        title = "Opened clicked link" if event.ok else "Click failed"
        kind = "web"
        code = "web.click"
    elif event.name == "find":
        title = "Found text in page" if event.ok else "Find in page failed"
        kind = "web"
        code = "web.find"
    elif event.name.startswith("browser"):
        title, detail, kind = _browser_activity_repr(event)
        detail = _append_elapsed_detail(detail, payload)
        if title.startswith("Browser errors"):
            code = "browser.errors"
        elif title.startswith("Browser requests"):
            code = "browser.requests"
        elif title.startswith("Browser console"):
            code = "browser.console"
        else:
            code = f"browser.{event.name.removeprefix('browser_')}"
    elif event.name == "policy_doc_import":
        title = "Imported policy documents" if event.ok else "Failed to import policy documents"
        code = "policy.import"
    elif event.name == "policy_doc_list":
        title = "Listed policy documents" if event.ok else "Failed to list policy documents"
        code = "policy.list"
    elif event.name == "policy_doc_search":
        title = "Searched policy documents" if event.ok else "Failed to search policy documents"
        code = "policy.search"
    elif event.name == "policy_doc_read":
        title = "Read policy Markdown" if event.ok else "Failed to read policy Markdown"
        code = "policy.read"
    elif event.name == "bootstrap":
        title = "Initialized local toolchain" if event.ok else "Initialization failed"
        code = "bootstrap.initialize"
    elif event.name == "refresh_owner_profile":
        title = "Refreshed owner profile" if event.ok else "Failed to refresh owner profile"
        code = "owner_profile.refresh"
    else:
        title = event.summary or event.name
        code = f"tool.{event.name}"

    return [ActivityEvent(title=title, status=status, detail=detail, kind=kind, code=code, params=params)]


def activity_detail_for_event(event: ToolEvent) -> str:
    return _activity_detail_for_event(event)


def detail_for_event(event: ToolEvent) -> str:
    return _detail_for_event(event)
