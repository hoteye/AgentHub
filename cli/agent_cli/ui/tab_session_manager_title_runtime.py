from __future__ import annotations

from typing import Any

from cli.agent_cli.ui import tab_session_manager_ui_state_runtime as ui_state_runtime
from cli.agent_cli.ui.tab_session_manager_models import TabSession


def active_session(manager: Any) -> TabSession:
    return manager._tabs[manager._active_tab_id]


def active_tab_id(manager: Any) -> str:
    return manager._active_tab_id


def get(manager: Any, tab_id: str) -> TabSession | None:
    return manager._tabs.get(tab_id)


def _base_tab_label(manager: Any, session: TabSession) -> str:
    return ui_state_runtime._base_tab_label(manager, session)


def _decorated_tab_label(manager: Any, session: TabSession) -> str:
    return ui_state_runtime._decorated_tab_label(manager, session)


def tab_labels(manager: Any) -> list[tuple[str, str, bool]]:
    return ui_state_runtime.tab_labels(manager)


def display_tab_label(manager: Any, tab_id: str) -> str:
    return ui_state_runtime.display_tab_label(manager, tab_id)


def rename_tab(manager: Any, tab_id: str, label: str) -> bool:
    session = manager._tabs.get(tab_id)
    if session is None:
        return False
    session.custom_label = " ".join(str(label or "").split())
    manager.save_manifest()
    return True


def mark_master(manager: Any, tab_id: str) -> bool:
    session = manager._tabs.get(tab_id)
    if session is None:
        return False
    session.role = "master"
    session.parent_tab_id = ""
    manager.save_manifest()
    return True
