import io
import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli import headless_stream_runtime_helpers
from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.headless import (
    _exit_code_for_response,
    build_codex_sidecar_headless_runtime,
    build_headless_runtime,
    prompt_response_to_dict,
)
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.main import main
from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    PromptAttachment,
    PromptResponse,
    ToolEvent,
    default_response_items,
    generic_tool_call_item_events,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_kernels.base import KernelSession
from cli.agent_cli.runtime_policy import RuntimePolicy, permission_mode_label
from cli.agent_cli.thread_store import ThreadStore
from cli.tests.provider_boundary_test_support import (
    PROVIDER_CONFIG_REF,
    provider_status_path_fields,
)


class _HeadlessAgent(RuleBasedAgent):
    def provider_status(self) -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "model_key": "deepseek_reasoner",
            "provider_planner": "deepseek_reasoner",
            "provider_model": "deepseek-reasoner",
            "provider_tools": "tool-calls",
            "session_line": "reasoner",
            "provider_label": "deepseek | deepseek-reasoner | tool-calls",
            "provider_base_url": "https://api.deepseek.com",
            "provider_source": "test",
            **provider_status_path_fields(),
            "platform_family": "windows",
            "platform_os": "windows",
            "shell_kind": "powershell",
        }

    def plan(self, text: str, history=None, *, tool_executor=None, attachments=None):
        normalized = text.strip().lower()
        if "You are executing AgentHub `/init` for this repository." in text:
            patch = "\n".join(
                [
                    "*** Begin Patch",
                    "*** Add File: AENGTHUB.md",
                    "+# Demo",
                    "*** End Patch",
                    "",
                ]
            )
            assistant_text, events = tool_executor(f"/apply_patch {shlex.quote(patch)}")
            approval_id = ""
            if events:
                approval_id = str((events[-1].payload or {}).get("approval_id") or "").strip()
            if approval_id:
                assistant_text, followup_events = tool_executor(f"/approve {approval_id}")
                events = [*events, *followup_events]
            return AgentIntent(
                assistant_text="init auto-applied",
                tool_events=events,
                status_hint="tool",
            )
        if normalized == "list current directory":
            return AgentIntent(
                commentary_text="Checking current workspace before execution.",
                assistant_text="Recognized as a local directory query. Preparing shell execution.",
                command_text="/shell Get-ChildItem -Force",
                status_hint="tool",
            )
        if normalized == "show office skills":
            return AgentIntent(
                assistant_text="Recognized as an office skill query. Preparing skill listing.",
                command_text="/office_skills",
                status_hint="tool",
            )
        if normalized == "run office markdown":
            return AgentIntent(
                assistant_text="Recognized as an office conversion request. Preparing skill execution.",
                command_text="/office_run read_docx_markdown --path C:/tmp/demo.docx",
                status_hint="tool",
            )
        if normalized == "fail shell":
            return AgentIntent(
                assistant_text="Recognized as a failure probe. Preparing shell execution.",
                command_text="/shell fail",
                status_hint="tool",
            )
        if normalized == "bad quoted command":
            return AgentIntent(
                assistant_text="Recognized as a malformed command probe.",
                command_text='/file_read "README.md',
                status_hint="tool",
            )
        if normalized == "commentary layering":
            return AgentIntent(
                commentary_text="Building narrative context before the action.",
                assistant_text="Ready to follow up with the run.",
            )
        if normalized == "commentary only":
            return AgentIntent(
                assistant_text="",
                commentary_text="Only commentary is available until the next response arrives.",
            )
        if normalized == "timed planner":
            return AgentIntent(
                assistant_text="timed reply",
                timings={
                    "initial_model_ms": 1200,
                    "tool_execution_ms": 3400,
                    "synthesis_model_ms": 800,
                    "total_ms": 5400,
                },
            )
        return AgentIntent(assistant_text=f"echo: {text}")


class _HeadlessTools:
    def set_workspace_root(self, path: Path | str):
        self.PROJECT_ROOT = str(Path(path).resolve())
        return self.PROJECT_ROOT

    def capabilities(self) -> dict:
        return {
            "ok": True,
            "tools": [
                {"name": "shell", "description": "shell"},
                {"name": "office_skills", "description": "office skills"},
                {"name": "office_run", "description": "office run"},
            ],
        }

    def apply_patch_result(self, patch_text: str) -> CommandExecutionResult:
        root = Path(getattr(self, "PROJECT_ROOT", Path.cwd()))
        target_path: Path | None = None
        file_lines: list[str] = []

        for line in patch_text.splitlines():
            if line.startswith("*** Add File: "):
                relative_path = line[len("*** Add File: ") :].strip()
                target_path = root / relative_path
                file_lines = []
                continue
            if line.startswith("*** End Patch"):
                break
            if target_path is None:
                continue
            if line.startswith("+"):
                file_lines.append(line[1:])

        if target_path is None:
            event = ToolEvent(
                name="apply_patch",
                ok=False,
                summary="patch failed",
                payload={"ok": False, "error": "unsupported patch fixture"},
            )
            return CommandExecutionResult(
                assistant_text="patch failed",
                tool_events=[event],
                item_events=generic_tool_call_item_events(
                    tool_name="apply_patch",
                    arguments={"patch": patch_text},
                    ok=False,
                    summary="patch failed",
                    structured_content=dict(event.payload or {}),
                ),
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            "\n".join(file_lines) + ("\n" if file_lines else ""), encoding="utf-8"
        )
        event = ToolEvent(
            name="apply_patch",
            ok=True,
            summary="patch applied",
            payload={"ok": True, "path": str(target_path)},
        )
        return CommandExecutionResult(
            assistant_text="patch applied",
            tool_events=[event],
            item_events=generic_tool_call_item_events(
                tool_name="apply_patch",
                arguments={"patch": patch_text},
                ok=True,
                summary="patch applied",
                structured_content=dict(event.payload or {}),
            ),
        )

    def shell(self, command: str) -> ToolEvent:
        if command == "fail":
            return ToolEvent(
                name="shell",
                ok=False,
                summary="shell failed: fail",
                payload={
                    "command": command,
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "boom",
                    "duration_ms": 5,
                },
            )
        return ToolEvent(
            name="shell",
            ok=True,
            summary=f"shell ok: {command}",
            payload={
                "command": command,
                "returncode": 0,
                "stdout": "a.txt\nb.txt\n",
                "stderr": "",
                "duration_ms": 5,
            },
        )

    def office_skills(self) -> ToolEvent:
        return ToolEvent(
            name="office_skills",
            ok=True,
            summary="office_skills=1",
            payload={"ok": True, "count": 1, "skills": [{"name": "read_docx_markdown"}]},
        )

    def office_run(self, skill_name: str, *, args=None) -> ToolEvent:
        return ToolEvent(
            name="office_run",
            ok=True,
            summary=skill_name,
            payload={"ok": True, "skill_name": skill_name, "args": args or {}},
        )

    def shell_start(
        self,
        command: str,
        *,
        cwd=None,
        login=True,
        tty=False,
        shell=None,
        max_output_chars=12000,
        on_activity=None,
    ) -> dict[str, object]:
        del max_output_chars, on_activity
        return {
            "session_id": "session_1",
            "call_id": "call_1",
            "process_id": "proc_1",
            "command": command,
            "cwd": cwd,
            "login": login,
            "tty": tty,
            "shell": shell,
        }

    def shell_write_stdin(
        self, session_id: str, chars: str, *, yield_time_ms=None, on_activity=None
    ) -> ToolEvent:
        del on_activity
        return ToolEvent(
            name="shell",
            ok=True,
            summary="shell ok",
            payload={
                "session_id": session_id,
                "call_id": "call_1",
                "process_id": "proc_1",
                "command": "python -V",
                "yield_time_ms": yield_time_ms,
                "stdout": "Python 3.12.0\n",
                "stderr": "",
                "aggregated_output": "Python 3.12.0\n",
                "status": "ok" if chars == "" else "written",
                "ok": True,
                "duration_ms": 12,
            },
        )

    def shell_write_stdin_result(
        self, session_id: str, chars: str, *, yield_time_ms=None, on_activity=None
    ) -> CommandExecutionResult:
        event = self.shell_write_stdin(
            session_id, chars, yield_time_ms=yield_time_ms, on_activity=on_activity
        )
        return CommandExecutionResult(
            assistant_text="shell",
            tool_events=[event],
            item_events=generic_tool_call_item_events(
                tool_name="shell",
                arguments={"session_id": session_id, "chars": chars},
                ok=True,
                summary="shell ok",
                structured_content=dict(event.payload or {}),
            ),
        )


class _LiveWebFallbackAgent(RuleBasedAgent):
    def __init__(self) -> None:
        self.host_platform = current_host_platform()
        self.cwd = Path("/tmp")
        self._plugin_manager_factory = None
        self._provider_availability_registry = None
        self._planner = None
        self._planner_managed = False
        self._planner_error = None
        self._planner_runtime_error = None
        self._planner_runtime_error_diagnostics = None
        self._runtime_policy_overrides = {}
        self._session_provider_env_overrides = {}
        self._session_route_overrides = {}
        self._session_delegation_overrides = {}
        self._provider_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

    def set_cwd(self, cwd):
        self.cwd = Path(cwd).resolve()
        self._planner = None
        self._planner_error = None
        self._planner_runtime_error = None
        return self.cwd

    def set_plugin_manager_factory(self, factory):
        self._plugin_manager_factory = factory
        self._planner = None
        self._planner_error = None
        self._planner_runtime_error = None

    def set_runtime_policy_overrides(self, overrides):
        self._runtime_policy_overrides = dict(overrides or {})

    def provider_status(self) -> dict[str, str]:
        return {
            "provider_ready": "false",
            "provider_name": "-",
            "provider_model": "-",
            "provider_planner": "-",
            "provider_tools": "-",
            "provider_label": "-",
            "provider_base_url": str(self._provider_paths.config_path),
            "provider_source": "test",
            "provider_config_path": str(self._provider_paths.config_path),
            "provider_auth_path": str(self._provider_paths.auth_path),
            "platform_family": "unix",
            "platform_os": "linux",
            "shell_kind": "posix",
        }


class _StreamingPromptRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_ready": "true",
                "provider_name": "stream-test",
                "provider_model": "gpt-5.4",
            }

    def __init__(self) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.thread_id = "thread_stream"
        self.thread_name = "stream"

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        if self.turn_event_callback is not None:
            self.turn_event_callback({"type": "turn.started"})
            self.turn_event_callback(
                {
                    "type": "item.completed",
                    "item": {"id": "item_0", "type": "reasoning", "text": "先检查上下文"},
                }
            )
            self.turn_event_callback(
                {
                    "type": "item.completed",
                    "item": {"id": "item_1", "type": "agent_message", "text": "已找到入口文件"},
                }
            )
            self.turn_event_callback(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                }
            )
        return PromptResponse(
            user_text=text,
            assistant_text="已找到入口文件",
            commentary_text="先检查上下文",
            response_items=default_response_items(
                commentary_text="先检查上下文", assistant_text="已找到入口文件"
            ),
            status=self.agent.provider_status(),
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {"id": "item_0", "type": "reasoning", "text": "先检查上下文"},
                },
                {
                    "type": "item.completed",
                    "item": {"id": "item_1", "type": "agent_message", "text": "已找到入口文件"},
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ],
        )


class _StreamingDeltaPromptRuntime(_StreamingPromptRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        if self.turn_event_callback is not None:
            self.turn_event_callback({"type": "turn.started"})
            self.turn_event_callback(
                {
                    "type": "item.started",
                    "item": {"id": "msg_1", "type": "agent_message", "text": ""},
                }
            )
            self.turn_event_callback(
                {
                    "type": "item.updated",
                    "item": {"id": "msg_1", "type": "agent_message", "text": "增量"},
                }
            )
            self.turn_event_callback(
                {
                    "type": "item.completed",
                    "item": {"id": "msg_1", "type": "agent_message", "text": "增量完成"},
                }
            )
            self.turn_event_callback(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                }
            )
        return PromptResponse(
            user_text=text,
            assistant_text="增量完成",
            status=self.agent.provider_status(),
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.started",
                    "item": {"id": "msg_1", "type": "agent_message", "text": ""},
                },
                {
                    "type": "item.updated",
                    "item": {"id": "msg_1", "type": "agent_message", "text": "增量"},
                },
                {
                    "type": "item.completed",
                    "item": {"id": "msg_1", "type": "agent_message", "text": "增量完成"},
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ],
        )


class _CapturingPlanner:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.turn_event_callbacks: list[object] = []

    def public_summary(self) -> dict[str, str]:
        return {
            "provider_name": "glm",
            "model_key": "glm_5",
            "planner_kind": "openai_chat",
            "model": "glm-5",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "source": "test",
            "config_path": "/tmp/config.toml",
            "auth_path": "/tmp/auth.json",
        }

    def plan(
        self, text, history, *, tool_executor=None, attachments=None, turn_event_callback=None
    ):
        self.calls.append(text)
        self.turn_event_callbacks.append(turn_event_callback)
        return AgentIntent(assistant_text="planner reply")


class _LiveReplayPlanner:
    def public_summary(self) -> dict[str, str]:
        return {
            "provider_name": "openai",
            "model_key": "gpt_54",
            "planner_kind": "openai_responses",
            "model": "gpt-5.4",
            "base_url": "https://example.test/v1",
            "source": "test",
            "config_path": "/tmp/config.toml",
            "auth_path": "/tmp/auth.json",
        }

    def plan(
        self, text, history, *, tool_executor=None, attachments=None, turn_event_callback=None
    ):
        del text, history, tool_executor, attachments
        if turn_event_callback is not None:
            turn_event_callback({"type": "turn.started"})
            turn_event_callback(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "live_msg_0",
                        "type": "agent_message",
                        "text": "我先查看当前目录内容。",
                    },
                }
            )
            turn_event_callback(
                {
                    "type": "item.started",
                    "item": {
                        "id": "live_tool_0",
                        "type": "mcp_tool_call",
                        "server": "local",
                        "tool": "list_dir",
                        "arguments": {"path": "."},
                        "result": None,
                        "error": None,
                        "status": "in_progress",
                    },
                }
            )
            turn_event_callback(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "live_tool_0",
                        "type": "mcp_tool_call",
                        "server": "local",
                        "tool": "list_dir",
                        "arguments": {"path": "."},
                        "result": {
                            "content": [{"type": "text", "text": "a.txt\nsrc\n"}],
                            "structured_content": {"path": ".", "entries": ["a.txt", "src"]},
                        },
                        "error": None,
                        "status": "completed",
                    },
                }
            )
            turn_event_callback(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "live_msg_1",
                        "type": "agent_message",
                        "text": "当前目录下有 a.txt 和 src/。",
                    },
                }
            )
        return AgentIntent(
            assistant_text="当前目录下有 a.txt 和 src/。",
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "canonical_msg_0",
                        "type": "agent_message",
                        "text": "我先查看当前目录内容。",
                    },
                },
                {
                    "type": "item.started",
                    "item": {
                        "id": "canonical_tool_0",
                        "type": "mcp_tool_call",
                        "server": "local",
                        "tool": "list_dir",
                        "arguments": {"path": "."},
                        "result": None,
                        "error": None,
                        "status": "in_progress",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "canonical_tool_0",
                        "type": "mcp_tool_call",
                        "server": "local",
                        "tool": "list_dir",
                        "arguments": {"path": "."},
                        "result": {
                            "content": [{"type": "text", "text": "a.txt\nsrc\n"}],
                            "structured_content": {"path": ".", "entries": ["a.txt", "src"]},
                        },
                        "error": None,
                        "status": "completed",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "canonical_msg_1",
                        "type": "agent_message",
                        "text": "当前目录下有 a.txt 和 src/。",
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ],
        )


class _PlannerBackedAgent(RuleBasedAgent):
    def __init__(self, planner) -> None:
        self.host_platform = current_host_platform()
        self.cwd = Path("/tmp")
        self._plugin_manager_factory = None
        self._planner = planner
        self._planner_error = None
        self._planner_runtime_error = None
        self._provider_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

    def set_cwd(self, cwd):
        self.cwd = Path(cwd).resolve()
        return self.cwd

    def set_plugin_manager_factory(self, factory):
        self._plugin_manager_factory = factory


class _HeadlessWebTools:
    def run_plugin_command(self, name, arg_text, runtime):
        return None

    def web_search(self, query, *, limit=5, domains=None, recency_days=None, market=None):
        return ToolEvent(
            name="web_search",
            ok=True,
            summary="web results=3",
            payload={
                "ok": True,
                "query": query,
                "count": 3,
                "results": [
                    {
                        "rank": 1,
                        "title": "北京天气预报",
                        "url": "https://weather.example.com/beijing",
                        "source_domain": "weather.example.com",
                    },
                    {
                        "rank": 2,
                        "title": "中央气象台北京天气",
                        "url": "https://nmc.example.com/beijing",
                        "source_domain": "nmc.example.com",
                    },
                    {
                        "rank": 3,
                        "title": "北京今日天气",
                        "url": "https://forecast.example.com/beijing",
                        "source_domain": "forecast.example.com",
                    },
                ],
            },
        )

    def web_fetch(self, url, *, max_chars=12000):
        return ToolEvent(
            name="web_fetch",
            ok=True,
            summary="web page loaded",
            payload={
                "ok": True,
                "url": url,
                "final_url": url,
                "title": "Example Report",
            },
        )


def _structured_tool_result(name, summary, payload=None, arguments=None):
    event = ToolEvent(name=name, ok=True, summary=summary, payload=dict(payload or {}))
    return CommandExecutionResult(
        assistant_text=summary,
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=name,
            arguments=dict(arguments or {}) or None,
            ok=True,
            summary=summary,
            structured_content=dict(payload or {}) or None,
        ),
    )


class _PipedStringIO(io.StringIO):
    def isatty(self) -> bool:
        return False


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class HeadlessModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())

    def test_build_headless_runtime_uses_process_cwd_when_not_resuming(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("cli.agent_cli.headless.Path.cwd", return_value=Path(tmp_dir)),
        ):
            runtime = build_headless_runtime(
                runtime_policy=RuntimePolicy.normalized(),
                persistent=False,
                resume_thread_id=None,
            )

        self.assertEqual(runtime.cwd, Path(tmp_dir).resolve())

    def test_build_headless_runtime_persistent_sets_cwd_before_starting_thread(self) -> None:
        class _PersistentRuntimeDouble:
            def __init__(self) -> None:
                self.thread_store = object()
                self.thread_id = None
                self.cwd = Path("/tmp")
                self.calls: list[tuple[str, Path]] = []

            def set_cwd(self, cwd):
                resolved = Path(cwd).resolve()
                self.cwd = resolved
                self.calls.append(("set_cwd", resolved))
                return resolved

            def start_thread(self):
                self.thread_id = "thread_1"
                self.calls.append(("start_thread", self.cwd))

        runtime_double = _PersistentRuntimeDouble()
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch(
                "cli.agent_cli.headless.build_persistent_runtime",
                return_value=runtime_double,
            ) as build_runtime,
            patch("cli.agent_cli.headless.Path.cwd", return_value=Path(tmp_dir)),
        ):
            runtime = build_headless_runtime(
                runtime_policy=RuntimePolicy.normalized(),
                persistent=True,
                resume_thread_id=None,
            )

        self.assertIs(runtime, runtime_double)
        self.assertEqual(
            runtime_double.calls,
            [
                ("set_cwd", Path(tmp_dir).resolve()),
                ("start_thread", Path(tmp_dir).resolve()),
            ],
        )
        _, kwargs = build_runtime.call_args
        self.assertEqual(kwargs["start_thread_if_unavailable"], False)

    def test_build_headless_runtime_codex_sidecar_engine_starts_sidecar_session(self) -> None:
        with patch(
            "cli.agent_cli.headless.build_codex_sidecar_headless_runtime",
            return_value="sidecar-runtime",
        ) as build_sidecar:
            runtime = build_headless_runtime(
                runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
                persistent=False,
                resume_thread_id=None,
                engine="codex_sidecar",
            )

        self.assertEqual(runtime, "sidecar-runtime")
        _, kwargs = build_sidecar.call_args
        self.assertEqual(kwargs["runtime_policy"].approval_policy, "never")

    def test_build_codex_sidecar_headless_runtime_passes_policy_metadata(self) -> None:
        class _KernelDouble:
            def __init__(self, *, codex_bin=None, cwd=None) -> None:
                self.codex_bin = codex_bin
                self.cwd = cwd
                self.requests = []

            async def start_session(self, request):
                self.requests.append(request)
                return KernelSession(
                    engine="codex_sidecar",
                    session_id="session-1",
                    thread_id="thread-1",
                    cwd=str(Path("/tmp/work").resolve()),
                    model_provider="openai",
                )

            async def aclose(self):
                return None

        kernels = []

        def kernel_factory(*, codex_bin=None, cwd=None):
            kernel = _KernelDouble(codex_bin=codex_bin, cwd=cwd)
            kernels.append(kernel)
            return kernel

        with patch("cli.agent_cli.headless.CodexSidecarKernel", side_effect=kernel_factory):
            runtime = build_codex_sidecar_headless_runtime(
                runtime_policy=RuntimePolicy.normalized(
                    approval_policy="never",
                    sandbox_mode="workspace-write",
                ),
                cwd=Path("/tmp/work"),
                codex_bin="/tmp/codex-app-server",
            )

        self.assertEqual(runtime.thread_id, "thread-1")
        self.assertEqual(kernels[0].codex_bin, "/tmp/codex-app-server")
        self.assertEqual(kernels[0].cwd, Path("/tmp/work").resolve())
        request = kernels[0].requests[0]
        self.assertIsNone(request.model_provider)
        self.assertEqual(request.metadata["approvalPolicy"], "never")
        self.assertEqual(request.metadata["sandbox"], "workspace-write")

    def test_prompt_response_to_dict_includes_structured_attachments(self) -> None:
        payload = prompt_response_to_dict(
            PromptResponse(
                user_text='Summarize "C:/project/AgentHub/cli/README.md"',
                commentary_text="Reviewing file reference.",
                assistant_text="done",
                attachments=[PromptAttachment.from_path("C:/project/AgentHub/cli/README.md")],
            )
        )

        self.assertEqual(payload["attachments"][0]["name"], "README.md")
        self.assertEqual(payload["attachments"][0]["path"], "C:/project/AgentHub/cli/README.md")
        self.assertEqual(payload["commentary_text"], "Reviewing file reference.")
        self.assertEqual(payload["response_items"][0]["phase"], "commentary")
        self.assertEqual(payload["response_items"][1]["phase"], "final_answer")

    def test_prompt_response_to_dict_keeps_timings_and_status_fields(self) -> None:
        response = self.runtime.handle_prompt("timed planner")
        payload = prompt_response_to_dict(response)

        self.assertEqual(payload["assistant_text"], "timed reply")
        self.assertEqual(payload["timings"]["total_ms"], 5400)
        self.assertEqual(payload["status"]["timing_total_ms"], "5400")
        self.assertIn("total=5.40s", payload["status"]["timing_summary"])
        self.assertEqual(payload["turn_events"][0]["type"], "turn.started")
        self.assertEqual(payload["turn_events"][-1]["type"], "turn.completed")

    def test_prompt_response_to_dict_surfaces_approval_continuation_status(self) -> None:
        payload = prompt_response_to_dict(
            PromptResponse(
                user_text="/approve approval_1",
                assistant_text="continued after approval",
                tool_events=[
                    ToolEvent(
                        name="approval_decision",
                        ok=True,
                        summary="approved approval_1",
                        payload={
                            "approval_id": "approval_1",
                            "status": "approved",
                            "continuation": {
                                "continuation_attempted": True,
                                "continuation_status": "completed",
                                "approval_id": "approval_1",
                                "action_id": "action_1",
                                "provider_session_kind": "codex_openai",
                                "previous_response_id": "resp_1",
                                "provider_call_id": "call_shell_1",
                                "function_call_name": "exec_command",
                                "provider_tool_type": "local_shell_call",
                                "tool_output_items": [{"type": "local_shell_call_output"}],
                            },
                        },
                    )
                ],
            )
        )

        self.assertTrue(payload["continuation_attempted"])
        self.assertEqual(payload["continuation_status"], "completed")
        self.assertEqual(
            payload["continuation"],
            {
                "continuation_attempted": True,
                "continuation_status": "completed",
                "approval_id": "approval_1",
                "action_id": "action_1",
                "provider_session_kind": "codex_openai",
                "provider_call_id": "call_shell_1",
                "function_call_name": "exec_command",
                "provider_tool_type": "local_shell_call",
            },
        )
        self.assertEqual(
            payload["tool_events"][0]["payload"]["continuation"]["previous_response_id"],
            "resp_1",
        )

    def test_prompt_response_to_dict_preserves_view_image_ready_artifact_contract(self) -> None:
        response = PromptResponse(
            user_text="inspect image",
            assistant_text="image artifact ready: example.png",
            tool_events=[
                ToolEvent(
                    name="view_image",
                    ok=True,
                    summary="image artifact ready: example.png",
                    payload={
                        "path": "/tmp/example.png",
                        "requested_path": "example.png",
                        "ok": True,
                        "image_artifacts": [
                            {
                                "path": "/tmp/example.png",
                                "mime_type": "image/png",
                                "size_bytes": 42,
                                "width": 10,
                                "height": 12,
                                "image_url": "data:image/png;base64,AAA",
                            }
                        ],
                    },
                )
            ],
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "call_1",
                        "type": "mcp_tool_call",
                        "tool": "view_image",
                        "arguments": {"path": "/tmp/example.png"},
                        "result": {
                            "summary": "image artifact ready: example.png",
                            "structured_content": {
                                "path": "/tmp/example.png",
                                "requested_path": "example.png",
                                "image_artifacts": [
                                    {
                                        "path": "/tmp/example.png",
                                        "mime_type": "image/png",
                                        "size_bytes": 42,
                                        "width": 10,
                                        "height": 12,
                                        "image_url": "data:image/png;base64,AAA",
                                    }
                                ],
                            },
                        },
                    },
                },
                {"type": "turn.completed"},
            ],
        )

        payload = prompt_response_to_dict(response)

        self.assertTrue(payload["tool_events"][0]["payload"]["ok"])
        self.assertEqual(
            payload["tool_events"][0]["payload"]["image_artifacts"][0]["mime_type"],
            "image/png",
        )
        completed_tool = next(
            event for event in payload["turn_events"] if event["type"] == "item.completed"
        )
        self.assertEqual(
            completed_tool["item"]["result"]["structured_content"]["image_artifacts"][0]["width"],
            10,
        )
        self.assertEqual(
            completed_tool["item"]["result"]["structured_content"]["image_artifacts"][0][
                "image_url"
            ],
            "data:image/png;base64,AAA",
        )

    def test_prompt_response_to_dict_preserves_view_image_injected_turn_event(self) -> None:
        response = PromptResponse(
            user_text="inspect image",
            assistant_text="the model can now inspect the image",
            tool_events=[],
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "function_call_output",
                        "call_id": "call_view_image_1",
                        "output": [
                            {
                                "type": "input_image",
                                "image_url": "data:image/png;base64,AAA",
                                "detail": "original",
                            }
                        ],
                        "image_transport_subject": "/tmp/example.png",
                        "success": True,
                    },
                },
                {"type": "turn.completed"},
            ],
        )

        payload = prompt_response_to_dict(response)

        completed_tool = next(
            event for event in payload["turn_events"] if event["type"] == "item.completed"
        )
        self.assertEqual(
            completed_tool["item"]["type"],
            "function_call_output",
        )
        self.assertEqual(
            completed_tool["item"]["output"][0]["type"],
            "input_image",
        )
        self.assertEqual(
            completed_tool["item"]["output"][0]["detail"],
            "original",
        )
        self.assertEqual(
            completed_tool["item"]["image_transport_subject"],
            "/tmp/example.png",
        )

    def test_prompt_response_to_dict_preserves_image_transport_family_metadata(self) -> None:
        response = PromptResponse(
            user_text="inspect image",
            assistant_text="the model can now inspect the image",
            tool_events=[],
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "function_call_output",
                        "call_id": "call_read_file_1",
                        "output": [
                            {
                                "type": "input_image",
                                "image_url": "data:image/png;base64,AAA",
                            }
                        ],
                        "image_transport_family": "image_aware_file_read",
                        "image_transport_subject": "/tmp/example.png",
                        "success": True,
                    },
                },
                {"type": "turn.completed"},
            ],
        )

        payload = prompt_response_to_dict(response)

        completed_tool = next(
            event for event in payload["turn_events"] if event["type"] == "item.completed"
        )
        self.assertEqual(
            completed_tool["item"]["image_transport_family"],
            "image_aware_file_read",
        )
        self.assertEqual(
            completed_tool["item"]["image_transport_subject"],
            "/tmp/example.png",
        )

    def test_runtime_response_carries_canonical_turn_events(self) -> None:
        response = self.runtime.handle_prompt("list current directory")

        self.assertEqual(response.turn_events[0]["type"], "turn.started")
        self.assertEqual(response.turn_events[-1]["type"], "turn.completed")
        command_started = next(
            event for event in response.turn_events if event["type"] == "item.started"
        )
        self.assertEqual(command_started["item"]["type"], "command_execution")
        command_completed = next(
            event
            for event in response.turn_events
            if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
        )
        self.assertEqual(command_completed["item"]["status"], "completed")
        self.assertEqual(command_completed["item"]["exit_code"], 0)
        self.assertEqual(command_completed["item"]["aggregated_output"], "a.txt\nb.txt\n")

    def test_headless_prompt_text_output(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(
            ["--headless", "--prompt", "list current directory"],
            runtime=self.runtime,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Checking current workspace before execution.", stdout.getvalue())
        self.assertTrue(
            (
                "Recognized as a local directory query." in stdout.getvalue()
                or "Request shell approval." in stdout.getvalue()
            ),
            stdout.getvalue(),
        )
        self.assertNotIn("shell ok: Get-ChildItem -Force", stdout.getvalue())

    def test_headless_text_output_prefers_commentary_then_assistant(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(
            ["--headless", "--prompt", "commentary layering"],
            runtime=self.runtime,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            stdout.getvalue().strip(),
            "Building narrative context before the action.\n\nReady to follow up with the run.",
        )

    def test_headless_text_output_commentary_only(self) -> None:
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "commentary only"],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, 0)
        self.assertEqual(
            stdout.getvalue().strip(),
            "Only commentary is available until the next response arrives.",
        )

    def test_prompt_response_to_dict_preserves_explicit_response_items(self) -> None:
        payload = prompt_response_to_dict(
            PromptResponse(
                user_text="phase aware",
                assistant_text="final body",
                commentary_text="commentary body",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "provider_loop",
                        "source": "provider",
                        "provider_used": True,
                    }
                },
                response_items=default_response_items(
                    commentary_text="commentary body",
                    assistant_text="final body",
                ),
            )
        )

        self.assertEqual(len(payload["response_items"]), 2)
        self.assertEqual(payload["response_items"][0]["phase"], "commentary")
        self.assertEqual(payload["response_items"][1]["phase"], "final_answer")
        self.assertEqual(payload["protocol_diagnostics"]["protocol_path"]["kind"], "provider_loop")

    def test_prompt_response_to_dict_injects_function_call_protocol_items_for_tool_turn(
        self,
    ) -> None:
        payload = prompt_response_to_dict(
            PromptResponse(
                user_text="先执行 pwd，再告诉我当前目录。",
                assistant_text="当前目录是 `/repo`。",
                response_items=default_response_items(assistant_text="当前目录是 `/repo`。"),
                tool_events=[
                    ToolEvent(
                        name="exec_command",
                        ok=True,
                        summary="exec_command completed",
                        payload={
                            "provider_call_id": "call_exec_1",
                            "function_call_name": "exec_command",
                            "function_call_arguments": {"cmd": "pwd"},
                            "function_call_output": "/repo\n",
                            "command": "pwd",
                            "stdout": "/repo\n",
                            "aggregated_output": "/repo\n",
                            "exit_code": 0,
                        },
                    )
                ],
            )
        )

        self.assertEqual(
            [item["type"] for item in payload["response_items"]],
            ["function_call", "function_call_output", "message"],
        )
        self.assertEqual(payload["response_items"][0]["call_id"], "call_exec_1")
        self.assertEqual(payload["response_items"][1]["output"], "/repo\n")

    def test_prompt_response_to_dict_injects_shell_call_protocol_items_for_native_shell_turn(
        self,
    ) -> None:
        payload = prompt_response_to_dict(
            PromptResponse(
                user_text="执行 shell",
                assistant_text="shell done",
                response_items=default_response_items(assistant_text="shell done"),
                tool_events=[
                    ToolEvent(
                        name="shell",
                        ok=True,
                        summary="shell rc=0",
                        payload={
                            "provider_call_id": "call_shell_1",
                            "provider_tool_type": "shell_call",
                            "provider_raw_item": {
                                "type": "shell_call",
                                "call_id": "call_shell_1",
                                "action": {
                                    "type": "exec",
                                    "command": ["pwd"],
                                    "timeout_ms": 1000,
                                    "max_output_length": 12000,
                                },
                            },
                            "command": "pwd",
                            "stdout": "/repo\n",
                            "stderr": "",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    )
                ],
            )
        )

        self.assertEqual(
            [item["type"] for item in payload["response_items"]],
            ["shell_call", "shell_call_output", "message"],
        )
        self.assertEqual(payload["response_items"][0]["call_id"], "call_shell_1")
        self.assertEqual(payload["response_items"][0]["action"]["command"], ["pwd"])
        self.assertEqual(payload["response_items"][1]["output"][0]["stdout"], "/repo\n")

    def test_prompt_response_to_dict_fallback_turn_events_are_message_only(self) -> None:
        payload = prompt_response_to_dict(
            PromptResponse(
                user_text="hello",
                commentary_text="thinking",
                assistant_text="answer",
                tool_events=[
                    ToolEvent(
                        name="shell",
                        ok=True,
                        summary="shell rc=0",
                        payload={"command": "echo hi", "returncode": 0},
                    )
                ],
            )
        )
        self.assertEqual(payload["turn_events"][0]["type"], "turn.started")
        self.assertEqual(payload["turn_events"][-1]["type"], "turn.completed")
        completed_items = [
            dict(event.get("item") or {})
            for event in payload["turn_events"]
            if event.get("type") == "item.completed"
        ]
        self.assertTrue(completed_items)
        self.assertEqual(completed_items[-1]["type"], "agent_message")

    def test_prompt_response_to_dict_shell_lifecycle_payload_uses_shell_turn_events(self) -> None:
        payload = prompt_response_to_dict(
            PromptResponse(
                user_text="hello",
                assistant_text="",
                commentary_text="",
                tool_events=[
                    ToolEvent(
                        name="shell",
                        ok=True,
                        summary="shell ok",
                        payload={
                            "phase": "completed",
                            "command": "echo hi",
                            "session_id": "session_1",
                            "call_id": "call_1",
                            "stdout": "hi\n",
                            "stderr": "",
                            "status": "ok",
                            "lifecycle": {
                                "phase": "completed",
                                "kind": "end",
                                "call_id": "call_1",
                                "session_id": "session_1",
                            },
                        },
                    )
                ],
            )
        )
        self.assertEqual(payload["turn_events"][0]["type"], "turn.started")
        self.assertEqual(payload["turn_events"][-1]["type"], "turn.completed")
        completed_shell_items = [
            dict(event.get("item") or {})
            for event in payload["turn_events"]
            if event.get("type") == "item.completed" and isinstance(event.get("item"), dict)
        ]
        self.assertTrue(completed_shell_items)
        self.assertEqual(completed_shell_items[-1]["type"], "function_call")
        self.assertEqual(completed_shell_items[-1]["name"], "shell")
        self.assertEqual(completed_shell_items[-1]["call_id"], "call_1")

    def test_headless_resume_thread_keeps_ready_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(
                name="resume old thread",
                provider_status={
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                },
            )

            runtime = AgentCliRuntime(
                agent=_HeadlessAgent(),
                tools=_HeadlessTools(),
                thread_store=store,
                thread_id=thread.thread_id,
            )

            status = runtime.agent.provider_status()
            self.assertEqual(status["provider_name"], "deepseek")
            self.assertEqual(status["provider_model"], "deepseek-reasoner")

    def test_headless_prompt_json_output(self) -> None:
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "list current directory", "--json"],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["commentary_text"], "Checking current workspace before execution.")
        self.assertEqual(payload["tool_events"][-1]["name"], "shell")
        self.assertEqual(payload["status"]["last_tool"], "shell")
        self.assertEqual(payload["status"]["provider_model"], "deepseek-reasoner")

    def test_headless_prompt_json_output_with_approval_policy_never_runs_shell(self) -> None:
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                "list current directory",
                "--json",
                "--approval-policy",
                "never",
            ],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["tool_events"][-1]["name"], "shell")
        self.assertEqual(payload["status"]["last_tool"], "shell")

    def test_headless_prompt_json_output_prompts_for_pure_network_exec(self) -> None:
        runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                "/exec_command 'curl -I https://example.com'",
                "--json",
                "--approval-policy",
                "on-request",
            ],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        tool_event = payload["tool_events"][-1]
        completed_tool = next(
            event
            for event in payload["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
        )
        self.assertEqual(code, 0)
        self.assertEqual(tool_event["name"], "shell_approval_requested")
        self.assertEqual(tool_event["payload"]["policy_decision"], "requires_approval")
        self.assertEqual(tool_event["payload"]["reason_code"], "exec.network.requires_approval")
        self.assertEqual(
            tool_event["payload"]["command_approval"]["reason_code"],
            "exec.network.requires_approval",
        )
        self.assertTrue(tool_event["payload"]["network_access_enabled"])
        self.assertEqual(completed_tool["item"]["tool"], "exec_command")
        self.assertEqual(completed_tool["item"]["status"], "completed")

    def test_headless_prompt_json_output_blocks_network_when_disabled_without_approval_path(
        self,
    ) -> None:
        runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                "/exec_command 'curl -I https://example.com'",
                "--json",
                "--approval-policy",
                "never",
                "--network-access",
                "disabled",
            ],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        tool_event = payload["tool_events"][-1]
        self.assertEqual(code, 2)
        self.assertEqual(tool_event["name"], "exec_command")
        self.assertFalse(tool_event["ok"])
        self.assertEqual(tool_event["payload"]["policy_decision"], "blocked")
        self.assertEqual(tool_event["payload"]["reason_code"], "exec.network.forbidden.no_approval")
        self.assertEqual(
            tool_event["payload"]["exec_approval_requirement"]["requirement"], "forbidden"
        )
        self.assertFalse(tool_event["payload"]["network_access_enabled"])

    def test_headless_prompt_json_output_prompts_for_requested_network_permission(self) -> None:
        runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                "/exec_command 'python -V' --additional-permissions-json '{\"network\":{\"enabled\":true}}'",
                "--json",
                "--approval-policy",
                "on-request",
                "--network-access",
                "disabled",
            ],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        tool_event = payload["tool_events"][-1]
        self.assertEqual(code, 0)
        self.assertEqual(tool_event["name"], "shell_approval_requested")
        self.assertEqual(tool_event["payload"]["policy_decision"], "requires_approval")
        self.assertEqual(tool_event["payload"]["reason_code"], "exec.network.requires_approval")
        self.assertEqual(
            tool_event["payload"]["additional_permissions"], {"network": {"enabled": True}}
        )
        self.assertEqual(
            tool_event["payload"]["action_policy"]["metadata"]["requested_additional_permissions"],
            {"network": {"enabled": True}},
        )

    def test_headless_prompt_json_output_approve_network_exec_continues_execution(self) -> None:
        runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
        approval_stdout = io.StringIO()

        approval_code = main(
            [
                "--headless",
                "--prompt",
                "/exec_command 'curl -I https://example.com'",
                "--json",
                "--approval-policy",
                "on-request",
            ],
            runtime=runtime,
            stdout=approval_stdout,
            stderr=io.StringIO(),
        )
        approval_payload = json.loads(approval_stdout.getvalue())
        approval_id = approval_payload["tool_events"][-1]["payload"]["approval_id"]
        decision_stdout = io.StringIO()

        decision_code = main(
            ["--headless", "--prompt", f"/approve {approval_id}", "--json"],
            runtime=runtime,
            stdout=decision_stdout,
            stderr=io.StringIO(),
        )

        decision_payload = json.loads(decision_stdout.getvalue())
        self.assertEqual(approval_code, 0)
        self.assertEqual(decision_code, 0)
        self.assertEqual(
            [event["name"] for event in decision_payload["tool_events"]],
            ["approval_decision", "shell_start"],
        )
        self.assertEqual(
            decision_payload["tool_events"][-1]["payload"]["command"], "curl -I https://example.com"
        )
        self.assertEqual(decision_payload["tool_events"][-1]["payload"]["status"], "started")

    def test_headless_prompt_json_output_already_decided_approval_does_not_reexecute(self) -> None:
        runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
        approval_stdout = io.StringIO()

        approval_code = main(
            [
                "--headless",
                "--prompt",
                "/exec_command 'curl -I https://example.com'",
                "--json",
                "--approval-policy",
                "on-request",
            ],
            runtime=runtime,
            stdout=approval_stdout,
            stderr=io.StringIO(),
        )
        approval_payload = json.loads(approval_stdout.getvalue())
        approval_id = approval_payload["tool_events"][-1]["payload"]["approval_id"]
        first_decision_stdout = io.StringIO()
        second_decision_stdout = io.StringIO()

        first_decision_code = main(
            ["--headless", "--prompt", f"/approve {approval_id}", "--json"],
            runtime=runtime,
            stdout=first_decision_stdout,
            stderr=io.StringIO(),
        )
        second_decision_code = main(
            ["--headless", "--prompt", f"/approve {approval_id}", "--json"],
            runtime=runtime,
            stdout=second_decision_stdout,
            stderr=io.StringIO(),
        )

        first_decision_payload = json.loads(first_decision_stdout.getvalue())
        second_decision_payload = json.loads(second_decision_stdout.getvalue())
        self.assertEqual(approval_code, 0)
        self.assertEqual(first_decision_code, 0)
        self.assertEqual(second_decision_code, 0)
        self.assertEqual(
            [event["name"] for event in first_decision_payload["tool_events"]],
            ["approval_decision", "shell_start"],
        )
        self.assertEqual(
            [event["name"] for event in second_decision_payload["tool_events"]],
            ["approval_decision"],
        )
        self.assertFalse(second_decision_payload["tool_events"][0]["ok"])
        self.assertIn(
            "approval already decided",
            second_decision_payload["tool_events"][0]["payload"]["error"],
        )

    def test_headless_prompt_json_output_reject_network_exec_does_not_execute(self) -> None:
        runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
        approval_stdout = io.StringIO()

        approval_code = main(
            [
                "--headless",
                "--prompt",
                "/exec_command 'curl -I https://example.com'",
                "--json",
                "--approval-policy",
                "on-request",
            ],
            runtime=runtime,
            stdout=approval_stdout,
            stderr=io.StringIO(),
        )
        approval_payload = json.loads(approval_stdout.getvalue())
        approval_id = approval_payload["tool_events"][-1]["payload"]["approval_id"]
        decision_stdout = io.StringIO()

        decision_code = main(
            ["--headless", "--prompt", f"/reject {approval_id}", "--json"],
            runtime=runtime,
            stdout=decision_stdout,
            stderr=io.StringIO(),
        )

        decision_payload = json.loads(decision_stdout.getvalue())
        self.assertEqual(approval_code, 0)
        self.assertEqual(decision_code, 0)
        self.assertEqual(
            [event["name"] for event in decision_payload["tool_events"]], ["approval_decision"]
        )
        self.assertEqual(decision_payload["tool_events"][-1]["payload"]["status"], "rejected")

    def test_headless_prompt_json_output_accepts_permission_mode_alias(self) -> None:
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                "commentary only",
                "--json",
                "--permission-mode",
                "accept-edits",
            ],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"]["approval_policy"], "never")
        self.assertEqual(payload["status"]["sandbox_mode"], "workspace-write")
        self.assertEqual(payload["status"]["network_access"], "enabled")
        self.assertEqual(
            permission_mode_label(
                approval_policy=payload["status"]["approval_policy"],
                sandbox_mode=payload["status"]["sandbox_mode"],
                network_access_enabled=payload["status"]["network_access"],
            ),
            "acceptEdits",
        )

    def test_headless_prompt_json_output_permission_mode_respects_explicit_axes(self) -> None:
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                "commentary only",
                "--json",
                "--permission-mode",
                "bypassPermissions",
                "--sandbox-mode",
                "read-only",
                "--network-access",
                "disabled",
            ],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"]["approval_policy"], "never")
        self.assertEqual(payload["status"]["sandbox_mode"], "read-only")
        self.assertEqual(payload["status"]["network_access"], "disabled")
        self.assertEqual(
            permission_mode_label(
                approval_policy=payload["status"]["approval_policy"],
                sandbox_mode=payload["status"]["sandbox_mode"],
                network_access_enabled=payload["status"]["network_access"],
            ),
            "custom",
        )

    def test_headless_prompt_json_output_supports_update_plan_slash_command(self) -> None:
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                '/update_plan \'{"explanation":"sync","plan":[{"step":"inspect","status":"completed"},{"step":"patch","status":"in_progress"}]}\'',
                "--json",
            ],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["handled_as_command"])
        self.assertEqual(payload["assistant_text"], "Plan updated")
        self.assertEqual(payload["tool_events"][-1]["name"], "update_plan")
        completed_tool = next(
            event
            for event in payload["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "todo_list"
        )
        self.assertEqual(
            completed_tool["item"]["items"],
            [
                {"text": "inspect", "completed": True},
                {"text": "patch", "completed": False},
            ],
        )

    def test_headless_prompt_json_output_supports_request_user_input_round_trip(self) -> None:
        runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
        runtime.collaboration_mode = "plan"
        runtime.request_user_input_handler = lambda payload: {
            "answers": {"confirm_path": {"answers": ["yes"]}},
            "questions": payload["questions"],
        }
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
                "--json",
            ],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["tool_events"][-1]["name"], "request_user_input")
        self.assertEqual(
            json.loads(payload["assistant_text"])["answers"]["confirm_path"]["answers"], ["yes"]
        )
        completed_tool = next(
            event
            for event in payload["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
        )
        self.assertEqual(completed_tool["item"]["tool"], "request_user_input")

    def test_headless_prompt_json_output_request_user_input_treats_non_object_result_as_cancelled(
        self,
    ) -> None:
        runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
        runtime.collaboration_mode = "plan"
        runtime.request_user_input_handler = lambda _payload: []  # type: ignore[assignment]
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
                "--json",
            ],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["tool_events"][-1]["name"], "request_user_input")
        self.assertFalse(payload["tool_events"][-1]["ok"])
        self.assertEqual(
            payload["assistant_text"],
            "request_user_input was cancelled before receiving a response",
        )

    def test_headless_prompt_json_output_supports_exec_command_slash_command(self) -> None:
        runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                "/exec_command 'python -V' --yield-time-ms 250 --tty",
                "--json",
                "--approval-policy",
                "never",
            ],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["tool_events"][-1]["name"], "exec_command")
        assistant_text = str(payload.get("assistant_text") or "")
        self.assertTrue(
            "Process running with session ID session_1" in assistant_text
            or "Python 3.12.0" in assistant_text,
            assistant_text,
        )
        completed_tool = next(
            event
            for event in payload["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
        )
        self.assertEqual(completed_tool["item"]["command"], "python -V")
        self.assertEqual(payload["status"]["approval_policy"], "never")

    def test_headless_prompt_json_output_supports_init_yes_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            (root / "package.json").write_text(
                '{"name":"demo","scripts":{"build":"vite build"}}', encoding="utf-8"
            )
            runtime = AgentCliRuntime(agent=_HeadlessAgent(), tools=_HeadlessTools())
            runtime.set_cwd(root)
            stdout = io.StringIO()

            code = main(
                ["--headless", "--prompt", "/init --yes", "--json", "--approval-policy", "never"],
                runtime=runtime,
                stdout=stdout,
                stderr=io.StringIO(),
            )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(payload["handled_as_command"])
            self.assertIn("init auto-applied", payload["assistant_text"])
            self.assertTrue((root / "AENGTHUB.md").is_file())

    def test_headless_office_skill_json_output(self) -> None:
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "show office skills", "--json"],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual([item["name"] for item in payload["tool_events"]], ["office_skills"])
        self.assertEqual(
            payload["tool_events"][0]["payload"]["skills"][0]["name"], "read_docx_markdown"
        )

    def test_headless_prompt_jsonl_output(self) -> None:
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "list current directory", "--jsonl"],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["type"], "thread.started")
        self.assertEqual(lines[1]["type"], "turn.started")
        self.assertEqual(lines[-1]["type"], "turn.completed")
        self.assertEqual(sum(1 for line in lines if line["type"] == "turn.started"), 1)
        command_started = next(line for line in lines if line["type"] == "item.started")
        self.assertEqual(command_started["item"]["type"], "command_execution")
        self.assertEqual(command_started["item"]["command"], "Get-ChildItem -Force")
        command_completed = next(
            line
            for line in lines
            if line["type"] == "item.completed" and line["item"]["type"] == "command_execution"
        )
        self.assertEqual(command_completed["item"]["status"], "completed")
        self.assertEqual(command_completed["item"]["exit_code"], 0)
        self.assertEqual(command_completed["item"]["aggregated_output"], "a.txt\nb.txt\n")
        agent_messages = [
            line["item"]["text"]
            for line in lines
            if line["type"] == "item.completed" and line["item"]["type"] == "agent_message"
        ]
        self.assertTrue(
            any("Checking current workspace before execution." in text for text in agent_messages),
            agent_messages,
        )
        self.assertTrue(
            any(
                "Recognized as a local directory query. Preparing shell execution." in text
                for text in agent_messages
            ),
            agent_messages,
        )

    def test_headless_prompt_jsonl_output_with_approval_policy_never_runs_shell(self) -> None:
        stdout = io.StringIO()

        code = main(
            [
                "--headless",
                "--prompt",
                "list current directory",
                "--jsonl",
                "--approval-policy",
                "never",
            ],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["type"], "thread.started")
        self.assertEqual(lines[1]["type"], "turn.started")
        self.assertEqual(lines[-1]["type"], "turn.completed")
        self.assertEqual(sum(1 for line in lines if line["type"] == "turn.started"), 1)
        command_started = next(line for line in lines if line["type"] == "item.started")
        self.assertEqual(command_started["item"]["type"], "command_execution")
        command_updated = next(line for line in lines if line["type"] == "item.updated")
        self.assertEqual(command_updated["item"]["aggregated_output"], "a.txt\nb.txt\n")
        command_completed = next(
            line
            for line in lines
            if line["type"] == "item.completed" and line["item"]["type"] == "command_execution"
        )
        self.assertEqual(command_completed["item"]["status"], "completed")
        self.assertEqual(command_completed["item"]["exit_code"], 0)
        self.assertEqual(command_completed["item"]["aggregated_output"], "a.txt\nb.txt\n")

    def test_headless_prompt_jsonl_writes_response_sidecar_when_requested(self) -> None:
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            response_path = Path(temp_dir) / "headless-response.json"
            with patch.dict(
                os.environ, {"AGENT_CLI_HEADLESS_RESPONSE_PATH": str(response_path)}, clear=False
            ):
                code = main(
                    ["--headless", "--prompt", "stream prompt", "--jsonl"],
                    runtime=_StreamingPromptRuntime(),
                    stdout=stdout,
                    stderr=io.StringIO(),
                )

            payload = json.loads(response_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(payload["assistant_text"], "已找到入口文件")
        self.assertEqual(payload["commentary_text"], "先检查上下文")
        self.assertEqual(payload["status"]["provider_name"], "stream-test")
        self.assertEqual(payload["turn_events"][-1]["type"], "turn.completed")

    def test_headless_prompt_jsonl_streams_live_turn_events_during_execution(self) -> None:
        # Modeled after Reference exec JSONL event stream expectations:
        # - reference_baseline/reference-rs/exec/tests/event_processor_with_json_output.rs
        # - reference_baseline/reference-rs/core/tests/suite/cli_stream.rs
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "stream prompt", "--jsonl"],
            runtime=_StreamingPromptRuntime(),
            stdout=stdout,
            stderr=io.StringIO(),
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["type"], "thread.started")
        self.assertEqual(lines[1]["type"], "turn.started")
        self.assertEqual(lines[2]["item"]["type"], "reasoning")
        self.assertEqual(lines[3]["item"]["type"], "agent_message")
        self.assertEqual(lines[-1]["type"], "turn.completed")
        self.assertEqual(sum(1 for line in lines if line["type"] == "turn.started"), 1)

    def test_headless_prompt_jsonl_suppresses_live_agent_message_deltas(self) -> None:
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "stream prompt", "--jsonl"],
            runtime=_StreamingDeltaPromptRuntime(),
            stdout=stdout,
            stderr=io.StringIO(),
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertFalse(
            any(
                line["type"] in {"item.started", "item.updated"}
                and line["item"]["type"] == "agent_message"
                for line in lines
            ),
            lines,
        )
        completed_messages = [
            line["item"]["text"]
            for line in lines
            if line["type"] == "item.completed" and line["item"]["type"] == "agent_message"
        ]
        self.assertEqual(completed_messages, ["增量完成"])

    def test_headless_jsonl_resume_uses_requested_thread_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")

            runtime1 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            runtime1.set_cwd(workspace)
            thread = runtime1.start_thread(name="resume probe")
            runtime1.handle_prompt("hello first turn")

            runtime2 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            runtime2.set_cwd(workspace)
            stdout = io.StringIO()

            code = main(
                [
                    "--headless",
                    "--resume",
                    thread["thread_id"],
                    "--prompt",
                    "hello second turn",
                    "--jsonl",
                ],
                runtime=runtime2,
                stdout=stdout,
                stderr=io.StringIO(),
            )

            lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(code, 0)
            self.assertEqual(runtime2.thread_id, thread["thread_id"])
            self.assertEqual(lines[0]["type"], "thread.started")
            self.assertEqual(lines[0]["thread_id"], thread["thread_id"])
            self.assertTrue(
                any(item.get("content") == "hello first turn" for item in runtime2.history)
            )
            self.assertTrue(
                any(item.get("content") == "echo: hello first turn" for item in runtime2.history)
            )

    def test_headless_jsonl_resume_path_uses_requested_rollout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")

            runtime1 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            runtime1.set_cwd(workspace)
            thread = runtime1.start_thread(name="resume path probe")
            runtime1.handle_prompt("hello first turn")

            runtime2 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            runtime2.set_cwd(workspace)
            stdout = io.StringIO()

            code = main(
                [
                    "--headless",
                    "--resume-path",
                    thread["rollout_path"],
                    "--prompt",
                    "hello second turn",
                    "--jsonl",
                ],
                runtime=runtime2,
                stdout=stdout,
                stderr=io.StringIO(),
            )

            lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(code, 0)
            self.assertEqual(runtime2.thread_id, thread["thread_id"])
            self.assertEqual(lines[0]["type"], "thread.started")
            self.assertEqual(lines[0]["thread_id"], thread["thread_id"])
            self.assertTrue(
                any(item.get("content") == "hello first turn" for item in runtime2.history)
            )
            self.assertTrue(
                any(item.get("content") == "echo: hello first turn" for item in runtime2.history)
            )

    def test_headless_jsonl_resume_last_uses_active_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")

            runtime1 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            runtime1.set_cwd(workspace)
            thread = runtime1.start_thread(name="resume last probe")
            runtime1.handle_prompt("hello first turn")

            runtime2 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            runtime2.set_cwd(workspace)
            stdout = io.StringIO()

            code = main(
                ["--headless", "--resume-last", "--prompt", "hello second turn", "--jsonl"],
                runtime=runtime2,
                stdout=stdout,
                stderr=io.StringIO(),
            )

            lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(code, 0)
            self.assertEqual(runtime2.thread_id, thread["thread_id"])
            self.assertEqual(lines[0]["type"], "thread.started")
            self.assertEqual(lines[0]["thread_id"], thread["thread_id"])
            self.assertTrue(
                any(item.get("content") == "hello first turn" for item in runtime2.history)
            )

    def test_headless_resume_last_slash_command_uses_active_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root / "state")

            runtime1 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            thread = runtime1.start_thread(name="slash resume last")
            runtime1.handle_prompt("hello first turn")

            runtime2 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            stdout = io.StringIO()

            code = main(
                ["--headless", "--prompt", "/resume_last", "--json"],
                runtime=runtime2,
                stdout=stdout,
                stderr=io.StringIO(),
            )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(runtime2.thread_id, thread["thread_id"])
            self.assertIn("resumed thread", payload["assistant_text"])
            self.assertIn(thread["thread_id"], payload["assistant_text"])

    def test_headless_threads_and_resume_path_slash_commands_expose_persisted_threads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root / "state")

            runtime1 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            thread = runtime1.start_thread(name="slash resume path")
            runtime1.handle_prompt("hello first turn")

            runtime2 = AgentCliRuntime(
                agent=_HeadlessAgent(), tools=_HeadlessTools(), thread_store=store
            )
            threads_stdout = io.StringIO()

            threads_code = main(
                ["--headless", "--prompt", "/threads --limit 5", "--json"],
                runtime=runtime2,
                stdout=threads_stdout,
                stderr=io.StringIO(),
            )

            threads_payload = json.loads(threads_stdout.getvalue())
            self.assertEqual(threads_code, 0)
            self.assertIn("threads=1", threads_payload["assistant_text"])
            self.assertIn(thread["thread_id"], threads_payload["assistant_text"])

            resume_stdout = io.StringIO()
            resume_code = main(
                ["--headless", "--prompt", f"/resume_path {thread['rollout_path']}", "--json"],
                runtime=runtime2,
                stdout=resume_stdout,
                stderr=io.StringIO(),
            )

            resume_payload = json.loads(resume_stdout.getvalue())
            self.assertEqual(resume_code, 0)
            self.assertEqual(runtime2.thread_id, thread["thread_id"])
            self.assertIn("resume_source=path", resume_payload["assistant_text"])
            self.assertIn(thread["rollout_path"], resume_payload["assistant_text"])

    def test_headless_provider_status_shortcut(self) -> None:
        stdout = io.StringIO()

        code = main(
            ["--headless", "--provider-status"],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, 0)
        self.assertIn("provider status", stdout.getvalue())
        self.assertIn(f"provider_config_path={PROVIDER_CONFIG_REF}", stdout.getvalue())

    def test_headless_reads_prompt_from_stdin(self) -> None:
        stdout = io.StringIO()

        code = main(
            ["--headless"],
            runtime=self.runtime,
            stdin=_PipedStringIO("/provider"),
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, 0)
        self.assertIn("provider_model=deepseek-reasoner", stdout.getvalue())

    def test_headless_missing_prompt_returns_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(
            ["--headless"],
            runtime=self.runtime,
            stdin=_TtyStringIO(""),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("provide --prompt, --provider-status, or --stdin", stderr.getvalue())

    def test_headless_invalid_arg_combo_returns_error(self) -> None:
        stderr = io.StringIO()

        code = main(
            ["--headless", "--json", "--jsonl", "--prompt", "/provider"],
            runtime=self.runtime,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, 1)
        self.assertIn("--json cannot be combined with --jsonl", stderr.getvalue())

    def test_headless_failed_tool_returns_exit_code_2(self) -> None:
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "fail shell", "--json", "--approval-policy", "never"],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["tool_events"][-1]["ok"], False)
        self.assertEqual(payload["status"]["last_ok"], "False")

    def test_headless_soft_failed_tool_keeps_exit_code_zero(self) -> None:
        response = PromptResponse(
            user_text="search missing",
            assistant_text="No matches found.",
            tool_events=[
                ToolEvent(
                    name="grep_files",
                    ok=False,
                    summary="No matches found.",
                    payload={
                        "result_success": False,
                        "text": "No matches found.",
                        "pattern": "needle",
                        "path": ".",
                    },
                )
            ],
        )

        self.assertEqual(_exit_code_for_response(response), 0)

    def test_codex_noninteractive_failed_exec_with_final_answer_keeps_exit_code_zero(self) -> None:
        self.runtime.agent._planner = SimpleNamespace(
            config=ProviderConfig(
                model="gpt-5.4",
                api_key="test-key",
                provider_name="openai",
                planner_kind="openai_responses",
                interaction_profile="codex_openai",
                interaction_profile_source="test",
            )
        )
        self.runtime._agenthub_headless_mode = "prompt"

        response = self.runtime._build_response(
            user_text="write file",
            assistant_text="写入失败，当前是只读沙箱。",
            attachments=[],
            tool_events=[
                ToolEvent(
                    name="exec_command",
                    ok=False,
                    summary="exec_command exited",
                    payload={
                        "returncode": 1,
                        "stderr": "/bin/bash: line 1: note.txt: Permission denied",
                    },
                )
            ],
            protocol_diagnostics={},
            source_text="write file",
            handled_as_command=False,
        )

        self.assertTrue(response.protocol_diagnostics["headless_contract"]["codex_noninteractive"])
        self.assertEqual(_exit_code_for_response(response), 0)

    def test_headless_malformed_command_returns_parse_error_instead_of_crashing(self) -> None:
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "bad quoted command", "--json"],
            runtime=self.runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertIn("命令解析失败", payload["assistant_text"])
        self.assertEqual(payload["tool_events"][-1]["name"], "command_parse")
        self.assertEqual(payload["tool_events"][-1]["ok"], False)

    def test_headless_serve_mode_outputs_response_lines(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "1", "provider_status": True}),
                    json.dumps({"id": "2", "prompt": "list current directory", "stream": True}),
                ]
            )
            + "\n"
        )

        code = main(
            ["--headless", "--serve"],
            runtime=self.runtime,
            stdin=stdin,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["type"], "response")
        self.assertEqual(lines[0]["id"], "1")
        self.assertIn("provider status", lines[0]["response"]["assistant_text"])
        streamed_lines = [line for line in lines if line.get("id") == "2"]
        self.assertEqual(streamed_lines[0]["type"], "thread.started")
        self.assertEqual(streamed_lines[1]["type"], "turn.started")
        self.assertEqual(streamed_lines[-1]["type"], "turn.completed")
        self.assertEqual(sum(1 for line in streamed_lines if line["type"] == "turn.started"), 1)
        self.assertTrue(
            any(
                line["type"] == "item.completed" and line["item"]["type"] == "command_execution"
                for line in streamed_lines
            )
        )

    def test_headless_serve_mode_emits_control_request_for_pending_approval(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(json.dumps({"id": "1", "prompt": "needs approval"}) + "\n")
        approval_event = ToolEvent(
            name="shell_approval_requested",
            ok=True,
            summary="shell approval requested approval_1",
            payload={
                "approval_id": "approval_1",
                "command": "printf hello > out.txt",
                "reason": "needs workspace write",
            },
        )

        code = headless_stream_runtime_helpers.run_serve_loop(
            object(),
            input_stream=stdin,
            output_stream=stdout,
            emit_json_line_fn=lambda stream, payload: print(json.dumps(payload), file=stream),
            request_id_for_payload_fn=lambda payload: (
                str(payload.get("id")) if "id" in payload else None
            ),
            resolve_serve_prompt_fn=lambda payload: str(payload["prompt"]),
            execute_prompt_fn=lambda *_args, **_kwargs: PromptResponse(
                user_text="needs approval",
                assistant_text="approval required",
                tool_events=[approval_event],
            ),
            prompt_response_to_dict_fn=lambda response: {
                "assistant_text": response.assistant_text,
                "tool_events": [item.to_dict() for item in response.tool_events],
            },
            exit_code_for_response_fn=lambda _response: 0,
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["type"], "control_request")
        self.assertEqual(lines[0]["request_id"], "approval_1")
        self.assertEqual(lines[0]["request"]["subtype"], "can_use_tool")
        self.assertEqual(lines[0]["request"]["tool_name"], "Bash")
        self.assertEqual(lines[0]["request"]["input"], {"command": "printf hello > out.txt"})
        self.assertEqual(lines[1]["type"], "response")
        self.assertEqual(lines[1]["id"], "1")

    def test_headless_serve_mode_accepts_claude_control_response(self) -> None:
        class _Runtime:
            def __init__(self) -> None:
                self.decisions: list[dict[str, str]] = []

            def decide_approval(self, approval_id, *, decision, decided_by, decision_note):
                self.decisions.append(
                    {
                        "approval_id": approval_id,
                        "decision": decision,
                        "decided_by": decided_by,
                        "decision_note": decision_note,
                    }
                )
                return {
                    "tool_events": [
                        ToolEvent(
                            name="approval_decision",
                            ok=True,
                            summary="approved approval_1",
                            payload={
                                "approval_id": approval_id,
                                "status": "approved",
                                "decision_type": decision,
                            },
                        )
                    ],
                }

        runtime = _Runtime()
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            json.dumps(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "success",
                        "request_id": "approval_1",
                        "response": {
                            "behavior": "allow",
                            "updatedInput": {},
                            "decisionClassification": "user_temporary",
                        },
                    },
                }
            )
            + "\n"
        )

        code = headless_stream_runtime_helpers.run_serve_loop(
            runtime,
            input_stream=stdin,
            output_stream=stdout,
            emit_json_line_fn=lambda stream, payload: print(json.dumps(payload), file=stream),
            request_id_for_payload_fn=lambda payload: (
                str(payload.get("id")) if "id" in payload else None
            ),
            resolve_serve_prompt_fn=lambda payload: str(payload["prompt"]),
            execute_prompt_fn=lambda *_args, **_kwargs: PromptResponse(
                user_text="",
                assistant_text="unused",
            ),
            prompt_response_to_dict_fn=lambda response: {
                "assistant_text": response.assistant_text,
                "tool_events": [item.to_dict() for item in response.tool_events],
            },
            exit_code_for_response_fn=lambda _response: 0,
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(runtime.decisions[0]["approval_id"], "approval_1")
        self.assertEqual(runtime.decisions[0]["decision"], "accept")
        self.assertEqual(runtime.decisions[0]["decided_by"], "headless")
        self.assertEqual(lines[0]["type"], "response")
        self.assertEqual(lines[0]["id"], "approval_1")
        self.assertEqual(lines[0]["response"]["tool_events"][0]["name"], "approval_decision")

    def test_build_headless_runtime_serve_does_not_resume_active_thread_by_default(self) -> None:
        with patch(
            "cli.agent_cli.headless.build_persistent_runtime", return_value=self.runtime
        ) as build_runtime:
            runtime = build_headless_runtime(
                runtime_policy=RuntimePolicy.normalized(),
                persistent=True,
                resume_thread_id=None,
            )

        self.assertIs(runtime, self.runtime)
        _, kwargs = build_runtime.call_args
        self.assertEqual(kwargs["resume_active_thread"], False)

    def test_headless_codex_sidecar_engine_uses_fake_sidecar(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        fake_codex_bin = Path(__file__).parent / "fixtures" / "fake_codex_sidecar.py"

        with patch.dict(
            os.environ,
            {"AGENTHUB_CODEX_SIDECAR_TEST_BIN": str(fake_codex_bin)},
            clear=False,
        ):
            code = main(
                [
                    "--headless",
                    "--engine",
                    "codex_sidecar",
                    "--prompt",
                    "hello sidecar",
                    "--json",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(payload["assistant_text"], "fake sidecar reply")
        self.assertEqual(payload["status"]["provider_source"], "codex_sidecar")
        self.assertEqual(payload["protocol_diagnostics"]["runtime_kernel"], "codex_sidecar")
        self.assertEqual(payload["turn_events"][0]["type"], "turn.started")
        self.assertEqual(payload["turn_events"][-1]["type"], "turn.completed")

    def test_headless_codex_sidecar_engine_rejects_resume_flags_before_starting(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        fake_codex_bin = Path(__file__).parent / "fixtures" / "fake_codex_sidecar.py"

        with patch.dict(
            os.environ,
            {"AGENTHUB_CODEX_SIDECAR_TEST_BIN": str(fake_codex_bin)},
            clear=False,
        ):
            code = main(
                [
                    "--headless",
                    "--engine",
                    "codex_sidecar",
                    "--resume",
                    "thread-old",
                    "--prompt",
                    "hello sidecar",
                    "--json",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("does not support resume flags yet", stderr.getvalue())

    def test_headless_live_weather_prompt_falls_back_to_web_search(self) -> None:
        runtime = AgentCliRuntime(
            agent=_LiveWebFallbackAgent(),
            tools=_HeadlessWebTools(),
        )
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "看看今天的北京天气", "--json"],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["commentary_text"], "这是实时信息查询，我先做网页搜索。")
        self.assertEqual([item["name"] for item in payload["tool_events"]], ["web_search"])
        self.assertEqual(payload["status"]["last_tool"], "web_search")
        self.assertEqual(payload["turn_events"][0]["type"], "turn.started")
        self.assertEqual(payload["turn_events"][-1]["type"], "turn.completed")
        completed_tool = next(
            event
            for event in payload["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
        )
        self.assertEqual(completed_tool["item"]["tool"], "web_search")
        self.assertEqual(
            completed_tool["item"]["result"]["structured_content"]["query"], "今天的北京天气"
        )
        self.assertIn("北京天气", payload["assistant_text"])
        self.assertIn("weather.example.com/beijing", payload["assistant_text"])

    def test_agent_with_planner_passes_original_live_web_prompt_through(self) -> None:
        planner = _CapturingPlanner()
        agent = _PlannerBackedAgent(planner)

        intent = agent.plan(
            "看看今天的北京天气", history=[], tool_executor=lambda text: ("", []), attachments=[]
        )

        self.assertEqual(intent.assistant_text, "planner reply")
        self.assertEqual(planner.calls, ["看看今天的北京天气"])

    def test_agent_with_planner_forwards_turn_event_callback(self) -> None:
        planner = _CapturingPlanner()
        agent = _PlannerBackedAgent(planner)

        def callback(event):
            return event

        intent = agent.plan(
            "请列出当前目录下的文件",
            history=[],
            tool_executor=lambda text: ("", []),
            attachments=[],
            turn_event_callback=callback,
        )

        self.assertEqual(intent.assistant_text, "planner reply")
        self.assertEqual(planner.calls, ["请列出当前目录下的文件"])
        self.assertEqual(planner.turn_event_callbacks, [callback])

    def test_runtime_backfills_only_missing_canonical_turn_events_after_live_stream(self) -> None:
        runtime = AgentCliRuntime(
            agent=_PlannerBackedAgent(_LiveReplayPlanner()),
            tools=_HeadlessTools(),
        )
        observed: list[dict[str, object]] = []
        runtime.turn_event_callback = lambda event: observed.append(dict(event))

        response = runtime.handle_prompt("请列出当前目录下的文件")

        self.assertEqual(response.turn_events[0]["type"], "turn.started")
        self.assertEqual(response.turn_events[-1]["type"], "turn.completed")
        self.assertEqual(
            [event["type"] for event in observed],
            [
                "turn.started",
                "item.completed",
                "item.started",
                "item.completed",
                "item.completed",
                "turn.completed",
            ],
        )
        self.assertEqual(sum(1 for event in observed if event["type"] == "turn.started"), 1)
        self.assertEqual(sum(1 for event in observed if event["type"] == "turn.completed"), 1)
        tool_started = next(
            event
            for event in observed
            if event["type"] == "item.started" and event["item"]["type"] == "mcp_tool_call"
        )
        self.assertEqual(tool_started["item"]["id"], "live_tool_0")
        tool_completed = next(
            event
            for event in observed
            if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
        )
        self.assertEqual(tool_completed["item"]["id"], "live_tool_0")
        agent_messages = [
            event["item"]["text"]
            for event in observed
            if event["type"] == "item.completed" and event["item"]["type"] == "agent_message"
        ]
        self.assertEqual(agent_messages, ["我先查看当前目录内容。", "当前目录下有 a.txt 和 src/。"])

    def test_headless_explicit_url_prompt_falls_back_to_web_fetch(self) -> None:
        runtime = AgentCliRuntime(
            agent=_LiveWebFallbackAgent(),
            tools=_HeadlessWebTools(),
        )
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", "看看 https://example.com/report", "--json"],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["commentary_text"], "这是实时信息查询，我先读取网页。")
        self.assertEqual([item["name"] for item in payload["tool_events"]], ["web_fetch"])
        completed_tool = next(
            event
            for event in payload["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
        )
        self.assertEqual(completed_tool["item"]["tool"], "web_fetch")
        self.assertEqual(
            completed_tool["item"]["result"]["structured_content"]["url"],
            "https://example.com/report",
        )
        self.assertIn("已读取网页：Example Report", payload["assistant_text"])
        self.assertIn("https://example.com/report", payload["assistant_text"])

    def test_headless_response_prefers_structured_web_search_result(self) -> None:
        runtime = AgentCliRuntime(
            agent=_LiveWebFallbackAgent(),
            tools=_HeadlessWebTools(),
        )
        runtime.agent.plan = (
            lambda text, history=None, *, tool_executor=None, attachments=None: AgentIntent(
                assistant_text="",
                commentary_text="",
                command_text="/web_search structured entry --limit 1",
                status_hint="tool",
            )
        )
        structured_result = _structured_tool_result(
            "web_search",
            "structured headless web summary",
            payload={"query": "structured entry"},
            arguments={"query": "structured entry", "limit": 1},
        )
        runtime.tools.web_search_result = lambda *args, **kwargs: structured_result

        stdout = io.StringIO()
        code = main(
            ["--headless", "--prompt", "structured prompt", "--json"],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["assistant_text"], "structured headless web summary")
        self.assertEqual([item["name"] for item in payload["tool_events"]], ["web_search"])
