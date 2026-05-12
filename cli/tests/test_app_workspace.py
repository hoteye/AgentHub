import re
import tempfile
import time
import unittest
from pathlib import Path

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.command_execution_summary_runtime import command_activity_params
from cli.agent_cli.models import (
    ActivityEvent,
    PromptResponse,
    ResponseInputItem,
    default_response_items,
)
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.ui.transcript_history import activity_entry


class AppWorkspaceTest(unittest.TestCase):
    _COMPLETION_SEPARATOR_RE = re.compile(r"^─{2,}.+─*$")

    @classmethod
    def _normalize_transcript_line(cls, line: str) -> str:
        text = str(line or "")
        if re.fullmatch(r"─+", text) or cls._COMPLETION_SEPARATOR_RE.fullmatch(text):
            return "<separator>"
        return text

    def wait_for_workspace_files(
        self, app: AgentCliApp, *, timeout_seconds: float = 1.0
    ) -> list[str]:
        deadline = time.monotonic() + max(0.05, float(timeout_seconds))
        files = app._workspace_files()
        while not files and time.monotonic() < deadline:
            time.sleep(0.02)
            files = app._workspace_files()
        return list(files)

    def assert_transcript_lines(self, actual: list[str], expected: list[str]) -> None:
        if len(actual) == len(expected) + 1 and re.match(
            r"^\s{2}(?:t|🏁)\s+\d{2}:\d{2}\s+(?:(?:⌛|⌛️|⏱|⏱️)\s+)?\d+[sm]$",
            str(actual[-1]),
        ):
            self.assertEqual(actual[:-1], expected)
            return
        self.assertEqual(
            [self._normalize_transcript_line(line) for line in actual],
            [self._normalize_transcript_line(line) for line in expected],
        )

    def test_app_uses_runtime_workspace_root_for_file_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            (workspace / "demo.txt").write_text("hello", encoding="utf-8")

            runtime = AgentCliRuntime()
            runtime.set_cwd(workspace)
            app = AgentCliApp(runtime=runtime)

            self.assertEqual(app._workspace_root, workspace.resolve())
            files = self.wait_for_workspace_files(app)
            self.assertIn("demo.txt", files)

    def test_app_refreshes_workspace_file_cache_when_runtime_cwd_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_a = root / "workspace-a"
            workspace_b = root / "workspace-b"
            workspace_a.mkdir()
            workspace_b.mkdir()
            (workspace_a / "alpha.txt").write_text("a", encoding="utf-8")
            (workspace_b / "beta.txt").write_text("b", encoding="utf-8")

            runtime = AgentCliRuntime()
            runtime.set_cwd(workspace_a)
            app = AgentCliApp(runtime=runtime)

            self.assertIn("alpha.txt", self.wait_for_workspace_files(app))
            runtime.set_cwd(workspace_b)

            files = self.wait_for_workspace_files(app)

            self.assertEqual(app._workspace_root, workspace_b.resolve())
            self.assertIn("beta.txt", files)
            self.assertNotIn("alpha.txt", files)

    def test_turn_event_entry_supports_partial_agent_message_updates(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        started_entry = app._turn_event_entry(
            {
                "type": "item.started",
                "item": {"id": "item_0", "type": "agent_message", "text": "先"},
            }
        )
        updated_entry = app._turn_event_entry(
            {
                "type": "item.updated",
                "item": {"id": "item_0", "type": "agent_message", "text": "先查看"},
            }
        )
        completed_entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "先查看当前目录。"},
            }
        )

        self.assertIsNone(started_entry)
        self.assertIsNotNone(updated_entry)
        self.assertIsNotNone(completed_entry)
        assert updated_entry is not None
        assert completed_entry is not None
        self.assertEqual(updated_entry.lines, ["• 先查看"])
        self.assertEqual(updated_entry.layer, "final")
        self.assertEqual(completed_entry.lines, ["• 先查看当前目录。"])
        self.assertEqual(completed_entry.layer, "final")

    def test_turn_event_entry_keeps_commentary_phase_distinct_from_final_answer(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        commentary_entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "agent_message",
                    "text": "我先查看当前目录。",
                    "phase": "commentary",
                },
            }
        )
        final_entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "agent_message",
                    "text": "当前目录下有 README.md。",
                    "phase": "final_answer",
                },
            }
        )

        assert commentary_entry is not None
        assert final_entry is not None
        self.assertEqual(commentary_entry.layer, "commentary")
        self.assertEqual(commentary_entry.status, "commentary")
        self.assertEqual(final_entry.layer, "final")
        self.assertEqual(final_entry.status, "final_answer")

    def test_turn_event_entry_hides_unheaded_reasoning_like_reference(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "reasoning", "text": "内部思考"},
            }
        )

        assert entry is None

    def test_turn_event_entry_renders_reasoning_summary(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "reasoning",
                    "text": "**Inspect** 先看目录，再决定是否读文件",
                },
            }
        )

        assert entry is not None
        self.assertEqual(entry.kind, "reasoning")
        self.assertEqual(entry.layer, "reasoning")
        self.assertEqual(entry.render_mode, "reasoning_markdown")
        self.assertEqual(entry.raw_content, "先看目录，再决定是否读文件")

    def test_busy_status_header_extracts_first_bold_from_reasoning_like_reference(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._refresh_dynamic_hint = lambda: None

        app._update_busy_status_from_reasoning_item(
            {"type": "reasoning", "text": "**Search** 检查仓库"}
        )

        self.assertEqual(app._busy_status_label, "Search")

    def test_busy_status_header_compacts_sed_read_command_like_codex(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._refresh_dynamic_hint = lambda: None

        app._update_busy_status_from_activity(
            ActivityEvent(
                title="Running sed -n '1,12p' /tmp/project/cli/agent_cli/ui/live_turn_controller.py",
                status="running",
                kind="command",
                code="command.run",
                params={
                    "command": "sed -n '1,12p' /tmp/project/cli/agent_cli/ui/live_turn_controller.py"
                },
            )
        )

        self.assertEqual(app._busy_status_label, "Reading live_turn_controller.py")

    def test_busy_status_header_compacts_rg_search_command_like_codex(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._refresh_dynamic_hint = lambda: None

        app._update_busy_status_from_activity(
            ActivityEvent(
                title="Running rg weather cli/tests",
                status="running",
                kind="command",
                code="command.run",
                params={"command": "rg weather cli/tests"},
            )
        )

        self.assertEqual(app._busy_status_label, "Searching weather in tests")

    def test_busy_status_header_ignores_banner_echo_and_uses_following_primary_command(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._refresh_dynamic_hint = lambda: None

        app._update_busy_status_from_activity(
            ActivityEvent(
                title="Running echo 'top files' && rg --files -g '!docs/**' -g '!build/**' -g '!dist/**'",
                status="running",
                kind="command",
                code="command.run",
                params={
                    "command": "echo 'top files' && rg --files -g '!docs/**' -g '!build/**' -g '!dist/**'"
                },
            )
        )

        self.assertEqual(app._busy_status_label, "Listing .")

    def test_busy_status_header_falls_back_to_raw_command_when_not_exploration_like(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._refresh_dynamic_hint = lambda: None

        app._update_busy_status_from_activity(
            ActivityEvent(
                title="Running python -V",
                status="running",
                kind="command",
                code="command.run",
                params={"command": "python -V"},
            )
        )

        self.assertEqual(app._busy_status_label, "Running python -V")

    def test_busy_status_header_compacts_compound_command_display_without_exposing_cd_prefix(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._refresh_dynamic_hint = lambda: None

        app._update_busy_status_from_activity(
            ActivityEvent(
                title="Running cd /home/lyc/project/gemini-cli && git fetch upstream && git merge upstream/main --no-edit 2>&1",
                status="running",
                kind="command",
                code="command.run",
                params=command_activity_params(
                    {
                        "command": "cd /home/lyc/project/gemini-cli && git fetch upstream && git merge upstream/main --no-edit 2>&1"
                    }
                ),
            )
        )

        self.assertEqual(
            app._busy_status_label,
            "Running git fetch upstream / git merge upstream/main --no-edit",
        )

    def test_busy_status_header_prefers_structured_command_summaries_for_help_search(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._refresh_dynamic_hint = lambda: None

        app._update_busy_status_from_activity(
            ActivityEvent(
                title="Running pytest --help | rg -n -- '-q'",
                status="running",
                kind="command",
                code="command.run",
                params={
                    "command": "pytest --help | rg -n -- '-q'",
                    "exploration_summaries": [
                        {"kind": "search", "query": "-q", "path": "pytest --help"},
                    ],
                },
            )
        )

        self.assertEqual(app._busy_status_label, "Searching -q in pytest --help")

    def test_busy_status_header_keeps_compact_read_label_for_fast_success_event(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._refresh_dynamic_hint = lambda: None

        app._update_busy_status_from_activity(
            ActivityEvent(
                title="Read file",
                status="success",
                kind="tool",
                code="file.read",
                params={"file_path": "README.md", "path": "README.md", "tool_name": "read_file"},
            )
        )

        self.assertEqual(app._busy_status_label, "Reading README.md")

    def test_live_reasoning_updates_busy_status_and_creates_transcript_entry(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._sync_transcript = lambda: None
        app._refresh_dynamic_hint = lambda: None
        app._begin_activity_capture()

        app._write_live_turn_event(
            {
                "type": "item.completed",
                "item": {"id": "item_reason", "type": "reasoning", "text": "**Search** 检查仓库"},
            }
        )

        self.assertEqual(app._busy_status_label, "Search")
        self.assert_transcript_lines(app._transcript_lines, ["• 检查仓库"])

    def test_web_search_turn_event_entry_uses_compact_web_cell_instead_of_raw_tool_invocation(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        started_event = {
            "type": "item.started",
            "item": {
                "id": "item_web_0",
                "type": "mcp_tool_call",
                "server": "local",
                "tool": "web_search",
                "arguments": {"query": "北京 今天天气", "limit": 5},
                "search_phase": "search_dispatched",
                "status": "in_progress",
            },
        }
        completed_event = {
            "type": "item.completed",
            "item": {
                "id": "item_web_0",
                "type": "mcp_tool_call",
                "server": "local",
                "tool": "web_search",
                "arguments": {"query": "北京 今天天气", "limit": 5},
                "search_phase": "search_results_received",
                "result": {
                    "content": [{"type": "text", "text": "北京当前多云，22°C。"}],
                    "structured_content": {
                        "query": "北京 今天天气",
                        "count": 1,
                        "engine": "openai_native_web_search",
                        "web_search_route": {
                            "effective_backend_id": "provider_native_openai_responses_web_search",
                            "effective_backend_kind": "provider_native",
                            "execution_path": "openai_responses_native",
                        },
                        "results": [
                            {
                                "rank": 1,
                                "title": "北京天气",
                                "url": "https://weather.com/weather/today/l/Beijing",
                                "source_domain": "weather.com",
                                "credibility_label": "high",
                            }
                        ],
                    },
                },
                "error": None,
                "status": "completed",
            },
        }

        started_entry = app._turn_event_entry(
            started_event,
            activity=app._turn_event_activity(started_event),
        )
        completed_entry = app._turn_event_entry(
            completed_event,
            activity=app._turn_event_activity(completed_event),
        )

        self.assertIsNotNone(started_entry)
        self.assertIsNotNone(completed_entry)
        assert started_entry is not None
        assert completed_entry is not None
        self.assertEqual(started_entry.layer, "web")
        self.assertEqual(started_entry.render_mode, "web_search")
        self.assertEqual(
            started_entry.lines,
            ["Searching the web", "  └ 北京 今天天气", "    state=search_dispatched"],
        )
        self.assertEqual(completed_entry.layer, "web")
        self.assertEqual(completed_entry.render_mode, "web_search")
        self.assertEqual(
            completed_entry.lines,
            [
                "Native web search",
                "  └ 北京 今天天气",
                "    state=search_results_received | backend=native | count=1",
            ],
        )
        self.assertNotIn("local.web_search", "\n".join(completed_entry.lines))

    def test_provider_native_web_search_call_renders_as_web_activity(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        event = {
            "type": "item.completed",
            "item": {
                "id": "ws_1",
                "type": "web_search_call",
                "status": "completed",
                "search_phase": "search_results_received",
                "action": {
                    "type": "search",
                    "query": "北京 今天天气",
                    "queries": ["北京 今天天气"],
                },
            },
        }

        activity = app._turn_event_activity(event)
        entry = app._turn_event_entry(event, activity=activity)

        assert activity is not None
        assert entry is not None
        self.assertEqual(activity.kind, "web")
        self.assertEqual(activity.code, "web.search")
        self.assertEqual(activity.title, "Native web search")
        self.assertEqual(entry.layer, "web")
        self.assertEqual(entry.render_mode, "web_search")
        self.assertEqual(
            entry.lines,
            [
                "Native web search",
                "  └ 北京 今天天气",
                "    state=search_results_received | backend=native",
            ],
        )

    def test_expert_review_turn_event_renders_as_tool_activity(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        event = {
            "type": "item.completed",
            "item": {
                "id": "er_1",
                "type": "expert_review",
                "phase": "completed",
                "status": "completed",
                "summary": "Expert review completed with 1 finding.",
                "request": {
                    "scope": "latest_turn",
                    "focus": ["correctness", "evidence"],
                },
                "reviewer": {
                    "provider": "anthropic",
                    "model": "claude-opus-4.1",
                    "reasoning_effort": "xhigh",
                },
                "outcome": {
                    "status": "ok",
                    "verdict": "revise",
                    "finding_count": 1,
                },
            },
        }

        activity = app._turn_event_activity(event)
        entry = app._turn_event_entry(event, activity=activity)

        assert activity is not None
        assert entry is not None
        self.assertEqual(activity.kind, "tool")
        self.assertEqual(activity.code, "expert_review")
        self.assertEqual(activity.title, "Expert review completed with 1 finding.")
        self.assertEqual(entry.layer, "tool")
        self.assertEqual(
            entry.lines,
            [
                "• Expert review completed with 1 finding.",
                "  └ reviewer=anthropic / claude-opus-4.1",
                "    scope=latest_turn",
                "    focus=correctness, evidence",
                "    verdict=revise | findings=1",
            ],
        )

    def test_render_response_includes_expert_review_turn_event(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._begin_activity_capture()
        app._sync_transcript = lambda: None
        app._update_status = lambda status: None
        app._focus_input = lambda: None

        response = PromptResponse(
            user_text="请复核刚才的方案",
            assistant_text="我已经根据评审意见修正了方案。",
            response_items=default_response_items(
                assistant_text="我已经根据评审意见修正了方案。",
            ),
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "er_2",
                        "type": "expert_review",
                        "phase": "completed",
                        "status": "completed",
                        "summary": "Expert review completed with 1 finding.",
                        "request": {
                            "scope": "latest_turn",
                            "focus": ["risk"],
                        },
                        "reviewer": {
                            "provider": "anthropic",
                            "model": "claude-opus-4.1",
                        },
                        "outcome": {
                            "status": "ok",
                            "verdict": "revise",
                            "finding_count": 1,
                        },
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_final",
                        "type": "agent_message",
                        "text": "我已经根据评审意见修正了方案。",
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ],
            status={},
        )

        app._render_response(response)

        self.assertIn("• Expert review completed with 1 finding.", app._transcript_lines)
        self.assertIn("  └ reviewer=anthropic / claude-opus-4.1", app._transcript_lines)
        self.assertIn("    verdict=revise | findings=1", app._transcript_lines)
        self.assertEqual(app._transcript_lines[-1], "• 我已经根据评审意见修正了方案。")

    def test_live_expert_review_turn_event_creates_transcript_entry(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._busy = True
        app._sync_transcript = lambda: None
        app._refresh_dynamic_hint = lambda: None
        app._begin_activity_capture()

        app._write_live_turn_event(
            {
                "type": "item.completed",
                "item": {
                    "id": "er_live",
                    "type": "expert_review",
                    "phase": "completed",
                    "status": "completed",
                    "summary": "Expert review completed with 1 finding.",
                    "request": {
                        "scope": "latest_turn",
                        "focus": ["policy"],
                    },
                    "reviewer": {
                        "provider": "anthropic",
                        "model": "claude-opus-4.1",
                    },
                    "outcome": {
                        "status": "ok",
                        "verdict": "block",
                        "finding_count": 1,
                    },
                },
            }
        )

        self.assertIn("• Expert review completed with 1 finding.", app._transcript_lines)
        self.assertIn("  └ reviewer=anthropic / claude-opus-4.1", app._transcript_lines)
        self.assertIn("    verdict=block | findings=1", app._transcript_lines)

    def test_render_response_inserts_separator_after_provider_native_web_search_call(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._begin_activity_capture()
        app._sync_transcript = lambda: None
        app._update_status = lambda status: None
        app._focus_input = lambda: None

        response = PromptResponse(
            user_text="北京天气怎么样",
            assistant_text="北京今天多云。",
            response_items=[
                ResponseInputItem(
                    item_type="web_search_call",
                    content="",
                    extra={
                        "id": "ws_1",
                        "status": "completed",
                        "action": {
                            "type": "search",
                            "query": "北京 今天天气",
                            "queries": ["北京 今天天气"],
                        },
                    },
                ),
                *default_response_items(assistant_text="北京今天多云。"),
            ],
            status={},
        )

        app._render_response(response)

        self.assertIn("Native web search", app._transcript_lines)
        self.assertIn("  └ 北京 今天天气", app._transcript_lines)
        self.assertIn("    state=search_results_received | backend=native", app._transcript_lines)
        self.assertTrue(
            any(
                ("完成" in line and "用时" in line) or "Done" in line
                for line in app._transcript_lines
            )
        )
        self.assertEqual(app._transcript_lines[-1], "• 北京今天多云。")

    def test_web_search_turn_event_entry_surfaces_degraded_reason_from_canonical_payload(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        completed_event = {
            "type": "item.completed",
            "item": {
                "id": "item_web_fail",
                "type": "mcp_tool_call",
                "server": "local",
                "tool": "web_search",
                "arguments": {"query": "北京 明天天气", "limit": 5},
                "result": {
                    "content": [{"type": "text", "text": ""}],
                    "structured_content": {
                        "ok": False,
                        "query": "北京 明天天气",
                        "count": 0,
                        "engine": "openai_native_web_search",
                        "display_message": "native web search response was incomplete before usable results were received",
                        "web_search_outcome": "native_interrupted",
                        "web_search_route": {
                            "effective_backend_id": "provider_native_openai_responses_web_search",
                            "effective_backend_kind": "provider_native",
                            "execution_path": "openai_responses_native",
                        },
                    },
                },
                "status": "completed",
            },
        }

        activity = app._turn_event_activity(completed_event)
        entry = app._turn_event_entry(completed_event, activity=activity)

        assert activity is not None
        assert entry is not None
        self.assertEqual(activity.title, "Native web search failed")
        self.assertEqual(
            entry.lines,
            [
                "Native web search failed",
                "  └ 北京 明天天气",
                "    state=native_interrupted | backend=native",
                "    reason=native web search response was incomplete before usable results were received",
            ],
        )

    def test_render_response_prefers_canonical_turn_events_without_duplicate_fallback_entries(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._begin_activity_capture()
        app._sync_transcript = lambda: None
        app._update_status = lambda status: None
        app._focus_input = lambda: None

        response = PromptResponse(
            user_text="请列出当前目录下的文件",
            assistant_text="fallback final",
            commentary_text="fallback commentary",
            activity_events=[
                ActivityEvent(
                    title="Listed directory",
                    status="success",
                    kind="tool",
                    detail="count=3\ndir_path=.",
                )
            ],
            response_items=default_response_items(
                commentary_text="fallback commentary",
                assistant_text="fallback final",
            ),
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {"id": "item_0", "type": "agent_message", "text": "我先查看当前目录。"},
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "mcp_tool_call",
                        "tool": "list_dir",
                        "arguments": {"dir_path": ".", "depth": 1, "offset": 0, "limit": 50},
                        "result": {
                            "content": [{"type": "text", "text": "E1: [file] README.md"}],
                            "structured_content": {"dir_path": ".", "count": 1},
                        },
                        "error": None,
                        "status": "completed",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_2",
                        "type": "agent_message",
                        "text": "当前目录下有 README.md。",
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ],
        )

        app._render_response(response)

        self.assert_transcript_lines(
            app._transcript_lines,
            [
                "• 我先查看当前目录。",
                "",
                "• Explored",
                "  └ List .",
                "",
                "────────────────────────────────────────────────────────────────",
                "",
                "• 当前目录下有 README.md。",
            ],
        )

    def test_render_response_fallback_ignores_raw_reasoning_without_reference_header(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._sync_transcript = lambda: None
        app._update_status = lambda status: None
        app._focus_input = lambda: None

        response = PromptResponse(
            user_text="看看readme",
            assistant_text="我看了根目录 README.md，核心内容是：",
            response_items=[
                type(
                    "ReasoningItem",
                    (),
                    {
                        "item_type": "reasoning",
                        "role": "",
                        "content": [
                            {"type": "reasoning", "text": "I think I should summarize the README."}
                        ],
                        "extra": {},
                    },
                )(),
                type(
                    "AssistantItem",
                    (),
                    {
                        "item_type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "我看了根目录 README.md，核心内容是："}
                        ],
                        "extra": {},
                    },
                )(),
            ],
            status={},
        )
        response.turn_events = []

        app._render_response(response)

        self.assert_transcript_lines(
            app._transcript_lines, ["• 我看了根目录 README.md，核心内容是："]
        )

    def test_render_response_backfill_dedupes_reasoning_with_provider_metadata(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._begin_activity_capture()
        app._sync_transcript = lambda: None
        app._update_status = lambda status: None
        app._focus_input = lambda: None

        app._write_live_turn_event(
            {
                "type": "item.completed",
                "item": {
                    "id": "stream_item_0",
                    "type": "reasoning",
                    "text": "**Inspect** 先看 README",
                },
            }
        )

        response = PromptResponse(
            user_text="看看readme",
            assistant_text="我看了 README。",
            status={},
        )
        response.turn_events = [
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "reasoning",
                    "text": "**Inspect** 先看 README",
                    "summary": [{"type": "summary_text", "text": "先看 README"}],
                    "encrypted_content": "enc-1",
                    "provider_item_id": "rs_1",
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {"id": "item_1", "type": "agent_message", "text": "我看了 README。"},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
            },
        ]

        app._render_response(response)

        self.assert_transcript_lines(
            app._transcript_lines,
            [
                "• 先看 README",
                "",
                "• 我看了 README。",
            ],
        )

    def test_live_turn_inserts_reference_style_separator_before_final_after_work(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime(), language="zh-CN")
        app._begin_activity_capture()
        app._sync_transcript = lambda: None

        app._write_live_turn_event(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "agent_message",
                    "text": "我先查看当前目录。",
                    "phase": "commentary",
                },
            }
        )
        app._write_live_turn_event(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": '/bin/bash -lc "find . -maxdepth 1 -mindepth 1 | sort"',
                    "aggregated_output": "README.md\nagent_cli\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            }
        )
        app._write_live_turn_event(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "agent_message",
                    "text": "当前目录下有 README.md 和 agent_cli。",
                    "phase": "final_answer",
                },
            }
        )
        app._write_live_turn_event(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
            }
        )

        self.assert_transcript_lines(
            app._transcript_lines,
            [
                "• 我先查看当前目录。",
                "",
                "• Explored",
                "  └ List .",
                "",
                "────────────────────────────────────────────────────────────────",
                "",
                "• 当前目录下有 README.md 和 agent_cli。",
            ],
        )

    def test_live_turn_replaces_streaming_assistant_message_in_place(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._begin_activity_capture()
        app._sync_transcript = lambda: None

        app._write_live_turn_event(
            {
                "type": "item.updated",
                "item": {
                    "id": "item_0",
                    "type": "agent_message",
                    "text": "我先",
                    "phase": "commentary",
                },
            }
        )
        app._write_live_turn_event(
            {
                "type": "item.updated",
                "item": {
                    "id": "item_0",
                    "type": "agent_message",
                    "text": "我先查看当前目录。",
                    "phase": "commentary",
                },
            }
        )

        self.assertEqual(app._transcript_lines, ["• 我先查看当前目录。"])

    def test_same_turn_item_ids_across_turns_do_not_replace_previous_turn_entries(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._sync_transcript = lambda: None

        app._begin_activity_capture()
        first = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "第一轮前置说明。"},
            }
        )
        assert first is not None
        app._append_transcript_entry(first, leading_blank=False)

        app._begin_activity_capture()
        second = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "第二轮前置说明。"},
            }
        )
        assert second is not None
        app._append_transcript_entry(second, leading_blank=True)

        self.assertEqual(
            app._transcript_lines,
            [
                "• 第一轮前置说明。",
                "",
                "• 第二轮前置说明。",
            ],
        )

    def test_command_execution_find_snapshot_renders_as_exploration(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": '/bin/bash -lc "find . -maxdepth 1 -mindepth 1 | sort"',
                    "aggregated_output": "README.md\nagent_cli\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            activity=app._turn_event_activity(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "command_execution",
                        "command": '/bin/bash -lc "find . -maxdepth 1 -mindepth 1 | sort"',
                        "aggregated_output": "README.md\nagent_cli\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            ),
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.lines, ["• Explored", "  └ List ."])

    def test_command_execution_ls_snapshot_renders_as_exploration(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "command_execution",
                    "command": '/bin/bash -lc "ls -la"',
                    "aggregated_output": "total 8\n.\n..\nREADME.md\nagent_cli\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            activity=app._turn_event_activity(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_2",
                        "type": "command_execution",
                        "command": '/bin/bash -lc "ls -la"',
                        "aggregated_output": "total 8\n.\n..\nREADME.md\nagent_cli\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            ),
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.lines, ["• Explored", "  └ List ."])

    def test_command_execution_started_without_status_keeps_running_exploration_projection(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        event = {
            "type": "item.started",
            "item": {
                "id": "item_readme",
                "type": "command_execution",
                "command": '/bin/bash -lc "sed -n \\"1,220p\\" README.md"',
            },
        }

        activity = app._turn_event_activity(event)

        self.assertIsNotNone(activity)
        assert activity is not None
        self.assertEqual(activity.status, "running")
        self.assertEqual(activity.code, "file.read")

        app._busy = True
        app._refresh_dynamic_hint = lambda: None
        app._update_busy_status_from_activity(activity)
        self.assertEqual(app._busy_status_label, "Reading README.md")

        entry = app._turn_event_entry(event, activity=activity)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.lines, ["• Exploring", "  └ Read README.md"])

    def test_command_execution_rg_then_cat_renders_as_grouped_exploration(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        event = {
            "type": "item.completed",
            "item": {
                "id": "item_3",
                "type": "command_execution",
                "command": '/bin/bash -lc "rg \\"Change Approved\\"\ncat diff_render.rs"',
                "aggregated_output": "",
                "exit_code": 0,
                "status": "completed",
            },
        }

        entry = app._turn_event_entry(
            event,
            activity=app._turn_event_activity(event),
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                "• Explored",
                "  └ Search Change Approved",
                "    Read diff_render.rs",
            ],
        )

    def test_command_execution_sequential_reads_within_one_call_coalesce_like_reference(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        event = {
            "type": "item.completed",
            "item": {
                "id": "item_4",
                "type": "command_execution",
                "command": '/bin/bash -lc "cat a.rs\ncat b.rs"',
                "aggregated_output": "",
                "exit_code": 0,
                "status": "completed",
            },
        }

        entry = app._turn_event_entry(
            event,
            activity=app._turn_event_activity(event),
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                "• Explored",
                "  └ Read a.rs, b.rs",
            ],
        )

    def test_command_execution_help_pipeline_projects_to_compact_search_activity(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        event = {
            "type": "item.started",
            "item": {
                "id": "item_help_search",
                "type": "command_execution",
                "command": "/bin/bash -lc \"pytest --help | rg -n -- '-q'\"",
            },
        }

        activity = app._turn_event_activity(event)

        self.assertIsNotNone(activity)
        assert activity is not None
        self.assertEqual(activity.status, "running")
        self.assertEqual(activity.code, "dir.search")
        self.assertEqual(activity.params.get("query"), "-q")
        self.assertEqual(activity.params.get("path"), "pytest --help")

        app._busy = True
        app._refresh_dynamic_hint = lambda: None
        app._update_busy_status_from_activity(activity)
        self.assertEqual(app._busy_status_label, "Searching -q in pytest --help")

    def test_command_execution_comment_label_is_used_for_non_exploration_busy_status(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        event = {
            "type": "item.started",
            "item": {
                "id": "item_python_version",
                "type": "command_execution",
                "command": '/bin/bash -lc "# Capture Python version\npython -V"',
            },
        }

        activity = app._turn_event_activity(event)

        self.assertIsNotNone(activity)
        assert activity is not None
        self.assertEqual(activity.status, "running")
        self.assertEqual(activity.code, "command.run")
        self.assertEqual(activity.title, "Running Capture Python version")
        self.assertEqual(activity.params.get("command_display"), "Capture Python version")

        app._busy = True
        app._refresh_dynamic_hint = lambda: None
        app._update_busy_status_from_activity(activity)
        self.assertEqual(app._busy_status_label, "Running Capture Python version")

        entry = app._turn_event_entry(event, activity=activity)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.lines, ["• Running Capture Python version"])

    def test_localized_file_read_activities_merge_via_structured_exploration_details(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        first = activity_entry(
            ActivityEvent(
                title="读取文件",
                status="success",
                detail="path=a.rs",
                kind="tool",
                code="file.read",
                params={"path": "a.rs", "file_path": "a.rs"},
            )
        )
        second = activity_entry(
            ActivityEvent(
                title="Lire le fichier",
                status="success",
                detail="path=b.rs",
                kind="tool",
                code="file.read",
                params={"path": "b.rs", "file_path": "b.rs"},
            )
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None
        assert second is not None

        app._append_transcript_entry(first)
        app._append_transcript_entry(second)

        merged_entry = app._transcript_entries[-1]
        self.assertEqual(
            merged_entry.lines,
            [
                "• Explored",
                "  └ Read a.rs, b.rs",
            ],
        )

    def test_command_execution_started_renders_reference_running_header(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.started",
                "item": {
                    "id": "item_cmd_0",
                    "type": "command_execution",
                    "command": "/bin/bash -lc 'python -V'",
                    "aggregated_output": "",
                    "exit_code": None,
                    "status": "in_progress",
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.lines, ["• Running python -V"])

    def test_command_execution_completed_renders_reference_no_output_block(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_cmd_1",
                    "type": "command_execution",
                    "command": '/bin/bash -lc "echo ok"',
                    "aggregated_output": "",
                    "exit_code": 0,
                    "status": "completed",
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.lines, ["• Ran echo ok", "  └ (no output)"])

    def test_local_exec_mcp_tool_renders_like_command_instead_of_raw_invocation(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_local_exec_0",
                    "type": "mcp_tool_call",
                    "server": "local",
                    "tool": "exec_command",
                    "arguments": {"cmd": "printf hi"},
                    "result": {
                        "content": [{"type": "text", "text": "hi"}],
                        "structured_content": {
                            "command": "printf hi",
                            "stdout": "hi",
                            "returncode": 0,
                        },
                    },
                    "error": None,
                    "status": "completed",
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.render_mode, "tool_command")
        self.assertEqual(entry.lines, ["• Ran printf hi", "  └ hi"])

    def test_local_exec_mcp_shell_approval_renders_as_approval_activity(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_local_exec_approval",
                    "type": "mcp_tool_call",
                    "server": "local",
                    "tool": "exec_command",
                    "arguments": {"cmd": "python -V"},
                    "result": {
                        "content": [
                            {"type": "text", "text": "shell approval requested approval_2"}
                        ],
                        "structured_content": {
                            "approval_id": "approval_2",
                            "status": "pending",
                            "summary": "Approve shell command",
                            "reason": "user approval required before running local shell command",
                            "command": "python -V",
                        },
                    },
                    "error": None,
                    "status": "completed",
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines, ["• Requested shell approval", "  └ approval_2", "    python -V"]
        )

    def test_command_execution_multiline_and_truncated_output_render_reference_structure(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_cmd_2",
                    "type": "command_execution",
                    "command": '/bin/bash -lc "set -o pipefail\\ncargo test --all-features --quiet"',
                    "aggregated_output": "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n",
                    "exit_code": 1,
                    "status": "failed",
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                "• Ran set -o pipefail",
                "  │ cargo test --all-features --quiet",
                "  └ 1",
                "    2",
                "    … +6 lines",
                "    9",
                "    10",
            ],
        )

    def test_sequential_exploration_entries_coalesce_like_reference(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._sync_transcript = lambda: None
        app._begin_activity_capture()

        app._write_live_activity_event(
            ActivityEvent(
                title="Searched files",
                status="success",
                kind="tool",
                detail="query=Change Approved",
            )
        )
        app._write_live_activity_event(
            ActivityEvent(
                title="Read file",
                status="success",
                kind="tool",
                detail="path=diff_render.rs",
            )
        )

        self.assertEqual(
            app._transcript_lines,
            [
                "• Explored",
                "  └ Search Change Approved",
                "    Read diff_render.rs",
            ],
        )

    def test_mcp_tool_call_started_renders_reference_calling_line(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.started",
                "item": {
                    "id": "item_tool_0",
                    "type": "mcp_tool_call",
                    "server": "search",
                    "tool": "find_docs",
                    "arguments": {"query": "ratatui styling", "limit": 3},
                    "result": None,
                    "error": None,
                    "status": "in_progress",
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            ['• Calling search.find_docs({"query":"ratatui styling","limit":3})'],
        )

    def test_mcp_tool_call_completed_renders_reference_called_line_and_summary(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_tool_1",
                    "type": "mcp_tool_call",
                    "server": "search",
                    "tool": "find_docs",
                    "arguments": {"query": "ratatui styling", "limit": 3},
                    "result": {
                        "content": [
                            {"type": "text", "text": "Found styling guidance in styles.md"}
                        ],
                        "structured_content": {"query": "ratatui styling"},
                    },
                    "error": None,
                    "status": "completed",
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                '• Called search.find_docs({"query":"ratatui styling","limit":3})',
                "  └ Found styling guidance in styles.md",
            ],
        )

    def test_mcp_view_image_completed_renders_image_ready_truthfully(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_tool_view_image",
                    "type": "mcp_tool_call",
                    "server": "local",
                    "tool": "view_image",
                    "arguments": {"path": "/tmp/diagram.png"},
                    "result": {
                        "structured_content": {
                            "path": "/tmp/diagram.png",
                            "requested_path": "diagram.png",
                            "image_artifacts": [
                                {
                                    "path": "/tmp/diagram.png",
                                    "mime_type": "image/png",
                                    "size_bytes": 42,
                                    "width": 10,
                                    "height": 12,
                                    "image_url": "data:image/png;base64,AAA",
                                }
                            ],
                        }
                    },
                    "error": None,
                    "status": "completed",
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                "• Image ready",
                "  └ diagram.png",
                "    state=image_ready",
            ],
        )

    def test_function_call_output_with_input_image_renders_image_injected_truthfully(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_output_view_image",
                    "type": "function_call_output",
                    "call_id": "call_view_image_1",
                    "output": [
                        {
                            "type": "input_image",
                            "image_url": "data:image/png;base64,AAA",
                            "detail": "original",
                        }
                    ],
                    "image_transport_subject": "/tmp/diagram.png",
                    "success": True,
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                "• Image injected (view_image continuation)",
                "  └ diagram.png",
                "    state=image_injected_tool_native",
            ],
        )

    def test_function_call_output_with_file_read_image_projection_renders_family_state(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_output_read_file",
                    "type": "function_call_output",
                    "call_id": "call_read_file_1",
                    "output": [
                        {
                            "type": "input_text",
                            "text": "image prepared",
                        },
                        {
                            "type": "input_image",
                            "image_url": "data:image/png;base64,AAA",
                        },
                    ],
                    "image_transport_family": "image_aware_file_read",
                    "image_transport_subject": "/tmp/diagram.png",
                    "success": True,
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                "• Image injected (image-aware file read)",
                "  └ diagram.png",
                "    state=image_injected_file_read",
            ],
        )

    def test_function_call_output_with_attachment_first_projection_renders_family_state(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_output_user_image",
                    "type": "function_call_output",
                    "call_id": "call_user_image_input_1",
                    "output": [
                        {
                            "type": "input_image",
                            "image_url": "data:image/png;base64,AAA",
                        }
                    ],
                    "image_transport_family": "attachment_first_message_native",
                    "image_transport_subject": "attachment:screenshot.png",
                    "success": True,
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                "• Image injected (attachment-first)",
                "  └ screenshot.png",
                "    state=image_injected_attachment",
            ],
        )

    def test_mcp_tool_call_failed_renders_reference_error_summary(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_tool_2",
                    "type": "mcp_tool_call",
                    "server": "search",
                    "tool": "find_docs",
                    "arguments": {"query": "ratatui styling", "limit": 3},
                    "result": None,
                    "error": {"message": "network timeout"},
                    "status": "failed",
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                '• Called search.find_docs({"query":"ratatui styling","limit":3})',
                "  └ Error: network timeout",
            ],
        )
        self.assertEqual(entry.status, "error")

    def test_todo_list_turn_item_renders_updated_plan_cell(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        entry = app._turn_event_entry(
            {
                "type": "item.updated",
                "item": {
                    "id": "item_plan_0",
                    "type": "todo_list",
                    "items": [
                        {"text": "inspect", "completed": True},
                        {"text": "patch", "completed": False},
                    ],
                },
            }
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            entry.lines,
            [
                "• Todo List",
                "  └ ✔ inspect",
                "    □ patch",
            ],
        )
        self.assertEqual(entry.render_mode, "todo_list")
