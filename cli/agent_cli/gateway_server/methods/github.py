from __future__ import annotations

from typing import Any

from cli.agent_cli.gateway_api.webhook_api import build_webhook_event, parse_webhook_body
from shared.integrations import github_delivery_id, github_source_id, normalize_github_event_type

from . import GatewayMethodFamily


def _first_text(params: dict[str, Any], *names: str) -> str:
    for name in names:
        value = params.get(name)
        if value is None:
            continue
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
    return ""


def _split_repo(params: dict[str, Any]) -> tuple[str, str]:
    owner = _first_text(params, "owner")
    repo = _first_text(params, "repo")
    if owner and repo and "/" not in repo:
        return owner, repo
    repo_text = owner if owner and "/" in owner and not repo else repo
    if "/" not in repo_text:
        raise ValueError("owner/repo is required")
    repo_owner, repo_name = repo_text.split("/", 1)
    repo_owner = repo_owner.strip()
    repo_name = repo_name.strip()
    if not repo_owner or not repo_name:
        raise ValueError("owner/repo is required")
    return repo_owner, repo_name


def _tool_event_result(*, method: str, tool_event: Any) -> dict[str, Any]:
    payload = dict(getattr(tool_event, "payload", {}) or {})
    status = str(
        payload.get("status")
        or payload.get("mode")
        or ("ok" if bool(getattr(tool_event, "ok", False)) else "failed")
    ).strip()
    return {
        "ok": bool(getattr(tool_event, "ok", False)),
        "method": method,
        "status": status,
        "summary": str(getattr(tool_event, "summary", "") or ""),
        "traceId": str(payload.get("trace_id") or payload.get("correlation_id") or "").strip() or None,
        "actionRequest": dict(payload.get("action_request") or {}) or None,
        "approvalTicket": dict(payload.get("approval_ticket") or {}) or None,
        "auditRecords": list(payload.get("audit_records") or []),
        "request": dict(payload.get("request") or {}) or None,
        "reason": str(payload.get("reason") or "").strip() or None,
        "details": payload,
    }


def _github_webhook_ingest(**kwargs: Any) -> dict[str, Any]:
    params = dict(kwargs.get("params") or {})
    runtime = kwargs["runtime"]
    raw_body = params.get("rawBody")
    if not isinstance(raw_body, str) or not raw_body.strip():
        raise ValueError("params.rawBody must be a non-empty string")
    headers = params.get("headers")
    if headers is None or not isinstance(headers, dict):
        raise ValueError("params.headers must be an object")
    payload = parse_webhook_body(raw_body)
    event_type = normalize_github_event_type(headers=headers, payload=payload)
    event = build_webhook_event(
        connector_key=_first_text(params, "connectorKey", "connector_key") or "github_webhook",
        event_type=event_type,
        payload=payload,
        headers=headers,
        source_id=github_source_id(payload),
        correlation_id=github_delivery_id(headers),
    )
    result = runtime.dispatch_gateway_event(event)
    decision = result["decision"]
    workflow_run = result.get("workflow_run")
    return {
        "ok": True,
        "method": "github.webhook.ingest",
        "status": "accepted",
        "event": event.to_dict(),
        "decision": {
            "targetKind": getattr(decision, "target_kind", None),
            "pluginName": getattr(decision, "plugin_name", None),
            "workflowName": getattr(decision, "workflow_name", None),
            "reason": getattr(decision, "reason", None),
        },
        "workflowRun": workflow_run.to_dict() if workflow_run is not None else None,
        "auditRecords": [item.to_dict() if hasattr(item, "to_dict") else dict(item or {}) for item in result.get("audit_records") or []],
    }


def _github_actions_dispatch(**kwargs: Any) -> dict[str, Any]:
    from plugins.github_phase1 import tools as github_tools

    params = dict(kwargs.get("params") or {})
    runtime = kwargs["runtime"]
    owner, repo = _split_repo(params)
    workflow_id = _first_text(params, "workflowId", "workflow_id")
    ref = _first_text(params, "ref")
    if not workflow_id:
        raise ValueError("workflowId is required")
    if not ref:
        raise ValueError("ref is required")
    inputs = params.get("inputs")
    if inputs is not None and not isinstance(inputs, dict):
        raise ValueError("inputs must be an object when provided")
    event = github_tools.github_workflow_dispatch(
        owner=owner,
        repo=repo,
        workflow_id=workflow_id,
        ref=ref,
        inputs=dict(inputs or {}),
        token_env=_first_text(params, "tokenEnv", "token_env") or "GITHUB_TOKEN",
        api_base_url=_first_text(params, "apiBaseUrl", "api_base_url") or "https://api.github.com",
        correlation_id=_first_text(params, "correlationId", "correlation_id") or None,
        runtime=runtime,
    )
    return _tool_event_result(method="github.actions.dispatch", tool_event=event)


def _github_issues_create(**kwargs: Any) -> dict[str, Any]:
    from plugins.github_phase1 import tools as github_tools

    params = dict(kwargs.get("params") or {})
    runtime = kwargs["runtime"]
    owner, repo = _split_repo(params)
    title = _first_text(params, "title")
    if not title:
        raise ValueError("title is required")
    event = github_tools.github_issue_create(
        owner=owner,
        repo=repo,
        title=title,
        body=_first_text(params, "body"),
        token_env=_first_text(params, "tokenEnv", "token_env") or "GITHUB_TOKEN",
        api_base_url=_first_text(params, "apiBaseUrl", "api_base_url") or "https://api.github.com",
        correlation_id=_first_text(params, "correlationId", "correlation_id") or None,
        runtime=runtime,
    )
    return _tool_event_result(method="github.issues.create", tool_event=event)


def _github_comments_create(**kwargs: Any) -> dict[str, Any]:
    from plugins.github_phase1 import tools as github_tools

    params = dict(kwargs.get("params") or {})
    runtime = kwargs["runtime"]
    owner, repo = _split_repo(params)
    issue_number_raw = params.get("issueNumber", params.get("issue_number"))
    if issue_number_raw is None:
        raise ValueError("issueNumber is required")
    body = _first_text(params, "body")
    if not body:
        raise ValueError("body is required")
    event = github_tools.github_issue_comment(
        owner=owner,
        repo=repo,
        issue_number=int(issue_number_raw),
        body=body,
        token_env=_first_text(params, "tokenEnv", "token_env") or "GITHUB_TOKEN",
        api_base_url=_first_text(params, "apiBaseUrl", "api_base_url") or "https://api.github.com",
        correlation_id=_first_text(params, "correlationId", "correlation_id") or None,
        runtime=runtime,
        event_id=_first_text(params, "eventId", "event_id") or None,
        workflow_run_id=_first_text(params, "workflowRunId", "workflow_run_id") or None,
        metadata=dict(params.get("metadata") or {}) if isinstance(params.get("metadata"), dict) else None,
    )
    return _tool_event_result(method="github.comments.create", tool_event=event)


_GITHUB_METHOD_SUMMARIES = {
    "github.webhook.ingest": "Ingest a GitHub webhook into the gateway event pipeline.",
    "github.actions.dispatch": "Create an approval-gated GitHub workflow dispatch action request.",
    "github.issues.create": "Create an approval-gated GitHub issue action request.",
    "github.comments.create": "Create an approval-gated GitHub issue comment action request.",
}

GITHUB_FAMILY = GatewayMethodFamily(
    family_name="github",
    methods=tuple(_GITHUB_METHOD_SUMMARIES.keys()),
    handlers={
        "github.webhook.ingest": _github_webhook_ingest,
        "github.actions.dispatch": _github_actions_dispatch,
        "github.issues.create": _github_issues_create,
        "github.comments.create": _github_comments_create,
    },
)

github_handlers = GITHUB_FAMILY.handlers

__all__ = [
    "GITHUB_FAMILY",
    "github_handlers",
]
