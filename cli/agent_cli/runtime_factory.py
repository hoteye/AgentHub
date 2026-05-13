from __future__ import annotations

import threading

from cli.agent_cli.gateway_core import JsonlGatewayStateStore
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli.runtime_services import approval_startup_cleanup_runtime
from cli.agent_cli.startup_debug import startup_profile_log, startup_timer
from cli.agent_cli.startup_environment import apply_shell_environment_updates
from cli.agent_cli.thread_store import ThreadStore


def _run_stale_approval_cleanup(
    runtime: AgentCliRuntime,
    *,
    stale_after_seconds: int,
) -> None:
    wait_until_loaded = getattr(
        getattr(runtime, "gateway_state_store", None), "wait_until_loaded", None
    )
    if callable(wait_until_loaded):
        try:
            wait_until_loaded()
        except Exception:
            pass
    approval_startup_cleanup_runtime.decline_stale_pending_approvals_on_startup(
        runtime,
        stale_after_seconds=stale_after_seconds,
    )


def build_persistent_runtime(
    *,
    runtime_policy: RuntimePolicy | None = None,
    resume_active_thread: bool = True,
    start_thread_if_unavailable: bool = True,
    cleanup_stale_pending_approvals: bool = True,
    stale_pending_approval_seconds: int = approval_startup_cleanup_runtime.DEFAULT_STALE_PENDING_APPROVAL_SECONDS,
    defer_shell_env: bool = True,
    build_initial_planner: bool = True,
) -> AgentCliRuntime:
    with startup_timer("runtime_factory.build_persistent_runtime"):
        with startup_timer("runtime_factory.shell_env"):
            if defer_shell_env:
                threading.Thread(target=apply_shell_environment_updates, daemon=True).start()
            else:
                apply_shell_environment_updates()
        with startup_timer("runtime_factory.thread_store.default"):
            store = ThreadStore.default()
        with startup_timer("runtime_factory.gateway_state_store.default"):
            gateway_state_store = JsonlGatewayStateStore.default(lazy=True)
        with startup_timer("runtime_factory.agent_cli_runtime.init"):
            runtime = AgentCliRuntime(
                thread_store=store,
                gateway_state_store=gateway_state_store,
                runtime_policy=runtime_policy,
                build_initial_planner=build_initial_planner,
            )
        if cleanup_stale_pending_approvals:
            with startup_timer("runtime_factory.approval_cleanup.start_background"):
                cleanup_thread = threading.Thread(
                    target=_run_stale_approval_cleanup,
                    kwargs={
                        "runtime": runtime,
                        "stale_after_seconds": stale_pending_approval_seconds,
                    },
                    name="agenthub-approval-startup-cleanup",
                    daemon=True,
                )
                runtime._approval_startup_cleanup_thread = cleanup_thread
                cleanup_thread.start()
        with startup_timer("runtime_factory.active_thread.lookup"):
            active_thread_id = store.get_active_thread_id() if resume_active_thread else None
        if active_thread_id:
            startup_profile_log(
                "profile.runtime_factory.active_thread.resume "
                f"thread_id={str(active_thread_id)[:16]}"
            )
            with startup_timer("runtime_factory.active_thread.resume"):
                try:
                    runtime.resume_thread(active_thread_id)
                    return runtime
                except Exception:
                    pass
        if start_thread_if_unavailable:
            with startup_timer("runtime_factory.start_thread"):
                runtime.start_thread()
        return runtime
