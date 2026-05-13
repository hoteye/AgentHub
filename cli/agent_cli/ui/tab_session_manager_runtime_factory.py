from __future__ import annotations

import asyncio
import copy
import logging
import threading
from types import SimpleNamespace
from typing import Any

from cli.agent_cli.runtime_kernels.base import (
    ForkSessionRequest,
    KernelEngine,
    KernelSession,
    ResumeSessionRequest,
    StartSessionRequest,
)
from cli.agent_cli.startup_debug import startup_timer
from cli.agent_cli.ui.codex_sidecar_metadata import runtime_policy_metadata_for_sidecar
from cli.agent_cli.ui.tab_session_manager_state import _tab_session_engine_for_runtime
from cli.agent_cli.ui.tab_session_restore_prefetch import CodexSidecarRestorePrefetch

logger = logging.getLogger("cli.agent_cli.ui.tab_session_manager")


def _is_codex_sidecar_runtime(runtime: Any) -> bool:
    return _tab_session_engine_for_runtime(runtime) == "codex_sidecar"


def _build_tab_runtime(app: Any, tab_id: str) -> Any | None:
    from cli.agent_cli.runtime import AgentCliRuntime
    from cli.agent_cli.runtime_core.thread_session import start_thread

    current = app.runtime
    thread_store = getattr(current, "thread_store", None)
    if thread_store is None:
        return None
    runtime_policy = getattr(current, "runtime_policy", None)
    gateway_state_store = getattr(current, "gateway_state_store", None)
    gateway_broadcaster = getattr(current, "gateway_broadcaster", None)
    runtime = AgentCliRuntime(
        thread_store=thread_store,
        runtime_policy=copy.deepcopy(runtime_policy) if runtime_policy else None,
        gateway_state_store=gateway_state_store,
        gateway_broadcaster=gateway_broadcaster,
    )
    runtime.activity_callback = lambda event, _tid=tab_id: app._on_tab_activity(_tid, event)
    runtime.turn_event_callback = lambda event, _tid=tab_id: app._on_tab_turn_event(_tid, event)
    runtime.thread_store_update_active_getter = (
        lambda _tid=tab_id: getattr(getattr(app, "_tab_manager", None), "active_tab_id", "") == _tid
    )
    runtime.request_user_input_handler = (
        lambda payload, _tid=tab_id: app._handle_request_user_input_from_runtime_for_tab(
            _tid, payload
        )
    )
    try:
        runtime.presentation_locale = app._presentation.locale
    except Exception:
        pass
    start_thread(runtime)
    return runtime


def _run_coro_blocking(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    result: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=_runner, name="agenthub-kernel-session-start", daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _build_codex_sidecar_tab_runtime(app: Any, tab_id: str) -> Any | None:
    kernel = _codex_sidecar_kernel_for_app(app)
    if kernel is None:
        return None
    metadata = _runtime_policy_metadata_for_sidecar(app)
    try:
        session = _run_coro_blocking(
            kernel.start_session(
                StartSessionRequest(
                    cwd=str(getattr(app, "_workspace_root", "") or ""),
                    metadata=metadata,
                )
            )
        )
    except Exception:
        return None
    return _runtime_adapter_for_codex_session(app, tab_id, kernel, session)


def _runtime_policy_metadata_for_sidecar(app: Any) -> dict[str, Any]:
    runtime_policy = getattr(getattr(app, "runtime", None), "runtime_policy", None)
    return runtime_policy_metadata_for_sidecar(runtime_policy)


def _codex_sidecar_kernel_for_app(app: Any) -> Any | None:
    from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

    kernel = getattr(app, "_codex_sidecar_kernel", None)
    if kernel is not None:
        return kernel
    try:
        kernel = CodexSidecarKernel(cwd=getattr(app, "cwd", None))
    except Exception:
        return None
    app._codex_sidecar_kernel = kernel
    return kernel


def _runtime_adapter_for_codex_session(app: Any, tab_id: str, kernel: Any, session: Any) -> Any:
    from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter import (
        CodexSidecarRuntimeAdapter,
    )

    gateway_state_store = getattr(
        getattr(app, "_direct_runtime", None), "gateway_state_store", None
    )
    if gateway_state_store is None:
        gateway_state_store = getattr(getattr(app, "runtime", None), "gateway_state_store", None)
    runtime = CodexSidecarRuntimeAdapter(
        kernel=kernel,
        session=session,
        gateway_state_store=gateway_state_store,
    )
    runtime.activity_callback = lambda event, _tid=tab_id: app._on_tab_activity(_tid, event)
    runtime.turn_event_callback = lambda event, _tid=tab_id: app._on_tab_turn_event(_tid, event)
    runtime.thread_store_update_active_getter = (
        lambda _tid=tab_id: getattr(getattr(app, "_tab_manager", None), "active_tab_id", "") == _tid
    )
    runtime.request_user_input_handler = (
        lambda payload, _tid=tab_id: app._handle_request_user_input_from_runtime_for_tab(
            _tid, payload
        )
    )
    try:
        runtime.presentation_locale = app._presentation.locale
    except Exception:
        pass
    return runtime


def _placeholder_codex_sidecar_tab_runtime(app: Any, tab_info: Any) -> Any | None:
    thread_id = str(getattr(tab_info, "thread_id", "") or "").strip()
    if not thread_id:
        return None
    session_id = str(getattr(tab_info, "kernel_session_id", "") or thread_id).strip() or thread_id
    provider_name = str(getattr(tab_info, "provider_name", "") or "").strip()
    provider_model = str(getattr(tab_info, "provider_model", "") or "").strip()
    kernel_session = KernelSession(
        engine="codex_sidecar",
        session_id=session_id,
        thread_id=thread_id,
        thread_name=str(getattr(tab_info, "thread_name", "") or thread_id),
        cwd=str(getattr(tab_info, "cwd", "") or getattr(app, "_workspace_root", "")),
        model=provider_model,
        model_provider=provider_name,
        metadata={"deferred_restore": True},
    )
    agent = SimpleNamespace(
        provider_status=lambda: {
            "provider_ready": "true",
            "provider_name": provider_name or "codex",
            "provider_public_name": provider_name or "codex",
            "provider_model": provider_model or "-",
            "provider_tools": "codex-sidecar",
            "provider_label": f"{provider_name or 'codex'} | {provider_model or '-'} | codex-sidecar",
            "provider_base_url": "-",
            "provider_source": "codex_sidecar",
            "kernel_engine": "codex_sidecar",
            "kernel_session_id": session_id,
            "thread_id": thread_id,
        }
    )
    return SimpleNamespace(
        agent=agent,
        cwd=kernel_session.cwd,
        deferred_restore=True,
        history=[],
        history_turns=[],
        kernel_session=kernel_session,
        thread_id=thread_id,
        thread_name=kernel_session.thread_name,
        turn_results=[],
    )


def _resume_codex_sidecar_tab_runtime(app: Any, tab_info: Any) -> Any | None:
    tab_label = str(getattr(tab_info, "tab_id", "") or "unknown")
    prefetched = _consume_codex_sidecar_restore_prefetch(app, tab_info)
    if prefetched is not None:
        with startup_timer(f"codex_sidecar.restore_tab.{tab_label}.prefetch_wait"):
            prefetched.wait()
        if prefetched.kernel is not None and prefetched.session is not None:
            app._codex_sidecar_kernel = prefetched.kernel
            with startup_timer(f"codex_sidecar.restore_tab.{tab_label}.runtime_adapter"):
                return _runtime_adapter_for_codex_session(
                    app,
                    tab_info.tab_id,
                    prefetched.kernel,
                    prefetched.session,
                )
        if prefetched.error is not None:
            _record_codex_sidecar_restore_error(
                app,
                tab_id=str(getattr(tab_info, "tab_id", "") or ""),
                thread_id=str(getattr(tab_info, "thread_id", "") or ""),
                error=prefetched.error,
            )
    with startup_timer(f"codex_sidecar.restore_tab.{tab_label}.kernel"):
        kernel = _codex_sidecar_kernel_for_app(app)
    if kernel is None:
        return None
    thread_id = str(getattr(tab_info, "thread_id", "") or "").strip()
    if not thread_id:
        return None
    with startup_timer(f"codex_sidecar.restore_tab.{tab_label}.metadata"):
        metadata = _runtime_policy_metadata_for_sidecar(app)
    try:
        with startup_timer(f"codex_sidecar.restore_tab.{tab_label}.resume_session"):
            session = _run_coro_blocking(
                kernel.resume_session(
                    ResumeSessionRequest(
                        session_id=str(getattr(tab_info, "kernel_session_id", "") or thread_id),
                        thread_id=thread_id,
                        cwd=str(
                            getattr(tab_info, "cwd", "") or getattr(app, "_workspace_root", "")
                        ),
                        metadata=metadata,
                    )
                )
            )
    except Exception as exc:
        _record_codex_sidecar_restore_error(
            app,
            tab_id=str(getattr(tab_info, "tab_id", "") or ""),
            thread_id=thread_id,
            error=exc,
        )
        return None
    with startup_timer(f"codex_sidecar.restore_tab.{tab_label}.runtime_adapter"):
        return _runtime_adapter_for_codex_session(app, tab_info.tab_id, kernel, session)


def _consume_codex_sidecar_restore_prefetch(
    app: Any,
    tab_info: Any,
) -> CodexSidecarRestorePrefetch | None:
    prefetch = getattr(app, "_codex_sidecar_restore_prefetch", None)
    if not isinstance(prefetch, CodexSidecarRestorePrefetch):
        return None
    tab_id = str(getattr(tab_info, "tab_id", "") or "").strip()
    thread_id = str(getattr(tab_info, "thread_id", "") or "").strip()
    kernel_session_id = str(getattr(tab_info, "kernel_session_id", "") or thread_id).strip()
    if (
        prefetch.tab_id != tab_id
        or prefetch.thread_id != thread_id
        or prefetch.kernel_session_id != (kernel_session_id or thread_id)
    ):
        return None
    try:
        app._codex_sidecar_restore_prefetch = None
    except Exception:
        pass
    return prefetch


def _build_runtime_for_engine(app: Any, tab_id: str, engine: KernelEngine) -> Any | None:
    if engine == "codex_sidecar":
        return _build_codex_sidecar_tab_runtime(app, tab_id)
    runtime = _build_tab_runtime(app, tab_id)
    if runtime is not None:
        return runtime
    if _is_codex_sidecar_runtime(getattr(app, "runtime", None)):
        return _build_codex_sidecar_tab_runtime(app, tab_id)
    return None


def _clone_tab_runtime(app: Any, tab_id: str, source_runtime: Any) -> Any | None:
    if _is_codex_sidecar_runtime(source_runtime):
        return None
    from cli.agent_cli.runtime import AgentCliRuntime

    thread_store = getattr(source_runtime, "thread_store", None)
    if thread_store is None:
        return None
    runtime = AgentCliRuntime(
        thread_store=thread_store,
        runtime_policy=copy.deepcopy(getattr(source_runtime, "runtime_policy", None)),
        gateway_state_store=getattr(source_runtime, "gateway_state_store", None),
        gateway_broadcaster=getattr(source_runtime, "gateway_broadcaster", None),
    )
    runtime.activity_callback = lambda event, _tid=tab_id: app._on_tab_activity(_tid, event)
    runtime.turn_event_callback = lambda event, _tid=tab_id: app._on_tab_turn_event(_tid, event)
    runtime.thread_store_update_active_getter = (
        lambda _tid=tab_id: getattr(getattr(app, "_tab_manager", None), "active_tab_id", "") == _tid
    )
    runtime.request_user_input_handler = (
        lambda payload, _tid=tab_id: app._handle_request_user_input_from_runtime_for_tab(
            _tid, payload
        )
    )
    try:
        runtime.presentation_locale = app._presentation.locale
    except Exception:
        pass
    return runtime


def _fork_tab_runtime(app: Any, tab_id: str, source_runtime: Any) -> Any | None:
    if _is_codex_sidecar_runtime(source_runtime):
        return _fork_codex_sidecar_tab_runtime(app, tab_id, source_runtime)
    from cli.agent_cli.runtime import AgentCliRuntime
    from cli.agent_cli.runtime_core.thread_fork import fork_thread_record

    current = app.runtime
    thread_store = getattr(current, "thread_store", None)
    if thread_store is None:
        return None

    # Create new runtime sharing the thread store.
    runtime = AgentCliRuntime(
        thread_store=thread_store,
        runtime_policy=copy.deepcopy(getattr(source_runtime, "runtime_policy", None)),
        gateway_state_store=getattr(current, "gateway_state_store", None),
        gateway_broadcaster=getattr(current, "gateway_broadcaster", None),
    )
    runtime.activity_callback = lambda event, _tid=tab_id: app._on_tab_activity(_tid, event)
    runtime.turn_event_callback = lambda event, _tid=tab_id: app._on_tab_turn_event(_tid, event)
    runtime.thread_store_update_active_getter = (
        lambda _tid=tab_id: getattr(getattr(app, "_tab_manager", None), "active_tab_id", "") == _tid
    )
    runtime.request_user_input_handler = (
        lambda payload, _tid=tab_id: app._handle_request_user_input_from_runtime_for_tab(
            _tid, payload
        )
    )
    try:
        runtime.presentation_locale = app._presentation.locale
    except Exception:
        pass

    try:
        fork_result = fork_thread_record(
            thread_store=thread_store,
            source_thread_id=str(getattr(source_runtime, "thread_id", "") or ""),
            cwd=str(getattr(source_runtime, "cwd", "") or ""),
            provider_status=source_runtime.agent.provider_status(),
            runtime_policy_status=source_runtime.runtime_policy_status(),
            prefer_source_status=False,
        )
    except Exception:
        return None

    runtime.resume_thread(str(fork_result.get("thread_id") or ""))
    return runtime


def _fork_codex_sidecar_tab_runtime(app: Any, tab_id: str, source_runtime: Any) -> Any | None:
    kernel = getattr(source_runtime, "kernel", None) or _codex_sidecar_kernel_for_app(app)
    if kernel is None:
        return None
    source_thread_id = str(getattr(source_runtime, "thread_id", "") or "").strip()
    if not source_thread_id:
        return None
    metadata = _runtime_policy_metadata_for_sidecar(app)
    try:
        session = _run_coro_blocking(
            kernel.fork_session(
                ForkSessionRequest(
                    source_session_id=str(
                        getattr(getattr(source_runtime, "kernel_session", None), "session_id", "")
                        or source_thread_id
                    ),
                    source_thread_id=source_thread_id,
                    cwd=str(
                        getattr(source_runtime, "cwd", "") or getattr(app, "_workspace_root", "")
                    ),
                    metadata=metadata,
                )
            )
        )
    except Exception as exc:
        if _should_fallback_to_start_for_codex_fork(exc):
            logger.warning(
                "codex sidecar fork fell back to thread/start",
                extra={
                    "tab_id": tab_id,
                    "source_thread_id": source_thread_id,
                    "error": str(exc),
                },
            )
            return _build_codex_sidecar_tab_runtime(app, tab_id)
        return None
    return _runtime_adapter_for_codex_session(app, tab_id, kernel, session)


def _should_fallback_to_start_for_codex_fork(error: BaseException) -> bool:
    message = str(error).lower()
    return "no rollout found" in message or "no rollout" in message


def _record_codex_sidecar_restore_error(
    app: Any,
    *,
    tab_id: str,
    thread_id: str,
    error: BaseException,
) -> None:
    errors = getattr(app, "_codex_sidecar_restore_errors", None)
    if not isinstance(errors, list):
        errors = []
        try:
            app._codex_sidecar_restore_errors = errors
        except Exception:
            return
    errors.append(
        {
            "tab_id": str(tab_id or "").strip(),
            "thread_id": str(thread_id or "").strip(),
            "error": str(error),
        }
    )
    logger.warning(
        "codex sidecar tab restore failed",
        extra={"tab_id": tab_id, "thread_id": thread_id, "error": str(error)},
    )
