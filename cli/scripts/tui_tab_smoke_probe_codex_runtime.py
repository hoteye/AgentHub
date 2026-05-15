from __future__ import annotations

# ruff: noqa: E402
import sys
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = CLI_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.runtime_factory import build_persistent_runtime
from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel
from cli.agent_cli.ui.runtime_bridge import QueuedRuntimeRequest
from cli.agent_cli.ui.tab_bar import TabBar

FAKE_CODEX_BIN = CLI_ROOT / "tests" / "fixtures" / "fake_codex_sidecar.py"


async def _probe_codex_sidecar_two_tab_prompts() -> None:
    app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
    app._codex_sidecar_kernel = CodexSidecarKernel(
        codex_bin=FAKE_CODEX_BIN,
        request_timeout=3,
    )
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause()
        tab_a = app._tab_manager.create_tab(engine="codex_sidecar")
        await pilot.pause()
        session_a = app._tab_manager.get(tab_a)
        assert session_a is not None
        assert session_a.engine == "codex_sidecar"
        await session_a.request_queue.put(
            QueuedRuntimeRequest(
                text="tab A: 你好，简单回答。",
                attachments=[],
                display_text="tab A: 你好，简单回答。",
            )
        )
        await session_a.request_queue.join()
        await pilot.pause()
        assert session_a.runtime.history_turns[-1]["assistant_text"] == "fake sidecar reply"
        assert any("tab A: 你好，简单回答。" in str(line) for line in app._transcript_lines)
        assert any("fake sidecar reply" in str(line) for line in app._transcript_lines)

        tab_b = app._tab_manager.create_tab(engine="codex_sidecar")
        await pilot.pause()
        session_b = app._tab_manager.get(tab_b)
        assert session_b is not None
        assert session_b.engine == "codex_sidecar"
        await session_b.request_queue.put(
            QueuedRuntimeRequest(
                text="tab B: 说一句测试回复。",
                attachments=[],
                display_text="tab B: 说一句测试回复。",
            )
        )
        await session_b.request_queue.join()
        await pilot.pause()
        assert session_b.runtime.history_turns[-1]["assistant_text"] == "fake sidecar reply"
        assert any("tab B: 说一句测试回复。" in str(line) for line in app._transcript_lines)
        assert any("fake sidecar reply" in str(line) for line in app._transcript_lines)

        assert app._tab_manager.switch_to_tab(tab_a)
        await pilot.pause()
        assert any("tab A: 你好，简单回答。" in str(line) for line in app._transcript_lines)
        assert not any("tab B: 说一句测试回复。" in str(line) for line in app._transcript_lines)

        assert app._tab_manager.switch_to_tab(tab_b)
        await pilot.pause()
        assert any("tab B: 说一句测试回复。" in str(line) for line in app._transcript_lines)
        assert not any("tab A: 你好，简单回答。" in str(line) for line in app._transcript_lines)

        for session in (session_a, session_b):
            diagnostics = session.runtime.turn_results[-1].protocol_diagnostics
            methods = [event.get("method") for event in diagnostics["codex_sidecar_events"]]
            assert "turn/started" in methods
            assert "item/agentMessage/delta" in methods
            assert "item/commandExecution/outputDelta" in methods
            assert "thread/tokenUsage/updated" in methods
            assert "turn/completed" in methods

        bar = app.query_one("#tab_bar", TabBar)
        rendered = bar.render().plain
        assert bar.orientation == "vertical"
        assert "1" in rendered and "2" in rendered
