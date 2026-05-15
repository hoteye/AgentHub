from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cli.agent_cli.runtime import AgentCliRuntime


def get_runtime(app: Any) -> AgentCliRuntime:
    mgr = app._tab_manager
    if mgr is not None:
        return mgr.active_session.runtime
    return app._direct_runtime


def set_runtime(app: Any, value: AgentCliRuntime) -> None:
    mgr = app._tab_manager
    if mgr is not None:
        mgr.active_session.runtime = value
        binder = getattr(mgr, "_bind_thread_store_update_active_getter", None)
        if callable(binder):
            binder(mgr.active_tab_id, value)
        backend_binder = getattr(mgr, "_bind_visible_child_tab_backend", None)
        if callable(backend_binder):
            backend_binder(mgr.active_tab_id, value)
    app._direct_runtime = value


def get_status_data(app: Any) -> dict:
    override = getattr(app, "_status_data_session_override", None)
    if override is not None:
        data = getattr(override, "status_data", None)
        if not isinstance(data, dict):
            override.status_data = {}
        return override.status_data
    mgr = app._tab_manager
    if mgr is not None:
        session = mgr.active_session
        data = getattr(session, "status_data", None)
        if not isinstance(data, dict):
            session.status_data = {}
        return session.status_data
    data = getattr(app, "_direct_status_data", None)
    if not isinstance(data, dict):
        app._direct_status_data = {}
    return app._direct_status_data


def set_status_data(app: Any, value: dict) -> None:
    data = dict(value or {})
    override = getattr(app, "_status_data_session_override", None)
    if override is not None:
        override.status_data = data
        return
    mgr = app._tab_manager
    if mgr is not None:
        mgr.active_session.status_data = data
        return
    app._direct_status_data = data


def get_request_queue(app: Any) -> Any:
    mgr = app._tab_manager
    if mgr is not None:
        return mgr.active_session.request_queue
    return app._direct_request_queue


def set_request_queue(app: Any, value: Any) -> None:
    mgr = app._tab_manager
    if mgr is not None:
        mgr.active_session.request_queue = value
    app._direct_request_queue = value


def get_request_worker_task(app: Any) -> Any:
    mgr = app._tab_manager
    if mgr is not None:
        return mgr.active_session.request_worker_task
    return app._direct_request_worker_task


def set_request_worker_task(app: Any, value: Any) -> None:
    mgr = app._tab_manager
    if mgr is not None:
        mgr.active_session.request_worker_task = value
    app._direct_request_worker_task = value
