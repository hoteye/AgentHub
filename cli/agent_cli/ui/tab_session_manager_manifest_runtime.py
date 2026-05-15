from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.runtime_kernels.base import KernelEngine
from cli.agent_cli.ui.tab_session_manifest import TabSessionManifest, TabSessionManifestTab
from cli.agent_cli.ui.tab_session_restore_prefetch import CodexSidecarRestorePrefetch

_Collaborators = Mapping[str, Any]


def _manifest_tab_restore_engine(tab_info: TabSessionManifestTab) -> KernelEngine:
    engine = str(getattr(tab_info, "engine", "") or "").strip()
    if engine == "codex_sidecar":
        return "codex_sidecar"
    thread_id = str(getattr(tab_info, "thread_id", "") or "").strip()
    kernel_session_id = str(getattr(tab_info, "kernel_session_id", "") or "").strip()
    if kernel_session_id and kernel_session_id == thread_id:
        return "codex_sidecar"
    return "agenthub_python"


def restore_from_manifest_if_available(
    manager: Any,
    source_runtime: Any,
    *,
    collaborators: _Collaborators,
) -> bool:
    startup_timer = collaborators["startup_timer"]
    startup_profile_log = collaborators["startup_profile_log"]
    tab_manifest_enabled_for_runtime = collaborators["tab_manifest_enabled_for_runtime"]
    tab_manifest_path_for_runtime = collaborators["tab_manifest_path_for_runtime"]
    load_tab_session_manifest = collaborators["load_tab_session_manifest"]

    with startup_timer("tabs.restore_manifest_if_available"):
        manager._clear_manifest_restore_notice()
        if not tab_manifest_enabled_for_runtime(source_runtime):
            return False
        manifest_path = manager._manifest_path or tab_manifest_path_for_runtime(source_runtime)
        manager.configure_manifest_path(manifest_path)
        startup_profile_log(f"profile.tabs.manifest_path path={manifest_path}")
        if not manifest_path.exists():
            return False
        with startup_timer("tabs.load_manifest"):
            manifest = load_tab_session_manifest(manifest_path)
        if manifest is None:
            manager._set_manifest_restore_notice(
                "system.tab_manifest_restore_failed",
                path=str(manifest_path),
            )
            return False
        return manager.restore_from_manifest(manifest, source_runtime=source_runtime)


def restore_from_manifest(
    manager: Any,
    manifest: TabSessionManifest,
    *,
    source_runtime: Any,
    collaborators: _Collaborators,
) -> bool:
    startup_timer = collaborators["startup_timer"]
    startup_profile_log = collaborators["startup_profile_log"]
    manifest_tab_restore_engine = collaborators["_manifest_tab_restore_engine"]
    placeholder_codex_sidecar_tab_runtime = collaborators["_placeholder_codex_sidecar_tab_runtime"]
    resume_codex_sidecar_tab_runtime = collaborators["_resume_codex_sidecar_tab_runtime"]
    clone_tab_runtime = collaborators["_clone_tab_runtime"]
    hydrate_codex_runtime_from_session_metadata = collaborators[
        "_hydrate_codex_runtime_from_session_metadata"
    ]
    restore_tab_provider = collaborators["_restore_tab_provider"]
    restore_runtime_transcript_snapshot = collaborators["_restore_runtime_transcript_snapshot"]
    create_request_queue = collaborators["_create_request_queue"]
    initial_status_data_for_new_tab = collaborators["_initial_status_data_for_new_tab"]
    tab_session_engine_for_runtime = collaborators["_tab_session_engine_for_runtime"]
    tab_session_kernel_session_id = collaborators["_tab_session_kernel_session_id"]
    tab_session_type = collaborators["TabSession"]

    with startup_timer("tabs.restore_manifest.prepare"):
        manager._clear_manifest_restore_notice()
        restored: dict[str, Any] = {}
        restored_order: list[str] = []
        skipped_count = 0
        source_thread_id = str(getattr(source_runtime, "thread_id", "") or "").strip()
        active_manifest_tab_id = str(getattr(manifest, "active_tab_id", "") or "").strip()
        active_tab_id_hint = (
            active_manifest_tab_id
            if any(tab_info.tab_id == active_manifest_tab_id for tab_info in manifest.tabs)
            else str((manifest.tab_order or [""])[0] or "").strip()
        )
    startup_profile_log(
        "profile.tabs.restore_manifest.info "
        f"tabs={len(list(manifest.tabs or []))} active={active_tab_id_hint}"
    )
    for tab_info in manifest.tabs:
        restore_engine = manifest_tab_restore_engine(tab_info)
        tab_label = str(getattr(tab_info, "tab_id", "") or "unknown")
        runtime_restore_pending = False
        runtime_restore_prefetch = None
        with startup_timer(f"tabs.restore_tab.{tab_label}.{restore_engine}.runtime"):
            if restore_engine == "codex_sidecar" and tab_info.tab_id != active_tab_id_hint:
                runtime = placeholder_codex_sidecar_tab_runtime(manager._app, tab_info)
                runtime_restore_pending = runtime is not None
            elif restore_engine == "codex_sidecar":
                runtime_restore_prefetch = manager._consume_active_restore_prefetch(tab_info)
                if runtime_restore_prefetch is not None:
                    runtime = placeholder_codex_sidecar_tab_runtime(manager._app, tab_info)
                    runtime_restore_pending = runtime is not None
                else:
                    runtime = resume_codex_sidecar_tab_runtime(manager._app, tab_info)
            else:
                runtime = source_runtime if tab_info.thread_id == source_thread_id else None
            if runtime is None and restore_engine != "codex_sidecar":
                runtime = clone_tab_runtime(manager._app, tab_info.tab_id, source_runtime)
        if runtime is None:
            skipped_count += 1
            continue
        if restore_engine != "codex_sidecar":
            with startup_timer(f"tabs.restore_tab.{tab_label}.resume_thread"):
                try:
                    if str(getattr(runtime, "thread_id", "") or "").strip() != tab_info.thread_id:
                        runtime.resume_thread(tab_info.thread_id)
                    set_cwd = getattr(runtime, "set_cwd", None)
                    if callable(set_cwd):
                        set_cwd(getattr(source_runtime, "cwd", "") or getattr(runtime, "cwd", ""))
                except Exception:
                    if runtime is source_runtime:
                        manager._set_manifest_restore_notice(
                            "system.tab_manifest_restore_failed",
                            path=str(manager._manifest_path or ""),
                        )
                        return False
                    skipped_count += 1
                    continue
        elif str(getattr(runtime, "thread_id", "") or "").strip() != tab_info.thread_id:
            skipped_count += 1
            continue
        if restore_engine == "codex_sidecar" and not runtime_restore_pending:
            with startup_timer(f"tabs.restore_tab.{tab_label}.codex_hydrate"):
                hydrate_codex_runtime_from_session_metadata(runtime)
        manager._bind_thread_store_update_active_getter(tab_info.tab_id, runtime)
        manager._bind_visible_child_tab_backend(tab_info.tab_id, runtime)
        with startup_timer(f"tabs.restore_tab.{tab_label}.provider"):
            restore_tab_provider(runtime, tab_info)
        restore_transcript_now = tab_info.tab_id == active_tab_id_hint
        if restore_transcript_now:
            with startup_timer(f"tabs.restore_tab.{tab_label}.transcript"):
                entries, lines = restore_runtime_transcript_snapshot(manager._app, runtime)
        else:
            entries, lines = [], []
        with startup_timer(f"tabs.restore_tab.{tab_label}.session"):
            queue = create_request_queue()
        restored[tab_info.tab_id] = tab_session_type(
            tab_id=tab_info.tab_id,
            thread_id=str(getattr(runtime, "thread_id", "") or tab_info.thread_id),
            thread_name=str(getattr(runtime, "thread_name", "") or tab_info.thread_name),
            runtime=runtime,
            request_queue=queue,
            status_data=initial_status_data_for_new_tab(manager._app, runtime),
            allow_legacy_approval_hydration=False,
            engine=tab_session_engine_for_runtime(runtime),
            kernel_session_id=tab_session_kernel_session_id(runtime),
            top_title_text=tab_info.title or tab_info.thread_name or tab_info.tab_id,
            custom_label=tab_info.custom_label,
            transcript_entries=entries,
            transcript_lines=lines,
            transcript_restore_pending=not restore_transcript_now or runtime_restore_pending,
            runtime_restore_pending=runtime_restore_pending,
            runtime_restore_prefetch=runtime_restore_prefetch,
            manifest_tab_info=tab_info if runtime_restore_pending else None,
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
    with startup_timer("tabs.restore_manifest.finalize"):
        for tab_id in list(manifest.tab_order or []):
            if tab_id in restored and tab_id not in restored_order:
                restored_order.append(tab_id)
        for tab_id in restored:
            if tab_id not in restored_order:
                restored_order.append(tab_id)
        if not restored_order:
            manager._set_manifest_restore_notice(
                "system.tab_manifest_restore_failed",
                path=str(manager._manifest_path or ""),
            )
            return False
        manager._tabs = restored
        manager._tab_order = restored_order
        manager._active_tab_id = (
            manifest.active_tab_id if manifest.active_tab_id in restored else restored_order[0]
        )
        manager._next_tab_serial = manager._next_serial_from_tab_order(restored_order)
        manager._set_active_thread_id_for_tab(manager._active_tab_id)
        manager._restore_tab_state(manager._active_tab_id)
        try:
            manager._app._tab_manifest_restored = True
        except Exception:
            pass
    if skipped_count:
        restore_errors = [
            dict(item)
            for item in list(getattr(manager._app, "_codex_sidecar_restore_errors", []) or [])
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
        manager._set_manifest_restore_notice(
            (
                "system.tab_manifest_restore_partial_detail"
                if error_preview
                else "system.tab_manifest_restore_partial"
            ),
            path=str(manager._manifest_path or ""),
            restored_count=len(restored_order),
            skipped_count=skipped_count,
            error_preview=error_preview,
        )
    return True


def _consume_active_restore_prefetch(
    manager: Any,
    tab_info: TabSessionManifestTab,
    *,
    collaborators: _Collaborators,
) -> CodexSidecarRestorePrefetch | None:
    prefetch_type = collaborators["CodexSidecarRestorePrefetch"]
    prefetch = getattr(manager._app, "_codex_sidecar_restore_prefetch", None)
    if not isinstance(prefetch, prefetch_type):
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
        manager._app._codex_sidecar_restore_prefetch = None
    except Exception:
        pass
    return prefetch


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


def save_manifest(
    manager: Any,
    *,
    collaborators: _Collaborators,
) -> None:
    if manager._manifest_path is None:
        return
    save_tab_session_manifest = collaborators["save_tab_session_manifest"]
    manifest_type = collaborators["TabSessionManifest"]
    manifest_tab_type = collaborators["TabSessionManifestTab"]
    tab_session_engine_for_runtime = collaborators["_tab_session_engine_for_runtime"]
    tab_session_kernel_session_id = collaborators["_tab_session_kernel_session_id"]

    manager._save_current_state()
    tabs = []
    for tab_id in manager._tab_order:
        session = manager._tabs.get(tab_id)
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
            manifest_tab_type(
                tab_id=tab_id,
                thread_id=thread_id,
                thread_name=str(getattr(runtime, "thread_name", "") or session.thread_name),
                title=session.top_title_text,
                custom_label=session.custom_label,
                prompt_text=session.prompt_text,
                prompt_cursor_position=session.prompt_cursor_position,
                cwd=str(getattr(runtime, "cwd", "") or ""),
                provider_name=str(status.get("provider_name") or ""),
                provider_model=str(status.get("provider_model") or status.get("model_key") or ""),
                engine=tab_session_engine_for_runtime(runtime),
                kernel_session_id=tab_session_kernel_session_id(runtime),
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
        manager._manifest_path,
        manifest_type(
            active_tab_id=manager._active_tab_id,
            tab_order=list(manager._tab_order),
            tabs=tabs,
        ),
    )
