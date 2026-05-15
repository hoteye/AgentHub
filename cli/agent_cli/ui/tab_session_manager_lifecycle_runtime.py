from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.runtime_kernels.base import KernelEngine
from cli.agent_cli.ui.tab_session_manager_models import TabSession

_Collaborators = Mapping[str, Any]


def create_tab(
    manager: Any,
    *,
    engine: KernelEngine = "agenthub_python",
    collaborators: _Collaborators,
) -> str:
    if len(manager._tabs) >= manager.MAX_TABS:
        return ""
    tab_id = f"tab-{manager._next_tab_serial}"
    manager._next_tab_serial += 1
    manager._save_current_state()
    runtime = collaborators["_build_runtime_for_engine"](manager._app, tab_id, engine)
    if runtime is None:
        manager._next_tab_serial -= 1
        return ""
    queue = collaborators["_create_request_queue"]()
    actual_engine = collaborators["_tab_session_engine_for_runtime"](runtime)
    tab_session_type = collaborators["TabSession"]
    session = tab_session_type(
        tab_id=tab_id,
        thread_id=runtime.thread_id,
        thread_name=runtime.thread_name or "",
        runtime=runtime,
        request_queue=queue,
        status_data=collaborators["_initial_status_data_for_new_tab"](manager._app, runtime),
        allow_legacy_approval_hydration=False,
        engine=actual_engine,
        kernel_session_id=collaborators["_tab_session_kernel_session_id"](runtime),
    )
    manager._tabs[tab_id] = session
    manager._tab_order.append(tab_id)
    manager._active_tab_id = tab_id
    manager._bind_thread_store_update_active_getter(tab_id, runtime)
    manager._bind_visible_child_tab_backend(tab_id, runtime)
    manager._set_active_thread_id_for_tab(tab_id)
    manager._start_worker_task(tab_id)
    manager._restore_tab_state(tab_id)
    manager.save_manifest()
    return tab_id


def fork_tab(
    manager: Any,
    from_tab_id: str,
    *,
    collaborators: _Collaborators,
) -> str:
    if len(manager._tabs) >= manager.MAX_TABS:
        return ""
    source = manager._tabs.get(from_tab_id)
    if source is None or source.runtime is None:
        return ""
    # Snapshot busy state before _save_current_state() overwrites it.
    source_was_busy = source.is_busy
    tab_id = f"tab-{manager._next_tab_serial}"
    manager._next_tab_serial += 1
    manager._save_current_state()
    runtime = collaborators["_fork_tab_runtime"](
        manager._app,
        tab_id,
        source_runtime=source.runtime,
    )
    if runtime is None:
        manager._next_tab_serial -= 1
        return ""
    queue = collaborators["_create_request_queue"]()
    is_codex_sidecar_runtime = collaborators["_is_codex_sidecar_runtime"]
    # Idle source: copy UI transcript directly (matches runtime history).
    # Busy source: skip live transcript - will rebuild from persisted turns.
    if source_was_busy:
        fork_entries: list = []
        fork_lines: list = []
        fork_prompt = ""
    elif is_codex_sidecar_runtime(source.runtime):
        fork_entries = []
        fork_lines = []
        fork_prompt = source.prompt_text
    else:
        fork_entries = list(source.transcript_entries)
        fork_lines = list(source.transcript_lines)
        fork_prompt = source.prompt_text
    tab_session_type = collaborators["TabSession"]
    session = tab_session_type(
        tab_id=tab_id,
        thread_id=runtime.thread_id,
        thread_name=runtime.thread_name or "",
        runtime=runtime,
        request_queue=queue,
        engine=collaborators["_tab_session_engine_for_runtime"](runtime),
        kernel_session_id=collaborators["_tab_session_kernel_session_id"](runtime),
        status_data=(
            collaborators["_initial_status_data_for_new_tab"](manager._app, runtime)
            if source_was_busy
            else collaborators["_fork_status_data_for_runtime"](source.status_data, runtime)
        ),
        allow_legacy_approval_hydration=False,
        transcript_entries=fork_entries,
        transcript_lines=fork_lines,
        prompt_text=fork_prompt,
        forked_from_tab_id=source.tab_id,
        forked_from_thread_id=str(getattr(source.runtime, "thread_id", "") or ""),
        fork_mode="running" if source_was_busy else "idle",
    )
    manager._tabs[tab_id] = session
    manager._tab_order.append(tab_id)
    manager._active_tab_id = tab_id
    manager._bind_thread_store_update_active_getter(tab_id, runtime)
    manager._bind_visible_child_tab_backend(tab_id, runtime)
    manager._set_active_thread_id_for_tab(tab_id)
    manager._start_worker_task(tab_id)
    manager._restore_tab_state(tab_id)
    # For busy source, rebuild transcript from fork runtime's persisted history
    # so UI matches what the provider actually has.
    if source_was_busy or is_codex_sidecar_runtime(runtime):
        if is_codex_sidecar_runtime(runtime):
            collaborators["_hydrate_codex_runtime_from_session_metadata"](runtime)
        manager._rebuild_fork_transcript_from_runtime(tab_id)
    manager.save_manifest()
    return tab_id


def switch_to_tab(
    manager: Any,
    tab_id: str,
    *,
    collaborators: _Collaborators,
) -> bool:
    del collaborators
    if tab_id == manager._active_tab_id or tab_id not in manager._tabs:
        return False
    previous_active_tab_id = manager._active_tab_id
    manager._save_current_state()
    manager._active_tab_id = tab_id
    if not manager._ensure_runtime_restored(tab_id):
        manager._remove_unrestorable_tab(tab_id)
        if previous_active_tab_id in manager._tabs:
            manager._active_tab_id = previous_active_tab_id
        elif manager._tab_order:
            manager._active_tab_id = manager._tab_order[0]
        else:
            return False
        manager._set_active_thread_id_for_tab(manager._active_tab_id)
        manager._restore_tab_state(manager._active_tab_id)
        manager.save_manifest()
        return False
    manager._set_active_thread_id_for_tab(tab_id)
    manager._restore_tab_state(tab_id)
    manager.save_manifest()
    return True


def close_tab(
    manager: Any,
    tab_id: str,
    *,
    collaborators: _Collaborators,
) -> str | None:
    del collaborators
    if len(manager._tabs) <= 1:
        return None
    session = manager._tabs.get(tab_id)
    if session is None:
        return None
    if session.is_busy:
        return None
    manager._cancel_worker_task(tab_id)
    idx = manager._tab_order.index(tab_id)
    manager._tab_order.remove(tab_id)
    del manager._tabs[tab_id]
    if tab_id == manager._active_tab_id:
        new_idx = min(idx, len(manager._tab_order) - 1)
        new_tab_id = manager._tab_order[new_idx]
        manager._active_tab_id = new_tab_id
        manager._set_active_thread_id_for_tab(new_tab_id)
        manager._restore_tab_state(new_tab_id)
        manager.save_manifest()
        return new_tab_id
    manager.save_manifest()
    return manager._active_tab_id


def fallback_deferred_restore_to_direct_runtime(
    manager: Any,
    tab_id: str,
    session: TabSession,
    *,
    collaborators: _Collaborators,
) -> bool:
    if len(manager._tabs) > 1:
        return False
    runtime = getattr(manager._app, "_direct_runtime", None)
    if runtime is None or runtime is session.runtime:
        return False
    manager._bind_thread_store_update_active_getter(tab_id, runtime)
    manager._bind_visible_child_tab_backend(tab_id, runtime)
    session.runtime = runtime
    session.thread_id = str(getattr(runtime, "thread_id", "") or session.thread_id)
    session.thread_name = str(getattr(runtime, "thread_name", "") or session.thread_name)
    session.status_data = collaborators["_initial_status_data_for_new_tab"](manager._app, runtime)
    session.engine = collaborators["_tab_session_engine_for_runtime"](runtime)
    session.kernel_session_id = collaborators["_tab_session_kernel_session_id"](runtime)
    session.runtime_restore_pending = False
    session.runtime_restore_prefetch = None
    session.runtime_restore_poll_scheduled = False
    session.manifest_tab_info = None
    session.transcript_restore_pending = True
    if session.request_worker_task is None:
        manager._start_worker_task(tab_id)
    return True


def remove_unrestorable_tab(
    manager: Any,
    tab_id: str,
    *,
    collaborators: _Collaborators,
) -> None:
    del collaborators
    if tab_id not in manager._tabs or len(manager._tabs) <= 1:
        return
    manager._cancel_worker_task(tab_id)
    try:
        manager._tab_order.remove(tab_id)
    except ValueError:
        pass
    manager._tabs.pop(tab_id, None)
