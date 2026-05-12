from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cli.agent_cli.runtime_kernels.base import KernelEngine
from cli.agent_cli.ui.tab_task_run import TabRole, TabTaskRun

RUNNING_FORK_NOTICE = (
    "Forked from a running tab. Only persisted context was copied; the parent "
    "tab's live turn, in-flight tools, and pending approvals were not copied."
)


@dataclass
class TabSession:
    tab_id: str
    thread_id: str = ""
    thread_name: str = ""
    runtime: Any = None
    request_queue: Any = None
    request_worker_task: Any = None
    is_busy: bool = False
    top_title_text: str = "AgentHub"
    custom_label: str = ""
    transcript_dirty: bool = False
    has_unread_output: bool = False
    live_turn_state: dict = field(default_factory=dict)
    status_data: dict = field(default_factory=dict)
    pending_approvals: list = field(default_factory=list)
    allow_legacy_approval_hydration: bool = True
    pending_request_user_input: Any = None
    transcript_entries: list = field(default_factory=list)
    transcript_lines: list = field(default_factory=list)
    transcript_scroll_x: int = 0
    transcript_scroll_y: int = 0
    prompt_text: str = ""
    prompt_cursor_position: int = 0
    engine: KernelEngine = "agenthub_python"
    kernel_session_id: str = ""
    forked_from_tab_id: str = ""
    forked_from_thread_id: str = ""
    fork_mode: str = ""
    role: TabRole = "standalone"
    parent_tab_id: str = ""
    current_task_run: TabTaskRun | None = None
    last_task_run: TabTaskRun | None = None
    task_history: list[TabTaskRun] = field(default_factory=list)
    child_task_inbox: list[dict[str, Any]] = field(default_factory=list)
    task_run_serial: int = 0
