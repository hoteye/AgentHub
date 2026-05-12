from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import tomllib
import uuid
from typing import Any, Optional

from cli.agent_cli.models import ToolEvent
from shared.integrations import (
    HttpClient,
    build_github_issue_close_request,
    build_github_issue_comment_request,
    build_github_issue_create_request,
    build_github_issue_labels_request,
    build_github_workflow_dispatch_request,
)
from workers.actions import ActionError, ControlledActionWorker


_EPHEMERAL_GITHUB_TOKEN_ENV = "AGENTHUB_GITHUB_TOKEN_EPHEMERAL"
_PHASE1_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "github_phase1.toml"


def _tool_event(name: str, *, ok: bool, summary: str, payload: dict[str, Any]) -> ToolEvent:
    return ToolEvent(name=name, ok=bool(ok), summary=summary, payload=payload)


def _resolve_token_env(token: Optional[str], token_env: str, *, allow_ephemeral: bool) -> tuple[str, str | None]:
    explicit = str(token or "").strip()
    env_name = str(token_env or "GITHUB_TOKEN").strip() or "GITHUB_TOKEN"
    if explicit:
        if not allow_ephemeral:
            raise ActionError(f"explicit GitHub token is not allowed here; set {env_name} in the environment instead")
        return _EPHEMERAL_GITHUB_TOKEN_ENV, explicit
    env_value = str(os.environ.get(env_name) or "").strip()
    if env_value:
        return env_name, None
    raise ActionError(f"GitHub token not found; set {env_name} or pass token explicitly")


@contextmanager
def _temporary_env(name: str, value: str | None):
    if value is None:
        yield
        return
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _execute_request(name: str, request: dict[str, Any], *, http_client: HttpClient | None = None) -> ToolEvent:
    worker = ControlledActionWorker(http_client=http_client)
    try:
        result = worker.execute(request)
    except ActionError as exc:
        return _tool_event(name, ok=False, summary=str(exc), payload={"ok": False, "error": str(exc), "request": request})
    return _tool_event(name, ok=result.ok, summary=result.summary, payload=result.to_dict())


def _request_approval(
    name: str,
    *,
    runtime: Any,
    request: dict[str, Any],
    action_type: str,
    requested_by: str,
    summary: str,
    reason: str,
    event_id: str | None = None,
    workflow_run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ToolEvent:
    trace_id = str(request.get("correlation_id") or f"trace_{uuid.uuid4().hex[:12]}")
    result = runtime.request_gateway_action(
        action_type=action_type,
        connector_key="github_webhook",
        plugin_name="github_phase1",
        request_payload=request,
        requested_by=requested_by,
        trace_id=trace_id,
        event_id=event_id,
        workflow_run_id=workflow_run_id,
        approval_required=True,
        approval_summary=summary,
        approval_reason=reason,
        metadata={"provider": "github", "phase": "phase1", **dict(metadata or {})},
    )
    approval_ticket = result["approval_ticket"]
    return _tool_event(
        name,
        ok=True,
        summary=f"approval requested: {approval_ticket.approval_id}",
        payload={
            "ok": True,
            "mode": "approval_required",
            "request": request,
            "action_request": result["action_request"].to_dict(),
            "approval_ticket": approval_ticket.to_dict() if approval_ticket is not None else None,
            "audit_records": [item.to_dict() for item in result["audit_records"]],
        },
    )


def _load_phase1_config() -> dict[str, Any]:
    if not _PHASE1_CONFIG_PATH.exists():
        return {}
    try:
        return tomllib.loads(_PHASE1_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _workflow_dispatch_allowed(owner: str, repo: str, workflow_id: str) -> tuple[bool, dict[str, Any]]:
    config = _load_phase1_config()
    block = config.get("workflow_dispatch")
    if not isinstance(block, dict):
        return False, {"reason": "missing_workflow_dispatch_config"}
    default_allowlist = [
        str(item).strip()
        for item in block.get("default_allowlisted_workflow_ids") or []
        if str(item).strip()
    ]
    repo_allowlist_map = block.get("repo_allowlisted_workflow_ids")
    repo_allowlist: list[str] = []
    repo_key = f"{owner}/{repo}"
    if isinstance(repo_allowlist_map, dict):
        repo_allowlist = [
            str(item).strip()
            for item in (repo_allowlist_map.get(repo_key) or [])
            if str(item).strip()
        ]
    allowlist = repo_allowlist or default_allowlist
    if not allowlist:
        return False, {"reason": "workflow_allowlist_empty", "repo": repo_key}
    normalized = str(workflow_id or "").strip()
    allowed = normalized in allowlist
    return allowed, {
        "reason": "workflow_not_allowlisted" if not allowed else "workflow_allowlisted",
        "repo": repo_key,
        "workflow_id": normalized,
        "allowlist": allowlist,
    }


def github_issue_create(
    *,
    owner: str,
    repo: str,
    title: str,
    body: str = "",
    token: str | None = None,
    token_env: str = "GITHUB_TOKEN",
    api_base_url: str = "https://api.github.com",
    correlation_id: str | None = None,
    http_client: HttpClient | None = None,
    runtime: Any | None = None,
) -> ToolEvent:
    token_env_name, ephemeral_token = _resolve_token_env(token, token_env, allow_ephemeral=True)
    request = build_github_issue_create_request(
        owner=owner,
        repo=repo,
        title=title,
        body=body,
        token_env=token_env_name,
        api_base_url=api_base_url,
        correlation_id=correlation_id,
    )
    if runtime is not None:
        if ephemeral_token is not None:
            raise ActionError("explicit GitHub token is not allowed for approval-gated requests; use token_env")
        return _request_approval(
            "github_issue_create",
            runtime=runtime,
            request=request,
            action_type="github.issue.create",
            requested_by="cli.github_issue_create",
            summary=f"Approve GitHub issue create for {owner}/{repo}",
            reason=f"Create GitHub issue '{title}' in {owner}/{repo}",
        )
    with _temporary_env(token_env_name, ephemeral_token):
        return _execute_request("github_issue_create", request, http_client=http_client)


def github_issue_comment(
    *,
    owner: str,
    repo: str,
    issue_number: int,
    body: str,
    token: str | None = None,
    token_env: str = "GITHUB_TOKEN",
    api_base_url: str = "https://api.github.com",
    correlation_id: str | None = None,
    http_client: HttpClient | None = None,
    runtime: Any | None = None,
    event_id: str | None = None,
    workflow_run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ToolEvent:
    token_env_name, ephemeral_token = _resolve_token_env(token, token_env, allow_ephemeral=True)
    request = build_github_issue_comment_request(
        owner=owner,
        repo=repo,
        issue_number=int(issue_number),
        body=body,
        token_env=token_env_name,
        api_base_url=api_base_url,
        correlation_id=correlation_id,
    )
    if runtime is not None:
        if ephemeral_token is not None:
            raise ActionError("explicit GitHub token is not allowed for approval-gated requests; use token_env")
        return _request_approval(
            "github_issue_comment",
            runtime=runtime,
            request=request,
            action_type="github.issue.comment",
            requested_by="cli.github_issue_comment",
            summary=f"Approve GitHub issue comment for {owner}/{repo}#{int(issue_number)}",
            reason=f"Comment on GitHub issue {owner}/{repo}#{int(issue_number)}",
            event_id=event_id,
            workflow_run_id=workflow_run_id,
            metadata=metadata,
        )
    with _temporary_env(token_env_name, ephemeral_token):
        return _execute_request("github_issue_comment", request, http_client=http_client)


def github_issue_add_labels(
    *,
    owner: str,
    repo: str,
    issue_number: int,
    labels: list[str],
    token: str | None = None,
    token_env: str = "GITHUB_TOKEN",
    api_base_url: str = "https://api.github.com",
    correlation_id: str | None = None,
    http_client: HttpClient | None = None,
    runtime: Any | None = None,
) -> ToolEvent:
    token_env_name, ephemeral_token = _resolve_token_env(token, token_env, allow_ephemeral=True)
    request = build_github_issue_labels_request(
        owner=owner,
        repo=repo,
        issue_number=int(issue_number),
        labels=list(labels),
        token_env=token_env_name,
        api_base_url=api_base_url,
        correlation_id=correlation_id,
    )
    if runtime is not None:
        if ephemeral_token is not None:
            raise ActionError("explicit GitHub token is not allowed for approval-gated requests; use token_env")
        return _request_approval(
            "github_issue_add_labels",
            runtime=runtime,
            request=request,
            action_type="github.issue.labels.add",
            requested_by="cli.github_issue_add_labels",
            summary=f"Approve GitHub label update for {owner}/{repo}#{int(issue_number)}",
            reason=f"Add labels to GitHub issue {owner}/{repo}#{int(issue_number)}",
        )
    with _temporary_env(token_env_name, ephemeral_token):
        return _execute_request("github_issue_add_labels", request, http_client=http_client)


def github_issue_close(
    *,
    owner: str,
    repo: str,
    issue_number: int,
    token: str | None = None,
    token_env: str = "GITHUB_TOKEN",
    api_base_url: str = "https://api.github.com",
    correlation_id: str | None = None,
    http_client: HttpClient | None = None,
    runtime: Any | None = None,
) -> ToolEvent:
    token_env_name, ephemeral_token = _resolve_token_env(token, token_env, allow_ephemeral=True)
    request = build_github_issue_close_request(
        owner=owner,
        repo=repo,
        issue_number=int(issue_number),
        token_env=token_env_name,
        api_base_url=api_base_url,
        correlation_id=correlation_id,
    )
    if runtime is not None:
        if ephemeral_token is not None:
            raise ActionError("explicit GitHub token is not allowed for approval-gated requests; use token_env")
        return _request_approval(
            "github_issue_close",
            runtime=runtime,
            request=request,
            action_type="github.issue.close",
            requested_by="cli.github_issue_close",
            summary=f"Approve GitHub issue close for {owner}/{repo}#{int(issue_number)}",
            reason=f"Close GitHub issue {owner}/{repo}#{int(issue_number)}",
        )
    with _temporary_env(token_env_name, ephemeral_token):
        return _execute_request("github_issue_close", request, http_client=http_client)


def github_workflow_dispatch(
    *,
    owner: str,
    repo: str,
    workflow_id: str,
    ref: str,
    inputs: dict[str, Any] | None = None,
    token: str | None = None,
    token_env: str = "GITHUB_TOKEN",
    api_base_url: str = "https://api.github.com",
    correlation_id: str | None = None,
    http_client: HttpClient | None = None,
    runtime: Any | None = None,
) -> ToolEvent:
    effective_correlation_id = str(correlation_id or "").strip() or f"trace_{uuid.uuid4().hex[:12]}"
    denied_request = {
        "action": "github_workflow_dispatch",
        "parameters": {
            "owner": owner,
            "repo": repo,
            "workflow_id": workflow_id,
            "ref": ref,
            "inputs": dict(inputs or {}),
        },
        "correlation_id": effective_correlation_id,
    }
    workflow_allowed, allowlist_payload = _workflow_dispatch_allowed(owner, repo, workflow_id)
    if not workflow_allowed:
        payload = {
            "ok": False,
            "trace_id": effective_correlation_id,
            "request": denied_request,
            **allowlist_payload,
        }
        if runtime is not None:
            denial = runtime.record_gateway_action_denied(
                action_type="github.workflow.dispatch",
                connector_key="github_webhook",
                plugin_name="github_phase1",
                request_payload=denied_request,
                requested_by="cli.github_workflow_dispatch",
                trace_id=effective_correlation_id,
                summary="workflow dispatch denied by allowlist",
                reason=str(allowlist_payload.get("reason") or "workflow_not_allowlisted"),
                metadata={"provider": "github", "phase": "phase1"},
            )
            payload["action_request"] = denial["action_request"].to_dict()
            payload["audit_records"] = [item.to_dict() for item in denial["audit_records"]]
        return _tool_event(
            "github_workflow_dispatch",
            ok=False,
            summary="workflow dispatch denied by allowlist",
            payload=payload,
        )
    enriched_inputs = dict(inputs or {})
    enriched_inputs.setdefault("trace_id", effective_correlation_id)
    enriched_inputs.setdefault("correlation_id", effective_correlation_id)
    token_env_name, ephemeral_token = _resolve_token_env(token, token_env, allow_ephemeral=True)
    request = build_github_workflow_dispatch_request(
        owner=owner,
        repo=repo,
        workflow_id=workflow_id,
        ref=ref,
        inputs=enriched_inputs,
        token_env=token_env_name,
        api_base_url=api_base_url,
        correlation_id=effective_correlation_id,
    )
    if runtime is not None:
        if ephemeral_token is not None:
            raise ActionError("explicit GitHub token is not allowed for approval-gated requests; use token_env")
        return _request_approval(
            "github_workflow_dispatch",
            runtime=runtime,
            request=request,
            action_type="github.workflow.dispatch",
            requested_by="cli.github_workflow_dispatch",
            summary=f"Approve GitHub workflow dispatch for {owner}/{repo}",
            reason=f"Dispatch workflow '{workflow_id}' on ref '{ref}' for {owner}/{repo}",
        )
    with _temporary_env(token_env_name, ephemeral_token):
        return _execute_request("github_workflow_dispatch", request, http_client=http_client)


def register_tools(registry) -> None:
    registry.add_tool(
        name="github_issue_create",
        label="GitHub Issue Create",
        description="Create a GitHub issue through the Phase 1 controlled HTTP path.",
        handler=github_issue_create,
        requires_confirmation=True,
    )
    registry.add_tool(
        name="github_issue_comment",
        label="GitHub Issue Comment",
        description="Add a comment to a GitHub issue through the Phase 1 controlled HTTP path.",
        handler=github_issue_comment,
        requires_confirmation=True,
    )
    registry.add_tool(
        name="github_issue_add_labels",
        label="GitHub Issue Labels",
        description="Add labels to a GitHub issue through the Phase 1 controlled HTTP path.",
        handler=github_issue_add_labels,
        requires_confirmation=True,
    )
    registry.add_tool(
        name="github_issue_close",
        label="GitHub Issue Close",
        description="Close a GitHub issue through the Phase 1 controlled HTTP path.",
        handler=github_issue_close,
        requires_confirmation=True,
    )
    registry.add_tool(
        name="github_workflow_dispatch",
        label="GitHub Workflow Dispatch",
        description="Dispatch a GitHub Actions workflow through the Phase 1 controlled HTTP path.",
        handler=github_workflow_dispatch,
        requires_confirmation=True,
    )
