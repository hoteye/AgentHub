from __future__ import annotations

# ruff: noqa: F401,I001

import json
from pathlib import Path
from typing import Any

from cli.agent_cli.models import PromptResponse
from cli.agent_cli.runtime_kernels.base import (
    ForkSessionRequest,
    KernelEngine,
    ResumeSessionRequest,
    StartSessionRequest,
)
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
    _record_codex_sidecar_restore_error,
    _resume_codex_sidecar_tab_runtime,
    _run_coro_blocking,
    _runtime_adapter_for_codex_session,
    _runtime_policy_metadata_for_sidecar,
    _should_fallback_to_start_for_codex_fork,
)
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
from cli.agent_cli.ui.runtime_bridge import QueuedRuntimeRequest
from cli.agent_cli.ui.tab_session_manager_task_runs import (
    _assignment_ref_from_request,
    _next_task_run_id,
    _task_status_snapshot_for_session,
    _task_transcript_index_for_session,
    complete_task_run as _complete_task_run,
    fail_task_run as _fail_task_run,
    start_task_run as _start_task_run,
)
from cli.agent_cli.ui.tab_task_run import TabTaskRun
from cli.agent_cli.ui.tab_session_manifest import (
    TabSessionManifest,
    TabSessionManifestTab,
    load_tab_session_manifest,
    save_tab_session_manifest,
    tab_manifest_enabled_for_runtime,
    tab_manifest_path_for_runtime,
)


class TabSessionManager:
    MAX_TABS = 8

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

    @property
    def active_session(self) -> TabSession:
        return self._tabs[self._active_tab_id]

    @property
    def active_tab_id(self) -> str:
        return self._active_tab_id

    def get(self, tab_id: str) -> TabSession | None:
        return self._tabs.get(tab_id)

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
        self._clear_manifest_restore_notice()
        if not tab_manifest_enabled_for_runtime(source_runtime):
            return False
        manifest_path = self._manifest_path or tab_manifest_path_for_runtime(source_runtime)
        self.configure_manifest_path(manifest_path)
        if not manifest_path.exists():
            return False
        manifest = load_tab_session_manifest(manifest_path)
        if manifest is None:
            self._set_manifest_restore_notice(
                "system.tab_manifest_restore_failed",
                path=str(manifest_path),
            )
            return False
        return self.restore_from_manifest(manifest, source_runtime=source_runtime)

    def restore_from_manifest(
        self,
        manifest: TabSessionManifest,
        *,
        source_runtime: Any,
    ) -> bool:
        self._clear_manifest_restore_notice()
        restored: dict[str, TabSession] = {}
        restored_order: list[str] = []
        skipped_count = 0
        source_thread_id = str(getattr(source_runtime, "thread_id", "") or "").strip()
        for tab_info in manifest.tabs:
            if tab_info.engine == "codex_sidecar":
                runtime = _resume_codex_sidecar_tab_runtime(self._app, tab_info)
            else:
                runtime = source_runtime if tab_info.thread_id == source_thread_id else None
            if runtime is None and tab_info.engine != "codex_sidecar":
                runtime = _clone_tab_runtime(self._app, tab_info.tab_id, source_runtime)
            if runtime is None:
                skipped_count += 1
                continue
            if tab_info.engine != "codex_sidecar":
                try:
                    if str(getattr(runtime, "thread_id", "") or "").strip() != tab_info.thread_id:
                        runtime.resume_thread(tab_info.thread_id)
                    set_cwd = getattr(runtime, "set_cwd", None)
                    if callable(set_cwd):
                        set_cwd(getattr(source_runtime, "cwd", "") or getattr(runtime, "cwd", ""))
                except Exception:
                    if runtime is source_runtime:
                        self._set_manifest_restore_notice(
                            "system.tab_manifest_restore_failed",
                            path=str(self._manifest_path or ""),
                        )
                        return False
                    skipped_count += 1
                    continue
            elif str(getattr(runtime, "thread_id", "") or "").strip() != tab_info.thread_id:
                skipped_count += 1
                continue
            if tab_info.engine == "codex_sidecar":
                _hydrate_codex_runtime_from_session_metadata(runtime)
            self._bind_thread_store_update_active_getter(tab_info.tab_id, runtime)
            self._bind_visible_child_tab_backend(tab_info.tab_id, runtime)
            _restore_tab_provider(runtime, tab_info)
            entries, lines = _restore_runtime_transcript_snapshot(self._app, runtime)
            queue = _create_request_queue()
            restored[tab_info.tab_id] = TabSession(
                tab_id=tab_info.tab_id,
                thread_id=str(getattr(runtime, "thread_id", "") or tab_info.thread_id),
                thread_name=str(getattr(runtime, "thread_name", "") or tab_info.thread_name),
                runtime=runtime,
                request_queue=queue,
                status_data=_initial_status_data_for_new_tab(self._app, runtime),
                allow_legacy_approval_hydration=False,
                engine=_tab_session_engine_for_runtime(runtime),
                kernel_session_id=_tab_session_kernel_session_id(runtime),
                top_title_text=tab_info.title or tab_info.thread_name or tab_info.tab_id,
                custom_label=tab_info.custom_label,
                transcript_entries=entries,
                transcript_lines=lines,
                prompt_text=tab_info.prompt_text,
                prompt_cursor_position=tab_info.prompt_cursor_position,
                forked_from_tab_id=tab_info.forked_from_tab_id,
                forked_from_thread_id=tab_info.forked_from_thread_id,
                fork_mode=tab_info.fork_mode,
                role=tab_info.role,
                parent_tab_id=tab_info.parent_tab_id,
                transcript_scroll_x=max(0, int(getattr(tab_info, "scroll_x", 0) or 0)),
                transcript_scroll_y=max(0, int(getattr(tab_info, "scroll_y", 0) or 0)),
            )
        for tab_id in list(manifest.tab_order or []):
            if tab_id in restored and tab_id not in restored_order:
                restored_order.append(tab_id)
        for tab_id in restored:
            if tab_id not in restored_order:
                restored_order.append(tab_id)
        if not restored_order:
            self._set_manifest_restore_notice(
                "system.tab_manifest_restore_failed",
                path=str(self._manifest_path or ""),
            )
            return False
        self._tabs = restored
        self._tab_order = restored_order
        self._active_tab_id = (
            manifest.active_tab_id if manifest.active_tab_id in restored else restored_order[0]
        )
        self._next_tab_serial = self._next_serial_from_tab_order(restored_order)
        self._set_active_thread_id_for_tab(self._active_tab_id)
        self._restore_tab_state(self._active_tab_id)
        try:
            self._app._tab_manifest_restored = True
        except Exception:
            pass
        if skipped_count:
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
                restored_count=len(restored_order),
                skipped_count=skipped_count,
                error_preview=error_preview,
            )
        return True

    @staticmethod
    def _next_serial_from_tab_order(tab_order: list[str]) -> int:
        next_serial = 1
        for tab_id in tab_order:
            if not str(tab_id).startswith("tab-"):
                continue
            try:
                serial = int(str(tab_id).split("-", 1)[1])
            except (IndexError, ValueError):
                continue
            next_serial = max(next_serial, serial + 1)
        return next_serial

    def save_manifest(self) -> None:
        if self._manifest_path is None:
            return
        self._save_current_state()
        tabs = []
        for tab_id in self._tab_order:
            session = self._tabs.get(tab_id)
            if session is None:
                continue
            runtime = session.runtime
            thread_id = str(getattr(runtime, "thread_id", "") or session.thread_id).strip()
            if not thread_id:
                continue
            status = {}
            try:
                status = dict(runtime.agent.provider_status() or {})
            except Exception:
                status = {}
            tabs.append(
                TabSessionManifestTab(
                    tab_id=tab_id,
                    thread_id=thread_id,
                    thread_name=str(getattr(runtime, "thread_name", "") or session.thread_name),
                    title=session.top_title_text,
                    custom_label=session.custom_label,
                    prompt_text=session.prompt_text,
                    prompt_cursor_position=session.prompt_cursor_position,
                    cwd=str(getattr(runtime, "cwd", "") or ""),
                    provider_name=str(status.get("provider_name") or ""),
                    provider_model=str(
                        status.get("provider_model") or status.get("model_key") or ""
                    ),
                    engine=session.engine,
                    kernel_session_id=session.kernel_session_id,
                    forked_from_tab_id=session.forked_from_tab_id,
                    forked_from_thread_id=session.forked_from_thread_id,
                    fork_mode=session.fork_mode,
                    role=session.role,
                    parent_tab_id=session.parent_tab_id,
                    scroll_x=max(0, int(session.transcript_scroll_x or 0)),
                    scroll_y=max(0, int(session.transcript_scroll_y or 0)),
                )
            )
        if not tabs:
            return
        save_tab_session_manifest(
            self._manifest_path,
            TabSessionManifest(
                active_tab_id=self._active_tab_id,
                tab_order=list(self._tab_order),
                tabs=tabs,
            ),
        )

    def _base_tab_label(self, session: TabSession) -> str:
        return (
            session.custom_label or session.thread_name or session.top_title_text or session.tab_id
        )

    def _decorated_tab_label(self, session: TabSession) -> str:
        label = self._base_tab_label(session)
        role = str(getattr(session, "role", "standalone") or "standalone").strip()
        if role == "master":
            return f"[M] {label}"
        if role == "child":
            return f"[C] {label}"
        return label

    def tab_labels(self) -> list[tuple[str, str, bool]]:
        return [
            (s.tab_id, self._decorated_tab_label(s), s.is_busy)
            for s in (self._tabs[tid] for tid in self._tab_order)
        ]

    def display_tab_label(self, tab_id: str) -> str:
        normalized = str(tab_id or "").strip()
        if not normalized:
            return ""
        try:
            index = self._tab_order.index(normalized)
        except ValueError:
            return "?"
        alphabet = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        code = alphabet[index] if 0 <= index < len(alphabet) else str(index + 1)
        return code

    def rename_tab(self, tab_id: str, label: str) -> bool:
        session = self._tabs.get(tab_id)
        if session is None:
            return False
        session.custom_label = " ".join(str(label or "").split())
        self.save_manifest()
        return True

    def mark_master(self, tab_id: str) -> bool:
        session = self._tabs.get(tab_id)
        if session is None:
            return False
        session.role = "master"
        session.parent_tab_id = ""
        self.save_manifest()
        return True

    def child_tab_ids(self, parent_tab_id: str) -> list[str]:
        return [
            tab_id
            for tab_id in self._tab_order
            if str(getattr(self._tabs.get(tab_id), "parent_tab_id", "") or "") == parent_tab_id
        ]

    def child_task_runs(self, parent_tab_id: str) -> list[TabTaskRun]:
        runs: list[TabTaskRun] = []
        for tab_id in self.child_tab_ids(parent_tab_id):
            session = self._tabs.get(tab_id)
            if session is None:
                continue
            runs.extend(list(getattr(session, "task_history", []) or []))
            current = getattr(session, "current_task_run", None)
            if current is not None:
                runs.append(current)
        return runs

    def create_tab(self, *, engine: KernelEngine = "agenthub_python") -> str:
        if len(self._tabs) >= self.MAX_TABS:
            return ""
        tab_id = f"tab-{self._next_tab_serial}"
        self._next_tab_serial += 1
        self._save_current_state()
        runtime = _build_runtime_for_engine(self._app, tab_id, engine)
        if runtime is None:
            self._next_tab_serial -= 1
            return ""
        queue = _create_request_queue()
        kernel_session = getattr(runtime, "kernel_session", None)
        session = TabSession(
            tab_id=tab_id,
            thread_id=runtime.thread_id,
            thread_name=runtime.thread_name or "",
            runtime=runtime,
            request_queue=queue,
            status_data=_initial_status_data_for_new_tab(self._app, runtime),
            allow_legacy_approval_hydration=False,
            engine=engine,
            kernel_session_id=str(getattr(kernel_session, "session_id", "") or ""),
        )
        self._tabs[tab_id] = session
        self._tab_order.append(tab_id)
        self._active_tab_id = tab_id
        self._bind_thread_store_update_active_getter(tab_id, runtime)
        self._bind_visible_child_tab_backend(tab_id, runtime)
        self._set_active_thread_id_for_tab(tab_id)
        self._start_worker_task(tab_id)
        self._restore_tab_state(tab_id)
        self.save_manifest()
        return tab_id

    def fork_child_tab(self, from_tab_id: str) -> str:
        source = self._tabs.get(from_tab_id)
        if source is None:
            return ""
        tab_id = self.fork_tab(from_tab_id)
        if not tab_id:
            return ""
        child = self._tabs.get(tab_id)
        source.role = "master"
        source.parent_tab_id = ""
        if child is not None:
            child.role = "child"
            child.parent_tab_id = source.tab_id
            child.custom_label = (
                child.custom_label or f"child {len(self.child_tab_ids(source.tab_id))}"
            )
        self.save_manifest()
        return tab_id

    def dispatch_visible_child_task(
        self,
        *,
        parent_tab_id: str,
        task_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._app is not None:
            call_from_thread = getattr(self._app, "call_from_thread", None)
            if callable(call_from_thread):
                try:
                    return dict(
                        call_from_thread(
                            self._dispatch_visible_child_task_on_app_thread,
                            parent_tab_id=parent_tab_id,
                            task_text=task_text,
                            metadata=dict(metadata or {}),
                        )
                    )
                except RuntimeError:
                    pass
        return self._dispatch_visible_child_task_on_app_thread(
            parent_tab_id=parent_tab_id,
            task_text=task_text,
            metadata=dict(metadata or {}),
        )

    def _dispatch_visible_child_task_on_app_thread(
        self,
        *,
        parent_tab_id: str,
        task_text: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        parent = self._tabs.get(parent_tab_id)
        if parent is None:
            raise RuntimeError(f"unknown parent tab: {parent_tab_id}")
        previous_active = self._active_tab_id
        child_tab_id = self.fork_child_tab(parent_tab_id)
        if not child_tab_id:
            raise RuntimeError("unable to create visible child tab")
        child = self._tabs.get(child_tab_id)
        if child is None:
            raise RuntimeError("visible child tab was not created")
        card_id = str(metadata.get("card_id") or "").strip()
        run_id = str(metadata.get("run_id") or "").strip()
        child.task_run_serial = max(0, int(child.task_run_serial or 0)) + 1
        task_run_id = f"{child_tab_id}-run-{child.task_run_serial}"
        if card_id:
            child.custom_label = f"{card_id}"
        if previous_active in self._tabs and self._active_tab_id != previous_active:
            self.switch_to_tab(previous_active)
        from cli.agent_cli.ui.runtime_bridge import QueuedRuntimeRequest

        child.request_queue.put_nowait(
            QueuedRuntimeRequest(
                text=str(task_text or ""),
                attachments=[],
                display_text=str(task_text or ""),
                display_attachments=[],
                priority="next",
                metadata={
                    "orchestration": {
                        "run_id": run_id,
                        "card_id": card_id,
                        "attempt": int(metadata.get("attempt") or 0),
                    },
                    "agenthub_task_run_id": task_run_id,
                    **dict(metadata or {}),
                },
            )
        )
        provider = ""
        model = ""
        try:
            status = dict(child.runtime.agent.provider_status() or {})
            provider = str(status.get("provider_name") or status.get("provider") or "")
            model = str(status.get("provider_model") or status.get("model_key") or "")
        except Exception:
            pass
        self.save_manifest()
        return {
            "tab_id": child_tab_id,
            "task_id": f"{run_id}:{card_id}:{int(metadata.get('attempt') or 0)}",
            "task_run_id": task_run_id,
            "provider_name": provider,
            "model": model,
            "route_label": "dispatch_visible_child_tab",
        }

    def send_visible_child_task(
        self,
        *,
        parent_tab_id: str,
        child_tab_id: str,
        task_text: str,
        interrupt: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._app is not None:
            call_from_thread = getattr(self._app, "call_from_thread", None)
            if callable(call_from_thread):
                try:
                    return dict(
                        call_from_thread(
                            self._send_visible_child_task_on_app_thread,
                            parent_tab_id=parent_tab_id,
                            child_tab_id=child_tab_id,
                            task_text=task_text,
                            interrupt=interrupt,
                            metadata=dict(metadata or {}),
                        )
                    )
                except RuntimeError:
                    pass
        return self._send_visible_child_task_on_app_thread(
            parent_tab_id=parent_tab_id,
            child_tab_id=child_tab_id,
            task_text=task_text,
            interrupt=interrupt,
            metadata=dict(metadata or {}),
        )

    def _send_visible_child_task_on_app_thread(
        self,
        *,
        parent_tab_id: str,
        child_tab_id: str,
        task_text: str,
        interrupt: bool,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        child = self._tabs.get(child_tab_id)
        if child is None:
            raise RuntimeError(f"unknown child tab: {child_tab_id}")
        actual_parent = str(getattr(child, "parent_tab_id", "") or "").strip()
        if actual_parent != parent_tab_id:
            raise RuntimeError(f"tab {child_tab_id} is not a child of {parent_tab_id}")
        if child.request_queue is None:
            raise RuntimeError(f"child tab {child_tab_id} has no request queue")
        from cli.agent_cli.ui.runtime_bridge import QueuedRuntimeRequest

        child.task_run_serial = max(0, int(child.task_run_serial or 0)) + 1
        task_run_id = f"{child_tab_id}-run-{child.task_run_serial}"
        child.request_queue.put_nowait(
            QueuedRuntimeRequest(
                text=str(task_text or ""),
                attachments=[],
                display_text=str(task_text or ""),
                display_attachments=[],
                priority="now" if interrupt else "next",
                metadata={
                    "visible_child": {
                        "parent_tab_id": parent_tab_id,
                        "child_tab_id": child_tab_id,
                        "interrupt": bool(interrupt),
                    },
                    "agenthub_task_run_id": task_run_id,
                    **dict(metadata or {}),
                },
            )
        )
        return {
            "tab_id": child_tab_id,
            "parent_tab_id": parent_tab_id,
            "task_run_id": task_run_id,
            "queued": True,
            "priority": "now" if interrupt else "next",
            "route_label": "send_visible_child_tab",
        }

    def visible_child_task_run_snapshots(self, parent_tab_id: str) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for tab_id in self.child_tab_ids(parent_tab_id):
            session = self._tabs.get(tab_id)
            if session is None:
                continue
            for run in list(getattr(session, "task_history", []) or []):
                runs.append(run.to_dict())
            current = getattr(session, "current_task_run", None)
            if current is not None:
                runs.append(current.to_dict())
            queue = getattr(session, "request_queue", None)
            if queue is None:
                continue
            try:
                queued_items = list(getattr(queue, "_queue", []) or [])
            except Exception:
                queued_items = []
            for request in queued_items:
                metadata = getattr(request, "metadata", None)
                if not isinstance(metadata, dict):
                    metadata = {}
                task_run_id = str(metadata.get("agenthub_task_run_id") or "").strip()
                if not task_run_id:
                    continue
                runs.append(
                    {
                        "run_id": task_run_id,
                        "tab_id": tab_id,
                        "parent_tab_id": parent_tab_id,
                        "provider": "",
                        "engine": str(getattr(session, "engine", "") or ""),
                        "state": "queued",
                        "terminal_state": "",
                        "terminal_reason": "",
                        "objective_state": "not_reported",
                        "started_at": 0.0,
                        "finished_at": None,
                        "user_prompt": str(getattr(request, "text", "") or ""),
                        "summary": "",
                        "error_message": "",
                        "transcript_range": [0, 0],
                        "provider_terminal_event": None,
                        "status_snapshot": dict(getattr(session, "status_data", {}) or {}),
                        "assignment_ref": self._assignment_ref_from_request(request),
                    }
                )
        return runs

    def _child_task_update_payload(self, run: TabTaskRun) -> dict[str, Any]:
        payload = run.to_dict()
        child = self._tabs.get(run.tab_id)
        child_name = ""
        if child is not None:
            child_name = str(child.custom_label or child.thread_name or "").strip()
        payload["child_display_tab"] = self.display_tab_label(run.tab_id)
        payload["child_label"] = child_name or payload["child_display_tab"]
        return payload

    @staticmethod
    def _child_task_update_notice(payload: dict[str, Any]) -> str:
        label = str(payload.get("child_label") or payload.get("child_display_tab") or "-")
        terminal = str(payload.get("terminal_state") or "-")
        objective = str(payload.get("objective_state") or "-")
        run_id = str(payload.get("run_id") or "-")
        summary = " ".join(str(payload.get("summary") or "").split())
        if len(summary) > 160:
            summary = summary[:157].rstrip() + "..."
        suffix = f" summary={summary}" if summary else ""
        return (
            f"Child tab {label} finished: terminal={terminal} "
            f"objective={objective} run_id={run_id}{suffix}"
        )

    def _append_system_notice_to_tab(self, tab_id: str, text: str, *, unread: bool) -> None:
        session = self._tabs.get(tab_id)
        if session is None:
            return
        app = self._app
        if app is not None:
            write_notice = getattr(app, "_write_system_notice", None)
            if tab_id == self._active_tab_id and callable(write_notice):
                write_notice(text)
                session.transcript_entries = list(getattr(app, "_transcript_entries", []) or [])
                session.transcript_lines = list(getattr(app, "_transcript_lines", []) or [])
                return
            run_with_state = getattr(app, "_run_with_tab_transcript_state", None)
            mark_updated = getattr(app, "_mark_tab_transcript_updated", None)
            if callable(write_notice) and callable(run_with_state):
                run_with_state(session, lambda: write_notice(text))
                if callable(mark_updated):
                    mark_updated(tab_id, unread=unread)
                return
        from cli.agent_cli.ui.transcript_history import system_notice_entry
        from cli.agent_cli.ui.transcript_visual_rendering import render_transcript_entries

        session.transcript_entries = [
            *list(session.transcript_entries or []),
            system_notice_entry(text),
        ]
        session.transcript_lines = render_transcript_entries(session.transcript_entries)
        session.transcript_dirty = True
        if unread:
            session.has_unread_output = True

    def _publish_child_task_run_update(self, run: TabTaskRun) -> None:
        parent_tab_id = str(run.parent_tab_id or "").strip()
        if not parent_tab_id:
            return
        parent = self._tabs.get(parent_tab_id)
        if parent is None:
            return
        payload = self._child_task_update_payload(run)
        run_id = str(payload.get("run_id") or "").strip()
        existing_ids = {
            str(item.get("run_id") or "").strip()
            for item in list(parent.child_task_inbox or [])
            if isinstance(item, dict)
        }
        if run_id and run_id not in existing_ids:
            parent.child_task_inbox.append(payload)
        self._append_system_notice_to_tab(
            parent_tab_id,
            self._child_task_update_notice(payload),
            unread=parent_tab_id != self._active_tab_id,
        )

    @staticmethod
    def _child_task_updates_context_text(updates: list[dict[str, Any]]) -> str:
        payload = json.dumps(updates, ensure_ascii=True, indent=2, sort_keys=True)
        return (
            "\n\n<agenthub_visible_child_task_updates>\n"
            "These visible child tab TaskRun results completed since your previous "
            "turn. Use them as structured context; do not ask the user to paste "
            "child transcripts.\n"
            f"{payload}\n"
            "</agenthub_visible_child_task_updates>"
        )

    def prepare_runtime_request_for_tab(
        self,
        tab_id: str,
        request: QueuedRuntimeRequest,
    ) -> QueuedRuntimeRequest:
        session = self._tabs.get(tab_id)
        if session is None:
            return request
        text = str(getattr(request, "text", "") or "")
        if text.strip().startswith("/"):
            return request
        updates = [
            dict(item)
            for item in list(getattr(session, "child_task_inbox", []) or [])
            if isinstance(item, dict)
        ]
        if not updates:
            return request
        session.child_task_inbox = []
        metadata = dict(getattr(request, "metadata", None) or {})
        metadata["visible_child_task_updates"] = updates
        return QueuedRuntimeRequest(
            text=text + self._child_task_updates_context_text(updates),
            attachments=list(getattr(request, "attachments", []) or []),
            display_text=getattr(request, "display_text", None),
            display_attachments=getattr(request, "display_attachments", None),
            priority=getattr(request, "priority", "next"),
            metadata=metadata,
        )

    def _task_status_snapshot_for_session(self, session: TabSession) -> dict[str, Any]:
        return _task_status_snapshot_for_session(session)

    def _task_transcript_index_for_session(self, session: TabSession) -> int:
        return _task_transcript_index_for_session(session, self._active_tab_id, self._app)

    def _next_task_run_id(self, session: TabSession) -> str:
        return _next_task_run_id(session)

    @staticmethod
    def _assignment_ref_from_request(request: Any) -> dict[str, Any]:
        return _assignment_ref_from_request(request)

    def start_task_run(self, tab_id: str, request: Any) -> TabTaskRun | None:
        return _start_task_run(tab_id, request, self._tabs, self._active_tab_id, self._app)

    def complete_task_run(
        self,
        tab_id: str,
        task_run: object,
        response: PromptResponse,
    ) -> TabTaskRun | None:
        run = _complete_task_run(
            tab_id, task_run, response, self._tabs, self._active_tab_id, self._app
        )
        if run is not None and run.is_terminal:
            self._publish_child_task_run_update(run)
        return run

    def fail_task_run(
        self,
        tab_id: str,
        task_run: object,
        error: BaseException,
    ) -> TabTaskRun | None:
        run = _fail_task_run(tab_id, task_run, error, self._tabs, self._active_tab_id, self._app)
        if run is not None:
            self._publish_child_task_run_update(run)
        return run

    def fork_tab(self, from_tab_id: str) -> str:
        if len(self._tabs) >= self.MAX_TABS:
            return ""
        source = self._tabs.get(from_tab_id)
        if source is None or source.runtime is None:
            return ""
        # Snapshot busy state before _save_current_state() overwrites it.
        source_was_busy = source.is_busy
        tab_id = f"tab-{self._next_tab_serial}"
        self._next_tab_serial += 1
        self._save_current_state()
        runtime = _fork_tab_runtime(self._app, tab_id, source_runtime=source.runtime)
        if runtime is None:
            self._next_tab_serial -= 1
            return ""
        queue = _create_request_queue()
        # Idle source: copy UI transcript directly (matches runtime history).
        # Busy source: skip live transcript — will rebuild from persisted turns.
        if source_was_busy:
            fork_entries: list = []
            fork_lines: list = []
            fork_prompt = ""
        elif _is_codex_sidecar_runtime(source.runtime):
            fork_entries = []
            fork_lines = []
            fork_prompt = source.prompt_text
        else:
            fork_entries = list(source.transcript_entries)
            fork_lines = list(source.transcript_lines)
            fork_prompt = source.prompt_text
        session = TabSession(
            tab_id=tab_id,
            thread_id=runtime.thread_id,
            thread_name=runtime.thread_name or "",
            runtime=runtime,
            request_queue=queue,
            engine=_tab_session_engine_for_runtime(runtime),
            kernel_session_id=_tab_session_kernel_session_id(runtime),
            status_data=(
                _initial_status_data_for_new_tab(self._app, runtime)
                if source_was_busy
                else _fork_status_data_for_runtime(source.status_data, runtime)
            ),
            allow_legacy_approval_hydration=False,
            transcript_entries=fork_entries,
            transcript_lines=fork_lines,
            prompt_text=fork_prompt,
            forked_from_tab_id=source.tab_id,
            forked_from_thread_id=str(getattr(source.runtime, "thread_id", "") or ""),
            fork_mode="running" if source_was_busy else "idle",
        )
        self._tabs[tab_id] = session
        self._tab_order.append(tab_id)
        self._active_tab_id = tab_id
        self._bind_thread_store_update_active_getter(tab_id, runtime)
        self._bind_visible_child_tab_backend(tab_id, runtime)
        self._set_active_thread_id_for_tab(tab_id)
        self._start_worker_task(tab_id)
        self._restore_tab_state(tab_id)
        # For busy source, rebuild transcript from fork runtime's persisted history
        # so UI matches what the provider actually has.
        if source_was_busy or _is_codex_sidecar_runtime(runtime):
            if _is_codex_sidecar_runtime(runtime):
                _hydrate_codex_runtime_from_session_metadata(runtime)
            self._rebuild_fork_transcript_from_runtime(tab_id)
        self.save_manifest()
        return tab_id

    def _rebuild_fork_transcript_from_runtime(self, tab_id: str) -> None:
        from cli.agent_cli.ui.transcript_history import system_notice_entry
        from cli.agent_cli.ui.transcript_visual_rendering import render_transcript_entries

        app = self._app
        session = self._tabs.get(tab_id)
        if session is None:
            return
        app._transcript_entries = []
        app._transcript_lines = []
        # Try rebuild from history_turns (full formatted transcript with proper entries)
        try:
            app._restore_transcript_from_runtime_history()
        except Exception:
            pass
        # If history_turns was empty, rebuild from structured replay items
        # first. runtime.history is a simplified user/assistant projection and
        # can omit provider-visible reasoning and tool replay context.
        if not app._transcript_lines and session.runtime is not None:
            entries = []
            for item in _fork_runtime_transcript_source_items(session.runtime):
                entry = _history_item_to_transcript_entry(item)
                if entry is not None:
                    entries.append(entry)
            if entries:
                app._transcript_entries = entries
                app._transcript_lines = render_transcript_entries(entries)
        notice = system_notice_entry(RUNNING_FORK_NOTICE)
        app._transcript_entries = [*list(app._transcript_entries), notice]
        app._transcript_lines = render_transcript_entries(app._transcript_entries)
        session.transcript_entries = list(app._transcript_entries)
        session.transcript_lines = list(app._transcript_lines)
        # Sync UI widget with rebuilt transcript
        self._restore_tab_state(tab_id)

    def switch_to_tab(self, tab_id: str) -> bool:
        if tab_id == self._active_tab_id or tab_id not in self._tabs:
            return False
        self._save_current_state()
        self._active_tab_id = tab_id
        self._set_active_thread_id_for_tab(tab_id)
        self._restore_tab_state(tab_id)
        self.save_manifest()
        return True

    def close_tab(self, tab_id: str) -> str | None:
        if len(self._tabs) <= 1:
            return None
        session = self._tabs.get(tab_id)
        if session is None:
            return None
        if session.is_busy:
            return None
        self._cancel_worker_task(tab_id)
        idx = self._tab_order.index(tab_id)
        self._tab_order.remove(tab_id)
        del self._tabs[tab_id]
        if tab_id == self._active_tab_id:
            new_idx = min(idx, len(self._tab_order) - 1)
            new_tab_id = self._tab_order[new_idx]
            self._active_tab_id = new_tab_id
            self._set_active_thread_id_for_tab(new_tab_id)
            self._restore_tab_state(new_tab_id)
            self.save_manifest()
            return new_tab_id
        self.save_manifest()
        return self._active_tab_id

    def _save_current_state(self) -> None:
        session = self._tabs.get(self._active_tab_id)
        if session is None:
            return
        app = self._app
        session.is_busy = getattr(app, "_busy", False)
        session.top_title_text = str(getattr(app, "_top_title_text", "AgentHub"))
        session.status_data = dict(getattr(app, "status_data", {}) or {})
        session.transcript_entries = list(getattr(app, "_transcript_entries", []))
        session.transcript_lines = list(getattr(app, "_transcript_lines", []))
        scroll_x, scroll_y = self._current_transcript_scroll_offset()
        if scroll_x > 0 or scroll_y > 0:
            session.transcript_scroll_x = scroll_x
            session.transcript_scroll_y = scroll_y
        try:
            from cli.agent_cli.ui import PromptComposer

            composer = app.query_one("#prompt_composer", PromptComposer)
            session.prompt_text = composer.text
            session.prompt_cursor_position = int(getattr(composer, "cursor_pos", 0) or 0)
        except Exception:
            pass

    def _restore_tab_state(self, tab_id: str) -> None:
        session = self._tabs.get(tab_id)
        if session is None:
            return
        app = self._app
        app._busy = session.is_busy
        app._top_title_text = session.top_title_text
        session.status_data = _merge_status_preserving_known_values(
            session.status_data,
            _provider_status_for_runtime(session.runtime),
        )
        app._transcript_entries = list(session.transcript_entries)
        app._transcript_lines = list(session.transcript_lines)
        screen_mode = str(getattr(app, "_screen_mode", "prompt") or "prompt").strip().lower()
        if screen_mode == "transcript":
            try:
                app._transcript_screen_snapshot_entries = app._snapshot_transcript_entries(
                    app._transcript_entries
                )
            except Exception:
                app._transcript_screen_snapshot_entries = list(app._transcript_entries)
        else:
            app._transcript_screen_snapshot_entries = None
        try:
            from cli.agent_cli.ui import PromptComposer

            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text(session.prompt_text)
            set_cursor = getattr(composer, "_set_cursor_position", None)
            if callable(set_cursor):
                set_cursor(session.prompt_cursor_position, extend=False)
                composer.refresh(repaint=True, layout=False)
        except Exception:
            pass
        try:
            from cli.agent_cli.ui import TranscriptArea, TranscriptVirtualList

            if screen_mode == "transcript":
                app._sync_transcript()
                log = app.query_one("#transcript_log", TranscriptVirtualList)
            else:
                log = app.query_one("#main_log", TranscriptArea)
                log.load_transcript(app._transcript_lines)
            self._restore_transcript_scroll(log, session)
        except Exception:
            pass
        session.transcript_dirty = False
        session.has_unread_output = False
        restore_pending = getattr(app, "_restore_pending_interactions_for_tab", None)
        if callable(restore_pending):
            try:
                restore_pending(tab_id)
            except Exception:
                pass
        update_fn = getattr(app, "_update_status", None)
        if callable(update_fn):
            try:
                update_fn({})
            except Exception:
                pass

    def _current_transcript_scroll_offset(self) -> tuple[int, int]:
        app = self._app
        screen_mode = str(getattr(app, "_screen_mode", "prompt") or "prompt").strip().lower()
        widget_id = "#transcript_log" if screen_mode == "transcript" else "#main_log"
        try:
            from cli.agent_cli.ui import TranscriptArea, TranscriptVirtualList

            widget_type = TranscriptVirtualList if screen_mode == "transcript" else TranscriptArea
            log = app.query_one(widget_id, widget_type)
        except Exception:
            return (0, 0)
        helper = getattr(log, "transcript_scroll_offset", None)
        if callable(helper):
            try:
                scroll_x, scroll_y = helper()
                return (max(0, int(scroll_x)), max(0, int(scroll_y)))
            except Exception:
                pass
        try:
            offset = log.scroll_offset
            return (max(0, int(offset.x)), max(0, int(offset.y)))
        except Exception:
            pass
        try:
            return (max(0, int(log.scroll_x)), max(0, int(log.scroll_y)))
        except Exception:
            return (0, 0)

    def _restore_transcript_scroll(self, log: Any, session: TabSession) -> None:
        scroll_x = max(0, int(session.transcript_scroll_x or 0))
        scroll_y = max(0, int(session.transcript_scroll_y or 0))
        if scroll_y <= 0:
            return
        tab_id = session.tab_id

        def _restore_if_active(_log: Any = log, _sx: int = scroll_x, _sy: int = scroll_y) -> None:
            if self._active_tab_id != tab_id:
                return
            self._scroll_widget_to(_log, scroll_x=_sx, scroll_y=_sy)

        self._scroll_widget_to(log, scroll_x=scroll_x, scroll_y=scroll_y)
        call_after_refresh = getattr(self._app, "call_after_refresh", None)
        if callable(call_after_refresh):
            call_after_refresh(_restore_if_active)
        set_timer = getattr(self._app, "set_timer", None)
        if callable(set_timer):
            set_timer(0.3, _restore_if_active)

    @staticmethod
    def _scroll_widget_to(log: Any, *, scroll_x: int, scroll_y: int) -> None:
        helper = getattr(log, "restore_transcript_viewport", None)
        if callable(helper):
            try:
                helper(scroll_x=scroll_x, scroll_y=scroll_y)
                return
            except Exception:
                pass
        try:
            log.scroll_to(
                x=scroll_x,
                y=scroll_y,
                animate=False,
                immediate=True,
                force=True,
            )
        except Exception:
            return

    def _start_worker_task(self, tab_id: str) -> None:
        session = self._tabs[tab_id]
        _start_tab_request_worker_task(session, self._app, tab_id)

    def _cancel_worker_task(self, tab_id: str) -> None:
        _cancel_tab_request_worker_task(self._tabs.get(tab_id))
