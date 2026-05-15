from __future__ import annotations

from typing import Any

from cli.agent_cli.models import PromptResponse
from cli.agent_cli.ui import tab_session_manager_visible_child_runtime as visible_child_runtime
from cli.agent_cli.ui.runtime_bridge import QueuedRuntimeRequest
from cli.agent_cli.ui.tab_session_manager_models import TabSession
from cli.agent_cli.ui.tab_session_manager_task_runs import (
    _assignment_ref_from_request as _task_assignment_ref_from_request,
)
from cli.agent_cli.ui.tab_session_manager_task_runs import (
    _next_task_run_id as _task_next_task_run_id,
)
from cli.agent_cli.ui.tab_session_manager_task_runs import (
    _task_status_snapshot_for_session as _task_status_snapshot_for_session_impl,
)
from cli.agent_cli.ui.tab_session_manager_task_runs import (
    _task_transcript_index_for_session as _task_transcript_index_for_session_impl,
)
from cli.agent_cli.ui.tab_session_manager_task_runs import (
    complete_task_run as _complete_task_run,
)
from cli.agent_cli.ui.tab_session_manager_task_runs import (
    fail_task_run as _fail_task_run,
)
from cli.agent_cli.ui.tab_session_manager_task_runs import (
    start_task_run as _start_task_run,
)
from cli.agent_cli.ui.tab_task_run import TabTaskRun


def child_tab_ids(manager: Any, parent_tab_id: str) -> list[str]:
    return visible_child_runtime.child_tab_ids(manager, parent_tab_id)


def child_task_runs(manager: Any, parent_tab_id: str) -> list[TabTaskRun]:
    return visible_child_runtime.child_task_runs(manager, parent_tab_id)


def fork_child_tab(manager: Any, from_tab_id: str) -> str:
    return visible_child_runtime.fork_child_tab(manager, from_tab_id)


def dispatch_visible_child_task(
    manager: Any,
    *,
    parent_tab_id: str,
    task_text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return visible_child_runtime.dispatch_visible_child_task(
        manager,
        parent_tab_id=parent_tab_id,
        task_text=task_text,
        metadata=metadata,
    )


def _dispatch_visible_child_task_on_app_thread(
    manager: Any,
    *,
    parent_tab_id: str,
    task_text: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return visible_child_runtime.dispatch_visible_child_task_on_app_thread(
        manager,
        parent_tab_id=parent_tab_id,
        task_text=task_text,
        metadata=metadata,
    )


def send_visible_child_task(
    manager: Any,
    *,
    parent_tab_id: str,
    child_tab_id: str,
    task_text: str,
    interrupt: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return visible_child_runtime.send_visible_child_task(
        manager,
        parent_tab_id=parent_tab_id,
        child_tab_id=child_tab_id,
        task_text=task_text,
        interrupt=interrupt,
        metadata=metadata,
    )


def _send_visible_child_task_on_app_thread(
    manager: Any,
    *,
    parent_tab_id: str,
    child_tab_id: str,
    task_text: str,
    interrupt: bool,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return visible_child_runtime.send_visible_child_task_on_app_thread(
        manager,
        parent_tab_id=parent_tab_id,
        child_tab_id=child_tab_id,
        task_text=task_text,
        interrupt=interrupt,
        metadata=metadata,
    )


def visible_child_task_run_snapshots(manager: Any, parent_tab_id: str) -> list[dict[str, Any]]:
    return visible_child_runtime.visible_child_task_run_snapshots(manager, parent_tab_id)


def _child_task_update_payload(manager: Any, run: TabTaskRun) -> dict[str, Any]:
    return visible_child_runtime.child_task_update_payload(manager, run)


def _child_task_update_notice(payload: dict[str, Any]) -> str:
    return visible_child_runtime.child_task_update_notice(payload)


def _append_system_notice_to_tab(
    manager: Any,
    tab_id: str,
    text: str,
    *,
    unread: bool,
) -> None:
    visible_child_runtime.append_system_notice_to_tab(manager, tab_id, text, unread=unread)


def _publish_child_task_run_update(manager: Any, run: TabTaskRun) -> None:
    visible_child_runtime.publish_child_task_run_update(manager, run)


def _child_task_updates_context_text(updates: list[dict[str, Any]]) -> str:
    return visible_child_runtime.child_task_updates_context_text(updates)


def prepare_runtime_request_for_tab(
    manager: Any,
    tab_id: str,
    request: QueuedRuntimeRequest,
) -> QueuedRuntimeRequest:
    return visible_child_runtime.prepare_runtime_request_for_tab(manager, tab_id, request)


def _task_status_snapshot_for_session(manager: Any, session: TabSession) -> dict[str, Any]:
    return _task_status_snapshot_for_session_impl(session)


def _task_transcript_index_for_session(manager: Any, session: TabSession) -> int:
    return _task_transcript_index_for_session_impl(
        session,
        manager._active_tab_id,
        manager._app,
    )


def _next_task_run_id(manager: Any, session: TabSession) -> str:
    return _task_next_task_run_id(session)


def _assignment_ref_from_request(request: Any) -> dict[str, Any]:
    return _task_assignment_ref_from_request(request)


def start_task_run(manager: Any, tab_id: str, request: Any) -> TabTaskRun | None:
    return _start_task_run(
        tab_id,
        request,
        manager._tabs,
        manager._active_tab_id,
        manager._app,
    )


def complete_task_run(
    manager: Any,
    tab_id: str,
    task_run: object,
    response: PromptResponse,
) -> TabTaskRun | None:
    run = _complete_task_run(
        tab_id,
        task_run,
        response,
        manager._tabs,
        manager._active_tab_id,
        manager._app,
    )
    if run is not None and run.is_terminal:
        manager._publish_child_task_run_update(run)
    return run


def fail_task_run(
    manager: Any,
    tab_id: str,
    task_run: object,
    error: BaseException,
) -> TabTaskRun | None:
    run = _fail_task_run(
        tab_id,
        task_run,
        error,
        manager._tabs,
        manager._active_tab_id,
        manager._app,
    )
    if run is not None:
        manager._publish_child_task_run_update(run)
    return run
