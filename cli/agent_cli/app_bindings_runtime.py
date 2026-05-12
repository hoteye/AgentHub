from __future__ import annotations

import re

from textual.binding import Binding

LARGE_PASTE_CHAR_THRESHOLD = 1000
MAX_USER_INPUT_TEXT_CHARS = 1 << 20
QUIT_SHORTCUT_TIMEOUT_SECONDS = 3.0
IDLE_STATUS_DELAY_SECONDS = 30.0
FILE_POPUP_MATCH_LIMIT = 40
COMMAND_OUTPUT_MAX_LINES = 5

QUEUED_REQUEST_BUSY_LABEL_KEYS = {
    "file_list": "busy.file_list",
    "file_search": "busy.file_search",
    "file_read": "busy.file_read",
    "apply_patch": "busy.apply_patch",
    "approve": "busy.approval",
    "reject": "busy.approval",
}

APP_CSS = ""
APP_TITLE = "AgentHub CLI"
APP_SUB_TITLE = "Reference-style operator shell"

APP_BINDINGS = [
    ("ctrl+c", "ctrl_c", "Quit"),
    Binding("ctrl+z", "focused_undo_or_noop", "Undo", show=False, priority=True),
    ("ctrl+l", "clear_logs", "Clear"),
    ("ctrl+o", "toggle_transcript", "Transcript"),
    ("ctrl+enter", "submit_prompt", "Send"),
    ("f5", "refresh_state", "Provider"),
    ("f6", "show_tools", "Tools"),
    ("f7", "toggle_latest_web_item", "Web Details"),
    ("f8", "paste_prompt", "Paste"),
    ("f9", "submit_prompt", "Send"),
    Binding("ctrl+t", "new_tab", "New Tab", show=False, priority=True),
    Binding("ctrl+shift+t", "fork_tab", "Fork Tab", show=False, priority=True),
    Binding("ctrl+w", "close_tab", "Close Tab", show=False),
    Binding("ctrl+tab", "next_tab", "Next Tab", show=False, priority=True),
    Binding("ctrl+shift+tab", "prev_tab", "Prev Tab", show=False, priority=True),
    Binding("ctrl+right", "next_tab", "Next Tab", show=False, priority=True),
    Binding("ctrl+left", "prev_tab", "Prev Tab", show=False, priority=True),
]

WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
WINDOWS_UNC_RE = re.compile(r"^\\\\[^\\\/]+[\\\/][^\\\/]+")
DEFAULT_THREAD_NAME_RE = re.compile(r"^Thread \d{4}-\d{2}-\d{2}\b", re.IGNORECASE)


__all__ = [
    "APP_BINDINGS",
    "APP_CSS",
    "APP_SUB_TITLE",
    "APP_TITLE",
    "COMMAND_OUTPUT_MAX_LINES",
    "DEFAULT_THREAD_NAME_RE",
    "FILE_POPUP_MATCH_LIMIT",
    "IDLE_STATUS_DELAY_SECONDS",
    "LARGE_PASTE_CHAR_THRESHOLD",
    "MAX_USER_INPUT_TEXT_CHARS",
    "QUEUED_REQUEST_BUSY_LABEL_KEYS",
    "QUIT_SHORTCUT_TIMEOUT_SECONDS",
    "WINDOWS_DRIVE_RE",
    "WINDOWS_UNC_RE",
]
