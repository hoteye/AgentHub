from __future__ import annotations

import json
import shlex
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events
from cli.agent_cli.slash_surface import surface_usage_text


def _compact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in dict(arguments or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        compact[key] = value
    return compact


def _single_event_result(
    assistant_text: str,
    event: ToolEvent,
    *,
    tool_name: str | None = None,
    arguments: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    normalized_arguments = _compact_arguments(arguments or {})
    return CommandExecutionResult(
        assistant_text=str(assistant_text or ""),
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=str(tool_name or event.name or "").strip(),
            arguments=normalized_arguments or None,
            ok=bool(event.ok),
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        ),
    )


def _invoke_plugin_tool_result(
    runtime_obj,
    *,
    tool_name: str,
    assistant_text: str,
    arguments: dict[str, Any],
    **kwargs: Any,
) -> CommandExecutionResult:
    if runtime_obj is None:
        raise RuntimeError("runtime is required for github plugin commands")
    result_getter = getattr(getattr(runtime_obj, "tools", None), "invoke_plugin_tool_result", None)
    if callable(result_getter):
        result = result_getter(tool_name, **kwargs)
        if isinstance(result, CommandExecutionResult):
            return CommandExecutionResult(
                assistant_text=assistant_text,
                tool_events=list(result.tool_events or []),
                item_events=[dict(item) for item in list(result.item_events or []) if isinstance(item, dict)],
            )
    event = runtime_obj.tools.invoke_plugin_tool(tool_name, **kwargs)
    return _single_event_result(
        assistant_text,
        event,
        tool_name=tool_name,
        arguments=arguments,
    )


def _parse_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
    if not arg_text:
        return [], {}
    tokens = shlex.split(arg_text, posix=True)
    positionals: list[str] = []
    options: dict[str, Any] = {}
    value_keywords = {
        "repo": "repo",
        "title": "title",
        "body": "body",
        "issue-number": "issue-number",
        "labels": "labels",
        "workflow-id": "workflow-id",
        "ref": "ref",
        "inputs-json": "inputs-json",
        "token-env": "token-env",
        "api-base-url": "api-base-url",
        "correlation-id": "correlation-id",
        "approval-id": "approval-id",
        "status": "status",
        "decided-by": "decided-by",
        "decision-note": "decision-note",
    }
    index = 0
    while index < len(tokens):
        token = tokens[index]
        normalized = token[2:] if token.startswith("--") else token
        if normalized in value_keywords:
            if index + 1 >= len(tokens):
                break
            options[value_keywords[normalized]] = tokens[index + 1]
            index += 2
            continue
        positionals.append(token)
        index += 1
    return positionals, options


def _usage_text(name: str) -> str:
    return surface_usage_text(name)


def _parse_repo(value: str) -> tuple[str, str] | None:
    text = str(value or "").strip()
    if "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    owner = owner.strip()
    repo = repo.strip()
    if not owner or not repo:
        return None
    return owner, repo


def _base_kwargs(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_env": str(options.get("token-env") or "GITHUB_TOKEN").strip() or "GITHUB_TOKEN",
        "api_base_url": str(options.get("api-base-url") or "https://api.github.com").strip() or "https://api.github.com",
        "correlation_id": str(options.get("correlation-id") or "").strip() or None,
    }


def github_issue_create_command(arg_text: str, runtime=None):
    _, options = _parse_args(arg_text)
    repo_parts = _parse_repo(options.get("repo") or "")
    title = str(options.get("title") or "").strip()
    if repo_parts is None or not title:
        return f"Usage: {_usage_text('github_issue_create')}", []
    owner, repo = repo_parts
    arguments = {
        "owner": owner,
        "repo": repo,
        "title": title,
        "body": str(options.get("body") or ""),
        **_base_kwargs(options),
    }
    return _invoke_plugin_tool_result(
        runtime,
        tool_name="github_issue_create",
        assistant_text="Request GitHub issue creation.",
        arguments=arguments,
        owner=owner,
        repo=repo,
        title=title,
        body=str(options.get("body") or ""),
        runtime=runtime,
        **_base_kwargs(options),
    )


def github_issue_comment_command(arg_text: str, runtime=None):
    _, options = _parse_args(arg_text)
    repo_parts = _parse_repo(options.get("repo") or "")
    issue_number_text = str(options.get("issue-number") or "").strip()
    body = str(options.get("body") or "").strip()
    if repo_parts is None or not issue_number_text or not body:
        return f"Usage: {_usage_text('github_issue_comment')}", []
    try:
        issue_number = int(issue_number_text)
    except ValueError:
        return f"Usage: {_usage_text('github_issue_comment')}", []
    owner, repo = repo_parts
    arguments = {
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number,
        "body": body,
        **_base_kwargs(options),
    }
    return _invoke_plugin_tool_result(
        runtime,
        tool_name="github_issue_comment",
        assistant_text="Request GitHub issue comment.",
        arguments=arguments,
        owner=owner,
        repo=repo,
        issue_number=issue_number,
        body=body,
        runtime=runtime,
        **_base_kwargs(options),
    )


def github_issue_add_labels_command(arg_text: str, runtime=None):
    _, options = _parse_args(arg_text)
    repo_parts = _parse_repo(options.get("repo") or "")
    issue_number_text = str(options.get("issue-number") or "").strip()
    labels_text = str(options.get("labels") or "").strip()
    if repo_parts is None or not issue_number_text or not labels_text:
        return f"Usage: {_usage_text('github_issue_add_labels')}", []
    try:
        issue_number = int(issue_number_text)
    except ValueError:
        return f"Usage: {_usage_text('github_issue_add_labels')}", []
    labels = [item.strip() for item in labels_text.split(",") if item.strip()]
    if not labels:
        return f"Usage: {_usage_text('github_issue_add_labels')}", []
    owner, repo = repo_parts
    arguments = {
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number,
        "labels": labels,
        **_base_kwargs(options),
    }
    return _invoke_plugin_tool_result(
        runtime,
        tool_name="github_issue_add_labels",
        assistant_text="Request GitHub issue label update.",
        arguments=arguments,
        owner=owner,
        repo=repo,
        issue_number=issue_number,
        labels=labels,
        runtime=runtime,
        **_base_kwargs(options),
    )


def github_issue_close_command(arg_text: str, runtime=None):
    _, options = _parse_args(arg_text)
    repo_parts = _parse_repo(options.get("repo") or "")
    issue_number_text = str(options.get("issue-number") or "").strip()
    if repo_parts is None or not issue_number_text:
        return f"Usage: {_usage_text('github_issue_close')}", []
    try:
        issue_number = int(issue_number_text)
    except ValueError:
        return f"Usage: {_usage_text('github_issue_close')}", []
    owner, repo = repo_parts
    arguments = {
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number,
        **_base_kwargs(options),
    }
    return _invoke_plugin_tool_result(
        runtime,
        tool_name="github_issue_close",
        assistant_text="Request GitHub issue close.",
        arguments=arguments,
        owner=owner,
        repo=repo,
        issue_number=issue_number,
        runtime=runtime,
        **_base_kwargs(options),
    )


def github_workflow_dispatch_command(arg_text: str, runtime=None):
    _, options = _parse_args(arg_text)
    repo_parts = _parse_repo(options.get("repo") or "")
    workflow_id = str(options.get("workflow-id") or "").strip()
    ref = str(options.get("ref") or "").strip()
    inputs_json = str(options.get("inputs-json") or "").strip()
    if repo_parts is None or not workflow_id or not ref:
        return f"Usage: {_usage_text('github_workflow_dispatch')}", []
    try:
        inputs = json.loads(inputs_json) if inputs_json else {}
    except json.JSONDecodeError:
        return f"Usage: {_usage_text('github_workflow_dispatch')}", []
    if not isinstance(inputs, dict):
        return f"Usage: {_usage_text('github_workflow_dispatch')}", []
    owner, repo = repo_parts
    arguments = {
        "owner": owner,
        "repo": repo,
        "workflow_id": workflow_id,
        "ref": ref,
        "inputs": inputs,
        **_base_kwargs(options),
    }
    return _invoke_plugin_tool_result(
        runtime,
        tool_name="github_workflow_dispatch",
        assistant_text="Request GitHub workflow dispatch.",
        arguments=arguments,
        owner=owner,
        repo=repo,
        workflow_id=workflow_id,
        ref=ref,
        inputs=inputs,
        runtime=runtime,
        **_base_kwargs(options),
    )


def github_approval_list_command(arg_text: str, runtime=None):
    _, options = _parse_args(arg_text)
    status = str(options.get("status") or "").strip() or None
    items = runtime.list_approval_tickets(limit=20, status=status)
    payload = {
        "ok": True,
        "approval_tickets": [item.to_dict() for item in items],
        "count": len(items),
        "status": status,
    }
    event = ToolEvent(
        name="github_approval_list",
        ok=True,
        summary=f"approval tickets={len(items)}",
        payload=payload,
    )
    return _single_event_result("List GitHub approval tickets.", event, tool_name="github_approval_list", arguments={"status": status})


def _approval_decision_command(arg_text: str, runtime=None, *, approved: bool):
    _, options = _parse_args(arg_text)
    approval_id = str(options.get("approval-id") or "").strip()
    if not approval_id:
        usage = _usage_text("github_approval_approve")
        if not approved:
            usage = _usage_text("github_approval_reject")
        return f"Usage: {usage}", []
    result = runtime.decide_gateway_approval(
        approval_id,
        approved=approved,
        decided_by=str(options.get("decided-by") or "cli").strip() or "cli",
        decision_note=str(options.get("decision-note") or "").strip(),
    )
    payload = {
        "ok": True,
        "approval_ticket": result["approval_ticket"].to_dict(),
        "action_request": result["action_request"].to_dict(),
        "action_result": result["action_result"].to_dict() if result["action_result"] is not None else None,
        "audit_records": [item.to_dict() for item in result["audit_records"]],
    }
    event = ToolEvent(
        name="github_approval_approve" if approved else "github_approval_reject",
        ok=True,
        summary=(
            f"approval executed: {result['approval_ticket'].approval_id}"
            if approved
            else f"approval rejected: {result['approval_ticket'].approval_id}"
        ),
        payload=payload,
    )
    return _single_event_result(
        "Approve and execute GitHub action." if approved else "Reject GitHub action.",
        event,
        tool_name="github_approval_approve" if approved else "github_approval_reject",
        arguments={
            "approval_id": approval_id,
            "approved": approved,
            "decided_by": str(options.get("decided-by") or "cli").strip() or "cli",
            "decision_note": str(options.get("decision-note") or "").strip(),
        },
    )


def github_approval_approve_command(arg_text: str, runtime=None):
    return _approval_decision_command(arg_text, runtime=runtime, approved=True)


def github_approval_reject_command(arg_text: str, runtime=None):
    return _approval_decision_command(arg_text, runtime=runtime, approved=False)


def register_commands(registry) -> None:
    registry.add_command(
        name="github_issue_create",
        usage=_usage_text("github_issue_create"),
        description="create a GitHub issue through the Phase 1 controlled path",
        handler=github_issue_create_command,
    )
    registry.add_command(
        name="github_issue_comment",
        usage=_usage_text("github_issue_comment"),
        description="add a GitHub issue comment through the Phase 1 controlled path",
        handler=github_issue_comment_command,
    )
    registry.add_command(
        name="github_issue_add_labels",
        usage=_usage_text("github_issue_add_labels"),
        description="add labels to a GitHub issue through the Phase 1 controlled path",
        handler=github_issue_add_labels_command,
    )
    registry.add_command(
        name="github_issue_close",
        usage=_usage_text("github_issue_close"),
        description="close a GitHub issue through the Phase 1 controlled path",
        handler=github_issue_close_command,
    )
    registry.add_command(
        name="github_workflow_dispatch",
        usage=_usage_text("github_workflow_dispatch"),
        description="dispatch a GitHub Actions workflow through the Phase 1 controlled path",
        handler=github_workflow_dispatch_command,
    )
    registry.add_command(
        name="github_approval_list",
        usage=_usage_text("github_approval_list"),
        description="list pending or completed GitHub approval tickets",
        handler=github_approval_list_command,
    )
    registry.add_command(
        name="github_approval_approve",
        usage=_usage_text("github_approval_approve"),
        description="approve and execute one pending GitHub action request",
        handler=github_approval_approve_command,
    )
    registry.add_command(
        name="github_approval_reject",
        usage=_usage_text("github_approval_reject"),
        description="reject one pending GitHub action request",
        handler=github_approval_reject_command,
    )
