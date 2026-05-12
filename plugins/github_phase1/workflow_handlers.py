from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from cli.agent_cli.models import ToolEvent
from plugins.github_phase1 import tools as github_tools


def _tool_event_to_dict(event: ToolEvent) -> dict[str, Any]:
    return {
        "name": str(event.name or "").strip(),
        "ok": bool(event.ok),
        "summary": str(event.summary or "").strip(),
        "payload": dict(event.payload or {}),
    }


def _event_trace_id(event: Any) -> str:
    trace_id = str(getattr(event, "trace_id", "") or "").strip()
    if trace_id:
        return trace_id
    return f"trace_{uuid4().hex[:12]}"


def _event_correlation_id(event: Any) -> str:
    correlation_id = str(getattr(event, "correlation_id", "") or "").strip()
    if correlation_id:
        return correlation_id
    return _event_trace_id(event)


def _event_payload(event: Any) -> dict[str, Any]:
    payload = getattr(event, "payload", {})
    if isinstance(payload, dict):
        return payload
    return {}


def _parse_repo(payload: dict[str, Any]) -> tuple[str, str]:
    repository = payload.get("repository")
    if not isinstance(repository, dict):
        return "", ""
    full_name = str(repository.get("full_name") or "").strip()
    if "/" not in full_name:
        return "", ""
    owner, repo = full_name.split("/", 1)
    owner = owner.strip()
    repo = repo.strip()
    if not owner or not repo:
        return "", ""
    return owner, repo


def _parse_issue_number(payload: dict[str, Any]) -> int | None:
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        return None
    try:
        issue_number = int(issue.get("number"))
    except (TypeError, ValueError):
        return None
    return issue_number if issue_number > 0 else None


def _issue_evidence_refs(payload: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    issue = payload.get("issue")
    if isinstance(issue, dict):
        issue_url = str(issue.get("html_url") or "").strip()
        if issue_url:
            refs.append(issue_url)
    repository = payload.get("repository")
    if isinstance(repository, dict):
        repo_url = str(repository.get("html_url") or "").strip()
        if repo_url:
            refs.append(repo_url)
    return refs


def _default_token_env() -> str:
    if str(os.environ.get("PM_GITHUB_TOKEN") or "").strip():
        return "PM_GITHUB_TOKEN"
    if str(os.environ.get("GITHUB_TOKEN") or "").strip():
        return "GITHUB_TOKEN"
    return "PM_GITHUB_TOKEN"


def _followup_comment_body(*, trace_id: str, issue_title: str, compliance_route: bool) -> str:
    route_text = "compliance" if compliance_route else "general"
    safe_title = str(issue_title or "").strip() or "(no title)"
    return (
        f"AgentHub workflow received this issue ({route_text} route).\n"
        f"Title: {safe_title}\n"
        f"trace_id: {trace_id}\n"
        "A maintainer review is requested."
    )


def _issue_opened_result(
    *,
    event: Any,
    decision: Any,
    workflow_run: Any,
    runtime: Any | None,
    compliance_route: bool,
) -> dict[str, Any]:
    payload = _event_payload(event)
    trace_id = _event_trace_id(event)
    correlation_id = _event_correlation_id(event)
    owner, repo = _parse_repo(payload)
    issue_number = _parse_issue_number(payload)
    evidence_refs = _issue_evidence_refs(payload)
    workflow_name = str(getattr(decision, "workflow_name", "") or "").strip()
    event_id = str(getattr(event, "event_id", "") or "").strip()
    workflow_run_id = str(getattr(workflow_run, "workflow_run_id", "") or "").strip()
    route_text = "compliance" if compliance_route else "general"
    issue = payload.get("issue")
    issue_title = str(issue.get("title") or "").strip() if isinstance(issue, dict) else ""
    reasoning_summary = f"routed GitHub issue to {route_text} workflow and proposed one approval-gated issue comment"

    if not owner or not repo or issue_number is None:
        return {
            "status": "invalid_event",
            "reasoning_summary": "missing repository or issue number in webhook payload; no action requested",
            "evidence_refs": evidence_refs,
            "action_requests": [],
            "trace_id": trace_id,
            "correlation_id": correlation_id,
            "event_id": event_id,
            "workflow_run_id": workflow_run_id,
            "workflow_name": workflow_name,
        }

    if runtime is None:
        return {
            "status": "blocked",
            "reasoning_summary": "runtime is unavailable; cannot request approval-gated GitHub follow-up action",
            "evidence_refs": evidence_refs,
            "action_requests": [],
            "trace_id": trace_id,
            "correlation_id": correlation_id,
            "event_id": event_id,
            "workflow_run_id": workflow_run_id,
            "workflow_name": workflow_name,
        }

    tool_event = github_tools.github_issue_comment(
        owner=owner,
        repo=repo,
        issue_number=issue_number,
        body=_followup_comment_body(
            trace_id=trace_id,
            issue_title=issue_title,
            compliance_route=compliance_route,
        ),
        token_env=_default_token_env(),
        correlation_id=trace_id,
        runtime=runtime,
        event_id=event_id or None,
        workflow_run_id=workflow_run_id or None,
        metadata={
            "workflow_name": workflow_name,
            "reasoning_summary": reasoning_summary,
            "evidence_refs": list(evidence_refs),
        },
    )
    tool_payload = dict(tool_event.payload or {})
    action_request = tool_payload.get("action_request")
    action_requests = [dict(action_request)] if isinstance(action_request, dict) else []
    status = "approval_requested" if tool_event.ok and tool_payload.get("mode") == "approval_required" else ("ok" if tool_event.ok else "failed")
    return {
        "status": status,
        "reasoning_summary": reasoning_summary,
        "evidence_refs": evidence_refs,
        "action_requests": action_requests,
        "trace_id": trace_id,
        "correlation_id": correlation_id,
        "event_id": event_id,
        "workflow_run_id": workflow_run_id,
        "workflow_name": workflow_name,
        "tool_event": _tool_event_to_dict(tool_event),
    }


def handle_github_issue_opened(*, event: Any, decision: Any, workflow_run: Any, runtime: Any | None = None) -> dict[str, Any]:
    return _issue_opened_result(
        event=event,
        decision=decision,
        workflow_run=workflow_run,
        runtime=runtime,
        compliance_route=False,
    )


def handle_github_compliance_issue_opened(*, event: Any, decision: Any, workflow_run: Any, runtime: Any | None = None) -> dict[str, Any]:
    return _issue_opened_result(
        event=event,
        decision=decision,
        workflow_run=workflow_run,
        runtime=runtime,
        compliance_route=True,
    )


def handle_github_issue_comment_created(*, event: Any, decision: Any, workflow_run: Any, runtime: Any | None = None) -> dict[str, Any]:
    payload = _event_payload(event)
    trace_id = _event_trace_id(event)
    correlation_id = _event_correlation_id(event)
    event_id = str(getattr(event, "event_id", "") or "").strip()
    workflow_run_id = str(getattr(workflow_run, "workflow_run_id", "") or "").strip()
    workflow_name = str(getattr(decision, "workflow_name", "") or "").strip()
    return {
        "status": "noop",
        "reasoning_summary": "issue_comment.created received; no follow-up action requested in phase 2 first slice",
        "evidence_refs": _issue_evidence_refs(payload),
        "action_requests": [],
        "trace_id": trace_id,
        "correlation_id": correlation_id,
        "event_id": event_id,
        "workflow_run_id": workflow_run_id,
        "workflow_name": workflow_name,
    }


def build_workflow_handlers(plugin_name: str = "github_phase1") -> list[dict[str, Any]]:
    return [
        {
            "workflow_name": "handle_github_compliance_issue_opened",
            "plugin_name": plugin_name,
            "description": "Handle compliance-oriented github.issues.opened events and propose one approval-gated follow-up comment.",
            "handler": handle_github_compliance_issue_opened,
        },
        {
            "workflow_name": "handle_github_issue_opened",
            "plugin_name": plugin_name,
            "description": "Handle general github.issues.opened events and propose one approval-gated follow-up comment.",
            "handler": handle_github_issue_opened,
        },
        {
            "workflow_name": "handle_github_issue_comment_created",
            "plugin_name": plugin_name,
            "description": "Handle github.issue_comment.created events as a structured no-op in phase 2 first slice.",
            "handler": handle_github_issue_comment_created,
        },
    ]
