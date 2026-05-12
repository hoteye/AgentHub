from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from cli.agent_cli.main import main as cli_main
from cli.agent_cli.models import AgentIntent, ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.tests.provider_boundary_test_support import provider_status_path_fields

ROOT = Path(__file__).resolve().parents[2]


def _event(
    name: str, ok: bool = True, summary: str = "ok", payload: dict | None = None
) -> ToolEvent:
    return ToolEvent(name=name, ok=ok, summary=summary, payload=payload or {})


class _FakeAgent:
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

    def plan(self, text, history=None, *, tool_executor=None, attachments=None):
        normalized = text.strip().lower()
        if normalized == "list current directory":
            return AgentIntent(
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
        return AgentIntent(assistant_text=f"echo: {text}")


class _FakeTools:
    def __init__(self) -> None:
        self.plugin_calls: list[tuple[str, str]] = []
        self.PROJECT_ROOT = str(ROOT / "_runtime_patch_preview_root")

    def shell(self, command: str) -> ToolEvent:
        return _event(
            "shell",
            True,
            f"shell ok: {command}",
            {
                "command": command,
                "returncode": 0,
                "stdout": "a.txt\nb.txt\n",
                "stderr": "",
                "duration_ms": 5,
            },
        )

    def apply_patch(self, patch_text: str) -> ToolEvent:
        return _event(
            "apply_patch",
            True,
            "apply_patch files=1",
            {
                "file_count": 1,
                "updated_count": 1,
                "changes": [{"path": "demo.txt", "change_type": "update"}],
                "patch": patch_text,
            },
        )

    def file_list(self, *, path=None, limit=50) -> ToolEvent:
        return _event(
            "file_list",
            True,
            "files=2",
            {
                "path": path or ".",
                "count": 2,
                "files": [{"path": "a.txt", "size": 3}, {"path": "b.py", "size": 5}],
            },
        )

    def file_search(self, query, *, path=None, limit=20) -> ToolEvent:
        return _event(
            "file_search",
            True,
            "file matches=1",
            {
                "query": query,
                "path": path or ".",
                "count": 1,
                "file_count": 1,
                "matches": [{"path": "b.py", "line": 3, "text": "hello"}],
            },
        )

    def file_read(self, path, *, max_chars=12000) -> ToolEvent:
        return _event(
            "file_read",
            True,
            "file loaded",
            {
                "path": path,
                "char_count": 12,
                "line_count": 2,
                "truncated": False,
                "text": "hello\nworld\n",
                "excerpt_lines": [{"line": 1, "text": "hello"}],
            },
        )

    def office_skills(self) -> ToolEvent:
        return _event(
            "office_skills",
            True,
            "office_skills=1",
            {"ok": True, "count": 1, "skills": [{"name": "read_docx_markdown"}]},
        )

    def office_run(self, skill_name, *, args=None) -> ToolEvent:
        return _event(
            "office_run",
            True,
            skill_name,
            {"ok": True, "skill_name": skill_name, "args": args or {}},
        )

    def capabilities(self):
        return {
            "ok": True,
            "tools": [
                {"name": "shell", "description": "shell"},
                {"name": "apply_patch", "description": "apply patch"},
                {"name": "file_list", "description": "file list"},
                {"name": "file_search", "description": "file search"},
                {"name": "file_read", "description": "file read"},
                {"name": "office_skills", "description": "office skills"},
                {"name": "office_run", "description": "office run"},
            ],
        }

    def list_plugins(self) -> ToolEvent:
        return _event(
            "plugins",
            True,
            "plugins=1",
            {"plugins": [{"name": "psbc_policy", "enabled": True, "version": "0.1.0"}]},
        )

    def run_plugin_command(self, name, arg_text, runtime):
        if name != "custom":
            return None
        self.plugin_calls.append((name, arg_text))
        return (
            "plugin handled",
            [_event("plugin_custom", True, "custom ok", {"arg_text": arg_text})],
        )


class _TuiRuntimeProbe:
    def __init__(self) -> None:
        self.runtime_policy_updates: list[dict[str, object]] = []

    def configure_runtime_policy(
        self,
        *,
        approval_policy=None,
        sandbox_mode=None,
        web_search_mode=None,
        network_access_enabled=None,
    ) -> dict[str, str]:
        self.runtime_policy_updates.append(
            {
                "approval_policy": approval_policy,
                "sandbox_mode": sandbox_mode,
                "web_search_mode": web_search_mode,
                "network_access_enabled": network_access_enabled,
            }
        )
        return {}


class RuntimeE2ETest(unittest.TestCase):
    @staticmethod
    def _fake_app_module(captured: dict[str, object]) -> ModuleType:
        module = ModuleType("cli.agent_cli.app")

        class FakeApp:
            def __init__(self, *, runtime=None, language=None, theme_id=None) -> None:
                captured["runtime"] = runtime
                captured["language"] = language
                captured["theme_id"] = theme_id

            def run(self) -> None:
                captured["ran"] = True

        module.AgentCliApp = FakeApp
        return module

    def _build_runtime(self):
        return AgentCliRuntime(agent=_FakeAgent(), tools=_FakeTools())

    def _build_approval_runtime(self):
        return AgentCliRuntime(
            agent=_FakeAgent(),
            tools=_FakeTools(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
        )

    def test_cli_main_tui_builds_runtime_with_requested_sandbox(self):
        captured: dict[str, object] = {}
        fake_runtime = object()

        with patch.dict(sys.modules, {"cli.agent_cli.app": self._fake_app_module(captured)}):
            with patch(
                "cli.agent_cli.runtime_factory.build_persistent_runtime", return_value=fake_runtime
            ) as build_runtime:
                code = cli_main(
                    [
                        "--sandbox-mode",
                        "danger-full-access",
                        "--web-search-mode",
                        "cached",
                        "--network-access",
                        "disabled",
                    ],
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )

        self.assertEqual(code, 0)
        self.assertIs(captured["runtime"], fake_runtime)
        self.assertTrue(captured["ran"])
        _, kwargs = build_runtime.call_args
        policy = kwargs["runtime_policy"]
        self.assertEqual(policy.approval_policy, "never")
        self.assertEqual(policy.sandbox_mode, "danger-full-access")
        self.assertEqual(policy.web_search_mode, "cached")
        self.assertEqual(policy.network_access_enabled, False)
        self.assertFalse(kwargs["resume_active_thread"])

    def test_cli_main_tui_applies_policy_to_injected_runtime(self):
        captured: dict[str, object] = {}
        runtime = _TuiRuntimeProbe()

        with patch.dict(sys.modules, {"cli.agent_cli.app": self._fake_app_module(captured)}):
            code = cli_main(
                ["--approval-policy", "on-request", "--sandbox-mode", "danger-full-access"],
                runtime=runtime,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

        self.assertEqual(code, 0)
        self.assertIs(captured["runtime"], runtime)
        self.assertTrue(captured["ran"])
        self.assertEqual(len(runtime.runtime_policy_updates), 1)
        self.assertEqual(runtime.runtime_policy_updates[0]["approval_policy"], "on-request")
        self.assertEqual(runtime.runtime_policy_updates[0]["sandbox_mode"], "danger-full-access")

    def test_provider_and_tools_commands(self):
        runtime = self._build_approval_runtime()

        provider_response = runtime.handle_prompt("/provider")
        tools_response = runtime.handle_prompt("/tools")

        self.assertIn("provider status", provider_response.assistant_text)
        self.assertIn("tools=7", tools_response.assistant_text)
        self.assertIn("office_run", tools_response.assistant_text)

    def test_apply_patch_command_routes_through_runtime(self):
        runtime = self._build_runtime()

        response = runtime.handle_prompt(
            "/apply_patch '*** Begin Patch\n*** Add File: demo.txt\n+hello\n*** End Patch'"
        )

        self.assertEqual(
            [event.name for event in response.tool_events], ["patch_approval_requested"]
        )
        self.assertTrue(response.tool_events[0].payload["approval_id"].startswith("approval_"))

    def test_patch_approval_commands_execute_after_manual_approval(self):
        runtime = self._build_runtime()

        request = runtime.handle_prompt(
            "/apply_patch '*** Begin Patch\n*** Add File: demo.txt\n+hello\n*** End Patch'"
        )
        approval_id = request.tool_events[0].payload["approval_id"]

        approvals = runtime.handle_prompt("/approvals --status pending")
        approved = runtime.handle_prompt(f"/approve {approval_id} --note ship-it")

        self.assertEqual([event.name for event in approvals.tool_events], ["approval_list"])
        self.assertEqual(
            [event.name for event in approved.tool_events], ["approval_decision", "apply_patch"]
        )
        self.assertEqual(approved.tool_events[-1].payload["file_count"], 1)

    def test_file_commands_route_through_runtime(self):
        runtime = self._build_runtime()

        list_response = runtime.handle_prompt("/file_list")
        search_response = runtime.handle_prompt("/file_search hello --path src")
        read_response = runtime.handle_prompt("/file_read README.md --max-chars 100")

        self.assertEqual([event.name for event in list_response.tool_events], ["file_list"])
        self.assertEqual([event.name for event in search_response.tool_events], ["file_search"])
        self.assertEqual([event.name for event in read_response.tool_events], ["file_read"])
        self.assertEqual(read_response.tool_events[0].payload["path"], "README.md")

    def test_plugins_command_lists_enabled_plugins(self):
        runtime = self._build_runtime()

        response = runtime.handle_prompt("/plugins")

        self.assertEqual([event.name for event in response.tool_events], ["plugins"])
        self.assertIn("psbc_policy", response.assistant_text)

    def test_plan_switches_to_plan_mode(self):
        runtime = self._build_runtime()

        response = runtime.handle_prompt("/plan")

        self.assertEqual(response.tool_events, [])
        self.assertEqual(runtime.collaboration_mode, "plan")
        self.assertIn("switched to Plan mode", response.assistant_text)

    def test_natural_language_shell_request_uses_agent_planner(self):
        runtime = self._build_approval_runtime()

        response = runtime.handle_prompt("list current directory")

        self.assertEqual([event.name for event in response.tool_events], ["shell"])
        self.assertIn("Run shell command.", response.assistant_text)
        self.assertEqual(response.tool_events[0].payload["command"], "Get-ChildItem -Force")

    def test_office_commands_run_through_runtime(self):
        runtime = self._build_runtime()

        skills_response = runtime.handle_prompt("show office skills")
        run_response = runtime.handle_prompt("run office markdown")

        self.assertEqual([event.name for event in skills_response.tool_events], ["office_skills"])
        self.assertEqual([event.name for event in run_response.tool_events], ["office_run"])
        self.assertEqual(run_response.tool_events[0].payload["skill_name"], "read_docx_markdown")
        self.assertEqual(run_response.tool_events[0].payload["args"]["path"], "C:/tmp/demo.docx")

    def test_plugin_command_routes_through_plugin_handler(self):
        runtime = self._build_runtime()

        response = runtime.handle_prompt("/custom value")

        self.assertEqual([event.name for event in response.tool_events], ["plugin_custom"])
        self.assertEqual(runtime.tools.plugin_calls, [("custom", "value")])

    def test_unknown_command_reports_help_hint(self):
        runtime = self._build_runtime()

        response = runtime.handle_prompt("/not_exists")

        self.assertEqual(response.tool_events, [])
        self.assertIn("/not_exists", response.assistant_text)
        self.assertIn("/help", response.assistant_text)
