from __future__ import annotations

import io
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.app_server import AgentCliAppServer
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.main import main
from cli.agent_cli.models import AgentIntent, PromptResponse
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.tools import ToolRegistry
from workers.actions import ActionResult

ROOT = Path(__file__).resolve().parents[2]


class _E2ECompatRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_ready": "true",
                "provider_name": "compat",
                "provider_model": "compat-model",
            }

    def __init__(self) -> None:
        self.agent = self._Agent()
        self.turn_event_callback = None
        self.thread_id = "thread_claude_alignment_e2e"
        self.runtime_policy_updates: list[dict[str, object]] = []
        self.prompts: list[str] = []

    def configure_runtime_policy(
        self,
        *,
        approval_policy=None,
        sandbox_mode=None,
        web_search_mode=None,
        network_access_enabled=None,
    ) -> None:
        self.runtime_policy_updates.append(
            {
                "approval_policy": approval_policy,
                "sandbox_mode": sandbox_mode,
                "web_search_mode": web_search_mode,
                "network_access_enabled": network_access_enabled,
            }
        )

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        self.prompts.append(text)
        if text == "/mcp list":
            assistant_text = "mcp servers: 0"
        elif text == "/plugins":
            assistant_text = "plugins: 0"
        else:
            assistant_text = f"echo: {text}"

        streamed_events = [
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "msg_1", "type": "agent_message", "text": assistant_text},
            },
            {"type": "turn.completed"},
        ]
        callback = getattr(self, "turn_event_callback", None)
        if callable(callback):
            for event in streamed_events:
                callback(dict(event))
        return PromptResponse(
            user_text=text,
            assistant_text=assistant_text,
            status=self.agent.provider_status(),
            turn_events=[dict(event) for event in streamed_events],
        )


class _CapturingActionWorker:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def execute(self, request):
        payload = dict(request) if isinstance(request, dict) else request.to_dict()
        self.requests.append(payload)
        return ActionResult(
            ok=True,
            action=str(payload.get("action") or ""),
            summary="ok",
            output={"echo": True},
            request_id=str(payload.get("request_id") or "") or None,
            correlation_id=str(payload.get("correlation_id") or "") or None,
            run_id=str(payload.get("run_id") or "") or None,
            agent_id=str(payload.get("agent_id") or "") or None,
        )


class _AppServerRuntime:
    def __init__(self) -> None:
        self.agent = type(
            "Agent",
            (),
            {
                "provider_status": staticmethod(
                    lambda: {
                        "platform_family": "linux",
                        "platform_os": "linux",
                        "shell_kind": "bash",
                        "provider_label": "test-provider",
                    }
                )
            },
        )()

    @staticmethod
    def has_active_run() -> bool:
        return False


class ClaudeAlignmentE2ESmokeTest(unittest.TestCase):
    @staticmethod
    def _copy_demo_plugin(dst_root: Path) -> Path:
        source = ROOT / "plugins" / "demo_plugin"
        dst = dst_root / "demo_plugin"
        shutil.copytree(source, dst)
        return dst

    def test_output_format_alias_and_stream_json_contract_end_to_end(self) -> None:
        runtime = _E2ECompatRuntime()
        stdout_json = io.StringIO()
        stderr_json = io.StringIO()
        code_json = main(
            ["--headless", "--prompt", "hello", "--output-format", "json"],
            runtime=runtime,
            stdout=stdout_json,
            stderr=stderr_json,
        )
        self.assertEqual(code_json, 0)
        self.assertEqual(stderr_json.getvalue(), "")
        payload = json.loads(stdout_json.getvalue())
        self.assertEqual(payload["assistant_text"], "echo: hello")

        stdout_alias = io.StringIO()
        stderr_alias = io.StringIO()
        code_alias = main(
            ["--headless", "--prompt", "hello", "--json"],
            runtime=_E2ECompatRuntime(),
            stdout=stdout_alias,
            stderr=stderr_alias,
        )
        self.assertEqual(code_alias, 0)
        self.assertEqual(stderr_alias.getvalue(), "")
        alias_payload = json.loads(stdout_alias.getvalue())
        self.assertEqual(alias_payload["assistant_text"], "echo: hello")

        stdout_stream = io.StringIO()
        stderr_stream = io.StringIO()
        code_stream = main(
            ["--headless", "--prompt", "hello", "--output-format", "stream-json"],
            runtime=_E2ECompatRuntime(),
            stdout=stdout_stream,
            stderr=stderr_stream,
        )
        self.assertEqual(code_stream, 0)
        self.assertEqual(stderr_stream.getvalue(), "")
        events = [
            json.loads(line) for line in stdout_stream.getvalue().splitlines() if line.strip()
        ]
        self.assertEqual(events[0]["type"], "thread.started")
        self.assertEqual(events[0]["event_type"], "session")
        self.assertIn("turn", {event.get("event_type") for event in events})

    def test_permission_mode_explicit_axes_precedence_end_to_end(self) -> None:
        runtime = _E2ECompatRuntime()
        code = main(
            [
                "--headless",
                "--prompt",
                "policy test",
                "--permission-mode",
                "plan",
                "--sandbox-mode",
                "workspace-write",
                "--network-access",
                "disabled",
            ],
            runtime=runtime,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        self.assertEqual(code, 0)
        self.assertGreaterEqual(len(runtime.runtime_policy_updates), 1)
        latest = runtime.runtime_policy_updates[-1]
        self.assertEqual(latest["approval_policy"], "on-request")
        self.assertEqual(latest["sandbox_mode"], "workspace-write")
        self.assertEqual(latest["network_access_enabled"], False)

    def test_top_level_subcommands_keep_slash_semantics_end_to_end(self) -> None:
        mcp_runtime = _E2ECompatRuntime()
        mcp_stdout = io.StringIO()
        mcp_code = main(
            ["mcp", "list"], runtime=mcp_runtime, stdout=mcp_stdout, stderr=io.StringIO()
        )
        self.assertEqual(mcp_code, 0)
        self.assertEqual(mcp_stdout.getvalue().strip(), "mcp servers: 0")
        self.assertIn("/mcp list", mcp_runtime.prompts)

        mcp_headless_stdout = io.StringIO()
        mcp_headless_code = main(
            ["--headless", "--prompt", "/mcp list"],
            runtime=_E2ECompatRuntime(),
            stdout=mcp_headless_stdout,
            stderr=io.StringIO(),
        )
        self.assertEqual(mcp_headless_code, 0)
        self.assertEqual(mcp_headless_stdout.getvalue().strip(), "mcp servers: 0")

        plugin_runtime = _E2ECompatRuntime()
        plugin_stdout = io.StringIO()
        plugin_code = main(
            ["plugin", "list"], runtime=plugin_runtime, stdout=plugin_stdout, stderr=io.StringIO()
        )
        self.assertEqual(plugin_code, 0)
        self.assertEqual(plugin_stdout.getvalue().strip(), "plugins: 0")
        self.assertIn("/plugins", plugin_runtime.prompts)

        plugin_headless_stdout = io.StringIO()
        plugin_headless_code = main(
            ["--headless", "--prompt", "/plugins"],
            runtime=_E2ECompatRuntime(),
            stdout=plugin_headless_stdout,
            stderr=io.StringIO(),
        )
        self.assertEqual(plugin_headless_code, 0)
        self.assertEqual(plugin_headless_stdout.getvalue().strip(), "plugins: 0")

    def test_plugin_marketplace_lifecycle_success_and_failure_paths_end_to_end(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            updated_source = root / "updated_demo_plugin"
            shutil.copytree(source_dir, updated_source)

            reference_home = root / ".agent_cli"
            tools = ToolRegistry()
            tools._plugin_manager = PluginManager(
                plugin_root=root / "plugins_target",
                state_path=root / "plugin_state.json",
                reference_home=reference_home,
                config_path=reference_home / "config.toml",
            )
            runtime = AgentCliRuntime(tools=tools)

            add = runtime.handle_prompt(
                f'/plugin_marketplace add demo_plugin@test "{source_dir}" scope project'
            )
            self.assertTrue(add.tool_events[0].ok)
            self.assertEqual(add.tool_events[0].name, "plugin_marketplace_add")

            update = runtime.handle_prompt(
                f'/plugin_marketplace update demo_plugin@test path "{updated_source}" scope user'
            )
            self.assertTrue(update.tool_events[0].ok)
            self.assertEqual(update.tool_events[0].name, "plugin_marketplace_update")

            missing_remove = runtime.handle_prompt("/plugin_marketplace remove missing@test")
            self.assertFalse(missing_remove.tool_events[0].ok)
            self.assertEqual(missing_remove.tool_events[0].name, "plugin_marketplace_remove")
            self.assertIn("not found", missing_remove.assistant_text.lower())

            remove = runtime.handle_prompt("/plugin_marketplace remove demo_plugin@test")
            self.assertTrue(remove.tool_events[0].ok)
            self.assertEqual(remove.tool_events[0].name, "plugin_marketplace_remove")

    def test_plugin_lifecycle_can_be_triggered_by_natural_language_end_to_end(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            reference_home = root / ".agent_cli"
            tools = ToolRegistry()
            tools._plugin_manager = PluginManager(
                plugin_root=root / "plugins_target",
                state_path=root / "plugin_state.json",
                reference_home=reference_home,
                config_path=reference_home / "config.toml",
            )

            class _NaturalLanguagePluginAgent:
                @staticmethod
                def provider_status() -> dict[str, str]:
                    return {
                        "provider_ready": "true",
                        "provider_name": "nl-e2e",
                        "provider_model": "rule-router",
                    }

                def plan(
                    self,
                    text,
                    history=None,
                    *,
                    tool_executor=None,
                    attachments=None,
                    input_items=None,
                ):
                    del history, tool_executor, attachments, input_items
                    normalized = str(text or "").strip().lower()
                    if "安装" in str(text or "") or "install" in normalized:
                        return AgentIntent(command_text=f'/plugin_install "{source_dir}"')
                    if (
                        "禁用" in str(text or "") and "全部" in str(text or "")
                    ) or "disable all" in normalized:
                        return AgentIntent(command_text="/plugin_disable --all")
                    if (
                        "卸载" in str(text or "")
                        or "remove" in normalized
                        or "uninstall" in normalized
                    ):
                        return AgentIntent(command_text="/plugin_remove demo_plugin")
                    return AgentIntent(assistant_text="无法识别请求")

            runtime = AgentCliRuntime(tools=tools, agent=_NaturalLanguagePluginAgent())

            install = runtime.handle_prompt("请安装 demo 插件")
            self.assertTrue(install.tool_events[0].ok)
            self.assertEqual(install.tool_events[0].name, "plugin_install")

            ping = runtime.handle_prompt("/demo_ping hello")
            self.assertTrue(ping.tool_events and ping.tool_events[0].ok)

            disable_all = runtime.handle_prompt("请禁用全部插件")
            self.assertTrue(disable_all.tool_events[0].ok)
            self.assertEqual(disable_all.tool_events[0].name, "plugin_disable")
            self.assertGreaterEqual(
                int(disable_all.tool_events[0].payload.get("disabled_count") or 0), 1
            )

            ping_after_disable = runtime.handle_prompt("/demo_ping hello")
            self.assertEqual(ping_after_disable.tool_events, [])
            self.assertIn("未知命令: /demo_ping", ping_after_disable.assistant_text)

            remove = runtime.handle_prompt("请卸载 demo 插件")
            self.assertTrue(remove.tool_events[0].ok)
            self.assertEqual(remove.tool_events[0].name, "plugin_remove")

    def test_busy_queue_and_prompt_history_contract_end_to_end(self) -> None:
        runtime = AgentCliRuntime()
        runtime._pending_steer_enabled = True
        run_token = runtime._begin_run("active run")
        try:
            steer = runtime.steer_active_run("follow-up while busy")
            self.assertTrue(steer["accepted"])
            self.assertFalse(steer["fallback_queue"])
            pending = runtime.take_pending_steer_input_items()
            self.assertEqual(len(pending), 1)
            self.assertIn("follow-up while busy", pending[0]["content"][0]["text"])
        finally:
            runtime._finish_run(run_token)

        with TemporaryDirectory() as tmpdir:
            history_root = Path(tmpdir)
            from cli.agent_cli.prompt_history import PromptHistoryStore

            store = PromptHistoryStore(history_root)
            store.append("/provider")
            store.append("normal prompt 1")
            store.append("/tools")
            store.append("normal prompt 2")

            app = AgentCliApp(runtime=AgentCliRuntime(), prompt_history_home=history_root)
            composer = type("Composer", (), {"text": "", "cursor_pos": 0})()
            applied: list[str] = []

            app.query_one = lambda *_args, **_kwargs: composer  # type: ignore[method-assign]

            def _apply(value: str) -> None:
                composer.text = value
                composer.cursor_pos = len(value)
                applied.append(value)

            app._apply_history_prompt = _apply  # type: ignore[method-assign]
            self.assertTrue(app.browse_prompt_history(-1))
            self.assertEqual(applied[-1], "normal prompt 2")
            self.assertTrue(app.browse_prompt_history(-1))
            self.assertEqual(applied[-1], "/tools")
            self.assertTrue(app.browse_prompt_history(-1))
            self.assertEqual(applied[-1], "normal prompt 1")
            self.assertTrue(app.browse_prompt_history(-1))
            self.assertEqual(applied[-1], "/provider")
            self.assertFalse(app.browse_prompt_history(-1))

    def test_multi_agent_projection_keeps_trace_ids_end_to_end(self) -> None:
        worker = _CapturingActionWorker()
        stdout = io.StringIO()
        server = AgentCliAppServer(
            runtime=_AppServerRuntime(),
            action_worker=worker,
            stdin=io.StringIO(),
            stdout=stdout,
        )
        server.state.initialized = True
        server.state.initialized_notification_received = True

        server._handle_line(
            json.dumps(
                {
                    "id": "action-e2e",
                    "method": "action/execute",
                    "params": {
                        "action": "noop",
                        "parameters": {"mode": "dry_run"},
                        "requestId": "req-e2e-1",
                        "runId": "run-e2e-1",
                        "agentId": "agent-e2e-1",
                    },
                }
            )
        )
        responses = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        result = next(item for item in responses if item.get("id") == "action-e2e")
        self.assertEqual(worker.requests[0]["request_id"], "req-e2e-1")
        self.assertEqual(worker.requests[0]["run_id"], "run-e2e-1")
        self.assertEqual(worker.requests[0]["agent_id"], "agent-e2e-1")
        action_result = result["result"]["actionResult"]
        self.assertEqual(action_result["request_id"], "req-e2e-1")
        self.assertEqual(action_result["run_id"], "run-e2e-1")
        self.assertEqual(action_result["agent_id"], "agent-e2e-1")
