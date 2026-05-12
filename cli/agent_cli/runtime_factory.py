from __future__ import annotations

import threading

from cli.agent_cli.gateway_core import JsonlGatewayStateStore
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli.runtime_services import approval_startup_cleanup_runtime
from cli.agent_cli.startup_environment import apply_shell_environment_updates
from cli.agent_cli.thread_store import ThreadStore


def build_persistent_runtime(
    *,
    runtime_policy: RuntimePolicy | None = None,
    resume_active_thread: bool = True,
    start_thread_if_unavailable: bool = True,
    cleanup_stale_pending_approvals: bool = True,
    stale_pending_approval_seconds: int = approval_startup_cleanup_runtime.DEFAULT_STALE_PENDING_APPROVAL_SECONDS,
    defer_shell_env: bool = True,
) -> AgentCliRuntime:
    if defer_shell_env:
        threading.Thread(target=apply_shell_environment_updates, daemon=True).start()
    else:
        apply_shell_environment_updates()
    store = ThreadStore.default()
    runtime = AgentCliRuntime(
        thread_store=store,
        gateway_state_store=JsonlGatewayStateStore.default(),
        runtime_policy=runtime_policy,
    )
    if cleanup_stale_pending_approvals:
        approval_startup_cleanup_runtime.decline_stale_pending_approvals_on_startup(
            runtime,
            stale_after_seconds=stale_pending_approval_seconds,
        )
    active_thread_id = store.get_active_thread_id() if resume_active_thread else None
    if active_thread_id:
        try:
            runtime.resume_thread(active_thread_id)
            return runtime
        except Exception:
            pass
    if start_thread_if_unavailable:
        runtime.start_thread()
    return runtime
