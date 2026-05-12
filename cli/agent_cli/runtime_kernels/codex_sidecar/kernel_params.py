from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_kernels.base import (
    ForkSessionRequest,
    ResumeSessionRequest,
    StartSessionRequest,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject
from cli.agent_cli.runtime_kernels.errors import RuntimeKernelSessionError


def _require_thread_id(thread_id: str) -> str:
    normalized = str(thread_id or "").strip()
    if not normalized:
        raise RuntimeKernelSessionError("codex sidecar thread_id is required")
    return normalized


def _require_absolute_path(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        raise RuntimeKernelSessionError("codex sidecar fs path is required")
    if not Path(normalized).is_absolute():
        raise RuntimeKernelSessionError("codex sidecar fs path must be absolute")
    return normalized


def _require_text(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeKernelSessionError(f"codex sidecar {label} is required")
    return normalized


def _thread_start_params(request: StartSessionRequest) -> JsonObject:
    params: JsonObject = {
        "persistExtendedHistory": True,
    }
    if request.cwd:
        params["cwd"] = request.cwd
    if request.model_provider:
        params["modelProvider"] = request.model_provider
    if request.model:
        params["model"] = request.model
    approval_policy = request.metadata.get("approvalPolicy") or request.metadata.get(
        "approval_policy"
    )
    sandbox = request.metadata.get("sandbox")
    dynamic_tools = request.metadata.get("codex_dynamic_tools") or request.metadata.get(
        "dynamicTools"
    )
    if approval_policy:
        params["approvalPolicy"] = approval_policy
    if sandbox:
        params["sandbox"] = sandbox
    if isinstance(dynamic_tools, list):
        params["dynamicTools"] = [dict(item) for item in dynamic_tools if isinstance(item, dict)]
    return params


def _apply_thread_common_params(
    params: JsonObject,
    *,
    model: str | None = None,
    model_provider: str | None = None,
    cwd: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> JsonObject:
    if model_provider:
        params["modelProvider"] = model_provider
    if model:
        params["model"] = model
    if cwd:
        params["cwd"] = cwd
    raw_metadata = dict(metadata or {})
    approval_policy = raw_metadata.get("approvalPolicy") or raw_metadata.get("approval_policy")
    sandbox = raw_metadata.get("sandbox")
    if approval_policy:
        params["approvalPolicy"] = approval_policy
    if sandbox:
        params["sandbox"] = sandbox
    return params


def _thread_resume_params(request: ResumeSessionRequest) -> JsonObject:
    thread_id = str(request.thread_id or request.session_id or "").strip()
    if not thread_id and not request.path and not request.history:
        raise RuntimeKernelSessionError("codex sidecar resume requires thread_id, path, or history")
    params: JsonObject = {
        "threadId": thread_id,
        "persistExtendedHistory": True,
    }
    if request.path:
        params["path"] = request.path
    if request.history:
        params["history"] = [dict(item) for item in request.history]
    _apply_thread_common_params(
        params,
        cwd=request.cwd,
        metadata=request.metadata,
    )
    return params


def _thread_fork_params(request: ForkSessionRequest) -> JsonObject:
    thread_id = str(request.source_thread_id or request.source_session_id or "").strip()
    if not thread_id and not request.source_path:
        raise RuntimeKernelSessionError(
            "codex sidecar fork requires source_thread_id or source_path"
        )
    params: JsonObject = {
        "threadId": thread_id,
        "persistExtendedHistory": True,
    }
    if request.source_path:
        params["path"] = request.source_path
    _apply_thread_common_params(
        params,
        cwd=request.cwd,
        metadata=request.metadata,
    )
    return params
