import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.main import _build_tui_runtime
from cli.agent_cli.models import AgentIntent, PromptResponse, ToolEvent
from cli.agent_cli.resume_support import normalize_resume_cli_args
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.thread_store import ThreadStore


class _MainResumeAgent(RuleBasedAgent):
    def provider_status(self) -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "provider_model": "deepseek-reasoner",
            "model_key": "deepseek_reasoner",
        }

    def plan(self, text: str, history=None, *, tool_executor=None, attachments=None):
        del history, tool_executor, attachments
        return AgentIntent(assistant_text=f"echo: {text}")


class MainResumeTest(unittest.TestCase):
    def test_normalize_resume_cli_args_maps_subcommand_forms(self) -> None:
        self.assertEqual(normalize_resume_cli_args(["resume"]), ["--resume-last"])
        self.assertEqual(
            normalize_resume_cli_args(
                ["resume", "thread_123", "--sandbox-mode", "danger-full-access"]
            ),
            ["--resume", "thread_123", "--sandbox-mode", "danger-full-access"],
        )
        self.assertEqual(
            normalize_resume_cli_args(
                ["resume", "--path", "/tmp/demo.jsonl", "--approval-policy", "never"]
            ),
            ["--resume-path", "/tmp/demo.jsonl", "--approval-policy", "never"],
        )
        self.assertEqual(
            normalize_resume_cli_args(
                [
                    "--sandbox-mode",
                    "danger-full-access",
                    "--approval-policy",
                    "never",
                    "resume",
                    "thread_123",
                ]
            ),
            [
                "--sandbox-mode",
                "danger-full-access",
                "--approval-policy",
                "never",
                "--resume",
                "thread_123",
            ],
        )
        self.assertEqual(
            normalize_resume_cli_args(["--approval-policy=never", "resume", "thread_123"]),
            ["--approval-policy=never", "--resume", "thread_123"],
        )

    def test_build_tui_runtime_resume_last_applies_startup_policy_after_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir) / "state")
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            alternate = Path(temp_dir) / "alternate"
            alternate.mkdir()

            runtime1 = AgentCliRuntime(agent=_MainResumeAgent(), thread_store=store)
            runtime1.set_cwd(workspace)
            runtime1.configure_runtime_policy(
                approval_policy="never",
                sandbox_mode="read-only",
                web_search_mode="disabled",
                network_access_enabled=False,
            )
            thread = runtime1.start_thread(name="resume last")
            runtime1.handle_prompt("first turn")

            runtime2 = AgentCliRuntime(agent=_MainResumeAgent(), thread_store=store)
            args = SimpleNamespace(
                resume=None,
                resume_path=None,
                resume_last=True,
                approval_policy="never",
                sandbox_mode="danger-full-access",
                web_search_mode="live",
                network_access="enabled",
            )

            with patch.dict("os.environ", {"AGENTHUB_STARTUP_CWD": str(alternate)}, clear=False):
                built = _build_tui_runtime(args, runtime2)

            self.assertIs(built, runtime2)
            self.assertEqual(runtime2.thread_id, thread["thread_id"])
            self.assertEqual(Path(runtime2.cwd), workspace.resolve())
            status = runtime2.runtime_policy_status()
            self.assertEqual(status["sandbox_mode"], "danger-full-access")
            self.assertEqual(status["web_search_mode"], "live")
            self.assertEqual(status["network_access"], "enabled")

    def test_build_tui_runtime_new_session_uses_startup_cwd_before_thread_start(self) -> None:
        calls: list[object] = []
        prefetched = object()

        class _FakeRuntime:
            runtime_policy = SimpleNamespace(
                approval_policy="never",
                sandbox_mode="danger-full-access",
                network_access_enabled="enabled",
            )

            def set_cwd(self, cwd) -> None:
                calls.append(("set_cwd", str(Path(cwd).resolve())))

            def start_thread(self) -> None:
                calls.append("start_thread")

            def configure_runtime_policy(
                self,
                *,
                approval_policy=None,
                sandbox_mode=None,
                web_search_mode=None,
                network_access_enabled=None,
            ) -> None:
                calls.append(
                    (
                        "configure_runtime_policy",
                        approval_policy,
                        sandbox_mode,
                        web_search_mode,
                        network_access_enabled,
                    )
                )

        args = SimpleNamespace(
            resume=None,
            resume_path=None,
            resume_last=False,
            approval_policy="never",
            sandbox_mode="danger-full-access",
            web_search_mode="disabled",
            network_access="enabled",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            startup_cwd = Path(temp_dir) / "gemini-cli"
            startup_cwd.mkdir()
            with patch.dict("os.environ", {"AGENTHUB_STARTUP_CWD": str(startup_cwd)}, clear=False):
                with (
                    patch(
                        "cli.agent_cli.runtime_factory.build_persistent_runtime",
                        return_value=_FakeRuntime(),
                    ) as mock_build,
                    patch(
                        "cli.agent_cli.main._start_tui_tab_restore_prefetch",
                        return_value=prefetched,
                    ) as mock_prefetch,
                ):
                    built = _build_tui_runtime(args, runtime=None)

        self.assertIsNotNone(built)
        self.assertIs(built._codex_sidecar_restore_prefetch, prefetched)
        self.assertEqual(
            calls,
            [
                ("set_cwd", str(startup_cwd.resolve())),
                "start_thread",
                ("configure_runtime_policy", "never", "danger-full-access", "disabled", "enabled"),
            ],
        )
        self.assertEqual(mock_build.call_count, 1)
        self.assertFalse(mock_build.call_args.kwargs["resume_active_thread"])
        self.assertFalse(mock_build.call_args.kwargs["start_thread_if_unavailable"])
        mock_prefetch.assert_called_once()

    def test_build_tui_runtime_skips_tab_prefetch_for_explicit_resume(self) -> None:
        runtime = AgentCliRuntime(agent=_MainResumeAgent())
        args = SimpleNamespace(
            resume="thread-explicit",
            resume_path=None,
            resume_last=False,
            approval_policy="never",
            sandbox_mode="danger-full-access",
            web_search_mode="disabled",
            network_access="enabled",
        )

        with (
            patch("cli.agent_cli.main._start_tui_tab_restore_prefetch") as mock_prefetch,
            patch("cli.agent_cli.resume_support.apply_runtime_resume_request") as mock_resume,
        ):
            built = _build_tui_runtime(args, runtime)

        self.assertIs(built, runtime)
        mock_prefetch.assert_not_called()
        mock_resume.assert_called_once()

    def test_build_tui_runtime_resume_restores_visible_transcript_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir) / "state")

            runtime1 = AgentCliRuntime(agent=_MainResumeAgent(), thread_store=store)
            thread = runtime1.start_thread(name="resume transcript")
            thread_id = str(thread["thread_id"])
            store.append_turn(
                thread_id,
                PromptResponse(
                    user_text="读取 README.md 的前3行",
                    assistant_text="README.md 的前 3 行是：\n1. # AgentHub\n2. \n3. 这是一个示例。",
                    commentary_text="我先读取 README.md。",
                    tool_events=[
                        ToolEvent(
                            name="file_read",
                            ok=True,
                            summary="file loaded",
                            payload={"path": "README.md", "line_count": 3},
                        )
                    ],
                    turn_events=[
                        {"type": "turn.started"},
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "tool_1",
                                "type": "function_call",
                                "name": "file_read",
                                "arguments": {"path": "README.md", "limit": 3},
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "msg_1",
                                "type": "agent_message",
                                "text": "我先读取 README.md。",
                                "phase": "commentary",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "msg_2",
                                "type": "agent_message",
                                "text": "README.md 的前 3 行是：\n1. # AgentHub\n2. \n3. 这是一个示例。",
                                "phase": "final_answer",
                            },
                        },
                        {"type": "turn.completed"},
                    ],
                ),
            )
            store.append_turn(
                thread_id,
                PromptResponse(
                    user_text="/quit",
                    assistant_text=f"exiting session\nthread_id={thread_id}",
                    tool_events=[
                        ToolEvent(
                            name="app_exit_requested",
                            ok=True,
                            summary="exit requested",
                            payload={
                                "thread_id": thread_id,
                                "resume_command": f"agenthub resume {thread_id}",
                            },
                        )
                    ],
                    turn_events=[
                        {"type": "turn.started"},
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "tool_2",
                                "type": "mcp_tool_call",
                                "tool": "app_exit_requested",
                                "status": "completed",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "msg_3",
                                "type": "agent_message",
                                "text": f"exiting session\nthread_id={thread_id}",
                                "phase": "final_answer",
                            },
                        },
                        {"type": "turn.completed"},
                    ],
                ),
            )

            runtime2 = AgentCliRuntime(agent=_MainResumeAgent(), thread_store=store)
            args = SimpleNamespace(
                resume=thread_id,
                resume_path=None,
                resume_last=False,
                approval_policy="never",
                sandbox_mode="danger-full-access",
                web_search_mode="disabled",
                network_access="enabled",
            )

            built = _build_tui_runtime(args, runtime2)

            self.assertIs(built, runtime2)
            self.assertEqual(runtime2.thread_id, thread_id)
            self.assertEqual(len(runtime2.history_turns), 2)

            app = AgentCliApp(runtime=runtime2)
            calls: list[object] = []
            app._begin_activity_capture = lambda: calls.append("begin")  # type: ignore[method-assign]
            app._write_user_prompt = lambda text, attachments=None: calls.append(
                ("user", text, list(attachments or []))
            )  # type: ignore[method-assign]
            app._write_assistant_reply = lambda text: calls.append(("assistant", text))  # type: ignore[method-assign]
            app._write_commentary_reply = lambda text: calls.append(("commentary", text))  # type: ignore[method-assign]
            app._render_canonical_turn_event_backfill = lambda events: calls.append(
                ("events", list(events))
            )  # type: ignore[method-assign]

            app._restore_transcript_from_runtime_history()

            self.assertEqual(
                calls,
                [
                    "begin",
                    ("user", "读取 README.md 的前3行", []),
                    ("assistant", "README.md 的前 3 行是：\n1. # AgentHub\n2. \n3. 这是一个示例。"),
                    "begin",
                    ("user", "/quit", []),
                ],
            )
