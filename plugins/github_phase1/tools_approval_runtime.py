from __future__ import annotations

import os
import tomllib
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from cli.agent_cli.models import ToolEvent
from shared.integrations import HttpClient
from workers.actions import ActionError, ControlledActionWorker

_EPHEMERAL_GITHUB_TOKEN_ENV = "AGENTHUB_GITHUB_TOKEN_EPHEMERAL"
_DEFAULT_PHASE1_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "github_phase1.toml"


def _tool_event(name: str, *, ok: bool, summary: str, payload: dict[str, Any]) -> ToolEvent:
    return ToolEvent(name=name, ok=bool(ok), summary=summary, payload=payload)


def _resolve_token_env(
    token: str | None,
    token_env: str,
    *,
    allow_ephemeral: bool,
    ephemeral_token_env: str | None = None,
) -> tuple[str, str | None]:
    effective_ephemeral_token_env = ephemeral_token_env or _EPHEMERAL_GITHUB_TOKEN_ENV
    explicit = str(token or "").strip()
    env_name = str(token_env or "GITHUB_TOKEN").strip() or "GITHUB_TOKEN"
    if explicit:
        if not allow_ephemeral:
            raise ActionError(
                f"explicit GitHub token is not allowed here; set {env_name} in the environment instead"
            )
        return effective_ephemeral_token_env, explicit
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


def _execute_request(
    name: str,
    request: dict[str, Any],
    *,
    http_client: HttpClient | None = None,
    worker_cls: Callable[..., Any] | None = None,
    tool_event_factory: Callable[..., ToolEvent] | None = None,
) -> ToolEvent:
    effective_worker_cls = worker_cls or ControlledActionWorker
    effective_tool_event_factory = tool_event_factory or _tool_event
    worker = effective_worker_cls(http_client=http_client)
    try:
        result = worker.execute(request)
    except ActionError as exc:
        return effective_tool_event_factory(
            name,
            ok=False,
            summary=str(exc),
            payload={"ok": False, "error": str(exc), "request": request},
        )
    return effective_tool_event_factory(
        name, ok=result.ok, summary=result.summary, payload=result.to_dict()
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
    tool_event_factory: Callable[..., ToolEvent] | None = None,
) -> ToolEvent:
    effective_tool_event_factory = tool_event_factory or _tool_event
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
    return effective_tool_event_factory(
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


def _load_phase1_config(config_path: Path | str | None = None) -> dict[str, Any]:
    path = Path(config_path or _DEFAULT_PHASE1_CONFIG_PATH)
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _workflow_dispatch_allowed(
    owner: str,
    repo: str,
    workflow_id: str,
    *,
    config: dict[str, Any] | None = None,
    config_path: Path | str | None = None,
) -> tuple[bool, dict[str, Any]]:
    effective_config = _load_phase1_config(config_path) if config is None else config
    block = effective_config.get("workflow_dispatch")
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
