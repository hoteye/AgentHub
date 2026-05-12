from __future__ import annotations

from typing import Any

from cli.agent_cli.command_execution_summary_runtime import populate_command_execution_summary_dicts
from cli.agent_cli.models import ActivityEvent
from cli.agent_cli.models_turn_events import canonical_command_execution_item_from_provider_shell_payload


def reference_visible_reasoning_text(text: str) -> str:
    content = str(text or "").strip()
    if not content:
        return ""
    open_index = content.find("**")
    if open_index < 0:
        return ""
    close_index = content.find("**", open_index + 2)
    if close_index < 0:
        return ""
    return content[close_index + 2 :].strip()


def native_web_search_query_text(item: dict[str, object]) -> str:
    action = item.get("action")
    if isinstance(action, dict):
        query = str(action.get("query") or "").strip()
        if query:
            return query
        queries = action.get("queries")
        if isinstance(queries, list):
            for entry in queries:
                text = str(entry or "").strip()
                if text:
                    return text
    return str(item.get("query") or "").strip()


def native_web_search_activity(event_type: str, item: dict[str, object]) -> ActivityEvent:
    status_text = str(item.get("status") or "").strip().lower()
    query_text = native_web_search_query_text(item)
    search_phase = str(item.get("search_phase") or "").strip().lower()
    is_running = event_type in {"item.started", "item.updated"} or status_text in {"in_progress", "running"}
    ok = status_text not in {"failed", "error"}
    return ActivityEvent(
        title="Searching the web" if is_running else ("Native web search" if ok else "Native web search failed"),
        status="running" if is_running else ("success" if ok else "error"),
        detail=f"query={query_text}" if query_text else "",
        kind="web",
        code="web.search",
        params={
            "tool_name": "web_search_call",
            "query": query_text,
            "provider_native": True,
            "web_search_outcome": search_phase,
        },
    )


def expert_review_focus_text(value: object) -> str:
    if isinstance(value, (list, tuple)):
        items = [str(item or "").strip() for item in value if str(item or "").strip()]
        return ", ".join(items)
    return str(value or "").strip()


def expert_review_default_title(phase: str) -> str:
    if phase == "requested":
        return "Expert review requested."
    if phase == "running":
        return "Expert review running."
    if phase == "failed":
        return "Expert review failed."
    return "Expert review completed."


def expert_review_activity(event_type: str, item: dict[str, object]) -> ActivityEvent:
    phase = str(item.get("phase") or "").strip().lower()
    status_text = str(item.get("status") or "").strip().lower()
    summary = str(item.get("summary") or "").strip()
    request = item.get("request")
    reviewer = item.get("reviewer")
    outcome = item.get("outcome")
    request_mapping = dict(request) if isinstance(request, dict) else {}
    reviewer_mapping = dict(reviewer) if isinstance(reviewer, dict) else {}
    outcome_mapping = dict(outcome) if isinstance(outcome, dict) else {}

    reviewer_provider = str(reviewer_mapping.get("provider") or "").strip()
    reviewer_model = str(reviewer_mapping.get("model") or "").strip()
    reviewer_name = " / ".join(part for part in (reviewer_provider, reviewer_model) if part)
    scope = str(request_mapping.get("scope") or "").strip()
    focus = expert_review_focus_text(request_mapping.get("focus"))
    verdict = str(outcome_mapping.get("verdict") or "").strip()
    error_code = str(outcome_mapping.get("error_code") or "").strip()
    finding_count = outcome_mapping.get("finding_count")
    outcome_status = str(outcome_mapping.get("status") or "").strip().lower()

    is_running = (
        event_type in {"item.started", "item.updated"}
        or status_text in {"in_progress", "running"}
        or phase in {"requested", "running"}
    )
    is_error = (
        not is_running
        and (
            status_text in {"failed", "error"}
            or outcome_status in {"failed", "error"}
            or phase == "failed"
            or bool(error_code)
        )
    )

    detail_lines: list[str] = []
    if reviewer_name:
        detail_lines.append(f"reviewer={reviewer_name}")
    if scope:
        detail_lines.append(f"scope={scope}")
    if focus:
        detail_lines.append(f"focus={focus}")
    verdict_line_parts: list[str] = []
    if verdict:
        verdict_line_parts.append(f"verdict={verdict}")
    if finding_count not in {None, ""}:
        verdict_line_parts.append(f"findings={finding_count}")
    if verdict_line_parts:
        detail_lines.append(" | ".join(verdict_line_parts))
    if error_code:
        detail_lines.append(f"error={error_code}")

    return ActivityEvent(
        title=summary or expert_review_default_title(phase),
        status="running" if is_running else ("error" if is_error else "success"),
        detail="\n".join(detail_lines),
        kind="tool",
        code="expert_review",
        params={
            "tool_name": "expert_review",
            "phase": phase,
            "scope": scope,
            "focus": focus,
            "verdict": verdict,
            "finding_count": finding_count,
            "reviewer_provider": reviewer_provider,
            "reviewer_model": reviewer_model,
            "call_id": str(item.get("call_id") or "").strip(),
            "id": str(item.get("id") or "").strip(),
        },
    )


def observable_turn_item(app: Any, item: dict[str, object]) -> dict[str, object]:
    canonical = canonical_command_execution_item_from_provider_shell_payload(
        dict(item),
        item_id=str(item.get("call_id") or item.get("id") or "").strip() or "command_execution",
    )
    if canonical is None:
        if str(item.get("type") or "").strip() == "command_execution":
            return populate_command_execution_summary_dicts(dict(item))
        return item
    command_state = getattr(app, "_live_command_execution_commands", None)
    if not isinstance(command_state, dict):
        command_state = {}
        setattr(app, "_live_command_execution_commands", command_state)
    item_key = str(canonical.get("id") or canonical.get("call_id") or "").strip()
    command_text = str(canonical.get("command") or "").strip()
    if command_text and item_key:
        command_state[item_key] = command_text
    elif item_key:
        remembered = str(command_state.get(item_key) or "").strip()
        if remembered:
            canonical = {**canonical, "command": remembered}
    return populate_command_execution_summary_dicts(canonical)
