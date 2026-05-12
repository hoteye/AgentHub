from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_workspace.context import (
    create_thread_workspace_context,
    override_thread_workspace_context,
)
from cli.agent_cli.runtime_workspace.models import ThreadWorkspaceContext


def preview_text(value: Any, *, max_chars: int = 240) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def runtime_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def resolve_runtime_cwd(value: Any | None) -> Path:
    raw = str(value or "").strip()
    return Path(raw or Path.cwd()).resolve()


def _git_marker_is_usable(marker_path: Path) -> bool:
    if marker_path.is_file():
        try:
            return (
                marker_path.read_text(encoding="utf-8", errors="ignore")
                .lstrip()
                .startswith("gitdir:")
            )
        except OSError:
            return False
    if not marker_path.is_dir():
        return False
    return any((marker_path / name).exists() for name in ("HEAD", "config", "objects", "refs"))


def _project_marker_is_usable(root: Path, marker: str) -> bool:
    marker_path = root / marker
    if marker == ".git":
        return _git_marker_is_usable(marker_path)
    return marker_path.exists()


def resolve_project_workspace_root(path: Path) -> Path:
    resolved = Path(path).resolve()
    try:
        from cli.agent_cli.workspace_context import project_root_markers

        markers = project_root_markers(resolved)
        marker_list = [str(item or "").strip() for item in markers if str(item or "").strip()]
        if not marker_list:
            return resolved
        for ancestor in (resolved, *resolved.parents):
            if any(_project_marker_is_usable(ancestor, marker) for marker in marker_list):
                return ancestor.resolve()
        return resolved
    except Exception:
        return resolved


def set_tools_workspace_root(*, tools: Any, path: Path) -> Path:
    setter = getattr(tools, "set_workspace_root", None)
    resolved = path.resolve()
    if callable(setter):
        resolved = Path(setter(resolved)).resolve()
    file_workspace_root = resolve_project_workspace_root(resolved)
    tools.WORKSPACE_ROOT = str(resolved)
    tools.PROJECT_ROOT = str(file_workspace_root)
    return resolved


def tools_file_workspace_root(*, tools: Any) -> Path:
    return Path(
        str(
            getattr(tools, "PROJECT_ROOT", None)
            or getattr(tools, "WORKSPACE_ROOT", None)
            or Path.cwd()
        )
    ).resolve()


def response_runtime_snapshot(
    *, cwd: Any, provider_status: dict[str, Any], runtime_policy: dict[str, Any]
) -> dict[str, Any]:
    return {
        "model": str(
            provider_status.get("provider_model") or provider_status.get("model_key") or ""
        ),
        "model_provider": str(provider_status.get("provider_name") or ""),
        "service_tier": None,
        "cwd": str(cwd or ""),
        "approval_policy": str(runtime_policy.get("approval_policy") or ""),
        "sandbox_mode": str(runtime_policy.get("sandbox_mode") or ""),
        "sandbox": str(runtime_policy.get("sandbox_mode") or ""),
        "web_search_mode": str(runtime_policy.get("web_search_mode") or ""),
        "reasoning_effort": str(provider_status.get("provider_reasoning_effort") or "") or None,
        "provider_status": provider_status,
        "runtime_policy": runtime_policy,
    }


def describe_thread_fallback(
    *,
    thread: dict[str, Any] | None,
    thread_id: str | None,
    thread_name: str,
    cwd: Any,
    turns: list[dict[str, Any]] | None,
    normalized_status: str,
    provider_status: dict[str, Any],
    runtime_policy: dict[str, Any],
    metadata_overrides: dict[str, Any] | None,
    cli_version: str,
) -> dict[str, Any]:
    fallback = dict(thread or {})
    resolved_thread_id = str(thread_id or fallback.get("thread_id") or "").strip()
    return {
        **fallback,
        "id": resolved_thread_id,
        "thread_id": resolved_thread_id,
        "name": str(fallback.get("name") or thread_name or ""),
        "preview": str(fallback.get("preview") or fallback.get("last_user_text") or ""),
        "ephemeral": True,
        "model_provider": str(provider_status.get("provider_name") or ""),
        "status": normalized_status,
        "path": None,
        "cwd": str(fallback.get("cwd") or cwd or ""),
        "cli_version": cli_version,
        "source": "agenthub_cli",
        "created_at_unix": 0,
        "updated_at_unix": 0,
        "turns": [dict(item) for item in list(turns or []) if isinstance(item, dict)],
        "metadata": {
            "provider_status": provider_status,
            "runtime_policy": runtime_policy,
            **dict(metadata_overrides or {}),
        },
    }


def apply_runtime_policy(
    *,
    runtime_policy: Any,
    approval_policy: str | None,
    sandbox_mode: str | None,
    web_search_mode: str | None,
    network_access_enabled: str | bool | None,
    agent_runtime_policy_setter: Callable[[dict[str, Any]], Any] | None,
    runtime_policy_override_payload_fn: Callable[[Any], dict[str, Any]],
) -> Any:
    updated_policy = runtime_policy.with_updates(
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=web_search_mode,
        network_access_enabled=network_access_enabled,
    )
    if callable(agent_runtime_policy_setter):
        agent_runtime_policy_setter(runtime_policy_override_payload_fn(updated_policy))
    return updated_policy


def runtime_policy_override_payload(runtime_policy: Any) -> dict[str, Any]:
    return {
        "approval_policy": runtime_policy.approval_policy,
        "sandbox_mode": runtime_policy.sandbox_mode,
        "web_search_mode": runtime_policy.web_search_mode,
        "network_access_enabled": runtime_policy.network_access_enabled,
    }


def configure_runtime_tool_hooks(
    *,
    tools: Any,
    shell_activity_callback: Callable[..., Any],
    shell_activity_suppressed_getter: Callable[..., Any],
    shell_cancel_event_getter: Callable[..., Any],
    runtime_policy_status_getter: Callable[..., Any] | None = None,
    request_patch_approval_fn: Callable[..., Any] | None = None,
) -> None:
    tools._shell_activity_callback = shell_activity_callback
    tools._shell_activity_suppressed_getter = shell_activity_suppressed_getter
    tools._shell_cancel_event_getter = shell_cancel_event_getter
    tools._runtime_policy_status_getter = runtime_policy_status_getter
    tools._request_patch_approval_fn = request_patch_approval_fn


def apply_runtime_cwd(
    *,
    cwd: str | Path,
    resolve_runtime_cwd_fn: Callable[[Any], Path],
    set_tools_workspace_root_fn: Callable[[Path], Path],
    agent_setter: Callable[[Path], Any] | None,
) -> Path:
    resolved = resolve_runtime_cwd_fn(cwd)
    runtime_cwd = set_tools_workspace_root_fn(resolved)
    if callable(agent_setter):
        runtime_cwd = Path(agent_setter(runtime_cwd)).resolve()
    return runtime_cwd


def runtime_state_defaults(*, threading_module: Any) -> dict[str, Any]:
    delegated_agents_lock = threading_module.Lock()
    pending_steer_lock = threading_module.Lock()
    return {
        "thread_id": None,
        "thread_name": "-",
        "history": [],
        "_base_history": [],
        "history_turns": [],
        "rollout_items": [],
        "reference_context_items": [],
        "_planner_input_items": [],
        "_environment_context_snapshot": {},
        "_environment_context_history": [],
        "_workspace_context_snapshot": {},
        "_memory_context_snapshot": {},
        "_context_update_history": [],
        "_forced_environment_context_snapshot": {},
        "_forced_workspace_context_snapshot": {},
        "selected_conversation": None,
        "pending_send_text": "",
        "send_ready": False,
        "last_plan": None,
        "_last_plan_text": None,
        "latest_task_plan": None,
        "collaboration_mode": "default",
        "default_mode_request_user_input": False,
        "request_user_input_handler": None,
        "_request_user_input_bridge": None,
        "thread_store_update_active_getter": None,
        "_run_state_lock": threading_module.Lock(),
        "_active_run_token": None,
        "_active_run_label": "",
        "_active_run_text": "",
        "_cancel_event": None,
        "_pending_steer_enabled": False,
        "_pending_steer_lock": pending_steer_lock,
        "_pending_steer_input_items": [],
        "_thread_local_state": threading_module.local(),
        "_local_tool_names": set(),
        "_local_keywords": (),
        "_delegated_agents_lock": delegated_agents_lock,
        "_delegated_scheduler_condition": threading_module.Condition(delegated_agents_lock),
        "_delegated_agents": {},
        "_background_task_adapter_cache": None,
        "_background_task_adapter_cwd": "",
    }


def runtime_policy_workspace_kwargs(runtime_policy: Any) -> dict[str, Any]:
    if isinstance(runtime_policy, dict):
        payload = dict(runtime_policy)
    else:
        payload = {
            "approval_policy": getattr(runtime_policy, "approval_policy", None),
            "sandbox_mode": getattr(runtime_policy, "sandbox_mode", None),
            "network_access_enabled": getattr(runtime_policy, "network_access_enabled", None),
            "web_search_mode": getattr(runtime_policy, "web_search_mode", None),
        }
    return {
        "approval_policy": payload.get("approval_policy"),
        "sandbox_mode": payload.get("sandbox_mode"),
        "network_access_enabled": payload.get("network_access_enabled"),
        "web_search_mode": payload.get("web_search_mode"),
    }


def build_runtime_workspace_context(
    *,
    thread_id: str | None,
    cwd: str | Path,
    runtime_policy: Any,
    workspace_root: str | None = None,
) -> ThreadWorkspaceContext:
    return create_thread_workspace_context(
        thread_id=str(thread_id or ""),
        cwd=str(cwd),
        workspace_root=workspace_root,
        **runtime_policy_workspace_kwargs(runtime_policy),
    )


def refresh_workspace_context_for_cwd(
    context: ThreadWorkspaceContext | None,
    *,
    cwd: str | Path,
    workspace_root: str | None = None,
) -> ThreadWorkspaceContext | None:
    if context is None:
        return None
    return override_thread_workspace_context(
        context,
        cwd=str(cwd),
        workspace_root=workspace_root,
    )


def refresh_workspace_context_for_runtime_policy(
    context: ThreadWorkspaceContext | None,
    *,
    runtime_policy: Any,
) -> ThreadWorkspaceContext | None:
    if context is None:
        return None
    return override_thread_workspace_context(
        context,
        **runtime_policy_workspace_kwargs(runtime_policy),
    )
