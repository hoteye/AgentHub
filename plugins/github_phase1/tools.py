from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

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

from .tools_approval_runtime import (
    _execute_request as _runtime_execute_request,
)
from .tools_approval_runtime import (
    _load_phase1_config as _runtime_load_phase1_config,
)
from .tools_approval_runtime import (
    _request_approval as _runtime_request_approval,
)
from .tools_approval_runtime import (
    _resolve_token_env as _runtime_resolve_token_env,
)
from .tools_approval_runtime import (
    _temporary_env as _runtime_temporary_env,
)
from .tools_approval_runtime import (
    _tool_event as _runtime_tool_event,
)
from .tools_approval_runtime import (
    _workflow_dispatch_allowed as _runtime_workflow_dispatch_allowed,
)

_EPHEMERAL_GITHUB_TOKEN_ENV = "AGENTHUB_GITHUB_TOKEN_EPHEMERAL"
_PHASE1_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "github_phase1.toml"


def _tool_event(name: str, *, ok: bool, summary: str, payload: dict[str, Any]) -> ToolEvent:
    return _runtime_tool_event(name, ok=ok, summary=summary, payload=payload)


def _resolve_token_env(
    token: str | None, token_env: str, *, allow_ephemeral: bool
) -> tuple[str, str | None]:
    return _runtime_resolve_token_env(
        token,
        token_env,
        allow_ephemeral=allow_ephemeral,
        ephemeral_token_env=_EPHEMERAL_GITHUB_TOKEN_ENV,
    )


def _temporary_env(name: str, value: str | None):
    return _runtime_temporary_env(name, value)


def _execute_request(
    name: str, request: dict[str, Any], *, http_client: HttpClient | None = None
) -> ToolEvent:
    return _runtime_execute_request(
        name,
        request,
        http_client=http_client,
        worker_cls=ControlledActionWorker,
        tool_event_factory=_tool_event,
    )


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
    return _runtime_request_approval(
        name,
        runtime=runtime,
        request=request,
        action_type=action_type,
        requested_by=requested_by,
        summary=summary,
        reason=reason,
        event_id=event_id,
        workflow_run_id=workflow_run_id,
        metadata=metadata,
        tool_event_factory=_tool_event,
    )


def _load_phase1_config() -> dict[str, Any]:
    return _runtime_load_phase1_config(_PHASE1_CONFIG_PATH)


def _workflow_dispatch_allowed(
    owner: str, repo: str, workflow_id: str
) -> tuple[bool, dict[str, Any]]:
    return _runtime_workflow_dispatch_allowed(
        owner, repo, workflow_id, config=_load_phase1_config()
    )


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
            raise ActionError(
                "explicit GitHub token is not allowed for approval-gated requests; use token_env"
            )
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
            raise ActionError(
                "explicit GitHub token is not allowed for approval-gated requests; use token_env"
            )
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
            raise ActionError(
                "explicit GitHub token is not allowed for approval-gated requests; use token_env"
            )
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
            raise ActionError(
                "explicit GitHub token is not allowed for approval-gated requests; use token_env"
            )
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
            raise ActionError(
                "explicit GitHub token is not allowed for approval-gated requests; use token_env"
            )
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
