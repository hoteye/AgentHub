from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli import app_event_helpers
from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.app_runtime_flow_request_user_input_helpers import _PendingRequestUserInput
from cli.agent_cli.models import ActivityEvent, AgentIntent, PromptResponse
from cli.agent_cli.orchestration import taskbook_runtime as taskbook_runtime_service
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.thread_store import ThreadStore
from cli.agent_cli.ui import PromptComposer
from cli.agent_cli.ui.runtime_bridge import QueuedRuntimeRequest
from cli.agent_cli.ui.tab_bar import TabBar
from cli.agent_cli.ui.tab_session_manager import (
    RUNNING_FORK_NOTICE,
    TabSession,
    TabSessionManager,
    _fork_runtime_transcript_source_items,
    _history_item_content_text,
    _history_item_to_transcript_entry,
)
from cli.agent_cli.ui.tab_session_manifest import (
    TabSessionManifest,
    TabSessionManifestTab,
    load_tab_session_manifest,
    migrate_tab_session_manifest_payload,
    save_tab_session_manifest,
)
from cli.agent_cli.ui.transcript_history import TranscriptEntry, user_message_entry
from cli.agent_cli.ui.widgets import TranscriptArea

FAKE_CODEX_BIN = Path(__file__).parent / "fixtures" / "fake_codex_sidecar.py"


def _static_plain(widget) -> str:
    renderable = getattr(widget, "renderable", None)
    if renderable is not None:
        return getattr(renderable, "plain", str(renderable))
    rendered = widget.render()
    return getattr(rendered, "plain", str(rendered))


class TestHistoryItemContentText(unittest.TestCase):
    def test_string_content(self):
        assert _history_item_content_text({"content": "hello"}) == "hello"

    def test_list_content(self):
        item = {"content": [{"type": "input_text", "text": "hi"}]}
        assert _history_item_content_text(item) == "hi"

    def test_reasoning_content(self):
        item = {"content": [{"type": "reasoning", "text": "thinking"}]}
        assert _history_item_content_text(item) == "thinking"

    def test_summary_content(self):
        item = {"summary": [{"type": "summary_text", "text": "summary"}]}
        assert _history_item_content_text(item) == "summary"

    def test_top_level_text(self):
        assert _history_item_content_text({"text": "top-level"}) == "top-level"

    def test_output_dict(self):
        assert _history_item_content_text({"output": {"stdout": "done"}}) == "done"

    def test_empty_string(self):
        assert _history_item_content_text({"content": ""}) == ""


class TestHistoryItemToTranscriptEntry(unittest.TestCase):
    def test_typed_message_user(self):
        entry = _history_item_to_transcript_entry(
            {"type": "message", "role": "user", "content": "hello"}
        )
        assert isinstance(entry, TranscriptEntry)
        assert entry.kind == "user"
        assert any("hello" in line for line in entry.lines)

    def test_typed_message_assistant(self):
        entry = _history_item_to_transcript_entry(
            {"type": "message", "role": "assistant", "content": "world"}
        )
        assert isinstance(entry, TranscriptEntry)
        assert entry.kind == "assistant"

    def test_bare_role_user(self):
        entry = _history_item_to_transcript_entry({"role": "user", "content": "hello"})
        assert isinstance(entry, TranscriptEntry)
        assert entry.kind == "user"

    def test_bare_role_assistant(self):
        entry = _history_item_to_transcript_entry({"role": "assistant", "content": "world"})
        assert isinstance(entry, TranscriptEntry)
        assert entry.kind == "assistant"

    def test_function_call(self):
        entry = _history_item_to_transcript_entry({"type": "function_call", "name": "read_file"})
        assert isinstance(entry, TranscriptEntry)
        assert "read_file" in entry.lines[0]

    def test_reasoning(self):
        entry = _history_item_to_transcript_entry({"type": "reasoning", "content": "thinking..."})
        assert isinstance(entry, TranscriptEntry)
        assert entry.kind == "reasoning"

    def test_reasoning_summary(self):
        entry = _history_item_to_transcript_entry(
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "thinking..."}]}
        )
        assert isinstance(entry, TranscriptEntry)
        assert entry.kind == "reasoning"

    def test_function_call_output(self):
        entry = _history_item_to_transcript_entry(
            {"type": "function_call_output", "call_id": "call_1", "output": "done"}
        )
        assert isinstance(entry, TranscriptEntry)
        assert "call_1" in entry.lines[0]
        assert "done" in entry.lines[0]

    def test_empty_content_returns_none(self):
        assert _history_item_to_transcript_entry({"role": "user", "content": ""}) is None

    def test_list_content(self):
        item = {"role": "user", "content": [{"type": "input_text", "text": "hi"}]}
        entry = _history_item_to_transcript_entry(item)
        assert isinstance(entry, TranscriptEntry)
        assert entry.kind == "user"

    def test_unknown_type_returns_none(self):
        assert _history_item_to_transcript_entry({"type": "unknown"}) is None


class TestCodexTurnsToHistoryTurns(unittest.TestCase):
    def test_accumulates_multiple_user_and_agent_messages(self):
        from cli.agent_cli.ui.tab_session_manager import _codex_turns_to_history_turns

        history_turns = _codex_turns_to_history_turns(
            [
                {
                    "id": "turn-1",
                    "items": [
                        {"type": "userMessage", "text": "first user"},
                        {"type": "userMessage", "text": "second user"},
                        {"type": "agentMessage", "text": "first assistant"},
                        {"type": "agentMessage", "text": "second assistant"},
                    ],
                    "turn_events": [{"type": "turn.completed"}],
                    "status": {"input_tokens": 1},
                }
            ]
        )

        assert history_turns == [
            {
                "user_text": "first user\n\nsecond user",
                "assistant_text": "first assistant\n\nsecond assistant",
                "turn_events": [{"type": "turn.completed"}],
                "codex_sidecar_events": [],
                "status": {"input_tokens": 1},
                "codex_turn_id": "turn-1",
            }
        ]


class TestForkRuntimeTranscriptSourceItems(unittest.TestCase):
    def test_prefers_structured_planner_items(self):
        runtime = type(
            "Runtime",
            (),
            {
                "_planner_input_items": [{"type": "reasoning", "content": "structured"}],
                "history": [{"role": "user", "content": "flat"}],
            },
        )()
        assert _fork_runtime_transcript_source_items(runtime) == [
            {"type": "reasoning", "content": "structured"}
        ]

    def test_falls_back_to_flat_history(self):
        runtime = type(
            "Runtime",
            (),
            {
                "_planner_input_items": [],
                "history": [{"role": "user", "content": "flat"}],
            },
        )()
        assert _fork_runtime_transcript_source_items(runtime) == [
            {"role": "user", "content": "flat"}
        ]


class TestTabSessionManifest(unittest.TestCase):
    def test_round_trip_normalizes_order_and_cursor(self):
        manifest = TabSessionManifest(
            active_tab_id="missing",
            tab_order=["tab-1"],
            tabs=[
                TabSessionManifestTab(
                    tab_id="main",
                    thread_id="thread-main",
                    custom_label="Custom Main",
                    forked_from_tab_id="source-tab",
                    forked_from_thread_id="source-thread",
                    fork_mode="idle",
                    role="child",
                    parent_tab_id="master-tab",
                    prompt_text="hello",
                    prompt_cursor_position=99,
                ),
                TabSessionManifestTab(tab_id="tab-1", thread_id="thread-tab"),
            ],
        )
        payload = manifest.to_dict()
        restored = TabSessionManifest.from_dict(payload)

        assert restored is not None
        assert restored.active_tab_id == "tab-1"
        assert restored.tab_order == ["tab-1", "main"]
        main_payload = next(item for item in restored.tabs if item.tab_id == "main")
        assert main_payload.prompt_cursor_position == 5
        assert main_payload.custom_label == "Custom Main"
        assert main_payload.forked_from_tab_id == "source-tab"
        assert main_payload.forked_from_thread_id == "source-thread"
        assert main_payload.fork_mode == "idle"
        assert main_payload.role == "child"
        assert main_payload.parent_tab_id == "master-tab"

    def test_round_trip_preserves_runtime_kernel_fields(self):
        manifest = TabSessionManifest(
            active_tab_id="tab-1",
            tab_order=["tab-1"],
            tabs=[
                TabSessionManifestTab(
                    tab_id="tab-1",
                    thread_id="thread-1",
                    engine="codex_sidecar",
                    kernel_session_id="kernel-thread-1",
                )
            ],
        )

        restored = TabSessionManifest.from_dict(manifest.to_dict())

        assert restored is not None
        assert restored.tabs[0].engine == "codex_sidecar"
        assert restored.tabs[0].kernel_session_id == "kernel-thread-1"

    def test_save_and_load_manifest_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "tabs.json"
            manifest = TabSessionManifest(
                active_tab_id="main",
                tab_order=["main"],
                tabs=[TabSessionManifestTab(tab_id="main", thread_id="thread-main")],
            )

            save_tab_session_manifest(path, manifest)
            restored = load_tab_session_manifest(path)

            assert restored is not None
            assert restored.active_tab_id == "main"
            assert restored.tabs[0].thread_id == "thread-main"

    def test_migrate_accepts_legacy_v1_payload_without_schema_version(self):
        payload = {
            "active_tab_id": "main",
            "tab_order": ["main"],
            "tabs": [{"tab_id": "main", "thread_id": "thread-main"}],
        }

        migrated = migrate_tab_session_manifest_payload(payload)
        restored = TabSessionManifest.from_dict(payload)

        assert migrated is not None
        assert migrated["schema_version"] == 1
        assert restored is not None
        assert restored.active_tab_id == "main"
        assert restored.tabs[0].thread_id == "thread-main"

    def test_migrate_rejects_unknown_future_schema_version(self):
        payload = {
            "schema_version": 999,
            "active_tab_id": "main",
            "tab_order": ["main"],
            "tabs": [{"tab_id": "main", "thread_id": "thread-main"}],
        }

        assert migrate_tab_session_manifest_payload(payload) is None
        assert TabSessionManifest.from_dict(payload) is None


class TestTabSession(unittest.TestCase):
    def test_default_fields(self):
        s = TabSession(tab_id="t1")
        assert s.tab_id == "t1"
        assert s.thread_id == ""
        assert s.runtime is None
        assert s.request_queue is None
        assert s.request_worker_task is None
        assert s.is_busy is False
        assert s.top_title_text == "AgentHub"
        assert s.pending_approvals == []
        assert s.pending_request_user_input is None
        assert s.transcript_dirty is False
        assert s.has_unread_output is False
        assert s.live_turn_state == {}
        assert s.role == "standalone"
        assert s.parent_tab_id == ""
        assert s.current_task_run is None
        assert s.last_task_run is None
        assert s.task_history == []

    def test_custom_fields(self):
        q = asyncio.Queue()
        s = TabSession(tab_id="t2", runtime="R", request_queue=q, is_busy=True)
        assert s.runtime == "R"
        assert s.request_queue is q
        assert s.is_busy is True


class TestTabSessionManager(unittest.TestCase):
    def _make_manager(self):
        session = TabSession(tab_id="main", top_title_text="Test")
        return TabSessionManager(app=None, initial_session=session)

    def test_active_session_returns_initial(self):
        mgr = self._make_manager()
        assert mgr.active_session.tab_id == "main"
        assert mgr.active_tab_id == "main"

    def test_tab_labels(self):
        mgr = self._make_manager()
        labels = mgr.tab_labels()
        assert len(labels) == 1
        assert labels[0] == ("main", "Test", False)

    def test_custom_label_takes_precedence(self):
        mgr = self._make_manager()
        assert mgr.rename_tab("main", "  Custom   Label  ") is True
        assert mgr.active_session.custom_label == "Custom Label"
        assert mgr.tab_labels()[0] == ("main", "Custom Label", False)
        assert mgr.rename_tab("main", "") is True
        assert mgr.active_session.custom_label == ""
        assert mgr.tab_labels()[0] == ("main", "Test", False)

    def test_active_session_mutable(self):
        mgr = self._make_manager()
        mgr.active_session.is_busy = True
        assert mgr.active_session.is_busy is True
        mgr.active_session.top_title_text = "New Title"
        assert mgr.active_session.top_title_text == "New Title"

    def test_mark_master_decorates_tab_label(self):
        mgr = self._make_manager()

        assert mgr.mark_master("main") is True

        assert mgr.active_session.role == "master"
        assert mgr.tab_labels()[0] == ("main", "[M] Test", False)

    def test_display_tab_label_uses_visible_rail_position_without_internal_id(self):
        mgr = self._make_manager()
        mgr._tabs["tab-1"] = TabSession(tab_id="tab-1")
        mgr._tabs["tab-2"] = TabSession(tab_id="tab-2")
        mgr._tab_order.extend(["tab-1", "tab-2"])

        assert mgr.display_tab_label("main") == "1"
        assert mgr.display_tab_label("tab-1") == "2"
        assert mgr.display_tab_label("tab-2") == "3"
        assert mgr.display_tab_label("missing") == "?"

    def test_task_run_start_and_complete_tracks_terminal_state(self):
        mgr = self._make_manager()
        mgr.active_session.status_data = {"provider_name": "openai"}
        request = QueuedRuntimeRequest(text="hello", attachments=[])

        run = mgr.start_task_run("main", request)
        assert run is not None
        assert run.state == "running"
        assert run.provider == "openai"

        completed = mgr.complete_task_run(
            "main",
            run,
            PromptResponse(user_text="hello", assistant_text="done"),
        )

        assert completed is run
        assert run.terminal_state == "completed"
        assert mgr.active_session.current_task_run is None
        assert mgr.active_session.last_task_run is run
        assert mgr.active_session.task_history == [run]

    def test_task_run_failure_tracks_error(self):
        mgr = self._make_manager()
        run = mgr.start_task_run("main", QueuedRuntimeRequest(text="hello", attachments=[]))

        failed = mgr.fail_task_run("main", run, RuntimeError("boom"))

        assert failed is run
        assert run.terminal_state == "failed"
        assert run.error_message == "boom"
        assert mgr.active_session.current_task_run is None
        assert mgr.active_session.last_task_run is run

    def test_child_task_runs_returns_structured_runs_without_transcript_scraping(self):
        mgr = self._make_manager()
        child = TabSession(tab_id="child", parent_tab_id="main", role="child")
        child_run = mgr.start_task_run("main", QueuedRuntimeRequest(text="parent", attachments=[]))
        mgr._tabs["child"] = child
        mgr._tab_order.append("child")
        run = mgr.start_task_run("child", QueuedRuntimeRequest(text="child task", attachments=[]))
        assert run is not None
        mgr.complete_task_run(
            "child",
            run,
            PromptResponse(
                user_text="child task",
                assistant_text="done",
                status={"objective_state": "claimed_done"},
            ),
        )

        runs = mgr.child_task_runs("main")

        assert child_run not in runs
        assert len(runs) == 1
        assert runs[0].tab_id == "child"
        assert runs[0].terminal_state == "completed"
        assert runs[0].objective_state == "claimed_done"
        assert len(mgr.active_session.child_task_inbox) == 1
        assert mgr.active_session.child_task_inbox[0]["tab_id"] == "child"
        assert mgr.active_session.child_task_inbox[0]["terminal_state"] == "completed"
        assert any("Child tab" in line for line in mgr.active_session.transcript_lines)

    def test_prepare_parent_request_consumes_child_task_inbox_as_structured_context(self):
        mgr = self._make_manager()
        mgr.active_session.child_task_inbox = [
            {
                "run_id": "child-run-1",
                "tab_id": "child",
                "terminal_state": "completed",
                "objective_state": "claimed_done",
                "summary": "child completed",
            }
        ]
        request = QueuedRuntimeRequest(text="continue from child result", attachments=[])

        prepared = mgr.prepare_runtime_request_for_tab("main", request)

        assert prepared is not request
        assert request.text == "continue from child result"
        assert "continue from child result" in prepared.text
        assert "<agenthub_visible_child_task_updates>" in prepared.text
        assert "child-run-1" in prepared.text
        assert prepared.metadata["visible_child_task_updates"][0]["run_id"] == "child-run-1"
        assert mgr.active_session.child_task_inbox == []

    def test_prepare_parent_request_keeps_child_task_inbox_for_slash_commands(self):
        mgr = self._make_manager()
        mgr.active_session.child_task_inbox = [{"run_id": "child-run-1"}]
        request = QueuedRuntimeRequest(text="/provider", attachments=[])

        prepared = mgr.prepare_runtime_request_for_tab("main", request)

        assert prepared is request
        assert mgr.active_session.child_task_inbox == [{"run_id": "child-run-1"}]

    def test_send_visible_child_task_queues_followup_to_existing_child(self):
        mgr = self._make_manager()
        child = TabSession(tab_id="child", parent_tab_id="main", role="child")
        child.request_queue = asyncio.Queue()
        mgr._tabs["child"] = child
        mgr._tab_order.append("child")

        payload = mgr.send_visible_child_task(
            parent_tab_id="main",
            child_tab_id="child",
            task_text="continue",
            interrupt=True,
            metadata={"run_id": "run_1"},
        )

        assert payload["queued"] is True
        assert payload["priority"] == "now"
        request = child.request_queue.get_nowait()
        assert request.text == "continue"
        assert request.priority == "now"
        assert request.metadata["visible_child"]["parent_tab_id"] == "main"
        assert request.metadata["run_id"] == "run_1"


class TestTabSessionManagerMultiTab(unittest.TestCase):
    def _make_manager(self):
        session = TabSession(tab_id="main", top_title_text="Test")
        return TabSessionManager(app=None, initial_session=session)

    def test_close_last_tab_rejected(self):
        mgr = self._make_manager()
        result = mgr.close_tab("main")
        assert result is None
        assert len(mgr._tabs) == 1

    def test_close_busy_tab_rejected(self):
        mgr = self._make_manager()
        mgr.active_session.is_busy = True
        result = mgr.close_tab("main")
        assert result is None

    def test_switch_to_nonexistent_rejected(self):
        mgr = self._make_manager()
        assert mgr.switch_to_tab("nope") is False

    def test_switch_to_same_rejected(self):
        mgr = self._make_manager()
        assert mgr.switch_to_tab("main") is False

    def test_get_returns_none_for_unknown(self):
        mgr = self._make_manager()
        assert mgr.get("nope") is None


class TestTabSessionStatusData(unittest.IsolatedAsyncioTestCase):
    async def test_switching_tabs_preserves_tab_scoped_status_data(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test(size=(120, 28)) as pilot:
            await pilot.pause()
            app._update_status(
                {"context_window_used_tokens": "1000", "model_context_window": "20000"}
            )
            await pilot.pause()

            app.action_new_tab()
            await pilot.pause()
            app._update_status(
                {"context_window_used_tokens": "5000", "model_context_window": "50000"}
            )
            await pilot.pause()

            app.action_prev_tab()
            await pilot.pause()
            assert app.status_data.get("context_window_used_tokens") == "1000"
            assert app.status_data.get("model_context_window") == "20000"

            app.action_next_tab()
            await pilot.pause()
            assert app.status_data.get("context_window_used_tokens") == "5000"
            assert app.status_data.get("model_context_window") == "50000"


class TestAppRuntimeProxy(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_proxied_through_tab_manager(self):
        from cli.agent_cli.ui.runtime_bridge import FallbackRuntime

        runtime = FallbackRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._tab_manager is not None
            assert app._tab_manager.active_session.runtime is runtime
            assert app.runtime is runtime

    async def test_request_queue_proxied_through_tab_manager(self):
        from cli.agent_cli.ui.runtime_bridge import FallbackRuntime

        app = AgentCliApp(runtime=FallbackRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            session_queue = app._tab_manager.active_session.request_queue
            assert app._request_queue is session_queue

    async def test_request_worker_task_proxied(self):
        from cli.agent_cli.ui.runtime_bridge import FallbackRuntime

        app = AgentCliApp(runtime=FallbackRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            task = app._request_worker_task
            assert task is not None
            assert app._tab_manager.active_session.request_worker_task is task


class TestAppMultiTab(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _make_runtime():
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        return build_persistent_runtime(resume_active_thread=False)

    async def test_create_new_tab_adds_to_tab_bar(self):
        from cli.agent_cli.ui.tab_bar import TabBar

        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(app._tab_manager._tabs) == 1
            app.action_new_tab()
            await pilot.pause()
            assert len(app._tab_manager._tabs) == 2
            tab_bar = app.query_one("#tab_bar", TabBar)
            rendered = tab_bar.render().plain
            assert len(rendered) > 5

    async def test_close_idle_tab_returns_to_first(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"
            app.action_close_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "main"
            assert len(app._tab_manager._tabs) == 1

    async def test_click_tab_rail_switches_idle_tab(self):
        from cli.agent_cli.ui.tab_bar import TabBar

        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"
            app.action_prev_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "main"
            tab_bar = app.query_one("#tab_bar", TabBar)
            tab_bar.render()
            tab_id, start, end = tab_bar._tab_spans[-1]
            assert tab_id == "tab-1"
            await pilot.click("#tab_bar", offset=(0, start + 1))
            await pilot.pause()
            assert len(app._tab_manager._tabs) == 2
            assert app._tab_manager.active_tab_id == "tab-1"
            assert end > start

    async def test_screen_position_click_tab_rail_switches_idle_tab(self):
        from cli.agent_cli.ui.tab_bar import TabBar

        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            app.action_prev_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "main"
            tab_bar = app.query_one("#tab_bar", TabBar)
            tab_bar.render()
            tab_id, start, end = tab_bar._tab_spans[-1]
            region = tab_bar.region
            event = SimpleNamespace(
                button=1,
                screen_x=region.x,
                screen_y=region.y + start + 1,
                stop=lambda: None,
                prevent_default=lambda: None,
            )

            app_event_helpers.on_mouse_down(app, event)
            await pilot.pause()

            assert tab_id == "tab-1"
            assert app._tab_manager.active_tab_id == "tab-1"
            assert end > start

    async def test_one_cell_tab_rail_has_no_close_marker_for_busy_tab(self):
        from cli.agent_cli.ui.tab_bar import TabBar

        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            app._set_busy(True)
            await pilot.pause()
            tab_bar = app.query_one("#tab_bar", TabBar)
            tab_bar.render()
            assert tab_bar._close_spans == []
            assert tab_bar._close_hitboxes == []
            assert len(app._tab_manager._tabs) == 2

    async def test_close_last_tab_rejected(self):
        from cli.agent_cli.ui.runtime_bridge import FallbackRuntime

        app = AgentCliApp(runtime=FallbackRuntime())
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(app._tab_manager._tabs) == 1
            app.action_close_tab()
            await pilot.pause()
            assert len(app._tab_manager._tabs) == 1

    async def test_new_tab_has_independent_runtime(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            first_runtime = app.runtime
            app.action_new_tab()
            await pilot.pause()
            second_runtime = app.runtime
            assert second_runtime is not first_runtime
            assert app._tab_manager.get("main").runtime is first_runtime

    async def test_new_tab_has_independent_queue(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            first_queue = app._request_queue
            app.action_new_tab()
            await pilot.pause()
            second_queue = app._request_queue
            assert second_queue is not first_queue

    async def test_tab_switch_keybindings_work_with_composer_focus(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"
            assert app.focused is app.query_one("#prompt_composer", PromptComposer)

            await pilot.press("ctrl+left")
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "main"

            await pilot.press("ctrl+right")
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"

            await pilot.press("ctrl+tab")
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "main"

            await pilot.press("ctrl+shift+tab")
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"

    async def test_tab_switch_preserves_prompt_scroll_position(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test(size=(80, 16)) as pilot:
            await pilot.pause()
            main_log = app.query_one("#main_log", TranscriptArea)
            app._transcript_entries = [
                user_message_entry("\n".join(f"main line {i}" for i in range(80)))
            ]
            app._sync_transcript()
            await pilot.pause()
            await pilot.pause()
            main_log.scroll_to(y=11, animate=False, immediate=True, force=True)
            await pilot.pause()

            app.action_new_tab()
            await pilot.pause()
            tab_log = app.query_one("#main_log", TranscriptArea)
            app._transcript_entries = [
                user_message_entry("\n".join(f"tab line {i}" for i in range(80)))
            ]
            app._sync_transcript()
            await pilot.pause()
            await pilot.pause()
            tab_log.scroll_to(y=4, animate=False, immediate=True, force=True)
            await pilot.pause()

            app._tab_manager.switch_to_tab("main")
            await pilot.pause()
            assert app.query_one("#main_log", TranscriptArea).transcript_scroll_offset()[1] == 11

            app._tab_manager.switch_to_tab("tab-1")
            await pilot.pause()
            assert app.query_one("#main_log", TranscriptArea).transcript_scroll_offset()[1] == 4

    async def test_visible_child_taskbook_dispatch_runs_two_child_tabs_concurrently(self):
        class _ConcurrentRuntime:
            _serial = 0

            def __init__(
                self,
                *,
                started_prompts: list[str],
                started_event: threading.Event,
                release_event: threading.Event,
            ) -> None:
                type(self)._serial += 1
                self.thread_id = f"thread-{type(self)._serial}"
                self.thread_name = f"thread {type(self)._serial}"
                self.activity_callback = None
                self.turn_event_callback = None
                self.thread_store = None
                self.cwd = str(Path.cwd())
                self.started_prompts = started_prompts
                self.started_event = started_event
                self.release_event = release_event
                self.agent = SimpleNamespace(
                    provider_status=lambda: {
                        "provider_name": "fake",
                        "provider_model": "visible-child",
                    }
                )

            def start_thread(self, name: str | None = None):
                self.thread_name = name or self.thread_name

            def fork_thread(self, *, source_thread_id: str | None = None, name: str | None = None):
                return self.thread_id

            def set_cwd(self, cwd):
                self.cwd = str(cwd)

            def resume_thread(self, thread_id: str):
                self.thread_id = thread_id

            def handle_prompt(self, text: str, *, attachments=None):
                del attachments
                self.started_prompts.append(text)
                if len(self.started_prompts) >= 2:
                    self.started_event.set()
                if not self.release_event.wait(timeout=5):
                    raise TimeoutError("visible child concurrency test timed out")
                return PromptResponse(
                    user_text=text,
                    assistant_text=f"done: {text.splitlines()[0]}",
                    status={"objective_state": "claimed_done"},
                )

            def _delegated_agent_state_snapshot(self):
                return []

        started_prompts: list[str] = []
        started_event = threading.Event()
        release_event = threading.Event()

        def _runtime_factory(app, tab_id, source_runtime):
            del app, tab_id, source_runtime
            return _ConcurrentRuntime(
                started_prompts=started_prompts,
                started_event=started_event,
                release_event=release_event,
            )

        runtime = _ConcurrentRuntime(
            started_prompts=started_prompts,
            started_event=started_event,
            release_event=release_event,
        )
        app = AgentCliApp(runtime=runtime)
        markdown = """
# visible child concurrency

### CARD-001: First visible child
- goal: read-only research first child
- owned_files: docs/first.md
- acceptance_criteria: first summary reported
- execution_mode: visible_child_tab

### CARD-002: Second visible child
- goal: read-only research second child
- owned_files: docs/second.md
- acceptance_criteria: second summary reported
- execution_mode: visible_child_tab
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime.cwd = temp_dir
            with patch(
                "cli.agent_cli.ui.tab_session_manager._fork_tab_runtime",
                _runtime_factory,
            ):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app._tab_manager.mark_master("main")
                    created = taskbook_runtime_service.create_orchestration_run(runtime, markdown)
                    run_id = str(created["run_id"])
                    dispatched = taskbook_runtime_service.dispatch_orchestration_run(
                        runtime, run_id
                    )

                    assert dispatched["dispatched_card_ids"] == ["CARD-001", "CARD-002"]
                    deadline = time.monotonic() + 5
                    while not started_event.is_set() and time.monotonic() < deadline:
                        await pilot.pause(0.05)
                    assert started_event.is_set()
                    assert len(started_prompts) == 2
                    assert len(app._tab_manager.child_tab_ids("main")) == 2

                    release_event.set()
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        await pilot.pause(0.05)
                        runs = app._tab_manager.child_task_runs("main")
                        if len([run for run in runs if run.terminal_state == "completed"]) >= 2:
                            break

                    progress = taskbook_runtime_service.progress_orchestration_run(
                        runtime,
                        run_id,
                        dispatch_ready=False,
                    )

                    assert sorted(progress["synced_card_ids"]) == ["CARD-001", "CARD-002"]
                    assert sorted(progress["accepted_card_ids"]) == ["CARD-001", "CARD-002"]
                    assert progress["status"] == "completed"

    async def test_tui_orchestrate_confirm_starts_visible_child_tabs_and_continue_completes(self):
        class _ScriptedRuntime:
            _serial = 0

            def __init__(
                self,
                *,
                started_prompts: list[str],
                started_event: threading.Event,
                release_event: threading.Event,
            ) -> None:
                type(self)._serial += 1
                self.thread_id = f"thread-{type(self)._serial}"
                self.thread_name = f"thread {type(self)._serial}"
                self.activity_callback = None
                self.turn_event_callback = None
                self.thread_store = None
                self.request_user_input_handler = None
                self.cwd = str(Path.cwd())
                self.started_prompts = started_prompts
                self.started_event = started_event
                self.release_event = release_event
                self.agent = SimpleNamespace(
                    provider_status=lambda: {
                        "provider_name": "fake",
                        "provider_model": "visible-child",
                    }
                )
                self._orchestration_runtime_services_cache = None
                self._orchestration_runtime_services_cwd = ""

            @staticmethod
            def _parse_args(arg_text: str):
                from cli.agent_cli.runtime_core import parse_args

                return parse_args(arg_text)

            def _run_command_text_result(self, text: str):
                from cli.agent_cli.runtime_core import run_command_text_result

                return run_command_text_result(self, text)

            def preview_orchestration_run(self, source_text: str, **kwargs):
                return taskbook_runtime_service.preview_orchestration_run(
                    self, source_text, **kwargs
                )

            def create_orchestration_run(self, source_text: str, **kwargs):
                return taskbook_runtime_service.create_orchestration_run(
                    self, source_text, **kwargs
                )

            def dispatch_orchestration_run(self, run_id: str):
                return taskbook_runtime_service.dispatch_orchestration_run(self, run_id)

            def progress_orchestration_run(self, run_id: str, *, dispatch_ready: bool = True):
                return taskbook_runtime_service.progress_orchestration_run(
                    self,
                    run_id,
                    dispatch_ready=dispatch_ready,
                )

            def continue_orchestration_run(
                self,
                run_id: str,
                *,
                max_passes: int = 8,
                dispatch_ready: bool = True,
            ):
                return taskbook_runtime_service.continue_orchestration_run(
                    self,
                    run_id,
                    max_passes=max_passes,
                    dispatch_ready=dispatch_ready,
                )

            def apply_orchestration_card(self, run_id: str, card_id: str):
                return taskbook_runtime_service.apply_orchestration_card(self, run_id, card_id)

            def reject_orchestration_card(self, run_id: str, card_id: str):
                return taskbook_runtime_service.reject_orchestration_card(self, run_id, card_id)

            @staticmethod
            def slash_command_matches(query: str):
                from cli.agent_cli.slash_commands import match_slash_commands

                return [
                    {
                        "name": spec.name,
                        "usage": spec.usage,
                        "description": spec.description,
                    }
                    for spec in match_slash_commands(str(query or ""))
                ]

            @staticmethod
            def slash_command_completion(query: str):
                del query
                return None

            @staticmethod
            def interrupt_active_run():
                return {"ok": False, "interrupted": False}

            def start_thread(self, name: str | None = None):
                self.thread_name = name or self.thread_name

            def fork_thread(self, *, source_thread_id: str | None = None, name: str | None = None):
                return self.thread_id

            def set_cwd(self, cwd):
                self.cwd = str(cwd)

            def resume_thread(self, thread_id: str):
                self.thread_id = thread_id

            def handle_prompt(self, text: str, *, attachments=None):
                del attachments
                if str(text or "").strip().startswith("/"):
                    command_result = self._run_command_text_result(text)
                    return PromptResponse(
                        user_text=text,
                        assistant_text=str(command_result.assistant_text or ""),
                        tool_events=list(command_result.tool_events or []),
                        turn_events=[
                            dict(item)
                            for item in list(command_result.turn_events or [])
                            if isinstance(item, dict)
                        ],
                        handled_as_command=True,
                        command_display_text=str(command_result.command_display_text or ""),
                    )
                self.started_prompts.append(text)
                if len(self.started_prompts) >= 2:
                    self.started_event.set()
                if not self.release_event.wait(timeout=5):
                    raise TimeoutError("visible child TUI flow test timed out")
                return PromptResponse(
                    user_text=text,
                    assistant_text=f"done: {text.splitlines()[0]}",
                    status={
                        "objective_state": "claimed_done",
                        "task_summary": f"completed {text.splitlines()[0]}",
                    },
                    turn_events=[{"type": "turn.completed"}],
                )

            def _delegated_agent_state_snapshot(self):
                return []

        def _runtime_factory(app, tab_id, source_runtime):
            del app, tab_id, source_runtime
            return _ScriptedRuntime(
                started_prompts=started_prompts,
                started_event=started_event,
                release_event=release_event,
            )

        def _submit_text(app: AgentCliApp, text: str) -> None:
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text(text)
            app.call_next(app.action_submit_prompt)

        async def _wait_for(
            pilot,
            predicate,
            *,
            timeout: float = 5.0,
            label: str = "condition",
            debug_text=None,
        ) -> None:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                await pilot.pause(0.05)
                if predicate():
                    return
            detail = f": {debug_text()}" if callable(debug_text) else ""
            raise AssertionError(f"{label} not observed within {timeout:.1f}s{detail}")

        def _transcript_text(app: AgentCliApp) -> str:
            return "\n".join(str(line) for line in list(app._transcript_lines or []))

        def _latest_run_id(app: AgentCliApp) -> str:
            for line in reversed(_transcript_text(app).splitlines()):
                stripped = line.strip()
                if stripped.startswith("run_id=run_"):
                    return stripped.split("=", 1)[1].strip()
            return ""

        def _run_status(run_id: str) -> dict[str, object]:
            services = taskbook_runtime_service.runtime_services(runtime)
            bundle = services.storage.load_run_bundle(run_id)
            run = bundle.get("run") if isinstance(bundle, dict) else None
            return run.to_dict() if run is not None else {}

        started_prompts: list[str] = []
        started_event = threading.Event()
        release_event = threading.Event()
        runtime = _ScriptedRuntime(
            started_prompts=started_prompts,
            started_event=started_event,
            release_event=release_event,
        )
        app = AgentCliApp(runtime=runtime)
        task_text = (
            "请把当前项目能力调研拆给两个 visible child tab 并并发执行："
            "一个看 README，一个看 docs。"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime.cwd = temp_dir
            with patch(
                "cli.agent_cli.ui.tab_session_manager._fork_tab_runtime",
                _runtime_factory,
            ):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app._request_user_input_modal_presenter = (
                        lambda *, payload, on_submit, on_cancel: (
                            on_submit({"answers": {"taskbook_action": "Confirm and start"}}) or True
                        )
                    )
                    _submit_text(app, "/master")
                    await _wait_for(
                        pilot,
                        lambda: app._tab_manager.active_session.role == "master",
                        label="master tab mark",
                    )

                    _submit_text(app, f"/orchestrate_confirm {task_text}")
                    await _wait_for(
                        pilot,
                        lambda: started_event.is_set(),
                        timeout=8.0,
                        label="two visible child prompts started",
                    )
                    await _wait_for(
                        pilot,
                        lambda: bool(_latest_run_id(app)),
                        timeout=5.0,
                        label="orchestration run id rendered",
                    )

                    run_id = _latest_run_id(app)
                    assert run_id.startswith("run_")
                    assert len(started_prompts) == 2
                    assert len(app._tab_manager.child_tab_ids("main")) == 2
                    assert all("visible child" in prompt for prompt in started_prompts)
                    transcript_before_release = _transcript_text(app)
                    assert "orchestration confirmation accepted" in transcript_before_release
                    assert "orchestration dispatch submitted" in transcript_before_release
                    assert "dispatched_cards=CARD-001,CARD-002" in transcript_before_release

                    _submit_text(app, f"/orchestrate_continue {run_id} max-passes 2")
                    await _wait_for(
                        pilot,
                        lambda: (
                            "orchestration continue paused" in _transcript_text(app)
                            and "stopped_reason=waiting_on_running_cards" in _transcript_text(app)
                        ),
                        label="paused continue while child tabs are running",
                        debug_text=lambda: _transcript_text(app),
                    )
                    running_status = _run_status(run_id)
                    assert running_status["status"] == "running"
                    assert sorted(running_status["running_card_ids"]) == [
                        "CARD-001",
                        "CARD-002",
                    ]

                    release_event.set()
                    await _wait_for(
                        pilot,
                        lambda: len(
                            [
                                run
                                for run in app._tab_manager.child_task_runs("main")
                                if run.terminal_state == "completed"
                            ]
                        )
                        >= 2,
                        timeout=8.0,
                        label="child task runs completed",
                    )

                    _submit_text(app, f"/orchestrate_continue {run_id} max-passes 4")
                    await _wait_for(
                        pilot,
                        lambda: _run_status(run_id).get("status") == "completed",
                        label="orchestration terminal completion",
                    )
                    await _wait_for(
                        pilot,
                        lambda: "orchestration continue finished" in _transcript_text(app),
                        label="terminal continue rendered",
                        debug_text=lambda: _transcript_text(app),
                    )
                    final_text = _transcript_text(app)
                    assert "orchestration continue finished" in final_text
                    assert "stopped_reason=terminal:completed" in final_text
                    assert "accepted_cards=CARD-001,CARD-002" in final_text
                    assert "completed_cards=2" in final_text
                    completed_status = _run_status(run_id)
                    assert sorted(completed_status["completed_card_ids"]) == [
                        "CARD-001",
                        "CARD-002",
                    ]


class TestTabPersistenceRecovery(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _runtime_with_store(store: ThreadStore) -> AgentCliRuntime:
        runtime = AgentCliRuntime(thread_store=store)
        runtime.start_thread(name="main persisted")
        runtime.tui_tab_manifest_enabled = True
        return runtime

    async def test_restart_restores_tab_order_active_thread_and_draft(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir) / "state")
            manifest_path = Path(temp_dir) / "tabs.json"
            runtime = self._runtime_with_store(store)
            app = AgentCliApp(runtime=runtime)
            app._tab_manager.configure_manifest_path(manifest_path)

            async with app.run_test() as pilot:
                await pilot.pause()
                main_thread_id = app._tab_manager.get("main").runtime.thread_id
                app.action_new_tab()
                await pilot.pause()
                tab_thread_id = app._tab_manager.active_session.runtime.thread_id
                composer = app.query_one("#prompt_composer", PromptComposer)
                composer.set_text("draft for restored tab")
                composer._set_cursor_position(5, extend=False)
                app._tab_manager.rename_tab("tab-1", "Restored Label")
                app._tab_manager.save_manifest()

            restored_runtime = AgentCliRuntime(thread_store=store)
            restored_runtime.tui_tab_manifest_enabled = True
            restored_runtime.resume_thread(main_thread_id)
            restored_app = AgentCliApp(runtime=restored_runtime)
            restored_app._tab_manager.configure_manifest_path(manifest_path)
            assert restored_app._tab_manager.restore_from_manifest_if_available(restored_runtime)

            async with restored_app.run_test() as pilot:
                await pilot.pause()
                assert restored_app._tab_manager._tab_order == ["main", "tab-1"]
                assert restored_app._tab_manager.active_tab_id == "tab-1"
                assert restored_app.runtime.thread_id == tab_thread_id
                assert store.get_active_thread_id() == tab_thread_id
                assert restored_app._tab_manager.active_session.custom_label == "Restored Label"
                assert "2" in restored_app.query_one("#tab_bar", TabBar).render().plain
                restored_composer = restored_app.query_one("#prompt_composer", PromptComposer)
                assert restored_composer.text == "draft for restored tab"
                assert restored_composer.cursor_pos == 5

                restored_app._tab_manager.switch_to_tab("main")
                await pilot.pause()
                assert restored_app.runtime.thread_id == main_thread_id

    async def test_restore_manifest_skips_missing_thread_and_keeps_single_tab(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir) / "state")
            runtime = self._runtime_with_store(store)
            manifest_path = Path(temp_dir) / "tabs.json"
            manifest = TabSessionManifest(
                active_tab_id="tab-1",
                tab_order=["main", "tab-1"],
                tabs=[
                    TabSessionManifestTab(tab_id="main", thread_id=runtime.thread_id),
                    TabSessionManifestTab(tab_id="tab-1", thread_id="missing-thread"),
                ],
            )
            app = AgentCliApp(runtime=runtime)
            app._tab_manager.configure_manifest_path(manifest_path)

            assert app._tab_manager.restore_from_manifest(manifest, source_runtime=runtime)
            assert app._tab_manager._tab_order == ["main"]
            assert app._tab_manager.active_tab_id == "main"
            notice = app._tab_manager.pop_manifest_restore_notice()
            assert notice is not None
            key, params = notice
            assert key == "system.tab_manifest_restore_partial"
            assert params["restored_count"] == 1
            assert params["skipped_count"] == 1

    async def test_restore_manifest_uses_current_startup_cwd_for_python_tabs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir) / "state")
            startup_cwd = Path(temp_dir) / "startup"
            stale_cwd = Path(temp_dir) / "stale"
            startup_cwd.mkdir()
            stale_cwd.mkdir()
            runtime = self._runtime_with_store(store)
            runtime.set_cwd(startup_cwd)
            manifest = TabSessionManifest(
                active_tab_id="main",
                tab_order=["main"],
                tabs=[
                    TabSessionManifestTab(
                        tab_id="main",
                        thread_id=runtime.thread_id,
                        cwd=str(stale_cwd),
                    ),
                ],
            )
            app = AgentCliApp(runtime=runtime)

            assert app._tab_manager.restore_from_manifest(manifest, source_runtime=runtime)

            assert Path(app.runtime.cwd) == startup_cwd.resolve()
            assert Path(app._tab_manager.active_session.runtime.cwd) == startup_cwd.resolve()

    async def test_restore_manifest_partial_notice_is_written_on_mount(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir) / "state")
            runtime = self._runtime_with_store(store)
            manifest_path = Path(temp_dir) / "tabs.json"
            manifest = TabSessionManifest(
                active_tab_id="tab-1",
                tab_order=["main", "tab-1"],
                tabs=[
                    TabSessionManifestTab(tab_id="main", thread_id=runtime.thread_id),
                    TabSessionManifestTab(tab_id="tab-1", thread_id="missing-thread"),
                ],
            )
            save_tab_session_manifest(manifest_path, manifest)

            app = AgentCliApp(runtime=runtime)
            app._tab_manager.configure_manifest_path(manifest_path)
            assert app._tab_manager.restore_from_manifest_if_available(runtime)

            async with app.run_test() as pilot:
                await pilot.pause()
                assert (
                    app._t(
                        "system.tab_manifest_restore_partial",
                        path=str(manifest_path),
                        restored_count=1,
                        skipped_count=1,
                    )
                    in app._transcript_lines
                )

    async def test_restore_manifest_failed_notice_is_written_on_mount(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir) / "state")
            runtime = self._runtime_with_store(store)
            manifest_path = Path(temp_dir) / "tabs.json"
            manifest_path.write_text("{not-json", encoding="utf-8")

            app = AgentCliApp(runtime=runtime)
            app._tab_manager.configure_manifest_path(manifest_path)
            assert app._tab_manager.restore_from_manifest_if_available(runtime) is False

            async with app.run_test() as pilot:
                await pilot.pause()
                assert (
                    app._t(
                        "system.tab_manifest_restore_failed",
                        path=str(manifest_path),
                    )
                    in app._transcript_lines
                )


class TestPhase3EdgeCases(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_runtime_new_tab_does_not_crash(self):
        from cli.agent_cli.ui.runtime_bridge import FallbackRuntime

        app = AgentCliApp(runtime=FallbackRuntime())
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(app._tab_manager._tabs) == 1
            app.action_new_tab()
            await pilot.pause()
            assert len(app._tab_manager._tabs) == 1

    async def test_composer_draft_preserved_without_focus(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("draft-main")
            app.set_focus(None)
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id != "main"
            assert composer.text == ""
            app.action_close_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "main"
            assert composer.text == "draft-main"


class TestCodexSidecarTabIntegration(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _make_runtime():
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        return build_persistent_runtime(resume_active_thread=False)

    async def test_codex_sidecar_tab_coexists_with_python_tab(self):
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        app = AgentCliApp(runtime=self._make_runtime())
        app._codex_sidecar_kernel = CodexSidecarKernel(
            codex_bin=FAKE_CODEX_BIN,
            request_timeout=3,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            python_runtime = app.runtime
            tab_id = app._tab_manager.create_tab(engine="codex_sidecar")
            await pilot.pause()

            assert tab_id == "tab-1"
            assert app._tab_manager.active_tab_id == tab_id
            codex_session = app._tab_manager.get(tab_id)
            assert codex_session is not None
            assert codex_session.engine == "codex_sidecar"
            assert codex_session.kernel_session_id == "thread-1"
            assert codex_session.runtime.thread_id == "thread-1"
            assert codex_session.runtime.agent.provider_status()["provider_source"] == (
                "codex_sidecar"
            )

            assert app._tab_manager.switch_to_tab("main")
            assert app.runtime is python_runtime
            assert app._tab_manager.switch_to_tab(tab_id)
            assert app.runtime is codex_session.runtime
            assert codex_session.runtime.gateway_state_store is python_runtime.gateway_state_store

    async def test_ctrl_t_routes_openai_runtime_to_sidecar_when_enabled(self):
        from cli.agent_cli.providers.config_catalog import ProviderConfig
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        runtime = AgentCliRuntime()
        runtime.agent._provider_config = ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
            interaction_profile="codex_openai",
        )
        app = AgentCliApp(runtime=runtime)
        kernel = CodexSidecarKernel(
            codex_bin=FAKE_CODEX_BIN,
            request_timeout=3,
        )
        app._codex_sidecar_kernel = kernel
        try:
            with patch.dict(
                "os.environ",
                {"AGENTHUB_CODEX_SIDECAR_DEFAULT_FOR_OPENAI": "1"},
                clear=False,
            ):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.action_new_tab()
                    await pilot.pause()

            session = app._tab_manager.active_session
            assert session.engine == "codex_sidecar"
            assert session.runtime.thread_id == "thread-1"
        finally:
            await kernel.aclose()

    async def test_ctrl_t_keeps_python_for_openai_when_sidecar_default_disabled(self):
        from cli.agent_cli.providers.config_catalog import ProviderConfig

        runtime = AgentCliRuntime()
        runtime.agent._provider_config = ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
            interaction_profile="codex_openai",
        )
        app = AgentCliApp(runtime=runtime)
        with patch.dict(
            "os.environ",
            {
                "AGENTHUB_CODEX_SIDECAR_DEFAULT_FOR_OPENAI": "0",
                "AGENTHUB_CODEX_SIDECAR_TEST_BIN": str(FAKE_CODEX_BIN),
            },
            clear=False,
        ):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_new_tab()
                await pilot.pause()

        session = app._tab_manager.active_session
        assert session.engine == "agenthub_python"

    async def test_codex_sidecar_tab_prompt_uses_turn_start(self):
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        app = AgentCliApp(runtime=self._make_runtime())
        app._codex_sidecar_kernel = CodexSidecarKernel(
            codex_bin=FAKE_CODEX_BIN,
            request_timeout=3,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            tab_id = app._tab_manager.create_tab(engine="codex_sidecar")
            await pilot.pause()
            assert tab_id == "tab-1"
            session = app._tab_manager.get(tab_id)
            assert session is not None

            await session.request_queue.put(
                QueuedRuntimeRequest(text="hello sidecar", attachments=[])
            )
            await session.request_queue.join()
            await pilot.pause()

            assert session.is_busy is False
            assert session.runtime.history[-1]["content"] == "hello sidecar"
            assert session.runtime.history_turns[-1]["user_text"] == "hello sidecar"
            assert session.runtime.history_turns[-1]["assistant_text"] == "fake sidecar reply"
            turn_events = session.runtime.turn_results[-1].turn_events
            assert turn_events[0]["type"] == "turn.started"
            assert turn_events[-1]["type"] == "turn.completed"
            assert any(
                event.get("type") == "item.completed"
                and (event.get("item") or {}).get("type") == "agent_message"
                and (event.get("item") or {}).get("text") == "fake sidecar reply"
                for event in turn_events
            )
            assert any("fake sidecar reply" in str(line) for line in app._transcript_lines)
            diagnostics = session.runtime.turn_results[-1].protocol_diagnostics
            assert diagnostics["turn_id"] == "turn-1"
            methods = [event.get("method") for event in diagnostics["codex_sidecar_events"]]
            assert "turn/started" in methods
            assert "turn/completed" in methods

    async def test_codex_sidecar_natural_language_visible_child_multiturn_harness(self):
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        def _submit_text(app: AgentCliApp, tab_id: str, text: str) -> None:
            if app._tab_manager.active_tab_id != tab_id:
                assert app._tab_manager.switch_to_tab(tab_id)
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text(text)
            app.call_next(app.action_submit_prompt)

        async def _wait_for(
            pilot,
            predicate,
            *,
            timeout: float = 8.0,
            label: str = "condition",
            debug_text=None,
        ) -> None:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                await pilot.pause(0.05)
                if predicate():
                    return
            detail = f": {debug_text()}" if callable(debug_text) else ""
            raise AssertionError(f"{label} not observed within {timeout:.1f}s{detail}")

        def _transcript_text(app: AgentCliApp) -> str:
            return "\n".join(str(line) for line in list(app._transcript_lines or []))

        app = AgentCliApp(runtime=self._make_runtime())
        app._codex_sidecar_kernel = CodexSidecarKernel(
            codex_bin=FAKE_CODEX_BIN,
            request_timeout=3,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            parent_tab_id = app._tab_manager.create_tab(engine="codex_sidecar")
            await pilot.pause()
            parent = app._tab_manager.get(parent_tab_id)
            assert parent is not None
            assert parent.engine == "codex_sidecar"

            _submit_text(
                app,
                parent_tab_id,
                "请用 visible child tabs 拆两个任务：一个看 README，一个看 docs。",
            )
            await _wait_for(
                pilot,
                lambda: len(parent.runtime.turn_results) >= 1,
                label="parent split turn completed",
                debug_text=lambda: _transcript_text(app),
            )
            await _wait_for(
                pilot,
                lambda: len(app._tab_manager.child_tab_ids(parent_tab_id)) == 2,
                label="two visible child tabs spawned",
                debug_text=lambda: str(app._tab_manager.tab_labels()),
            )
            child_ids = app._tab_manager.child_tab_ids(parent_tab_id)
            assert [app._tab_manager.get(tab_id).custom_label for tab_id in child_ids] == [
                "README",
                "DOCS",
            ]
            assert parent.role == "master"
            assert all(app._tab_manager.get(tab_id).role == "child" for tab_id in child_ids)

            await _wait_for(
                pilot,
                lambda: len(
                    [
                        run
                        for run in app._tab_manager.child_task_runs(parent_tab_id)
                        if run.terminal_state == "completed"
                    ]
                )
                >= 2,
                timeout=10.0,
                label="initial child task runs completed",
                debug_text=lambda: str(
                    [run.to_dict() for run in app._tab_manager.child_task_runs(parent_tab_id)]
                ),
            )
            initial_runs = app._tab_manager.child_task_runs(parent_tab_id)
            assert sorted(run.assignment_ref.get("card_id") for run in initial_runs) == [
                "DOCS",
                "README",
            ]
            assert any("README child" in run.user_prompt for run in initial_runs)
            assert any("Docs child" in run.user_prompt for run in initial_runs)
            assert len(parent.child_task_inbox) == 2
            assert all("summary" in update for update in parent.child_task_inbox)
            assert any("Child tab README finished" in line for line in parent.transcript_lines)
            assert any("Child tab DOCS finished" in line for line in parent.transcript_lines)
            split_methods = [
                event.get("method")
                for event in parent.runtime.turn_results[-1].protocol_diagnostics[
                    "codex_sidecar_events"
                ]
            ]
            assert split_methods.count("item/tool/call") >= 2

            _submit_text(
                app,
                parent_tab_id,
                "请根据刚完成的两个子任务继续总结。",
            )
            await _wait_for(
                pilot,
                lambda: len(parent.runtime.turn_results) >= 2,
                label="parent result-inspection turn completed",
                debug_text=lambda: _transcript_text(app),
            )
            result_text = parent.runtime.turn_results[-1].assistant_text
            assert "<agenthub_visible_child_task_updates>" in parent.runtime.history[-1]["content"]
            assert '"terminal_state": "completed"' in parent.runtime.history[-1]["content"]
            assert '"card_id": "README"' in parent.runtime.history[-1]["content"]
            assert '"card_id": "DOCS"' in parent.runtime.history[-1]["content"]
            assert parent.child_task_inbox == []
            assert "visible child task snapshots" not in result_text

            latest_child_id = child_ids[-1]
            latest_child = app._tab_manager.get(latest_child_id)
            assert latest_child is not None
            latest_history_before = len(latest_child.task_history)
            _submit_text(
                app,
                parent_tab_id,
                "根据这些结果给 latest child 注入 follow-up 新命令。",
            )
            await _wait_for(
                pilot,
                lambda: len(parent.runtime.turn_results) >= 3,
                label="parent follow-up injection turn completed",
                debug_text=lambda: _transcript_text(app),
            )
            followup_text = parent.runtime.turn_results[-1].assistant_text
            assert "visible child tab input queued" in followup_text

            await _wait_for(
                pilot,
                lambda: (
                    len(latest_child.task_history) >= latest_history_before + 1
                    and latest_child.task_history[-1].terminal_state == "completed"
                ),
                timeout=10.0,
                label="latest child follow-up task completed",
                debug_text=lambda: str([run.to_dict() for run in latest_child.task_history]),
            )
            latest_run = latest_child.task_history[-1]
            assert latest_run.assignment_ref == {
                "run_id": "fake_nl_run",
                "card_id": "FOLLOWUP",
                "attempt": 1,
            }
            assert latest_run.user_prompt == (
                "Follow up: report one missing risk and the next action."
            )
            assert len(app._tab_manager.child_task_runs(parent_tab_id)) >= 3

    async def test_codex_sidecar_natural_language_visible_child_tabs_run_concurrently(self):
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        class _BlockingChildRuntime:
            _serial = 0

            def __init__(
                self,
                *,
                started_prompts: list[str],
                started_event: threading.Event,
                release_event: threading.Event,
            ) -> None:
                type(self)._serial += 1
                self.thread_id = f"child-thread-{type(self)._serial}"
                self.thread_name = f"child thread {type(self)._serial}"
                self.activity_callback = None
                self.turn_event_callback = None
                self.thread_store = None
                self.request_user_input_handler = None
                self.cwd = str(Path.cwd())
                self.history: list[dict[str, object]] = []
                self.history_turns: list[dict[str, object]] = []
                self.turn_results: list[PromptResponse] = []
                self.started_prompts = started_prompts
                self.started_event = started_event
                self.release_event = release_event
                self.agent = SimpleNamespace(
                    provider_status=lambda: {
                        "provider_name": "fake",
                        "provider_model": "blocking-visible-child",
                    }
                )

            def start_thread(self, name: str | None = None):
                self.thread_name = name or self.thread_name

            def fork_thread(
                self,
                *,
                source_thread_id: str | None = None,
                name: str | None = None,
            ):
                del source_thread_id
                self.thread_name = name or self.thread_name
                return self.thread_id

            def set_cwd(self, cwd):
                self.cwd = str(cwd)

            def resume_thread(self, thread_id: str):
                self.thread_id = thread_id

            def handle_prompt(self, text: str, *, attachments=None):
                del attachments
                self.started_prompts.append(text)
                if len(self.started_prompts) >= 2:
                    self.started_event.set()
                if not self.release_event.wait(timeout=5):
                    raise TimeoutError("visible child natural-language concurrency timed out")
                response = PromptResponse(
                    user_text=text,
                    assistant_text=f"child done: {text.splitlines()[0]}",
                    status={
                        "objective_state": "claimed_done",
                        "task_summary": f"completed {text.splitlines()[0]}",
                    },
                    turn_events=[
                        {"type": "turn.started"},
                        {"type": "turn.completed"},
                    ],
                )
                self.history.append({"type": "message", "role": "user", "content": text})
                self.history.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": response.assistant_text,
                    }
                )
                self.history_turns.append(
                    {
                        "user_text": text,
                        "assistant_text": response.assistant_text,
                    }
                )
                self.turn_results.append(response)
                return response

            def _delegated_agent_state_snapshot(self):
                return []

        def _submit_text(app: AgentCliApp, tab_id: str, text: str) -> None:
            if app._tab_manager.active_tab_id != tab_id:
                assert app._tab_manager.switch_to_tab(tab_id)
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text(text)
            app.call_next(app.action_submit_prompt)

        async def _wait_for(
            pilot,
            predicate,
            *,
            timeout: float = 8.0,
            label: str = "condition",
            debug_text=None,
        ) -> None:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                await pilot.pause(0.05)
                if predicate():
                    return
            detail = f": {debug_text()}" if callable(debug_text) else ""
            raise AssertionError(f"{label} not observed within {timeout:.1f}s{detail}")

        started_prompts: list[str] = []
        started_event = threading.Event()
        release_event = threading.Event()

        def _runtime_factory(app, tab_id, source_runtime):
            del app, tab_id, source_runtime
            return _BlockingChildRuntime(
                started_prompts=started_prompts,
                started_event=started_event,
                release_event=release_event,
            )

        app = AgentCliApp(runtime=self._make_runtime())
        app._codex_sidecar_kernel = CodexSidecarKernel(
            codex_bin=FAKE_CODEX_BIN,
            request_timeout=3,
        )
        with patch(
            "cli.agent_cli.ui.tab_session_manager._fork_tab_runtime",
            _runtime_factory,
        ):
            async with app.run_test() as pilot:
                await pilot.pause()
                parent_tab_id = app._tab_manager.create_tab(engine="codex_sidecar")
                await pilot.pause()
                parent = app._tab_manager.get(parent_tab_id)
                assert parent is not None

                _submit_text(
                    app,
                    parent_tab_id,
                    "请用 visible child tabs 并发拆两个任务：一个看 README，一个看 docs。",
                )

                await _wait_for(
                    pilot,
                    lambda: len(app._tab_manager.child_tab_ids(parent_tab_id)) == 2,
                    label="two natural-language visible child tabs spawned",
                    debug_text=lambda: str(app._tab_manager.tab_labels()),
                )
                await _wait_for(
                    pilot,
                    started_event.is_set,
                    label="both child tabs started before either could finish",
                    debug_text=lambda: str(started_prompts),
                )

                child_ids = app._tab_manager.child_tab_ids(parent_tab_id)
                assert [app._tab_manager.get(tab_id).custom_label for tab_id in child_ids] == [
                    "README",
                    "DOCS",
                ]
                assert len(started_prompts) == 2
                assert any("README child" in prompt for prompt in started_prompts)
                assert any("Docs child" in prompt for prompt in started_prompts)
                assert all(app._tab_manager.get(tab_id).is_busy for tab_id in child_ids)
                current_runs = app._tab_manager.child_task_runs(parent_tab_id)
                assert len([run for run in current_runs if run.state == "running"]) == 2
                assert not [run for run in current_runs if run.terminal_state == "completed"]

                release_event.set()
                await _wait_for(
                    pilot,
                    lambda: len(
                        [
                            run
                            for run in app._tab_manager.child_task_runs(parent_tab_id)
                            if run.terminal_state == "completed"
                        ]
                    )
                    >= 2,
                    timeout=8.0,
                    label="both natural-language child task runs completed",
                    debug_text=lambda: str(
                        [run.to_dict() for run in app._tab_manager.child_task_runs(parent_tab_id)]
                    ),
                )

                completed_runs = [
                    run
                    for run in app._tab_manager.child_task_runs(parent_tab_id)
                    if run.terminal_state == "completed"
                ]
                assert sorted(run.assignment_ref.get("card_id") for run in completed_runs) == [
                    "DOCS",
                    "README",
                ]
                assert len(parent.child_task_inbox) == 2
                assert all("summary" in update for update in parent.child_task_inbox)
                assert any("Child tab README finished" in line for line in parent.transcript_lines)
                assert any("Child tab DOCS finished" in line for line in parent.transcript_lines)

    async def test_codex_sidecar_background_turn_marks_dirty(self):
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        app = AgentCliApp(runtime=self._make_runtime())
        app._codex_sidecar_kernel = CodexSidecarKernel(
            codex_bin=FAKE_CODEX_BIN,
            request_timeout=3,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            tab_id = app._tab_manager.create_tab(engine="codex_sidecar")
            await pilot.pause()
            session = app._tab_manager.get(tab_id)
            assert session is not None
            assert app._tab_manager.switch_to_tab("main")
            await pilot.pause()

            await session.request_queue.put(QueuedRuntimeRequest(text="background", attachments=[]))
            await session.request_queue.join()
            await pilot.pause()

            assert app._tab_manager.active_tab_id == "main"
            assert session.transcript_dirty is True
            assert session.runtime.history[-1]["content"] == "background"

    async def test_codex_sidecar_fork_after_turn_uses_thread_fork(self):
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        app = AgentCliApp(runtime=self._make_runtime())
        app._codex_sidecar_kernel = CodexSidecarKernel(
            codex_bin=FAKE_CODEX_BIN,
            request_timeout=3,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            source_tab_id = app._tab_manager.create_tab(engine="codex_sidecar")
            await pilot.pause()
            source = app._tab_manager.get(source_tab_id)
            assert source is not None
            await source.request_queue.put(
                QueuedRuntimeRequest(
                    text="seed fork",
                    attachments=[],
                    display_text="seed fork",
                )
            )
            await source.request_queue.join()
            await pilot.pause()
            source_thread_id = source.runtime.thread_id

            fork_tab_id = app._tab_manager.fork_tab(source_tab_id)
            await pilot.pause()

            forked = app._tab_manager.get(fork_tab_id)
            assert forked is not None
            assert forked.engine == "codex_sidecar"
            assert forked.runtime.thread_id != source_thread_id
            assert forked.forked_from_tab_id == source_tab_id
            assert forked.forked_from_thread_id == source_thread_id
            assert forked.fork_mode == "idle"
            assert any("seed fork" in str(line) for line in app._transcript_lines)
            assert any("fake sidecar reply" in str(line) for line in app._transcript_lines)

    async def test_codex_sidecar_blank_fork_falls_back_to_start(self):
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        app = AgentCliApp(runtime=self._make_runtime())
        app._codex_sidecar_kernel = CodexSidecarKernel(
            codex_bin=FAKE_CODEX_BIN,
            request_timeout=3,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            source_tab_id = app._tab_manager.create_tab(engine="codex_sidecar")
            await pilot.pause()
            source = app._tab_manager.get(source_tab_id)
            assert source is not None
            source_thread_id = source.runtime.thread_id

            fork_tab_id = app._tab_manager.fork_tab(source_tab_id)
            await pilot.pause()

            forked = app._tab_manager.get(fork_tab_id)
            assert forked is not None
            assert forked.engine == "codex_sidecar"
            assert forked.runtime.thread_id != source_thread_id
            assert forked.runtime.history_turns == []
            assert forked.forked_from_tab_id == source_tab_id
            assert forked.forked_from_thread_id == source_thread_id

    async def test_codex_sidecar_manifest_restore_uses_thread_resume(self):
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "tabs.json"
            sidecar_state_path = Path(temp_dir) / "fake_sidecar_state.json"
            app = AgentCliApp(runtime=self._make_runtime())
            app._codex_sidecar_kernel = CodexSidecarKernel(
                codex_bin=FAKE_CODEX_BIN,
                extra_env={"FAKE_CODEX_SIDECAR_STATE": str(sidecar_state_path)},
                request_timeout=3,
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                tab_id = app._tab_manager.create_tab(engine="codex_sidecar")
                await pilot.pause()
                session = app._tab_manager.get(tab_id)
                assert session is not None
                await session.request_queue.put(
                    QueuedRuntimeRequest(
                        text="persist sidecar",
                        attachments=[],
                        display_text="persist sidecar",
                    )
                )
                await session.request_queue.join()
                await pilot.pause()
                thread_id = session.runtime.thread_id
                app._tab_manager.configure_manifest_path(manifest_path)
                app._tab_manager.save_manifest()

            restored_app = AgentCliApp(runtime=self._make_runtime())
            restored_app._codex_sidecar_kernel = CodexSidecarKernel(
                codex_bin=FAKE_CODEX_BIN,
                extra_env={"FAKE_CODEX_SIDECAR_STATE": str(sidecar_state_path)},
                request_timeout=3,
            )
            restored_app._tab_manager.configure_manifest_path(manifest_path)
            manifest = load_tab_session_manifest(manifest_path)
            assert manifest is not None
            assert restored_app._tab_manager.restore_from_manifest(
                manifest,
                source_runtime=restored_app.runtime,
            )

            async with restored_app.run_test() as pilot:
                await pilot.pause()
                restored = restored_app._tab_manager.get(tab_id)
                assert restored is not None
                assert restored.engine == "codex_sidecar"
                assert restored.runtime.thread_id == thread_id
                assert restored.runtime.history_turns[-1]["user_text"] == "persist sidecar"
                assert restored.runtime.turn_results[-1].user_text == "persist sidecar"
                assert restored.runtime.turn_results[-1].assistant_text == "fake sidecar reply"
                assert any(
                    "persist sidecar" in str(line) for line in restored_app._transcript_lines
                )
                assert any(
                    "fake sidecar reply" in str(line) for line in restored_app._transcript_lines
                )

    async def test_codex_sidecar_manifest_resume_failure_records_partial_notice(self):
        from cli.agent_cli.runtime_kernels.codex_sidecar.errors import CodexSidecarRequestError

        class FailingResumeKernel:
            async def resume_session(self, request):
                raise CodexSidecarRequestError(f"missing rollout for {request.thread_id}")

        app = AgentCliApp(runtime=self._make_runtime())
        app._codex_sidecar_kernel = FailingResumeKernel()
        manifest = TabSessionManifest(
            active_tab_id="main",
            tab_order=["main", "codex-tab"],
            tabs=[
                TabSessionManifestTab(tab_id="main", thread_id=app.runtime.thread_id),
                TabSessionManifestTab(
                    tab_id="codex-tab",
                    thread_id="codex-missing",
                    engine="codex_sidecar",
                    kernel_session_id="codex-missing",
                ),
            ],
        )

        assert app._tab_manager.restore_from_manifest(manifest, source_runtime=app.runtime)
        assert app._tab_manager._tab_order == ["main"]
        errors = getattr(app, "_codex_sidecar_restore_errors", [])
        assert errors == [
            {
                "tab_id": "codex-tab",
                "thread_id": "codex-missing",
                "error": "missing rollout for codex-missing",
            }
        ]
        notice = app._tab_manager.pop_manifest_restore_notice()
        assert notice is not None
        key, params = notice
        assert key == "system.tab_manifest_restore_partial_detail"
        assert params["restored_count"] == 1
        assert params["skipped_count"] == 1
        assert "codex-tab" in params["error_preview"]
        assert "missing rollout" in params["error_preview"]


class TestCloseTabWorkerCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_close_idle_tab_cancels_worker(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            tab_id = app._tab_manager.active_tab_id
            session = app._tab_manager.get(tab_id)
            worker = session.request_worker_task
            assert worker is not None
            app.action_close_tab()
            await pilot.pause()
            assert worker.cancelled() or worker.done()


class TestBackgroundTabOutputIsolation(unittest.IsolatedAsyncioTestCase):
    async def test_background_tab_transcript_not_visible(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            main_entries_before = list(app._transcript_entries)
            app.action_new_tab()
            await pilot.pause()
            new_tab_id = app._tab_manager.active_tab_id
            session = app._tab_manager.get(new_tab_id)
            assert session is not None
            session.transcript_entries = ["bg-entry-1"]
            session.transcript_dirty = True
            assert app._transcript_entries == main_entries_before

    async def test_background_reply_marks_unread_until_tab_switch(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"
            active_entries_before = list(app._transcript_entries)

            app._write_reply_for_tab("main", "background done")
            await pilot.pause()

            main_session = app._tab_manager.get("main")
            assert main_session is not None
            assert main_session.transcript_dirty is True
            assert main_session.has_unread_output is True
            assert any("background done" in line for line in main_session.transcript_lines)
            assert app._transcript_entries == active_entries_before
            assert "*" in app.query_one("#tab_bar", TabBar).render().plain

            app.action_prev_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "main"
            assert main_session.transcript_dirty is False
            assert main_session.has_unread_output is False
            assert any("background done" in line for line in app._transcript_lines)
            assert "*" not in app.query_one("#tab_bar", TabBar).render().plain

    async def test_background_response_render_marks_unread_until_tab_switch(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"
            active_lines_before = list(app._transcript_lines)

            app._render_response_for_tab(
                "main",
                PromptResponse(user_text="background prompt", assistant_text="background answer"),
            )
            await pilot.pause()

            main_session = app._tab_manager.get("main")
            assert main_session is not None
            assert main_session.transcript_dirty is True
            assert main_session.has_unread_output is True
            assert any("background answer" in line for line in main_session.transcript_lines)
            assert app._transcript_lines == active_lines_before
            assert "*" in app.query_one("#tab_bar", TabBar).render().plain

            app.action_prev_tab()
            await pilot.pause()
            assert main_session.transcript_dirty is False
            assert main_session.has_unread_output is False
            assert any("background answer" in line for line in app._transcript_lines)

    async def test_background_turn_event_renders_into_session_without_polluting_active_tab(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"
            active_lines_before = list(app._transcript_lines)
            active_turn_key_before = app._active_transcript_turn_key

            app._on_tab_turn_event(
                "main",
                {
                    "type": "item.completed",
                    "item": {
                        "id": "bg-agent-message",
                        "type": "agent_message",
                        "text": "background live answer",
                    },
                },
            )
            await pilot.pause()

            main_session = app._tab_manager.get("main")
            assert main_session is not None
            assert main_session.transcript_dirty is True
            assert main_session.has_unread_output is False
            assert any("background live answer" in line for line in main_session.transcript_lines)
            assert app._transcript_lines == active_lines_before
            assert app._active_transcript_turn_key == active_turn_key_before
            assert "~" in app.query_one("#tab_bar", TabBar).render().plain

            app.action_prev_tab()
            await pilot.pause()
            assert any("background live answer" in line for line in app._transcript_lines)
            assert main_session.transcript_dirty is False
            assert main_session.has_unread_output is False

    async def test_background_activity_renders_into_session_without_polluting_active_tab(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"
            active_lines_before = list(app._transcript_lines)

            app._on_tab_activity(
                "main",
                ActivityEvent(
                    title="Running command",
                    status="info",
                    detail="echo background activity",
                    kind="command",
                    code="command.running",
                ),
            )
            await pilot.pause()

            main_session = app._tab_manager.get("main")
            assert main_session is not None
            assert main_session.transcript_dirty is True
            assert any("background activity" in line for line in main_session.transcript_lines)
            assert app._transcript_lines == active_lines_before
            assert "~" in app.query_one("#tab_bar", TabBar).render().plain

    async def test_background_busy_change_refreshes_tab_bar_marker(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"

            app._set_busy_for_tab("main", True)
            await pilot.pause()
            assert "●" in app.query_one("#tab_bar", TabBar).render().plain

            app._set_busy_for_tab("main", False)
            await pilot.pause()
            assert "●" not in app.query_one("#tab_bar", TabBar).render().plain

    async def test_real_worker_background_completion_marks_unread_until_switch(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            main_runtime = app.runtime
            release_worker = threading.Event()

            def _slow_handle_prompt(text: str, *, attachments=None):
                del attachments
                release_worker.wait(timeout=5.0)
                return PromptResponse(
                    user_text=text,
                    assistant_text="real worker background complete",
                )

            main_runtime.handle_prompt = _slow_handle_prompt  # type: ignore[method-assign]
            await app._enqueue_runtime_request("real worker background prompt", [])
            for _ in range(80):
                main_session = app._tab_manager.get("main")
                if main_session is not None and main_session.is_busy:
                    break
                await asyncio.sleep(0.02)
            main_session = app._tab_manager.get("main")
            assert main_session is not None
            assert main_session.is_busy is True

            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"
            assert "●" in app.query_one("#tab_bar", TabBar).render().plain
            release_worker.set()

            for _ in range(120):
                if main_session.has_unread_output:
                    break
                await asyncio.sleep(0.05)
            await pilot.pause()
            assert main_session.is_busy is False
            assert main_session.transcript_dirty is True
            assert main_session.has_unread_output is True
            assert any(
                "real worker background complete" in line for line in main_session.transcript_lines
            )
            assert not any(
                "real worker background complete" in line for line in app._transcript_lines
            )
            assert "*" in app.query_one("#tab_bar", TabBar).render().plain

            app.action_prev_tab()
            await pilot.pause()
            assert any("real worker background complete" in line for line in app._transcript_lines)
            assert main_session.transcript_dirty is False
            assert main_session.has_unread_output is False

    async def test_background_worker_completion_does_not_update_active_thread_id(self):
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        async with app.run_test() as pilot:
            await pilot.pause()
            main_session = app._tab_manager.get("main")
            assert main_session is not None
            main_thread_id = main_session.runtime.thread_id

            app.action_new_tab()
            await pilot.pause()
            active_session = app._tab_manager.active_session
            active_thread_id = active_session.runtime.thread_id
            assert app._tab_manager.active_tab_id == "tab-1"
            assert active_thread_id != main_thread_id
            assert app.runtime.thread_store.get_active_thread_id() == active_thread_id

            release_worker = threading.Event()

            def _background_plan(text: str, **kwargs):
                del kwargs
                release_worker.wait(timeout=5.0)
                return AgentIntent(
                    assistant_text="background persisted without activating",
                )

            main_session.runtime.agent.plan = _background_plan  # type: ignore[method-assign]
            await main_session.request_queue.put(
                QueuedRuntimeRequest(
                    text="background persist prompt",
                    attachments=[],
                )
            )
            for _ in range(80):
                if main_session.is_busy:
                    break
                await asyncio.sleep(0.02)
            assert main_session.is_busy is True
            release_worker.set()

            for _ in range(120):
                if main_session.has_unread_output:
                    break
                await asyncio.sleep(0.05)
            await pilot.pause()

            assert main_session.has_unread_output is True
            assert app._tab_manager.active_tab_id == "tab-1"
            assert app.runtime.thread_store.get_active_thread_id() == active_thread_id
            active_before_resume = app.runtime.thread_store.get_active_thread_id()
            resumed = app.runtime.thread_store.resume_thread(main_thread_id)
            assert any(
                turn.get("assistant_text") == "background persisted without activating"
                for turn in list(resumed.get("turns") or [])
            )
            app.runtime.thread_store.set_active_thread_id(active_before_resume)


class TestTabPendingInteractions(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _make_runtime():
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        return build_persistent_runtime(resume_active_thread=False)

    async def test_background_approval_marks_tab_pending_until_switch(self):
        from cli.agent_cli.gateway_core import ApprovalTicket

        approval_id = "appr_bg_switch"
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            main_session = app._tab_manager.get("main")
            assert main_session is not None
            main_session.runtime.gateway_state_store.save_approval_ticket(
                ApprovalTicket(
                    approval_id=approval_id,
                    action_id="act_bg_switch",
                    trace_id="trace_bg_switch",
                    status="pending",
                    requested_at="2026-05-09T00:00:00Z",
                    requested_by="test",
                    summary="Approve main shell",
                    available_decisions=[{"type": "accept"}, {"type": "decline"}],
                )
            )
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"

            app._on_tab_activity(
                "main",
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail=approval_id,
                    code="approval.request.shell",
                    params={"approval_id": approval_id},
                ),
            )
            await pilot.pause()

            main_session = app._tab_manager.get("main")
            assert main_session is not None
            assert main_session.pending_approvals == [approval_id]
            assert app._tab_manager.active_tab_id == "tab-1"
            assert app.status_data.get("latest_pending_approval_id") != approval_id
            rendered = app.query_one("#tab_bar", TabBar).render().plain
            assert "!" in rendered
            assert "~" not in rendered

            app.action_prev_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "main"
            assert app.status_data.get("latest_pending_approval_id") == approval_id

    async def test_new_tab_does_not_inherit_existing_tab_approval_status(self):
        from cli.agent_cli.gateway_core import ApprovalTicket

        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            main_session = app._tab_manager.active_session
            main_session.runtime.gateway_state_store.save_approval_ticket(
                ApprovalTicket(
                    approval_id="appr_main",
                    action_id="act_main",
                    trace_id="trace_main",
                    status="pending",
                    requested_at="2026-05-09T00:00:00Z",
                    requested_by="test",
                    summary="Approve main shell",
                    available_decisions=[{"type": "accept"}, {"type": "decline"}],
                )
            )
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail="appr_main",
                    code="approval.request.shell",
                    params={"approval_id": "appr_main"},
                )
            )
            await pilot.pause()
            assert main_session.pending_approvals == ["appr_main"]
            assert app.status_data.get("latest_pending_approval_id") == "appr_main"

            app.action_new_tab()
            await pilot.pause()

            assert app._tab_manager.active_tab_id == "tab-1"
            assert app._tab_manager.active_session.pending_approvals == []
            assert app.status_data.get("pending_approvals") == "0"
            assert app.status_data.get("latest_pending_approval_id") == "-"
            assert getattr(app, "_pending_approval_surface_id", "") in {"", "-"}
            assert list(getattr(app, "_approval_overlay_queue", []) or []) == []

            app.action_prev_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "main"
            assert app.status_data.get("pending_approvals") == "1"
            assert app.status_data.get("latest_pending_approval_id") == "appr_main"

    async def test_pending_approval_decision_uses_owning_tab_runtime(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"

            main_session = app._tab_manager.get("main")
            active_session = app._tab_manager.active_session
            assert main_session is not None
            main_runtime = SimpleNamespace(name="main-sidecar-runtime")
            active_runtime = SimpleNamespace(name="active-python-runtime")
            main_session.runtime = main_runtime
            active_session.runtime = active_runtime
            main_session.pending_approvals = ["appr_main"]

            assert app._tab_id_for_pending_approval("appr_main") == "main"
            assert app._runtime_for_pending_approval("appr_main") is main_runtime
            assert app._runtime_for_pending_approval("missing") is active_runtime

    async def test_manual_approval_command_must_run_in_owning_tab(self):
        app = AgentCliApp(runtime=self._make_runtime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"

            main_session = app._tab_manager.get("main")
            active_session = app._tab_manager.active_session
            assert main_session is not None
            main_session.pending_approvals = ["appr_main"]

            await app._enqueue_runtime_request("/approve appr_main", [], priority="later")
            await pilot.pause()

            assert main_session.request_queue.qsize() == 0
            assert active_session.request_queue.qsize() == 0
            assert main_session.pending_approvals == ["appr_main"]
            assert notices == [
                app._t(
                    "system.approval_wrong_tab",
                    approval_id="appr_main",
                    tab_id="main",
                )
            ]

            app.action_prev_tab()
            await pilot.pause()
            await app._enqueue_runtime_request("/approve appr_main", [], priority="later")

            assert main_session.request_queue.qsize() == 1

    async def test_pending_interaction_summary_lists_background_tabs(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            main_session = app._tab_manager.get("main")
            active_session = app._tab_manager.active_session
            assert main_session is not None
            main_session.thread_name = "Main pending approvals"
            main_session.pending_approvals = ["appr_main_1", "appr_main_2"]
            active_session.pending_request_user_input = _PendingRequestUserInput(
                payload={}, tab_id=app._tab_manager.active_tab_id
            )

            summary = app._tab_pending_interaction_summary()
            main_summary = next(item for item in summary if item["tab_id"] == "main")
            active_summary = next(
                item for item in summary if item["tab_id"] == app._tab_manager.active_tab_id
            )
            assert main_summary["label"] == "Main pending approvals"
            assert main_summary["approvals"] == 2
            assert main_summary["request_user_input"] == 0
            assert main_summary["total"] == 2
            assert main_summary["is_active"] is False
            assert active_summary["approvals"] == 0
            assert active_summary["request_user_input"] == 1
            assert active_summary["is_active"] is True

            hint = app._build_tab_pending_interaction_hint(120)
            assert "2" in hint
            assert "Main pending ap" in hint
            assert ":2" in hint
            active_session.pending_request_user_input = None

    async def test_approval_inbox_rows_prune_resolved_tickets(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            main_session = app._tab_manager.get("main")
            assert main_session is not None
            main_session.thread_name = "Main pending approvals"
            main_session.pending_approvals = ["appr_pending", "appr_resolved"]
            app._approval_ticket_status = (  # type: ignore[method-assign]
                lambda approval_id: "approved" if approval_id == "appr_resolved" else "pending"
            )

            rows = app._tab_approval_inbox_rows()

            assert main_session.pending_approvals == ["appr_pending"]
            assert rows == [
                {
                    "tab_id": "main",
                    "label": "Main pending approvals",
                    "is_active": False,
                    "approvals": [
                        {
                            "approval_id": "appr_pending",
                            "status": "pending",
                            "summary": "",
                            "action_id": "",
                        }
                    ],
                    "total": 1,
                }
            ]

    async def test_background_request_user_input_waits_until_tab_switch(self):
        app = AgentCliApp(runtime=self._make_runtime())
        payload = {
            "questions": [
                {
                    "id": "confirm_reset",
                    "header": "Confirm",
                    "question": "Continue?",
                    "options": [
                        {"label": "Yes (Recommended)", "description": "Continue."},
                        {"label": "No", "description": "Stop."},
                    ],
                }
            ]
        }
        presenter_calls = []

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del on_cancel
            presenter_calls.append(payload)
            on_submit({"answers": {"confirm_reset": {"answers": ["Yes (Recommended)"]}}})
            return True

        app._request_user_input_modal_presenter = _presenter
        result: dict[str, object] = {}

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"

            def _call_handler() -> None:
                result["value"] = app._handle_request_user_input_from_runtime_for_tab(
                    "main", payload
                )

            thread = threading.Thread(target=_call_handler, daemon=True)
            thread.start()
            for _ in range(80):
                main_session = app._tab_manager.get("main")
                if main_session is not None and main_session.pending_request_user_input is not None:
                    break
                await asyncio.sleep(0.05)
            main_session = app._tab_manager.get("main")
            assert main_session is not None
            assert main_session.pending_request_user_input is not None
            assert presenter_calls == []
            await pilot.pause()
            assert "!" in app.query_one("#tab_bar", TabBar).render().plain

            app.action_prev_tab()
            for _ in range(80):
                if "value" in result:
                    break
                await asyncio.sleep(0.05)
            thread.join(timeout=1)

            assert app._tab_manager.active_tab_id == "main"
            assert result["value"] == {
                "answers": {"confirm_reset": {"answers": ["Yes (Recommended)"]}}
            }
            assert main_session.pending_request_user_input is None
            assert presenter_calls

    async def test_background_request_user_input_updates_pending_summary(self):
        app = AgentCliApp(runtime=self._make_runtime())
        payload = {
            "questions": [
                {
                    "id": "confirm_reset",
                    "header": "Confirm",
                    "question": "Continue?",
                    "options": [
                        {"label": "Yes (Recommended)", "description": "Continue."},
                        {"label": "No", "description": "Stop."},
                    ],
                }
            ]
        }
        presenter_calls = []

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit, on_cancel
            presenter_calls.append(True)
            return True

        app._request_user_input_modal_presenter = _presenter
        result: dict[str, object] = {}

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_tab()
            await pilot.pause()
            assert app._tab_manager.active_tab_id == "tab-1"

            def _call_handler() -> None:
                result["value"] = app._handle_request_user_input_from_runtime_for_tab(
                    "main", payload
                )

            thread = threading.Thread(target=_call_handler, daemon=True)
            thread.start()
            for _ in range(80):
                summary = app._tab_pending_interaction_summary()
                if any(item["tab_id"] == "main" and item["total"] == 1 for item in summary):
                    break
                await asyncio.sleep(0.05)

            summary = app._tab_pending_interaction_summary()
            assert any(item["tab_id"] == "main" and item["total"] == 1 for item in summary)
            hint = ""
            for _ in range(80):
                hint = _static_plain(app.query_one("#status_line"))
                if "1" in hint:
                    break
                await asyncio.sleep(0.05)
            assert "1" in hint
            assert "AgentHub" in hint
            assert presenter_calls == []
            assert "value" not in result

            main_session = app._tab_manager.get("main")
            assert main_session is not None
            pending = main_session.pending_request_user_input
            assert pending is not None
            pending.cancelled = True
            pending.response_payload = None
            main_session.pending_request_user_input = None
            pending.response_event.set()
            thread.join(timeout=1)
            assert result["value"] is None


class TestForkTab(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _make_runtime():
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        return build_persistent_runtime(resume_active_thread=False)

    async def test_fork_copies_transcript(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app._transcript_entries = ["entry-1", "entry-2"]
            app._transcript_lines = ["line-1", "line-2"]
            app._tab_manager.active_session.transcript_entries = ["entry-1", "entry-2"]
            app._tab_manager.active_session.transcript_lines = ["line-1", "line-2"]
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            fork_session = app._tab_manager.get(tab_id)
            assert fork_session is not None
            assert fork_session.transcript_entries == ["entry-1", "entry-2"]
            assert fork_session.transcript_lines == ["line-1", "line-2"]

    async def test_fork_has_independent_runtime(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            source_runtime = app.runtime
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            fork_session = app._tab_manager.get(tab_id)
            assert fork_session is not None
            assert fork_session.runtime is not source_runtime
            assert fork_session.runtime.thread_id != source_runtime.thread_id

    async def test_fork_records_source_metadata(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            source_thread_id = app.runtime.thread_id
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            fork_session = app._tab_manager.get(tab_id)
            assert fork_session is not None
            assert fork_session.forked_from_tab_id == "main"
            assert fork_session.forked_from_thread_id == source_thread_id
            assert fork_session.fork_mode == "idle"

    async def test_fork_has_independent_history(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            source_runtime = app.runtime
            source_history_before = list(source_runtime.history)
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            fork_session = app._tab_manager.get(tab_id)
            assert fork_session is not None
            assert fork_session.runtime.history == source_history_before
            fork_session.runtime.history.append(
                {"type": "message", "role": "user", "content": "fork-only"}
            )
            assert fork_session.runtime.history != source_runtime.history

    async def test_fork_busy_tab_succeeds(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            app._tab_manager.active_session.is_busy = True
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""

    async def test_fork_busy_tab_does_not_copy_live_transcript(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            # Set both app-level and session-level transcript state
            live_lines = [
                "› persisted question",
                "• persisted answer",
                "› inprogress partial",
            ]
            app._transcript_lines = list(live_lines)
            app._tab_manager.active_session.transcript_lines = list(live_lines)
            app._tab_manager.active_session.is_busy = True
            source_lines_snapshot = list(live_lines)
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            fork_session = app._tab_manager.get(tab_id)
            assert fork_session is not None
            # Fork should NOT have the live in-progress content
            assert "inprogress partial" not in fork_session.transcript_lines
            # Fork transcript differs from source's live transcript
            assert fork_session.transcript_lines != source_lines_snapshot

    async def test_fork_busy_rebuilds_from_history_when_no_turns(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            source = app._tab_manager.active_session
            # Set up app-level transcript with live content
            app._transcript_lines = ["› live question", "• live answer", "› inprogress"]
            source.transcript_lines = list(app._transcript_lines)
            source.is_busy = True
            # Fork — the fork runtime will have runtime.history but no history_turns
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            fork_session = app._tab_manager.get(tab_id)
            assert fork_session is not None
            # Fork should not have in-progress content
            assert "inprogress" not in fork_session.transcript_lines
            # All entries must be real TranscriptEntry objects, not raw dicts
            for entry in fork_session.transcript_entries:
                assert isinstance(
                    entry, TranscriptEntry
                ), f"expected TranscriptEntry, got {type(entry)}"
            # If runtime has history, transcript should be non-empty
            fork_runtime = fork_session.runtime
            if fork_runtime and fork_runtime.history:
                assert len(fork_session.transcript_lines) > 0

    async def test_fork_busy_adds_ui_only_running_fork_notice(self):
        runtime = self._make_runtime()
        runtime.resume_thread(
            history=[
                {"type": "message", "role": "user", "content": "seed user"},
                {"type": "message", "role": "assistant", "content": "seed answer"},
            ]
        )
        app = AgentCliApp(runtime=runtime)
        async with app.run_test() as pilot:
            await pilot.pause()
            source = app._tab_manager.active_session
            app._write_user_prompt("seed user")
            app._write_assistant_reply("seed answer")
            app._write_user_prompt("live partial")
            source.transcript_lines = list(app._transcript_lines)
            source.is_busy = True

            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            fork_session = app._tab_manager.get(tab_id)
            assert fork_session is not None
            assert any(RUNNING_FORK_NOTICE in line for line in fork_session.transcript_lines)
            assert not any("live partial" in line for line in fork_session.transcript_lines)
            assert not any(
                RUNNING_FORK_NOTICE in str(item) for item in fork_session.runtime.history
            )

    async def test_fork_busy_survives_subsequent_message(self):
        runtime = self._make_runtime()
        runtime.resume_thread(
            history=[
                {"type": "message", "role": "user", "content": "seed user"},
                {"type": "message", "role": "assistant", "content": "seed answer"},
            ]
        )
        app = AgentCliApp(runtime=runtime)
        async with app.run_test() as pilot:
            await pilot.pause()
            source = app._tab_manager.active_session
            app._write_user_prompt("seed user")
            app._write_assistant_reply("seed answer")
            app._write_user_prompt("inprogress")
            source.transcript_lines = list(app._transcript_lines)
            source.is_busy = True
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            app._write_user_prompt("after fork")
            assert any("seed user" in line for line in app._transcript_lines)
            assert any("seed answer" in line for line in app._transcript_lines)
            assert any("after fork" in line for line in app._transcript_lines)
            assert not any("inprogress" in line for line in app._transcript_lines)

            log = app.query_one("#main_log", TranscriptArea)
            widget_lines = list(getattr(log, "_loaded_transcript_lines", []) or [])
            assert any("seed user" in line for line in widget_lines)
            assert any("after fork" in line for line in widget_lines)

            app._tab_manager.switch_to_tab("main")
            app._tab_manager.switch_to_tab(tab_id)
            assert any("seed user" in line for line in app._transcript_lines)
            assert any("after fork" in line for line in app._transcript_lines)

    async def test_fork_busy_rebuilds_from_structured_replay_items(self):
        runtime = self._make_runtime()
        runtime.resume_thread(
            history=[
                {"type": "message", "role": "user", "content": "seed user"},
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "seed reasoning"}],
                    "encrypted_content": "enc_seed",
                },
                {
                    "type": "function_call",
                    "call_id": "call_seed_1",
                    "name": "exec_command",
                    "arguments": '{"cmd":"pwd"}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_seed_1",
                    "output": "pwd output",
                },
                {"type": "message", "role": "assistant", "content": "seed answer"},
            ]
        )
        app = AgentCliApp(runtime=runtime)
        async with app.run_test() as pilot:
            await pilot.pause()
            source = app._tab_manager.active_session
            app._write_user_prompt("seed user")
            app._write_reasoning_reply("seed reasoning")
            app._write_system_notice("⚙ exec_command")
            app._write_system_notice("⚙ call_seed_1 output: pwd output")
            app._write_user_prompt("inprogress")
            source.transcript_lines = list(app._transcript_lines)
            source.is_busy = True

            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            fork_session = app._tab_manager.get(tab_id)
            assert fork_session is not None
            assert [item.get("type") for item in fork_session.runtime._planner_input_items] == [
                "message",
                "reasoning",
                "function_call",
                "function_call_output",
                "message",
            ]
            assert any("seed user" in line for line in fork_session.transcript_lines)
            assert any("seed reasoning" in line for line in fork_session.transcript_lines)
            assert any("exec_command" in line for line in fork_session.transcript_lines)
            assert any("pwd output" in line for line in fork_session.transcript_lines)
            assert any("seed answer" in line for line in fork_session.transcript_lines)
            assert not any("inprogress" in line for line in fork_session.transcript_lines)

    async def test_fork_switch_preserves_history(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            source = app._tab_manager.active_session
            app._transcript_lines = ["› live question", "• live answer"]
            source.transcript_lines = list(app._transcript_lines)
            source.is_busy = True
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id != ""
            fork_session = app._tab_manager.get(tab_id)
            fork_lines_after_fork = list(fork_session.transcript_lines)
            # Switch away and back
            app._tab_manager.switch_to_tab("main")
            app._tab_manager.switch_to_tab(tab_id)
            restored_session = app._tab_manager.get(tab_id)
            assert restored_session is not None
            assert restored_session.transcript_lines == fork_lines_after_fork

    async def test_fork_fallback_runtime_fails_gracefully(self):
        from cli.agent_cli.ui.runtime_bridge import FallbackRuntime

        app = AgentCliApp(runtime=FallbackRuntime())
        async with app.run_test() as pilot:
            await pilot.pause()
            tab_id = app._tab_manager.fork_tab("main")
            assert tab_id == ""
            assert len(app._tab_manager._tabs) == 1

    async def test_fork_max_tabs_rejected(self):
        app = AgentCliApp(runtime=self._make_runtime())
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(7):
                app.action_new_tab()
                await pilot.pause()
            assert len(app._tab_manager._tabs) == 8
            result = app._tab_manager.fork_tab("main")
            assert result == ""
            assert len(app._tab_manager._tabs) == 8

    async def test_fork_metadata_persists_through_manifest_restore(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            from cli.agent_cli.runtime import AgentCliRuntime
            from cli.agent_cli.thread_store import ThreadStore

            store = ThreadStore(Path(temp_dir) / "state")
            manifest_path = Path(temp_dir) / "tabs.json"
            runtime = AgentCliRuntime(thread_store=store)
            runtime.start_thread(name="main persisted")
            runtime.tui_tab_manifest_enabled = True
            app = AgentCliApp(runtime=runtime)
            app._tab_manager.configure_manifest_path(manifest_path)

            async with app.run_test() as pilot:
                await pilot.pause()
                main_thread_id = app._tab_manager.get("main").runtime.thread_id
                tab_id = app._tab_manager.fork_tab("main")
                await pilot.pause()
                fork_session = app._tab_manager.get(tab_id)
                assert fork_session is not None
                fork_thread_id = fork_session.runtime.thread_id
                app._tab_manager.save_manifest()

            restored_runtime = AgentCliRuntime(thread_store=store)
            restored_runtime.tui_tab_manifest_enabled = True
            restored_runtime.resume_thread(main_thread_id)
            restored_app = AgentCliApp(runtime=restored_runtime)
            restored_app._tab_manager.configure_manifest_path(manifest_path)
            assert restored_app._tab_manager.restore_from_manifest_if_available(restored_runtime)

            async with restored_app.run_test() as pilot:
                await pilot.pause()
                restored_fork = restored_app._tab_manager.get(tab_id)
                assert restored_fork is not None
                assert restored_fork.runtime.thread_id == fork_thread_id
                assert restored_fork.forked_from_tab_id == "main"
                assert restored_fork.forked_from_thread_id == main_thread_id
                assert restored_fork.fork_mode == "idle"


if __name__ == "__main__":
    unittest.main()
