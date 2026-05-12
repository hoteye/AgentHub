from __future__ import annotations

import asyncio
import sys
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any

from cli.agent_cli import app_runtime_support_runtime
from cli.agent_cli.prompt_history import PromptHistoryManager, PromptHistoryStore
from cli.agent_cli.terminal_driver import AgentHubLinuxDriver
from cli.agent_cli.ui.presentation import resolve_presentation_settings
from cli.agent_cli.ui.prompt_transcript_window_runtime import PromptTranscriptWindowState
from cli.agent_cli.ui.status_indicator import IdleCatAnimator
from cli.agent_cli.ui.theme import build_app_css
from cli.agent_cli.ui.transcript_browsing_runtime import TranscriptBrowsingState


@dataclass(frozen=True)
class AppBootstrapContext:
    runtime: Any
    workspace_root: Path
    driver_class: type[Any] | None
    presentation: Any


def build_bootstrap_context(
    *,
    runtime: Any,
    language: str | None,
    theme_id: str | None,
) -> AppBootstrapContext:
    workspace_root = app_runtime_support_runtime.workspace_root_for_runtime(runtime)
    presentation = resolve_presentation_settings(
        cwd=workspace_root,
        lang=language,
        theme_id=theme_id,
    )
    driver_class = AgentHubLinuxDriver if sys.platform != "win32" else None
    return AppBootstrapContext(
        runtime=runtime,
        workspace_root=workspace_root,
        driver_class=driver_class,
        presentation=presentation,
    )


def apply_pre_super_state(
    app: Any,
    *,
    language: str | None,
    theme_id: str | None,
    context: AppBootstrapContext,
) -> None:
    app._presentation_cli_language = language
    app._presentation_cli_theme_id = theme_id
    app._presentation = context.presentation
    app._theme = context.presentation.theme
    app._messages = context.presentation.messages
    app.CSS = build_app_css(app._theme)
    app._tab_manager = None
    app._direct_runtime = None
    app._direct_request_queue = None
    app._direct_request_worker_task = None
    app._direct_status_data = {}
    app._status_data_session_override = None
    app._codex_sidecar_kernel = None


def initialize_app_state(
    app: Any,
    *,
    prompt_history_home: Path | None,
    context: AppBootstrapContext,
) -> None:
    app.title = app._messages.text("app.title")
    app.sub_title = app._subtitle_text(False)
    _initialize_tab_manager_state(app)
    _initialize_title_state(app)
    _initialize_live_turn_state(app)
    _initialize_transcript_state(app)
    _initialize_runtime_state(app, runtime=context.runtime)
    manifest_restored = _restore_tab_manager_state(app, runtime=context.runtime)
    _initialize_request_tracking_state(
        app,
        prompt_history_home=prompt_history_home,
        workspace_root=context.workspace_root,
    )
    _initialize_shutdown_state(app)
    app._tab_manifest_restored = manifest_restored
    initial_thread_title = app._resolve_thread_title_from_runtime(refresh_from_store=False)
    if initial_thread_title and not manifest_restored:
        app._top_title_text = initial_thread_title
    app._transcript_task_hint_text = app._resolve_transcript_task_hint_text()


def _initialize_tab_manager_state(app: Any) -> None:
    from cli.agent_cli.ui.tab_session_manager import TabSession, TabSessionManager

    initial_session = TabSession(tab_id="main")
    app._tab_manager = TabSessionManager(app=app, initial_session=initial_session)


def _restore_tab_manager_state(app: Any, *, runtime: Any) -> bool:
    mgr = getattr(app, "_tab_manager", None)
    restore_manifest = getattr(mgr, "restore_from_manifest_if_available", None)
    if callable(restore_manifest):
        try:
            return bool(restore_manifest(runtime))
        except Exception:
            return False
    return False


def _initialize_title_state(app: Any) -> None:
    app._top_title_base = "AgentHub"
    app._top_title_text = app._top_title_base
    app._top_title_leading_symbol = "⌬"


def _initialize_live_turn_state(app: Any) -> None:
    app._live_activity_signatures = set()
    app._live_turn_event_signatures = set()
    app._live_turn_backfill_counts = {}
    app._live_streamed_texts = set()
    app._live_turn_event_sequence = 0
    app._live_turn_last_tool_sequence = -1
    app._live_turn_last_agent_message_key = None
    app._live_turn_last_agent_message_sequence = -1
    app._live_turn_had_work_activity = False
    app._live_turn_final_separator_emitted = False
    app._live_turn_interrupt_requested = False
    app._assistant_message_streaming_active = False
    app._busy_status_hidden = False
    app._pending_status_indicator_restore = False
    app._pending_approval_surface_id = ""
    app._pending_approval_surface_commands = []
    app._approval_overlay_active_id = ""
    app._approval_overlay_queue = []
    app._approval_overlay_suppressed_ids = set()
    app._approval_overlay = None


def _initialize_transcript_state(app: Any) -> None:
    app._transcript_turn_serial = 0
    app._transcript_entry_serial = 0
    app._active_transcript_turn_key = "turn:0"
    app._screen_mode = "prompt"
    app._transcript_screen_snapshot_entries = None
    app._prompt_transcript_window_state = PromptTranscriptWindowState()
    app._prompt_transcript_clear_boundary_entry_id = None
    app._transcript_browsing_state = TranscriptBrowsingState()
    app._transcript_entries = []
    app._transcript_lines = []


def _initialize_runtime_state(app: Any, *, runtime: Any) -> None:
    app.runtime = runtime
    try:
        app.runtime.presentation_locale = app._presentation.locale
    except Exception:
        pass
    app.runtime.activity_callback = app._on_runtime_activity
    app.runtime.turn_event_callback = app._on_runtime_turn_event
    app.session_started_at = datetime.now()
    app.prompt_count = 0
    app.status_data = {
        **app_runtime_support_runtime.initial_status_data(
            runtime=app.runtime,
            session_started_text=app.session_started_at.strftime("%Y-%m-%d %H:%M:%S"),
            thread_id=getattr(app.runtime, "thread_id", None),
            thread_name=getattr(app.runtime, "thread_name", None),
        )
    }


def _initialize_request_tracking_state(
    app: Any,
    *,
    prompt_history_home: Path | None,
    workspace_root: Path,
) -> None:
    app._slash_matches = []
    app._slash_selected_index = 0
    app._slash_popup_mode = "slash"
    app._suppressed_slash_popup_text = None
    app._file_matches = []
    app._file_selected_index = 0
    app._pending_pastes = []
    app._large_paste_counters = {}
    app._quit_shortcut_expires_at = None
    app._busy = False
    app._busy_started_at = None
    app._busy_status_label = ""
    app._queued_run_labels = deque()
    app._prompt_history = PromptHistoryManager(PromptHistoryStore(prompt_history_home))
    app._applying_history_prompt = False
    app._workspace_root = workspace_root
    app._workspace_files_cache = None
    app._workspace_files_indexing = False
    app._workspace_files_index_root = None
    app._request_queue = asyncio.Queue()
    app._request_worker_task = None
    app._active_runtime_request_text = ""
    app._active_runtime_request_is_slash = False
    app._last_transcript_render_width = 0
    app._last_transcript_virtual_width = 0
    app._shortcut_overlay_active = False
    app._idle_cat_animator = IdleCatAnimator()
    app._idle_status_started_at = monotonic()
    app._restored_transcript_from_history = False
    app._prompt_burst_timer = None
    app._dynamic_hint_timer = None


def _initialize_shutdown_state(app: Any) -> None:
    app._shutdown_initiated = False
    app._preview_pane_close_attempted = False
    app._exit_requested = False
    app._exit_thread_id = ""
    app._exit_resume_command = ""
    app._exit_summary_requires_post_run_print = False
    app._request_user_input_previous_handler = None
    app._request_user_input_pending = None
    app._request_user_input_pending_lock = threading.Lock()
    app._request_user_input_modal_presenter = None
    app._request_user_input_test_responder = None
    app._approval_modal_presenter = None
