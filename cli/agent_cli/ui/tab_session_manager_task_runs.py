from __future__ import annotations

from typing import Any

from cli.agent_cli.models import PromptResponse
from cli.agent_cli.ui.tab_session_manager_models import TabSession
from cli.agent_cli.ui.tab_session_manager_state import (
    _merge_status_preserving_known_values,
    _provider_status_for_runtime,
)
from cli.agent_cli.ui.tab_task_run import (
    TabTaskRun,
    queued_task_run,
    task_run_from_exception,
    task_run_from_response,
)


def _task_status_snapshot_for_session(session: TabSession) -> dict[str, Any]:
    status = dict(getattr(session, "status_data", {}) or {})
    runtime = getattr(session, "runtime", None)
    if runtime is not None:
        try:
            status = _merge_status_preserving_known_values(
                status,
                _provider_status_for_runtime(runtime),
            )
        except Exception:
            pass
    return status


def _task_transcript_index_for_session(
    session: TabSession,
    active_tab_id: str,
    app: Any,
) -> int:
    if session.tab_id == active_tab_id and app is not None:
        try:
            return len(list(getattr(app, "_transcript_entries", []) or []))
        except Exception:
            pass
    return len(list(getattr(session, "transcript_entries", []) or []))


def _reserved_task_run_id_from_request(request: Any) -> str:
    metadata = getattr(request, "metadata", None)
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("agenthub_task_run_id") or "").strip()


def _next_task_run_id(session: TabSession, request: Any | None = None) -> str:
    reserved = _reserved_task_run_id_from_request(request)
    if reserved:
        return reserved
    session.task_run_serial = max(0, int(session.task_run_serial or 0)) + 1
    return f"{session.tab_id}-run-{session.task_run_serial}"


def _assignment_ref_from_request(request: Any) -> dict[str, Any]:
    metadata = getattr(request, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    orchestration = metadata.get("orchestration")
    if isinstance(orchestration, dict):
        return dict(orchestration)
    return {}


def start_task_run(
    tab_id: str,
    request: Any,
    tabs: dict[str, TabSession],
    active_tab_id: str,
    app: Any,
) -> TabTaskRun | None:
    session = tabs.get(tab_id)
    if session is None:
        return None
    status = _task_status_snapshot_for_session(session)
    run = queued_task_run(
        run_id=_next_task_run_id(session, request),
        tab_id=tab_id,
        parent_tab_id=str(getattr(session, "parent_tab_id", "") or ""),
        provider=str(status.get("provider_name") or status.get("provider") or ""),
        engine=str(getattr(session, "engine", "") or ""),
        user_prompt=str(getattr(request, "text", "") or ""),
        transcript_start_index=_task_transcript_index_for_session(session, active_tab_id, app),
        assignment_ref=_assignment_ref_from_request(request),
    )
    run.status_snapshot = status
    run.mark_running()
    session.current_task_run = run
    return run


def complete_task_run(
    tab_id: str,
    task_run: object,
    response: PromptResponse,
    tabs: dict[str, TabSession],
    active_tab_id: str,
    app: Any,
) -> TabTaskRun | None:
    session = tabs.get(tab_id)
    if session is None:
        return None
    run = task_run if isinstance(task_run, TabTaskRun) else session.current_task_run
    if run is None:
        return None
    start_index = int(run.transcript_range[0])
    end_index = _task_transcript_index_for_session(session, active_tab_id, app)
    task_run_from_response(
        run,
        response,
        transcript_range=(start_index, max(start_index, end_index)),
    )
    if run.is_terminal:
        session.current_task_run = None
        session.last_task_run = run
        session.task_history.append(run)
    else:
        session.current_task_run = run
    return run


def fail_task_run(
    tab_id: str,
    task_run: object,
    error: BaseException,
    tabs: dict[str, TabSession],
    active_tab_id: str,
    app: Any,
) -> TabTaskRun | None:
    session = tabs.get(tab_id)
    if session is None:
        return None
    run = task_run if isinstance(task_run, TabTaskRun) else session.current_task_run
    if run is None:
        return None
    start_index = int(run.transcript_range[0])
    end_index = _task_transcript_index_for_session(session, active_tab_id, app)
    task_run_from_exception(
        run,
        error,
        transcript_range=(start_index, max(start_index, end_index)),
    )
    session.current_task_run = None
    session.last_task_run = run
    session.task_history.append(run)
    return run
