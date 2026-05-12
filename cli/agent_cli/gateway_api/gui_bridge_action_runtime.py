from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.gateway_api.gui_bridge_action_catalog_runtime import (
    audit_list,
    connector_list,
    gateway_dispatch,
    plugin_list,
    plugin_mutation,
    settings_get,
    settings_update,
)
from cli.agent_cli.gateway_api.gui_bridge_action_chat_runtime import (
    chat_send,
    task_run,
    task_stop,
)
from cli.agent_cli.gateway_api.gui_bridge_action_shell_runtime import shell_run
from cli.agent_cli.gateway_api.gui_bridge_action_threads_runtime import (
    thread_list,
    thread_resume,
)

GuiBridgeResponseBuilder = Callable[..., dict[str, Any]]

__all__ = [
    "GuiBridgeResponseBuilder",
    "audit_list",
    "chat_send",
    "connector_list",
    "gateway_dispatch",
    "plugin_list",
    "plugin_mutation",
    "settings_get",
    "settings_update",
    "shell_run",
    "task_run",
    "task_stop",
    "thread_list",
    "thread_resume",
]
