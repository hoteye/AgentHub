from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli.startup_cwd import resolve_startup_cwd


def build_tui_runtime(
    args: Any,
    runtime: Any,
    *,
    start_tui_tab_restore_prefetch_fn: Callable[..., Any],
    start_new_tui_thread_fn: Callable[[Any, Path], None],
    configure_tui_runtime_policy_fn: Callable[[Any, Any], None],
) -> Any:
    from cli.agent_cli.resume_support import (
        apply_runtime_resume_request,
        has_explicit_resume_request,
    )
    from cli.agent_cli.runtime_factory import build_persistent_runtime
    from cli.agent_cli.runtime_policy import RuntimePolicy

    resume_thread_id = getattr(args, "resume", None)
    resume_rollout_path = getattr(args, "resume_path", None)
    resume_last = bool(getattr(args, "resume_last", False))
    startup_cwd = resolve_startup_cwd()
    explicit_resume = has_explicit_resume_request(
        thread_id=resume_thread_id,
        rollout_path=resume_rollout_path,
        resume_last=resume_last,
    )
    if runtime is None:
        runtime_policy = RuntimePolicy.normalized(
            permission_mode=getattr(args, "permission_mode", None),
            approval_policy=getattr(args, "approval_policy", None) or "never",
            sandbox_mode=getattr(args, "sandbox_mode", None),
            web_search_mode=getattr(args, "web_search_mode", None),
            network_access_enabled=getattr(args, "network_access", None),
        )
        tab_restore_prefetch = start_tui_tab_restore_prefetch_fn(
            runtime_policy=runtime_policy,
            startup_cwd=startup_cwd,
            explicit_resume=explicit_resume,
        )
        runtime = build_persistent_runtime(
            runtime_policy=runtime_policy,
            resume_active_thread=False,
            start_thread_if_unavailable=False,
            build_initial_planner=False,
        )
        if tab_restore_prefetch is not None:
            runtime._codex_sidecar_restore_prefetch = tab_restore_prefetch
        runtime.tui_tab_manifest_enabled = not explicit_resume
        if not explicit_resume:
            start_new_tui_thread_fn(runtime, startup_cwd)
    elif not explicit_resume:
        try:
            runtime.tui_tab_manifest_enabled = True
        except Exception:
            pass
    if explicit_resume:
        apply_runtime_resume_request(
            runtime,
            thread_id=resume_thread_id,
            rollout_path=resume_rollout_path,
            resume_last=resume_last,
        )
    configure_tui_runtime_policy_fn(runtime, args)
    return runtime


def start_tui_tab_restore_prefetch(
    *,
    runtime_policy: Any,
    startup_cwd: Path,
    explicit_resume: bool,
) -> Any:
    if explicit_resume:
        return None
    try:
        from cli.agent_cli.ui.tab_session_restore_prefetch import (
            start_active_codex_sidecar_restore_prefetch,
        )

        return start_active_codex_sidecar_restore_prefetch(
            runtime_policy=runtime_policy,
            startup_cwd=startup_cwd,
        )
    except Exception:
        return None


def start_new_tui_thread(runtime: Any, startup_cwd: Path) -> None:
    set_cwd = getattr(runtime, "set_cwd", None)
    if callable(set_cwd):
        set_cwd(startup_cwd)
    start_thread = getattr(runtime, "start_thread", None)
    if callable(start_thread):
        start_thread()


def configure_tui_runtime_policy(runtime: Any, args: Any) -> None:
    configure = getattr(runtime, "configure_runtime_policy", None)
    if not callable(configure):
        return
    approval_policy = getattr(args, "approval_policy", None)
    sandbox_mode = getattr(args, "sandbox_mode", None)
    network_access_enabled = getattr(args, "network_access", None)
    permission_mode = getattr(args, "permission_mode", None)
    if str(permission_mode or "").strip():
        from cli.agent_cli.runtime_permission_mode import resolve_permission_mode_updates

        current_policy = getattr(runtime, "runtime_policy", None)
        resolution = resolve_permission_mode_updates(
            current_approval_policy=getattr(current_policy, "approval_policy", None),
            current_sandbox_mode=getattr(current_policy, "sandbox_mode", None),
            current_network_access_enabled=getattr(current_policy, "network_access_enabled", None),
            permission_mode=permission_mode,
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            network_access_enabled=network_access_enabled,
        )
        approval_policy = resolution.approval_policy
        sandbox_mode = resolution.sandbox_mode
        network_access_enabled = resolution.network_access_enabled
    configure(
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=getattr(args, "web_search_mode", None),
        network_access_enabled=network_access_enabled,
    )


__all__ = [
    "build_tui_runtime",
    "configure_tui_runtime_policy",
    "start_new_tui_thread",
    "start_tui_tab_restore_prefetch",
]
