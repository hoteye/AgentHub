from __future__ import annotations

# ruff: noqa: F401,I001

from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_kernels.base import (
    ForkSessionRequest,
    KernelEngine,
    ResumeSessionRequest,
    StartSessionRequest,
)
from cli.agent_cli.startup_debug import startup_profile_log, startup_timer
from cli.agent_cli.ui.tab_session_manager_models import RUNNING_FORK_NOTICE, TabSession
from cli.agent_cli.ui.tab_session_manager_runtime_factory import (
    _build_codex_sidecar_tab_runtime,
    _build_runtime_for_engine,
    _build_tab_runtime,
    _clone_tab_runtime,
    _codex_sidecar_kernel_for_app,
    _fork_codex_sidecar_tab_runtime,
    _fork_tab_runtime,
    _is_codex_sidecar_runtime,
    _placeholder_codex_sidecar_tab_runtime,
    _record_codex_sidecar_restore_error,
    _resume_codex_sidecar_tab_runtime,
    _run_coro_blocking,
    _runtime_adapter_for_codex_session,
    _runtime_policy_metadata_for_sidecar,
    _should_fallback_to_start_for_codex_fork,
)
from cli.agent_cli.ui import tab_session_manager_title_runtime as title_runtime
from cli.agent_cli.ui.tab_session_restore_prefetch import CodexSidecarRestorePrefetch
from cli.agent_cli.ui.tab_session_manager_state import (
    _HISTORY_TEXT_BLOCK_TYPES,
    _codex_turns_to_history_turns,
    _fork_runtime_transcript_source_items,
    _fork_status_data_for_runtime,
    _history_content_value_text,
    _history_item_content_text,
    _history_item_to_transcript_entry,
    _hydrate_codex_runtime_from_session_metadata,
    _initial_status_data_for_new_tab,
    _initial_status_data_for_runtime,
    _merge_status_preserving_known_values,
    _provider_status_for_runtime,
    _restore_runtime_transcript_snapshot,
    _restore_tab_provider,
    _tab_session_engine_for_runtime,
    _tab_session_kernel_session_id,
    _without_pending_approval_status,
)
from cli.agent_cli.ui.tab_session_manager_workers import (
    _cancel_tab_request_worker_task,
    _create_request_queue,
    _start_tab_request_worker_task,
)
from cli.agent_cli.ui import tab_session_manager_lifecycle_runtime as lifecycle_runtime
from cli.agent_cli.ui import tab_session_manager_manifest_runtime as manifest_runtime
from cli.agent_cli.ui import tab_session_manager_ui_state_runtime as ui_state_runtime
from cli.agent_cli.ui import tab_session_manager_visible_child_runtime as visible_child_runtime
from cli.agent_cli.ui.tab_session_manager_visible_child_facade_runtime import (
    _append_system_notice_to_tab,
    _assignment_ref_from_request,
    _child_task_update_notice,
    _child_task_update_payload,
    _child_task_updates_context_text,
    _dispatch_visible_child_task_on_app_thread,
    _next_task_run_id,
    _publish_child_task_run_update,
    _send_visible_child_task_on_app_thread,
    _task_status_snapshot_for_session,
    _task_transcript_index_for_session,
    child_tab_ids as _child_tab_ids,
    child_task_runs as _child_task_runs,
    complete_task_run as _complete_task_run,
    dispatch_visible_child_task as _dispatch_visible_child_task,
    fail_task_run as _fail_task_run,
    fork_child_tab as _fork_child_tab,
    prepare_runtime_request_for_tab as _prepare_runtime_request_for_tab,
    send_visible_child_task as _send_visible_child_task,
    start_task_run as _start_task_run,
    visible_child_task_run_snapshots as _visible_child_task_run_snapshots,
)
from cli.agent_cli.ui.tab_session_manifest import (
    TabSessionManifest,
    TabSessionManifestTab,
    load_tab_session_manifest,
    save_tab_session_manifest,
    tab_manifest_enabled_for_runtime,
    tab_manifest_path_for_runtime,
)


def _manifest_tab_restore_engine(tab_info: TabSessionManifestTab) -> KernelEngine:
    return manifest_runtime._manifest_tab_restore_engine(tab_info)


def _manifest_runtime_collaborators() -> dict[str, Any]:
    return {
        "CodexSidecarRestorePrefetch": CodexSidecarRestorePrefetch,
        "TabSession": TabSession,
        "TabSessionManifest": TabSessionManifest,
        "TabSessionManifestTab": TabSessionManifestTab,
        "_clone_tab_runtime": _clone_tab_runtime,
        "_create_request_queue": _create_request_queue,
        "_hydrate_codex_runtime_from_session_metadata": (
            _hydrate_codex_runtime_from_session_metadata
        ),
        "_initial_status_data_for_new_tab": _initial_status_data_for_new_tab,
        "_manifest_tab_restore_engine": _manifest_tab_restore_engine,
        "_placeholder_codex_sidecar_tab_runtime": _placeholder_codex_sidecar_tab_runtime,
        "_restore_runtime_transcript_snapshot": _restore_runtime_transcript_snapshot,
        "_restore_tab_provider": _restore_tab_provider,
        "_resume_codex_sidecar_tab_runtime": _resume_codex_sidecar_tab_runtime,
        "_tab_session_engine_for_runtime": _tab_session_engine_for_runtime,
        "_tab_session_kernel_session_id": _tab_session_kernel_session_id,
        "load_tab_session_manifest": load_tab_session_manifest,
        "save_tab_session_manifest": save_tab_session_manifest,
        "startup_profile_log": startup_profile_log,
        "startup_timer": startup_timer,
        "tab_manifest_enabled_for_runtime": tab_manifest_enabled_for_runtime,
        "tab_manifest_path_for_runtime": tab_manifest_path_for_runtime,
    }


def _ui_state_runtime_collaborators() -> dict[str, Any]:
    return {
        "RUNNING_FORK_NOTICE": RUNNING_FORK_NOTICE,
        "_fork_runtime_transcript_source_items": _fork_runtime_transcript_source_items,
        "_history_item_to_transcript_entry": _history_item_to_transcript_entry,
        "_merge_status_preserving_known_values": _merge_status_preserving_known_values,
        "_provider_status_for_runtime": _provider_status_for_runtime,
        "_restore_runtime_transcript_snapshot": _restore_runtime_transcript_snapshot,
    }


def _lifecycle_runtime_collaborators() -> dict[str, Any]:
    return {
        "TabSession": TabSession,
        "_build_runtime_for_engine": _build_runtime_for_engine,
        "_create_request_queue": _create_request_queue,
        "_fork_status_data_for_runtime": _fork_status_data_for_runtime,
        "_fork_tab_runtime": _fork_tab_runtime,
        "_hydrate_codex_runtime_from_session_metadata": (
            _hydrate_codex_runtime_from_session_metadata
        ),
        "_initial_status_data_for_new_tab": _initial_status_data_for_new_tab,
        "_is_codex_sidecar_runtime": _is_codex_sidecar_runtime,
        "_tab_session_engine_for_runtime": _tab_session_engine_for_runtime,
        "_tab_session_kernel_session_id": _tab_session_kernel_session_id,
    }


def _delegate_global(name: str):
    def delegated(self, *args, **kwargs):
        return globals()[name](self, *args, **kwargs)

    delegated.__name__ = name.lstrip("_")
    return delegated


def _static_delegate_global(name: str):
    def delegated(*args, **kwargs):
        return globals()[name](*args, **kwargs)

    delegated.__name__ = name.lstrip("_")
    return staticmethod(delegated)


class TabSessionManager:
    MAX_TABS = 15

    def __init__(self, *, app: Any, initial_session: TabSession) -> None:
        self._app = app
        self._tabs: dict[str, TabSession] = {initial_session.tab_id: initial_session}
        self._active_tab_id: str = initial_session.tab_id
        self._tab_order: list[str] = [initial_session.tab_id]
        self._next_tab_serial: int = 1
        self._manifest_path: Path | None = None
        self._manifest_restore_notice: tuple[str, dict[str, object]] | None = None
        self._scroll_capture_timer: Any = None
        self._bind_thread_store_update_active_getter(
            initial_session.tab_id, initial_session.runtime
        )
        self._bind_visible_child_tab_backend(initial_session.tab_id, initial_session.runtime)

    def _start_scroll_capture_timer(self) -> None:
        set_interval = getattr(self._app, "set_interval", None)
        if callable(set_interval):
            self._scroll_capture_timer = set_interval(2.0, self._capture_active_scroll)

    def _capture_active_scroll(self) -> None:
        session = self._tabs.get(self._active_tab_id)
        if session is None:
            return
        scroll_x, scroll_y = self._current_transcript_scroll_offset()
        if scroll_x > 0 or scroll_y > 0:
            session.transcript_scroll_x = scroll_x
            session.transcript_scroll_y = scroll_y

    def stop_scroll_capture_timer(self) -> None:
        if self._scroll_capture_timer is not None:
            try:
                self._scroll_capture_timer.stop()
            except Exception:
                pass
            self._scroll_capture_timer = None

    def _bind_thread_store_update_active_getter(self, tab_id: str, runtime: Any) -> None:
        if runtime is None:
            return
        runtime.thread_store_update_active_getter = lambda _tid=tab_id: self._active_tab_id == _tid

    def _bind_visible_child_tab_backend(self, tab_id: str, runtime: Any) -> None:
        if runtime is None:
            return
        try:
            runtime.visible_child_tab_backend = self
            runtime.visible_child_parent_tab_id = tab_id
        except Exception:
            pass

    def _set_active_thread_id_for_tab(self, tab_id: str) -> None:
        session = self._tabs.get(tab_id)
        runtime = getattr(session, "runtime", None)
        thread_id = str(getattr(runtime, "thread_id", "") or "").strip()
        thread_store = getattr(runtime, "thread_store", None)
        setter = getattr(thread_store, "set_active_thread_id", None)
        if thread_id and callable(setter):
            setter(thread_id)

    def configure_manifest_path(self, path: Path | None) -> None:
        self._manifest_path = path

    def _set_manifest_restore_notice(self, key: str, **params: object) -> None:
        self._manifest_restore_notice = (key, dict(params))

    def _clear_manifest_restore_notice(self) -> None:
        self._manifest_restore_notice = None

    def pop_manifest_restore_notice(self) -> tuple[str, dict[str, object]] | None:
        notice = self._manifest_restore_notice
        self._manifest_restore_notice = None
        return notice

    def restore_from_manifest_if_available(self, source_runtime: Any) -> bool:
        return manifest_runtime.restore_from_manifest_if_available(
            self,
            source_runtime,
            collaborators=_manifest_runtime_collaborators(),
        )

    def restore_from_manifest(
        self,
        manifest: TabSessionManifest,
        *,
        source_runtime: Any,
    ) -> bool:
        return manifest_runtime.restore_from_manifest(
            self,
            manifest,
            source_runtime=source_runtime,
            collaborators=_manifest_runtime_collaborators(),
        )

    def _consume_active_restore_prefetch(
        self,
        tab_info: TabSessionManifestTab,
    ) -> CodexSidecarRestorePrefetch | None:
        return manifest_runtime._consume_active_restore_prefetch(
            self,
            tab_info,
            collaborators=_manifest_runtime_collaborators(),
        )

    @staticmethod
    def _next_serial_from_tab_order(tab_order: list[str]) -> int:
        return manifest_runtime._next_serial_from_tab_order(tab_order)

    def save_manifest(self) -> None:
        manifest_runtime.save_manifest(
            self,
            collaborators=_manifest_runtime_collaborators(),
        )

    child_tab_ids = _delegate_global("_child_tab_ids")
    child_task_runs = _delegate_global("_child_task_runs")

    def create_tab(self, *, engine: KernelEngine = "agenthub_python") -> str:
        return lifecycle_runtime.create_tab(
            self,
            engine=engine,
            collaborators=_lifecycle_runtime_collaborators(),
        )

    def fork_tab(self, from_tab_id: str) -> str:
        return lifecycle_runtime.fork_tab(
            self,
            from_tab_id,
            collaborators=_lifecycle_runtime_collaborators(),
        )

    def _rebuild_fork_transcript_from_runtime(self, tab_id: str) -> None:
        ui_state_runtime._rebuild_fork_transcript_from_runtime(
            self,
            tab_id,
            collaborators=_ui_state_runtime_collaborators(),
        )

    def switch_to_tab(self, tab_id: str) -> bool:
        return lifecycle_runtime.switch_to_tab(
            self,
            tab_id,
            collaborators=_lifecycle_runtime_collaborators(),
        )

    def close_tab(self, tab_id: str) -> str | None:
        return lifecycle_runtime.close_tab(
            self,
            tab_id,
            collaborators=_lifecycle_runtime_collaborators(),
        )

    def _save_current_state(self) -> None:
        ui_state_runtime._save_current_state(self)

    def _restore_tab_state(self, tab_id: str) -> None:
        ui_state_runtime._restore_tab_state(
            self,
            tab_id,
            collaborators=_ui_state_runtime_collaborators(),
        )

    def _ensure_runtime_restored(self, tab_id: str) -> bool:
        session = self._tabs.get(tab_id)
        if session is None or not bool(getattr(session, "runtime_restore_pending", False)):
            return True
        prefetch = getattr(session, "runtime_restore_prefetch", None)
        if isinstance(prefetch, CodexSidecarRestorePrefetch) and not prefetch.wait(0):
            self._schedule_runtime_restore_poll(tab_id)
            return True
        tab_info = getattr(session, "manifest_tab_info", None)
        if tab_info is None:
            session.runtime_restore_pending = False
            return True
        runtime = None
        prefetch = getattr(session, "runtime_restore_prefetch", None)
        if (
            isinstance(prefetch, CodexSidecarRestorePrefetch)
            and prefetch.kernel is not None
            and prefetch.session is not None
        ):
            self._app._codex_sidecar_kernel = prefetch.kernel
            runtime = _runtime_adapter_for_codex_session(
                self._app,
                tab_id,
                prefetch.kernel,
                prefetch.session,
            )
        elif isinstance(prefetch, CodexSidecarRestorePrefetch) and prefetch.error is not None:
            _record_codex_sidecar_restore_error(
                self._app,
                tab_id=str(getattr(tab_info, "tab_id", "") or ""),
                thread_id=str(getattr(tab_info, "thread_id", "") or ""),
                error=prefetch.error,
            )
        with startup_timer(f"tabs.restore_tab.{tab_id}.deferred_runtime"):
            if runtime is None:
                runtime = _resume_codex_sidecar_tab_runtime(self._app, tab_info)
        if runtime is None:
            self._set_deferred_restore_failed_notice()
            if self._fallback_deferred_restore_to_direct_runtime(tab_id, session):
                return True
            return False
        with startup_timer(f"tabs.restore_tab.{tab_id}.deferred_hydrate"):
            _hydrate_codex_runtime_from_session_metadata(runtime)
        self._bind_thread_store_update_active_getter(tab_id, runtime)
        self._bind_visible_child_tab_backend(tab_id, runtime)
        _restore_tab_provider(runtime, tab_info)
        session.runtime = runtime
        session.thread_id = str(getattr(runtime, "thread_id", "") or session.thread_id)
        session.thread_name = str(getattr(runtime, "thread_name", "") or session.thread_name)
        session.status_data = _initial_status_data_for_new_tab(self._app, runtime)
        session.engine = _tab_session_engine_for_runtime(runtime)
        session.kernel_session_id = _tab_session_kernel_session_id(runtime)
        session.runtime_restore_pending = False
        session.runtime_restore_prefetch = None
        session.manifest_tab_info = None
        session.transcript_restore_pending = True
        if session.request_worker_task is None:
            self._start_worker_task(tab_id)
        return True

    def _fallback_deferred_restore_to_direct_runtime(
        self,
        tab_id: str,
        session: TabSession,
    ) -> bool:
        return lifecycle_runtime.fallback_deferred_restore_to_direct_runtime(
            self,
            tab_id,
            session,
            collaborators=_lifecycle_runtime_collaborators(),
        )

    def _schedule_runtime_restore_poll(self, tab_id: str) -> None:
        session = self._tabs.get(tab_id)
        if session is not None and bool(getattr(session, "runtime_restore_poll_scheduled", False)):
            return
        set_timer = getattr(self._app, "set_timer", None)
        if not callable(set_timer):
            return
        if session is not None:
            session.runtime_restore_poll_scheduled = True

        def _poll() -> None:
            session = self._tabs.get(tab_id)
            if session is not None:
                session.runtime_restore_poll_scheduled = False
            if session is None or not bool(getattr(session, "runtime_restore_pending", False)):
                return
            prefetch = getattr(session, "runtime_restore_prefetch", None)
            if isinstance(prefetch, CodexSidecarRestorePrefetch) and not prefetch.wait(0):
                self._schedule_runtime_restore_poll(tab_id)
                return
            if not self._ensure_runtime_restored(tab_id):
                self._remove_unrestorable_tab(tab_id)
                if self._active_tab_id == tab_id and self._tab_order:
                    self._active_tab_id = self._tab_order[0]
                    self._restore_tab_state(self._active_tab_id)
                return
            if tab_id == self._active_tab_id:
                self._restore_tab_state(tab_id)

        if not bool(getattr(self._app, "_running", False)):
            call_after_refresh = getattr(self._app, "call_after_refresh", None)
            if callable(call_after_refresh) and call_after_refresh(_poll):
                return
            if session is not None:
                session.runtime_restore_poll_scheduled = False
            return
        try:
            set_timer(0.05, _poll)
        except RuntimeError:
            if session is not None:
                session.runtime_restore_poll_scheduled = False

    def _set_deferred_restore_failed_notice(self) -> None:
        restore_errors = [
            dict(item)
            for item in list(getattr(self._app, "_codex_sidecar_restore_errors", []) or [])
            if isinstance(item, dict)
        ]
        error_preview = "; ".join(
            (
                f"{str(item.get('tab_id') or '').strip() or '-'}"
                f":{str(item.get('thread_id') or '').strip() or '-'}"
                f":{str(item.get('error') or '').strip()}"
            ).strip(":")
            for item in restore_errors[:3]
        )
        self._set_manifest_restore_notice(
            (
                "system.tab_manifest_restore_partial_detail"
                if error_preview
                else "system.tab_manifest_restore_partial"
            ),
            path=str(self._manifest_path or ""),
            restored_count=max(0, len(self._tab_order) - 1),
            skipped_count=1,
            error_preview=error_preview,
        )

    def _remove_unrestorable_tab(self, tab_id: str) -> None:
        lifecycle_runtime.remove_unrestorable_tab(
            self,
            tab_id,
            collaborators=_lifecycle_runtime_collaborators(),
        )

    def _current_transcript_scroll_offset(self) -> tuple[int, int]:
        return ui_state_runtime._current_transcript_scroll_offset(self)

    def _restore_transcript_scroll(self, log: Any, session: TabSession) -> None:
        ui_state_runtime._restore_transcript_scroll(self, log, session)

    @staticmethod
    def _scroll_widget_to(log: Any, *, scroll_x: int, scroll_y: int) -> None:
        ui_state_runtime._scroll_widget_to(log, scroll_x=scroll_x, scroll_y=scroll_y)

    def _start_worker_task(self, tab_id: str) -> None:
        session = self._tabs[tab_id]
        if bool(getattr(session, "runtime_restore_pending", False)):
            return
        _start_tab_request_worker_task(session, self._app, tab_id)

    def _cancel_worker_task(self, tab_id: str) -> None:
        _cancel_tab_request_worker_task(self._tabs.get(tab_id))


TabSessionManager.fork_child_tab = _delegate_global("_fork_child_tab")
TabSessionManager.dispatch_visible_child_task = _delegate_global("_dispatch_visible_child_task")
TabSessionManager._dispatch_visible_child_task_on_app_thread = _delegate_global(
    "_dispatch_visible_child_task_on_app_thread"
)
TabSessionManager.send_visible_child_task = _delegate_global("_send_visible_child_task")
TabSessionManager._send_visible_child_task_on_app_thread = _delegate_global(
    "_send_visible_child_task_on_app_thread"
)
TabSessionManager.visible_child_task_run_snapshots = _delegate_global(
    "_visible_child_task_run_snapshots"
)
TabSessionManager._child_task_update_payload = _delegate_global("_child_task_update_payload")
TabSessionManager._child_task_update_notice = _static_delegate_global("_child_task_update_notice")
TabSessionManager._append_system_notice_to_tab = _delegate_global("_append_system_notice_to_tab")
TabSessionManager._publish_child_task_run_update = _delegate_global(
    "_publish_child_task_run_update"
)
TabSessionManager._child_task_updates_context_text = _static_delegate_global(
    "_child_task_updates_context_text"
)
TabSessionManager.prepare_runtime_request_for_tab = _delegate_global(
    "_prepare_runtime_request_for_tab"
)
TabSessionManager._task_status_snapshot_for_session = _delegate_global(
    "_task_status_snapshot_for_session"
)
TabSessionManager._task_transcript_index_for_session = _delegate_global(
    "_task_transcript_index_for_session"
)
TabSessionManager._next_task_run_id = _delegate_global("_next_task_run_id")
TabSessionManager._assignment_ref_from_request = _static_delegate_global(
    "_assignment_ref_from_request"
)
TabSessionManager.start_task_run = _delegate_global("_start_task_run")
TabSessionManager.complete_task_run = _delegate_global("_complete_task_run")
TabSessionManager.fail_task_run = _delegate_global("_fail_task_run")
TabSessionManager.active_session = property(title_runtime.active_session)
TabSessionManager.active_tab_id = property(title_runtime.active_tab_id)
TabSessionManager.get = title_runtime.get
TabSessionManager._base_tab_label = title_runtime._base_tab_label
TabSessionManager._decorated_tab_label = title_runtime._decorated_tab_label
TabSessionManager.tab_labels = title_runtime.tab_labels
TabSessionManager.display_tab_label = title_runtime.display_tab_label
TabSessionManager.rename_tab = title_runtime.rename_tab
TabSessionManager.mark_master = title_runtime.mark_master
