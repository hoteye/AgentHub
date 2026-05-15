from __future__ import annotations

# ruff: noqa: E402
import argparse
import asyncio
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

CLI_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = CLI_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from textual.widgets import Static

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.app_runtime_flow_request_user_input_helpers import _PendingRequestUserInput
from cli.agent_cli.models import ActivityEvent, AgentIntent, PromptResponse
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_factory import build_persistent_runtime
from cli.agent_cli.thread_store import ThreadStore
from cli.agent_cli.ui import PromptComposer
from cli.agent_cli.ui.runtime_bridge import QueuedRuntimeRequest
from cli.agent_cli.ui.tab_bar import TabBar
from cli.scripts.tui_tab_smoke_probe_codex_runtime import _probe_codex_sidecar_two_tab_prompts


def _static_plain(widget: Any) -> str:
    renderable = getattr(widget, "renderable", None)
    if renderable is not None:
        return str(getattr(renderable, "plain", str(renderable)))
    rendered = widget.render()
    return str(getattr(rendered, "plain", str(rendered)))


async def _wait_until(
    predicate,
    *,
    timeout_iterations: int = 120,
    interval_seconds: float = 0.05,
) -> bool:
    for _ in range(timeout_iterations):
        if predicate():
            return True
        await asyncio.sleep(interval_seconds)
    return bool(predicate())


async def _probe_tab_lifecycle_and_overflow() -> None:
    app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause()
        labels = [
            "主会话策略分析上下文隔离恢复确认",
            "abcdefghijklmnopqrstuvwxyz0123456789",
            "策略-Provider-Alignment-OpenAI-Anthropic",
            "Chrome style tab overflow and pending summary",
            "中文English混合宽度Tab标题长文本",
            "Approval Queue Background Pending",
            "Request User Input Waiting Tab",
        ]
        app._tab_manager.active_session.thread_name = labels[0]
        app._refresh_top_title_bar()
        for label in labels[1:]:
            app.action_new_tab()
            await pilot.pause()
            app._tab_manager.active_session.thread_name = label
            app._refresh_top_title_bar()

        assert len(app._tab_manager._tabs) == 7
        assert app._tab_manager.active_tab_id == "tab-6"

        await pilot.press("ctrl+left")
        await pilot.pause()
        assert app._tab_manager.active_tab_id == "tab-5"
        await pilot.press("ctrl+right")
        await pilot.pause()
        assert app._tab_manager.active_tab_id == "tab-6"

        app.action_close_tab()
        await pilot.pause()
        assert app._tab_manager.active_tab_id == "tab-5"
        assert len(app._tab_manager._tabs) == 6

        bar = app.query_one("#tab_bar", TabBar)
        rendered = bar.render().plain
        assert "\n" in rendered
        assert len(bar._tab_spans) == 6
        assert all(end > start for _tab_id, start, end in bar._tab_spans)
        assert all(
            bar._tab_spans[idx][2] <= bar._tab_spans[idx + 1][1]
            for idx in range(len(bar._tab_spans) - 1)
        )
        assert bar._close_spans == []
        assert bar._close_hitboxes == []
        visible_height = int(getattr(bar.size, "height", 0) or 0)
        rail_lines = [line for line in rendered.splitlines() if line]
        rail_width = max(1, int(getattr(getattr(bar, "size", None), "width", 0) or 0))
        assert all(len(line) == rail_width for line in rail_lines)
        assert set("".join(rail_lines)) <= set(" 123456n▕🭾🭿▔▁")
        if visible_height > len(bar._tab_spans) * 3:
            assert bar._tab_spans[0][1] > 0
            assert rendered.startswith("\n" * bar._tab_spans[0][1])

        click_tab_id, click_start, click_end = next(
            span
            for span in bar._tab_spans
            if span[0] != app._tab_manager.active_tab_id and span[1] + 1 < visible_height
        )
        await pilot.click("#tab_bar", offset=(0, click_start + 1))
        await pilot.pause()
        assert app._tab_manager.active_tab_id == click_tab_id
        assert click_end > click_start

        closed_tab_id = app._tab_manager.active_tab_id
        app.action_close_tab()
        await pilot.pause()
        assert len(app._tab_manager._tabs) == 5
        assert closed_tab_id not in app._tab_manager._tabs


async def _probe_fork_idle_and_running() -> None:
    runtime = build_persistent_runtime(resume_active_thread=False)
    runtime.thread_store.append_turn(
        runtime.thread_id,
        PromptResponse(
            user_text="persisted parent prompt",
            assistant_text="persisted parent answer",
        ),
    )
    runtime.resume_thread(runtime.thread_id)
    app = AgentCliApp(runtime=runtime)
    async with app.run_test() as pilot:
        await pilot.pause()
        idle_source = app.runtime
        idle_fork_id = app._tab_manager.fork_tab("main")
        assert idle_fork_id
        idle_fork = app._tab_manager.get(idle_fork_id)
        assert idle_fork is not None
        assert idle_fork.runtime is not idle_source
        assert idle_fork.runtime.thread_id != idle_source.thread_id

        app._tab_manager.switch_to_tab("main")
        await pilot.pause()
        source = app._tab_manager.get("main")
        assert source is not None
        source.is_busy = True
        app._transcript_lines = [
            "› persisted parent prompt",
            "• persisted parent answer",
            "• live partial should not copy",
        ]
        source.transcript_lines = list(app._transcript_lines)
        running_fork_id = app._tab_manager.fork_tab("main")
        assert running_fork_id
        running_fork = app._tab_manager.get(running_fork_id)
        assert running_fork is not None
        assert "live partial should not copy" not in "\n".join(running_fork.transcript_lines)


async def _probe_background_completion_and_thread_store() -> None:
    app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
    async with app.run_test() as pilot:
        await pilot.pause()
        main_session = app._tab_manager.get("main")
        assert main_session is not None
        main_thread_id = main_session.runtime.thread_id

        app.action_new_tab()
        await pilot.pause()
        active_thread_id = app.runtime.thread_id
        assert app._tab_manager.active_tab_id == "tab-1"
        assert active_thread_id != main_thread_id

        release_worker = threading.Event()

        def _background_plan(text: str, **kwargs: Any) -> AgentIntent:
            del text, kwargs
            release_worker.wait(timeout=5.0)
            return AgentIntent(assistant_text="probe background persisted")

        main_session.runtime.agent.plan = _background_plan  # type: ignore[method-assign]
        await main_session.request_queue.put(
            QueuedRuntimeRequest(text="probe background prompt", attachments=[])
        )
        assert await _wait_until(lambda: bool(main_session.is_busy), timeout_iterations=80)
        release_worker.set()
        assert await _wait_until(lambda: bool(main_session.has_unread_output))
        await pilot.pause()

        assert main_session.is_busy is False
        assert main_session.has_unread_output is True
        assert "*" in app.query_one("#tab_bar", TabBar).render().plain
        assert app._tab_manager.active_tab_id == "tab-1"
        assert await _wait_until(
            lambda: app.runtime.thread_store.get_active_thread_id() == active_thread_id,
            timeout_iterations=80,
        )
        active_before_resume = app.runtime.thread_store.get_active_thread_id()
        resumed = app.runtime.thread_store.resume_thread(main_thread_id)
        assert any(
            turn.get("assistant_text") == "probe background persisted"
            for turn in list(resumed.get("turns") or [])
        )
        app.runtime.thread_store.set_active_thread_id(active_before_resume)

        app.action_prev_tab()
        await pilot.pause()
        assert app._tab_manager.active_tab_id == "main"
        assert main_session.has_unread_output is False


async def _probe_pending_interactions() -> None:
    app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause()
        app.action_new_tab()
        await pilot.pause()
        assert app._tab_manager.active_tab_id == "tab-1"

        app._on_tab_activity(
            "main",
            ActivityEvent(
                title="Requested shell approval",
                status="info",
                detail="appr_probe_main",
                code="approval.request.shell",
                params={"approval_id": "appr_probe_main"},
            ),
        )
        main_session = app._tab_manager.get("main")
        assert main_session is not None
        assert main_session.pending_approvals == ["appr_probe_main"]
        assert app.status_data.get("latest_pending_approval_id") != "appr_probe_main"

        tab_session = app._tab_manager.active_session
        tab_session.pending_request_user_input = _PendingRequestUserInput(
            payload={"questions": []},
            tab_id=app._tab_manager.active_tab_id,
        )
        app._refresh_tab_pending_interaction_indicators()
        await pilot.pause()

        rendered = app.query_one("#tab_bar", TabBar).render().plain
        assert "!" in rendered
        hint = _static_plain(app.query_one("#status_line", Static))
        assert "1" in hint

        app.action_prev_tab()
        await pilot.pause()
        assert app._tab_manager.active_tab_id == "main"
        assert app.status_data.get("latest_pending_approval_id") == "appr_probe_main"


async def _probe_restart_recovery() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
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
            app.action_new_tab()
            await pilot.pause()
            tab_thread_id = app._tab_manager.active_session.runtime.thread_id
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("probe restored draft")
            composer._set_cursor_position(6, extend=False)
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
            restored_composer = restored_app.query_one("#prompt_composer", PromptComposer)
            assert restored_composer.text == "probe restored draft"
            assert restored_composer.cursor_pos == 6


async def _probe_tab_rename_command_and_recovery() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        store = ThreadStore(Path(temp_dir) / "state")
        manifest_path = Path(temp_dir) / "tabs.json"
        runtime = AgentCliRuntime(thread_store=store)
        runtime.start_thread(name="main persisted")
        runtime.tui_tab_manifest_enabled = True

        app = AgentCliApp(runtime=runtime)
        app._tab_manager.configure_manifest_path(manifest_path)
        async with app.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            main_thread_id = app._tab_manager.get("main").runtime.thread_id
            app._set_prompt_text("/tab_rename Phase 11 Probe")
            await app.action_submit_prompt()
            await pilot.pause()

            assert app._tab_manager.active_session.custom_label == "Phase 11 Probe"
            assert "Phase 11 Probe" not in app.query_one("#tab_bar", TabBar).render().plain
            app._tab_manager.save_manifest()

        restored_runtime = AgentCliRuntime(thread_store=store)
        restored_runtime.tui_tab_manifest_enabled = True
        restored_runtime.resume_thread(main_thread_id)
        restored_app = AgentCliApp(runtime=restored_runtime)
        restored_app._tab_manager.configure_manifest_path(manifest_path)
        assert restored_app._tab_manager.restore_from_manifest_if_available(restored_runtime)

        async with restored_app.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            assert restored_app._tab_manager.active_session.custom_label == "Phase 11 Probe"
            assert "Phase 11 Probe" not in restored_app.query_one("#tab_bar", TabBar).render().plain
            restored_app._set_prompt_text("/tab_rename")
            await restored_app.action_submit_prompt()
            await pilot.pause()
            assert restored_app._tab_manager.active_session.custom_label == ""
            assert "Phase 11 Probe" not in restored_app.query_one("#tab_bar", TabBar).render().plain


async def _run() -> None:
    await _probe_tab_lifecycle_and_overflow()
    await _probe_fork_idle_and_running()
    await _probe_background_completion_and_thread_store()
    await _probe_pending_interactions()
    await _probe_restart_recovery()
    await _probe_tab_rename_command_and_recovery()
    await _probe_codex_sidecar_two_tab_prompts()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AgentHub TUI tab smoke probe.")
    parser.add_argument("--quiet", action="store_true", help="Only print failures.")
    args = parser.parse_args(argv)
    asyncio.run(_run())
    if not args.quiet:
        print("PROBE PASS tui tab smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
