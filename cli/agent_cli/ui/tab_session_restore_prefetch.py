from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_kernels.base import ResumeSessionRequest
from cli.agent_cli.runtime_paths import project_local_data_dir
from cli.agent_cli.startup_debug import startup_profile_log, startup_timer
from cli.agent_cli.ui.codex_sidecar_metadata import runtime_policy_metadata_for_sidecar
from cli.agent_cli.ui.tab_session_manifest import (
    MANIFEST_FILENAME,
    TabSessionManifestTab,
    load_tab_session_manifest,
)


@dataclass
class CodexSidecarRestorePrefetch:
    manifest_path: Path
    tab_id: str
    thread_id: str
    kernel_session_id: str
    cwd: str
    kernel: Any | None = None
    session: Any | None = None
    error: BaseException | None = None
    _done: threading.Event = field(default_factory=threading.Event)

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    def set_result(self, *, kernel: Any, session: Any) -> None:
        self.kernel = kernel
        self.session = session
        self._done.set()

    def set_error(self, error: BaseException) -> None:
        self.error = error
        self._done.set()


def default_tab_manifest_path() -> Path:
    return project_local_data_dir() / MANIFEST_FILENAME


def start_active_codex_sidecar_restore_prefetch(
    *,
    runtime_policy: Any,
    startup_cwd: Path,
    manifest_path: Path | None = None,
) -> CodexSidecarRestorePrefetch | None:
    path = manifest_path or default_tab_manifest_path()
    if not path.exists():
        return None
    with startup_timer("tabs.restore_prefetch.load_manifest"):
        manifest = load_tab_session_manifest(path)
    if manifest is None:
        return None
    tab_info = _active_codex_sidecar_tab(manifest.tabs, manifest.active_tab_id)
    if tab_info is None:
        return None
    thread_id = str(getattr(tab_info, "thread_id", "") or "").strip()
    if not thread_id:
        return None
    prefetch = CodexSidecarRestorePrefetch(
        manifest_path=path,
        tab_id=str(getattr(tab_info, "tab_id", "") or "").strip(),
        thread_id=thread_id,
        kernel_session_id=str(getattr(tab_info, "kernel_session_id", "") or thread_id).strip()
        or thread_id,
        cwd=str(getattr(tab_info, "cwd", "") or startup_cwd).strip(),
    )
    worker = threading.Thread(
        target=_prefetch_active_codex_sidecar,
        kwargs={
            "prefetch": prefetch,
            "runtime_policy": runtime_policy,
        },
        name="agenthub-codex-sidecar-restore-prefetch",
        daemon=True,
    )
    startup_profile_log(
        "profile.tabs.restore_prefetch.start "
        f"tab={prefetch.tab_id} thread_id={prefetch.thread_id[:16]}"
    )
    worker.start()
    return prefetch


def _active_codex_sidecar_tab(
    tabs: list[TabSessionManifestTab],
    active_tab_id: str,
) -> TabSessionManifestTab | None:
    active_id = str(active_tab_id or "").strip()
    for tab_info in tabs:
        if str(getattr(tab_info, "tab_id", "") or "").strip() != active_id:
            continue
        if _is_codex_sidecar_manifest_tab(tab_info):
            return tab_info
        return None
    return None


def _is_codex_sidecar_manifest_tab(tab_info: TabSessionManifestTab) -> bool:
    engine = str(getattr(tab_info, "engine", "") or "").strip()
    if engine == "codex_sidecar":
        return True
    thread_id = str(getattr(tab_info, "thread_id", "") or "").strip()
    kernel_session_id = str(getattr(tab_info, "kernel_session_id", "") or "").strip()
    return bool(kernel_session_id and kernel_session_id == thread_id)


def _prefetch_active_codex_sidecar(
    *,
    prefetch: CodexSidecarRestorePrefetch,
    runtime_policy: Any,
) -> None:
    kernel = None
    run_coro_blocking = None
    try:
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel
        from cli.agent_cli.ui.tab_session_manager_runtime_factory import _run_coro_blocking

        run_coro_blocking = _run_coro_blocking
        with startup_timer(f"tabs.restore_prefetch.{prefetch.tab_id}.kernel"):
            kernel = CodexSidecarKernel(cwd=prefetch.cwd or None)
        with startup_timer(f"tabs.restore_prefetch.{prefetch.tab_id}.resume_session"):
            session = run_coro_blocking(
                kernel.resume_session(
                    ResumeSessionRequest(
                        session_id=prefetch.kernel_session_id,
                        thread_id=prefetch.thread_id,
                        cwd=prefetch.cwd,
                        metadata=runtime_policy_metadata_for_sidecar(runtime_policy),
                    )
                )
            )
        prefetch.set_result(kernel=kernel, session=session)
    except BaseException as exc:
        if kernel is not None and callable(run_coro_blocking):
            try:
                run_coro_blocking(kernel.aclose())
            except BaseException:
                pass
        prefetch.set_error(exc)
