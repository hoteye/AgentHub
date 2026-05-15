from __future__ import annotations

import copy
import sys
from typing import Any

from cli.agent_cli.runtime_kernels.base import KernelEngine
from cli.agent_cli.ui import tab_session_manager_codex_runtime_factory as codex_runtime_factory
from cli.agent_cli.ui.tab_session_manager_state import _tab_session_engine_for_runtime


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


def _codex_facade() -> Any:
    return sys.modules[__name__]


def _build_codex_sidecar_tab_runtime(app: Any, tab_id: str) -> Any | None:
    return codex_runtime_factory._build_codex_sidecar_tab_runtime(
        app,
        tab_id,
        facade=_codex_facade(),
    )


def _run_coro_blocking(coro: Any) -> Any:
    return codex_runtime_factory._run_coro_blocking(coro)


def _runtime_policy_metadata_for_sidecar(app: Any) -> dict[str, Any]:
    return codex_runtime_factory._runtime_policy_metadata_for_sidecar(app)


def _codex_sidecar_kernel_for_app(app: Any) -> Any | None:
    return codex_runtime_factory._codex_sidecar_kernel_for_app(app)


def _runtime_adapter_for_codex_session(app: Any, tab_id: str, kernel: Any, session: Any) -> Any:
    return codex_runtime_factory._runtime_adapter_for_codex_session(
        app,
        tab_id,
        kernel,
        session,
    )


def _placeholder_codex_sidecar_tab_runtime(app: Any, tab_info: Any) -> Any | None:
    return codex_runtime_factory._placeholder_codex_sidecar_tab_runtime(app, tab_info)


def _resume_codex_sidecar_tab_runtime(app: Any, tab_info: Any) -> Any | None:
    return codex_runtime_factory._resume_codex_sidecar_tab_runtime(
        app,
        tab_info,
        facade=_codex_facade(),
    )


def _consume_codex_sidecar_restore_prefetch(app: Any, tab_info: Any) -> Any | None:
    return codex_runtime_factory._consume_codex_sidecar_restore_prefetch(app, tab_info)


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
    return codex_runtime_factory._fork_codex_sidecar_tab_runtime(
        app,
        tab_id,
        source_runtime,
        facade=_codex_facade(),
    )


def _should_fallback_to_start_for_codex_fork(error: BaseException) -> bool:
    return codex_runtime_factory._should_fallback_to_start_for_codex_fork(error)


def _record_codex_sidecar_restore_error(
    app: Any,
    *,
    tab_id: str,
    thread_id: str,
    error: BaseException,
) -> None:
    codex_runtime_factory._record_codex_sidecar_restore_error(
        app,
        tab_id=tab_id,
        thread_id=thread_id,
        error=error,
    )
