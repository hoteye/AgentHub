from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ActivityEvent, activity_code
from cli.agent_cli.ui.transcript_structured_runtime import (
    activity_payload,
    exploration_activity_payload,
    todo_payload,
)


def activity_entry(
    transcript_entry_cls: Any,
    event: ActivityEvent,
    *,
    should_skip_activity_entry_fn: Any,
    format_plan_steps_fn: Any,
    format_activity_detail_lines_fn: Any,
    normalized_activity_detail_fn: Any,
    format_web_activity_lines_fn: Any,
    exploration_detail_item_fn: Any,
    format_exploration_activity_lines_fn: Any,
    format_file_activity_lines_fn: Any,
    format_patch_activity_lines_fn: Any,
    format_activity_summary_fn: Any,
    activity_key_fn: Any,
    uses_compact_web_search_cell_fn: Any,
    web_search_activity_lines_fn: Any,
):
    if should_skip_activity_entry_fn(event):
        return None
    if event.kind == "command_output":
        return None
    render_mode = "plain"
    if event.kind == "plan":
        render_mode = "todo_list"
        steps = format_plan_steps_fn(str(event.detail or ""))
        lines = ["• Todo List"]
        if steps:
            first_step, *rest_steps = steps
            lines.append(f"  └ {first_step}")
            lines.extend(f"    {step}" for step in rest_steps)
        else:
            lines.append("  └ (no steps provided)")
        return transcript_entry_cls(
            kind="activity",
            layer="commentary",
            lines=lines,
            status=event.status,
            structured=todo_payload(
                todos=[{"text": step, "completed": False} for step in steps],
                source="plan_activity",
                state=str(event.status or "info"),
            ),
            render_mode=render_mode,
        )
    if event.kind == "command_output":
        lines = format_activity_detail_lines_fn(
            str(event.title or ""), stream=str(event.detail or "stdout")
        )
        if not lines:
            return None
        return transcript_entry_cls(kind="activity", layer="tool", lines=lines, status=event.status)
    detail_text = normalized_activity_detail_fn(event)
    normalized_event = ActivityEvent(
        title=event.title,
        status=event.status,
        detail=detail_text,
        kind=event.kind,
        code=event.code,
        params=dict(event.params or {}),
    )
    exploration_details: list[tuple[str, str]] | None = None
    full_lines = None
    if event.kind == "web":
        if activity_code(event) == "web.search":
            if uses_compact_web_search_cell_fn(normalized_event):
                lines = web_search_activity_lines_fn(normalized_event)
                full_lines = list(lines)
            else:
                full_lines = format_web_activity_lines_fn(normalized_event)
                lines = format_web_activity_lines_fn(normalized_event, max_search_results=0)
            render_mode = "web_search"
        else:
            full_lines = format_web_activity_lines_fn(normalized_event)
            lines = format_web_activity_lines_fn(normalized_event, max_search_results=0)
    elif activity_code(event) in {
        "dir.list",
        "dir.search",
        "file.read",
        "file.list",
        "file.search",
        "image.view",
        "tool.run",
    }:
        detail_item = exploration_detail_item_fn(normalized_event)
        lines = format_exploration_activity_lines_fn(normalized_event)
        if lines is not None and detail_item is not None:
            exploration_details = [detail_item]
        if lines is None:
            lines = format_file_activity_lines_fn(normalized_event)
    elif activity_code(event).startswith("approval.") or activity_code(event) == "patch.apply":
        lines = format_patch_activity_lines_fn(normalized_event)
    else:
        summary = format_activity_summary_fn(event)
        detail_lines = format_activity_detail_lines_fn(detail_text) if detail_text else []
        lines = [summary] if summary else []
        lines.extend(detail_lines)
    if not lines:
        return None
    if event.kind == "web":
        layer = "web"
    elif event.kind in {"tool", "command"}:
        layer = "tool"
    else:
        layer = "commentary"
    return transcript_entry_cls(
        kind="activity",
        layer=layer,
        lines=lines,
        status=event.status,
        activity_key=activity_key_fn(event),
        exploration_details=exploration_details,
        expanded_lines=full_lines if event.kind == "web" and full_lines != lines else None,
        render_mode=render_mode,
        structured=(
            exploration_activity_payload(normalized_event, details=exploration_details)
            if exploration_details
            else activity_payload(normalized_event, detail_text=detail_text)
        ),
    )


def activity_key(event: ActivityEvent, *, strip_activity_prefix_fn: Any) -> str | None:
    code = activity_code(event)
    title = str(event.title or "").strip()
    if not title and not code:
        return None
    if code == "command.run" or event.kind == "command":
        params = event.params or {}
        call_id = str(params.get("call_id") or params.get("id") or "").strip()
        if call_id:
            # Reuse the canonical turn-item key so live command activities can collapse into the
            # later command_execution transcript cell instead of leaving a duplicate failure row.
            return f"turn_item:{call_id}"
        subject = str(params.get("command") or "").strip()
        if not subject:
            subject = (
                strip_activity_prefix_fn(title, "Running ")
                if event.status == "running"
                else strip_activity_prefix_fn(
                    strip_activity_prefix_fn(title, "Ran "), "Command failed: "
                )
            )
        return f"command:{subject.lower()}"
    if event.status == "running":
        subject = str(
            (event.params or {}).get("tool_name") or ""
        ).strip() or strip_activity_prefix_fn(title, "Running ")
        return f"{event.kind}:{subject.lower()}"
    return None


def should_include_activity_detail(event: ActivityEvent) -> bool:
    if not str(event.detail or "").strip():
        return False
    if event.status == "error":
        return True
    if event.kind == "interrupt":
        return True
    if event.kind == "command":
        return event.status != "running"
    if event.kind != "tool":
        return True
    code = activity_code(event)
    if code in {
        "policy.import",
        "policy.list",
        "policy.search",
        "policy.read",
        "office.skills.list",
        "bootstrap.initialize",
        "owner_profile.refresh",
    }:
        return False
    return True


def should_skip_activity_entry(event: ActivityEvent) -> bool:
    if event.status == "error":
        return False
    code = activity_code(event)
    if code == "conversation.list":
        return True
    return code.startswith("approval.request.")


def normalized_activity_detail(
    event: ActivityEvent, *, should_include_activity_detail_fn: Any
) -> str:
    if not should_include_activity_detail_fn(event):
        return ""
    raw = str(event.detail or "").strip()
    if not raw:
        return ""
    if event.status == "error":
        return raw
    code = activity_code(event)
    if event.kind == "command" and event.status == "success":
        return ""
    if code == "conversation.read_recent":
        return ""
    if code == "conversation.summarize":
        return ""
    if code == "conversation.draft_reply":
        return ""
    if code == "conversation.prepare_send":
        risk_lines = [line.strip() for line in raw.splitlines() if line.strip().startswith("risk ")]
        return "\n".join(risk_lines)
    return raw


__all__ = [
    "activity_entry",
    "activity_key",
    "normalized_activity_detail",
    "should_include_activity_detail",
    "should_skip_activity_entry",
]
