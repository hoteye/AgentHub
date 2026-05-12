from __future__ import annotations

import inspect
import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import cli.agent_cli.tools as tools_module
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_paths import PROJECT_ROOT_ENV
from cli.agent_cli.tools import ToolRegistry
from cli.agent_cli.tools_core.browser_action_normalization import (
    browser_event_name,
    browser_request_error,
    normalize_browser_payload,
)
from cli.agent_cli.tools_core.project_loader import dumps_pretty, find_project_root, json_safe
from cli.agent_cli.tools_core.registry import (
    PluginBridge,
    app_connector_contract_item,
    build_capabilities_payload,
    gateway_connector_contract_item,
    runtime_registry_app_connector_entries,
    runtime_registry_mcp_server_entries,
)


class _FakeScalar:
    def __init__(self, value: int) -> None:
        self._value = value

    def item(self) -> int:
        return self._value


class _FakePluginManager:
    def __init__(self) -> None:
        self.enabled: dict[str, bool] = {}

    def tool_specs(self) -> list[dict[str, Any]]:
        return [{"name": "fake_tool"}]

    def command_specs(self) -> list[dict[str, str]]:
        return [{"name": "fake_cmd", "description": "fake"}]

    def execute_command(
        self, name: str, arg_text: str, runtime: Any
    ) -> tuple[str, list[ToolEvent]] | None:
        if name != "fake_cmd":
            return None
        event = ToolEvent(name="fake_tool", ok=True, summary="ok", payload={"arg_text": arg_text})
        return ("command ok", [event])

    def invoke_tool(self, name: str, *args: Any, **kwargs: Any) -> ToolEvent:
        return ToolEvent(
            name=name, ok=True, summary="invoked", payload={"args": list(args), "kwargs": kwargs}
        )

    def list_plugins(self) -> list[dict[str, Any]]:
        return [{"name": "fake"}]

    def enable_plugin(self, plugin_name: str) -> dict[str, Any]:
        self.enabled[plugin_name] = True
        return {"ok": True, "plugin_name": plugin_name}

    def disable_plugin(self, plugin_name: str) -> dict[str, Any]:
        self.enabled[plugin_name] = False
        return {"ok": True, "plugin_name": plugin_name}

    def reload(self) -> None:
        return None

    def install_plugin(
        self, path: str, *, replace: bool = False, scope: str = "user"
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "path": path,
            "replace": bool(replace),
            "scope": str(scope),
            "plugin_name": "fake",
        }

    def remove_plugin(self, plugin_name: str) -> dict[str, Any]:
        return {"ok": True, "plugin_name": plugin_name}

    def workspace_trust_level(self) -> str:
        return "untrusted"

    def configured_mcp_servers(self) -> dict[str, dict[str, Any]]:
        return {"sample": {"url": "https://example.com/mcp"}}

    def effective_app_connectors(self) -> list[dict[str, str]]:
        return [{"name": "demo", "source": "plugin"}]


class _FakeShellSessions:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def start_session(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("start_session", (), kwargs))
        return {"session_id": "s-1", "phase": "started"}

    def start_session_result(self, **kwargs: Any) -> CommandExecutionResult:
        self.calls.append(("start_session_result", (), kwargs))
        return CommandExecutionResult(assistant_text="started")

    def write_stdin(self, *args: Any, **kwargs: Any) -> ToolEvent:
        self.calls.append(("write_stdin", args, kwargs))
        return ToolEvent(
            name="shell_write_stdin", ok=True, summary="ok", payload={"session_id": args[0]}
        )

    def write_stdin_result(self, *args: Any, **kwargs: Any) -> CommandExecutionResult:
        self.calls.append(("write_stdin_result", args, kwargs))
        return CommandExecutionResult(assistant_text="write")

    def terminate(self, *args: Any, **kwargs: Any) -> ToolEvent:
        self.calls.append(("terminate", args, kwargs))
        return ToolEvent(
            name="shell_terminate", ok=True, summary="ok", payload={"session_id": args[0]}
        )

    def terminate_result(self, *args: Any, **kwargs: Any) -> CommandExecutionResult:
        self.calls.append(("terminate_result", args, kwargs))
        return CommandExecutionResult(assistant_text="terminated")

    def subscribe(self, *args: Any, **kwargs: Any) -> ToolEvent:
        self.calls.append(("subscribe", args, kwargs))
        return ToolEvent(
            name="shell_subscribe", ok=True, summary="ok", payload={"session_id": args[0]}
        )

    def subscribe_result(self, *args: Any, **kwargs: Any) -> CommandExecutionResult:
        self.calls.append(("subscribe_result", args, kwargs))
        return CommandExecutionResult(assistant_text="subscribed")


class ToolsCoreSplitTest(unittest.TestCase):
    def test_browser_action_normalization_helpers_cover_target_resolution_and_request_validation(
        self,
    ) -> None:
        class _FakeBrowserClient:
            def status(self):
                return type("Status", (), {"active_tab": "tab-active"})()

            def tabs(self, profile=None):
                return [type("Tab", (), {"tab_id": "tab-active"})()]

        client = _FakeBrowserClient()

        normalized_snapshot = normalize_browser_payload(
            {
                "ok": True,
                "text": "Example snapshot text for normalization",
                "refs": [{"ref": "r1"}],
            },
            client=client,
            action="snapshot",
            profile="review",
            requested_target=None,
            requested_url="https://example.com/report",
            requested_ref=None,
        )
        self.assertEqual(normalized_snapshot["target_id"], "tab-active")
        self.assertEqual(normalized_snapshot["profile"], "review")
        self.assertEqual(normalized_snapshot["ref"], "r1")
        self.assertEqual(normalized_snapshot["ref_count"], 1)
        self.assertEqual(normalized_snapshot["url"], "https://example.com/report")
        self.assertIn("preview", normalized_snapshot)

        normalized_dialog = normalize_browser_payload(
            {
                "ok": True,
                "artifact": {
                    "path": "/tmp/capture.png",
                    "content_type": "image/png",
                    "size_bytes": 42,
                    "kind": "screenshot",
                },
            },
            client=client,
            action="dialog",
            profile=None,
            requested_target="tab-dialog",
            requested_url=None,
            requested_ref=None,
            requested_paths=None,
            requested_input_ref="input-1",
            requested_accept=True,
            requested_prompt_text="approved",
        )
        self.assertEqual(normalized_dialog["target_id"], "tab-dialog")
        self.assertEqual(normalized_dialog["input_ref"], "input-1")
        self.assertTrue(normalized_dialog["accept"])
        self.assertEqual(normalized_dialog["prompt_text"], "approved")
        self.assertEqual(normalized_dialog["path"], "/tmp/capture.png")
        self.assertEqual(normalized_dialog["content_type"], "image/png")
        self.assertEqual(normalized_dialog["size"], 42)
        self.assertEqual(normalized_dialog["format"], "png")

        self.assertEqual(browser_event_name("snapshot"), "browser_snapshot")
        self.assertEqual(browser_event_name("requests"), "browser_console")
        self.assertEqual(
            browser_request_error(
                action="act",
                kind="scroll-into-view",
                ref=None,
                start_ref=None,
                end_ref=None,
                width=None,
                height=None,
            ),
            "action requires ref",
        )
        self.assertEqual(
            browser_request_error(
                action="act",
                kind="resize",
                ref=None,
                start_ref=None,
                end_ref=None,
                width=0,
                height=50,
            ),
            "resize requires width and height",
        )

    def test_plugin_bridge_delegates_to_plugin_manager(self) -> None:
        manager = _FakePluginManager()
        bridge = PluginBridge(manager)

        self.assertEqual(bridge.tool_specs()[0]["name"], "fake_tool")
        self.assertEqual(bridge.command_specs()[0]["name"], "fake_cmd")

        command_result = bridge.execute_command("fake_cmd", "--x", runtime=object())
        self.assertIsNotNone(command_result)
        assert command_result is not None
        self.assertEqual(command_result[0], "command ok")
        self.assertEqual(command_result[1][0].name, "fake_tool")

        command_result_structured = bridge.execute_command_result(
            "fake_cmd", "--x", runtime=object()
        )
        self.assertIsInstance(command_result_structured, CommandExecutionResult)
        assert command_result_structured is not None
        self.assertEqual(command_result_structured.assistant_text, "command ok")
        self.assertEqual(command_result_structured.tool_events[0].name, "fake_tool")
        self.assertEqual(command_result_structured.item_events[0]["type"], "item.started")

        invoke_event = bridge.invoke_tool("fake_tool", 1, b=2)
        self.assertTrue(invoke_event.ok)
        self.assertEqual(invoke_event.payload["kwargs"]["b"], 2)

        invoke_result = bridge.invoke_tool_result("fake_tool", 1, b=2)
        self.assertIsInstance(invoke_result, CommandExecutionResult)
        self.assertEqual(invoke_result.tool_events[0].name, "fake_tool")
        self.assertEqual(invoke_result.item_events[0]["item"]["type"], "mcp_tool_call")
        self.assertEqual(invoke_result.item_events[-1]["item"]["tool"], "fake_tool")

        list_event = bridge.list_plugins()
        self.assertTrue(list_event.ok)
        self.assertEqual(list_event.name, "plugins")
        self.assertIn("loaded 1 plugins", list_event.summary)

        enable_event = bridge.enable_plugin("demo")
        disable_event = bridge.disable_plugin("demo")
        install_event = bridge.install_plugin("C:/tmp/demo.zip", replace=True)
        remove_event = bridge.remove_plugin("demo")
        reload_event = bridge.reload_plugins()

        self.assertTrue(enable_event.ok)
        self.assertTrue(disable_event.ok)
        self.assertTrue(install_event.ok)
        self.assertTrue(remove_event.ok)
        self.assertTrue(reload_event.ok)

    def test_project_loader_helpers_are_json_safe_and_find_root(self) -> None:
        payload = {
            "path": Path("C:/tmp/demo.txt"),
            "set_values": {3, 1, 2},
            "scalar": _FakeScalar(7),
        }
        safe = json_safe(payload)
        self.assertEqual(safe["path"], "C:\\tmp\\demo.txt")
        self.assertEqual(safe["set_values"], [1, 2, 3])
        self.assertEqual(safe["scalar"], 7)
        rendered = dumps_pretty(payload)
        self.assertIn('"scalar": 7', rendered)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "plugins").mkdir()
            (root / "tools").mkdir()
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            with patch.dict(
                "os.environ",
                {PROJECT_ROOT_ENV: str(root / "_nonexistent_runtime_root")},
                clear=False,
            ):
                found = find_project_root(nested)
            self.assertEqual(found, root)

    def test_tool_registry_prefers_structured_bridge_results_when_available(self) -> None:
        registry = object.__new__(ToolRegistry)
        workspace_root = Path("/tmp/workspace")

        def workspace_root_factory() -> Path:
            return workspace_root

        registry.workspace_root = workspace_root_factory  # type: ignore[method-assign]

        expected_apply = CommandExecutionResult(assistant_text="apply structured")
        expected_list = CommandExecutionResult(assistant_text="file list structured")
        expected_search = CommandExecutionResult(assistant_text="file search structured")
        expected_read = CommandExecutionResult(assistant_text="file read structured")

        with patch.object(
            tools_module.apply_patch_bridge_module,
            "execute_apply_patch_result",
            return_value=expected_apply,
            create=True,
        ):
            result = ToolRegistry.apply_patch_result(registry, "*** Begin Patch\n*** End Patch")
            self.assertIs(result, expected_apply)

        with patch.object(
            tools_module.file_tools_bridge_module,
            "file_list_result",
            return_value=expected_list,
            create=True,
        ):
            result = ToolRegistry.file_list_result(registry, path=".", limit=5)
            self.assertIs(result, expected_list)

        with patch.object(
            tools_module.file_tools_bridge_module,
            "file_search_result",
            return_value=expected_search,
            create=True,
        ):
            result = ToolRegistry.file_search_result(registry, "needle", path="src", limit=3)
            self.assertIs(result, expected_search)

        with patch.object(
            tools_module.file_tools_bridge_module,
            "file_read_result",
            return_value=expected_read,
            create=True,
        ):
            result = ToolRegistry.file_read_result(registry, "README.md", max_chars=120)
            self.assertIs(result, expected_read)

    def test_tool_registry_binds_library_methods_from_runtime_with_compatible_signatures(
        self,
    ) -> None:
        browser_params = inspect.signature(ToolRegistry.browser).parameters
        self.assertEqual(list(browser_params)[:2], ["self", "action"])
        self.assertIn("transport", browser_params)

        read_result_params = inspect.signature(ToolRegistry.policy_doc_read_result).parameters
        self.assertEqual(list(read_result_params)[:2], ["self", "doc_id"])
        self.assertIn("max_chars", read_result_params)

    def test_tool_registry_claude_write_guard_requires_read_before_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            target = workspace_root / "demo.txt"
            target.write_text("before\n", encoding="utf-8")
            registry = ToolRegistry()
            registry.set_workspace_root(workspace_root)

            patch_text = json.dumps(
                {
                    "operation": "file_write",
                    "file_path": "demo.txt",
                    "content": "after\n",
                    "source_tool_name": "Write",
                    "guard_profile": "claude_write",
                }
            )

            blocked = registry.apply_patch_result(patch_text)
            self.assertFalse(blocked.tool_events[-1].ok)
            self.assertIn(
                "reading the current file first",
                str(blocked.tool_events[-1].payload.get("error") or ""),
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "before\n")

            read_result = registry.read_file_result(str(target), offset=1, limit=20)
            self.assertTrue(read_result.tool_events[-1].ok)

            allowed = registry.apply_patch_result(patch_text)
            self.assertTrue(allowed.tool_events[-1].ok)
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")

    def test_tool_registry_claude_write_guard_rejects_stale_overwrite_after_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            target = workspace_root / "demo.txt"
            target.write_text("before\n", encoding="utf-8")
            registry = ToolRegistry()
            registry.set_workspace_root(workspace_root)

            read_result = registry.read_file_result(str(target), offset=1, limit=20)
            self.assertTrue(read_result.tool_events[-1].ok)
            target.write_text("external change\n", encoding="utf-8")

            patch_text = json.dumps(
                {
                    "operation": "file_write",
                    "file_path": "demo.txt",
                    "content": "after\n",
                    "source_tool_name": "Write",
                    "guard_profile": "claude_write",
                }
            )

            blocked = registry.apply_patch_result(patch_text)
            self.assertFalse(blocked.tool_events[-1].ok)
            self.assertIn(
                "changed since it was read", str(blocked.tool_events[-1].payload.get("error") or "")
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "external change\n")

    def test_tool_registry_claude_write_guard_allows_new_file_without_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            registry = ToolRegistry()
            registry.set_workspace_root(workspace_root)

            patch_text = json.dumps(
                {
                    "operation": "file_write",
                    "file_path": "new.txt",
                    "content": "created\n",
                    "source_tool_name": "Write",
                    "guard_profile": "claude_write",
                }
            )

            result = registry.apply_patch_result(patch_text)
            self.assertTrue(result.tool_events[-1].ok)
            self.assertEqual((workspace_root / "new.txt").read_text(encoding="utf-8"), "created\n")

    def test_runtime_bootstrap_wires_model_facing_apply_patch_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)

            class _RuntimeAgent:
                @staticmethod
                def provider_status() -> dict[str, str]:
                    return {
                        "provider_ready": "true",
                        "provider_name": "demo",
                        "provider_model": "demo-model",
                    }

                @staticmethod
                def available_providers() -> list[dict[str, Any]]:
                    return []

                @staticmethod
                def available_models(provider_name=None) -> list[dict[str, Any]]:
                    return []

            runtime = AgentCliRuntime(agent=_RuntimeAgent())
            runtime.set_cwd(workspace_root)

            patch_text = "*** Begin Patch\n*** Add File: demo.txt\n+hello\n*** End Patch"
            blocked = runtime.tools.apply_patch_result(patch_text)

            self.assertEqual(
                [event.name for event in blocked.tool_events], ["patch_approval_requested"]
            )
            approval_id = str(blocked.tool_events[0].payload.get("approval_id") or "")
            self.assertTrue(approval_id.startswith("approval_"))
            self.assertIn(f"/approve {approval_id}", blocked.assistant_text)
            self.assertFalse((workspace_root / "demo.txt").exists())

            runtime.configure_runtime_policy(approval_policy="never")
            allowed = runtime.tools.apply_patch_result(patch_text)
            self.assertEqual([event.name for event in allowed.tool_events], ["apply_patch"])
            self.assertTrue(allowed.tool_events[0].ok)
            self.assertEqual((workspace_root / "demo.txt").read_text(encoding="utf-8"), "hello\n")

    def test_tool_registry_claude_edit_guard_requires_read_before_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            target = workspace_root / "demo.txt"
            target.write_text("Status: TODO\n", encoding="utf-8")
            registry = ToolRegistry()
            registry.set_workspace_root(workspace_root)

            patch_text = json.dumps(
                {
                    "operation": "file_edit",
                    "file_path": "demo.txt",
                    "old_string": "TODO",
                    "new_string": "DONE",
                    "source_tool_name": "Edit",
                    "guard_profile": "claude_edit",
                }
            )

            blocked = registry.apply_patch_result(patch_text)
            self.assertFalse(blocked.tool_events[-1].ok)
            self.assertIn(
                "reading the current file first",
                str(blocked.tool_events[-1].payload.get("error") or ""),
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "Status: TODO\n")

            read_result = registry.read_file_result(str(target), offset=1, limit=20)
            self.assertTrue(read_result.tool_events[-1].ok)

            allowed = registry.apply_patch_result(patch_text)
            self.assertTrue(allowed.tool_events[-1].ok)
            self.assertEqual(target.read_text(encoding="utf-8"), "Status: DONE\n")

    def test_tool_registry_claude_edit_guard_rejects_stale_edit_after_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            target = workspace_root / "demo.txt"
            target.write_text("Status: TODO\n", encoding="utf-8")
            registry = ToolRegistry()
            registry.set_workspace_root(workspace_root)

            read_result = registry.read_file_result(str(target), offset=1, limit=20)
            self.assertTrue(read_result.tool_events[-1].ok)
            target.write_text("Status: external\n", encoding="utf-8")

            patch_text = json.dumps(
                {
                    "operation": "file_edit",
                    "file_path": "demo.txt",
                    "old_string": "TODO",
                    "new_string": "DONE",
                    "source_tool_name": "Edit",
                    "guard_profile": "claude_edit",
                }
            )

            blocked = registry.apply_patch_result(patch_text)
            self.assertFalse(blocked.tool_events[-1].ok)
            self.assertIn(
                "changed since it was read", str(blocked.tool_events[-1].payload.get("error") or "")
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "Status: external\n")

    def test_tool_registry_shell_exec_methods_delegate_through_shell_runtime(self) -> None:
        registry = object.__new__(ToolRegistry)
        cancel_event = threading.Event()

        def activity_callback(payload: dict[str, Any]) -> None:
            return None

        registry._host_platform = object()

        def resolve_shell_cwd(cwd: str | None) -> str:
            return f"/resolved/{cwd}"

        registry._resolve_shell_cwd = resolve_shell_cwd  # type: ignore[method-assign]
        registry._shell_activity_callback = activity_callback

        def cancel_event_getter() -> threading.Event:
            return cancel_event

        registry._shell_cancel_event_getter = cancel_event_getter

        shell_event = ToolEvent(
            name="shell", ok=True, summary="ok", payload={"status": "completed"}
        )
        shell_result = CommandExecutionResult(assistant_text="ok")

        with patch.object(
            tools_module.shell_tools_runtime, "execute_shell", return_value=shell_event
        ) as execute_mock:
            result = ToolRegistry.shell(
                registry,
                "echo hi",
                cwd="tmp",
                timeout_sec=12,
                login=False,
                tty=True,
                shell="/bin/zsh",
                max_output_chars=99,
            )
        self.assertIs(result, shell_event)
        execute_mock.assert_called_once_with(
            host_platform=registry._host_platform,
            command="echo hi",
            cwd="/resolved/tmp",
            timeout_sec=12,
            login=False,
            tty=True,
            shell="/bin/zsh",
            max_output_chars=99,
            on_activity=activity_callback,
            cancel_event=cancel_event,
        )

        def explicit_callback(payload: dict[str, Any]) -> None:
            return None

        explicit_cancel = threading.Event()
        with patch.object(
            tools_module.shell_tools_runtime, "execute_shell_result", return_value=shell_result
        ) as result_mock:
            result = ToolRegistry.shell_result(
                registry,
                "pwd",
                cwd=".",
                on_activity=explicit_callback,
                cancel_event=explicit_cancel,
            )
        self.assertIs(result, shell_result)
        result_mock.assert_called_once_with(
            host_platform=registry._host_platform,
            command="pwd",
            cwd="/resolved/.",
            timeout_sec=60,
            login=True,
            tty=False,
            shell=None,
            max_output_chars=12000,
            on_activity=explicit_callback,
            cancel_event=explicit_cancel,
        )

    def test_tool_registry_shell_session_methods_preserve_session_payloads_and_runtime_fallbacks(
        self,
    ) -> None:
        registry = object.__new__(ToolRegistry)
        sessions = _FakeShellSessions()
        cancel_event = threading.Event()

        def activity_callback(payload: dict[str, Any]) -> None:
            return None

        registry._shell_sessions = sessions

        def resolve_shell_cwd(cwd: str | None) -> str:
            return f"/workspace/{cwd}"

        registry._resolve_shell_cwd = resolve_shell_cwd  # type: ignore[method-assign]
        registry._shell_activity_callback = activity_callback

        def cancel_event_getter() -> threading.Event:
            return cancel_event

        registry._shell_cancel_event_getter = cancel_event_getter

        started = ToolRegistry.shell_start(registry, "sleep 1", cwd="logs")
        started_result = ToolRegistry.shell_start_result(registry, "sleep 1", cwd="logs")
        write_event = ToolRegistry.shell_write_stdin(registry, "s-1", "y", yield_time_ms=10)
        write_result = ToolRegistry.shell_write_stdin_result(registry, "s-1", "n")
        terminate_event = ToolRegistry.shell_terminate(registry, "s-1")
        terminate_result = ToolRegistry.shell_terminate_result(registry, "s-1")
        subscribe_event = ToolRegistry.shell_subscribe(registry, "s-1")
        subscribe_result = ToolRegistry.shell_subscribe_result(registry, "s-1")

        self.assertEqual(started, {"session_id": "s-1", "phase": "started"})
        self.assertEqual(started_result.assistant_text, "started")
        self.assertEqual(write_event.payload["session_id"], "s-1")
        self.assertEqual(write_result.assistant_text, "write")
        self.assertEqual(terminate_event.payload["session_id"], "s-1")
        self.assertEqual(terminate_result.assistant_text, "terminated")
        self.assertEqual(subscribe_event.payload["session_id"], "s-1")
        self.assertEqual(subscribe_result.assistant_text, "subscribed")

        self.assertEqual(
            sessions.calls,
            [
                (
                    "start_session",
                    (),
                    {
                        "command": "sleep 1",
                        "cwd": "/workspace/logs",
                        "login": True,
                        "tty": False,
                        "shell": None,
                        "max_output_chars": 12000,
                        "on_activity": activity_callback,
                    },
                ),
                (
                    "start_session_result",
                    (),
                    {
                        "command": "sleep 1",
                        "cwd": "/workspace/logs",
                        "login": True,
                        "tty": False,
                        "shell": None,
                        "max_output_chars": 12000,
                        "on_activity": activity_callback,
                    },
                ),
                (
                    "write_stdin",
                    ("s-1", "y"),
                    {
                        "yield_time_ms": 10,
                        "allow_extended_empty_poll": False,
                        "on_activity": activity_callback,
                        "cancel_event": cancel_event,
                    },
                ),
                (
                    "write_stdin_result",
                    ("s-1", "n"),
                    {
                        "yield_time_ms": None,
                        "allow_extended_empty_poll": False,
                        "on_activity": activity_callback,
                        "cancel_event": cancel_event,
                    },
                ),
                ("terminate", ("s-1",), {"on_activity": activity_callback}),
                ("terminate_result", ("s-1",), {"on_activity": activity_callback}),
                ("subscribe", ("s-1",), {"on_activity": activity_callback}),
                ("subscribe_result", ("s-1",), {"on_activity": activity_callback}),
            ],
        )

    def test_tool_registry_prefers_structured_web_result_helpers_when_available(self) -> None:
        registry = object.__new__(ToolRegistry)

        class _WebTools:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

            def _record(self, name: str, *args: Any, **kwargs: Any) -> CommandExecutionResult:
                self.calls.append((name, args, kwargs))
                return CommandExecutionResult(assistant_text=name)

            def web_search_result(self, *args: Any, **kwargs: Any) -> CommandExecutionResult:
                return self._record("web_search_result", *args, **kwargs)

            def web_fetch_result(self, *args: Any, **kwargs: Any) -> CommandExecutionResult:
                return self._record("web_fetch_result", *args, **kwargs)

            def open_result(self, *args: Any, **kwargs: Any) -> CommandExecutionResult:
                return self._record("open_result", *args, **kwargs)

            def click_result(self, *args: Any, **kwargs: Any) -> CommandExecutionResult:
                return self._record("click_result", *args, **kwargs)

            def find_result(self, *args: Any, **kwargs: Any) -> CommandExecutionResult:
                return self._record("find_result", *args, **kwargs)

        web_tools = _WebTools()
        registry._get_web_search_tools = lambda: web_tools  # type: ignore[attr-defined]

        self.assertEqual(
            ToolRegistry.web_search_result(
                registry, "weather", limit=3, domains=["example.com"]
            ).assistant_text,
            "web_search_result",
        )
        self.assertEqual(
            ToolRegistry.web_fetch_result(registry, "https://example.com").assistant_text,
            "web_fetch_result",
        )
        self.assertEqual(
            ToolRegistry.open_result(registry, "turn0search0", line=12).assistant_text,
            "open_result",
        )
        self.assertEqual(
            ToolRegistry.click_result(registry, "turn0search0", id=5).assistant_text, "click_result"
        )
        self.assertEqual(
            ToolRegistry.find_result(registry, "turn0search0", pattern="needle").assistant_text,
            "find_result",
        )
        self.assertEqual(
            [name for name, _args, _kwargs in web_tools.calls],
            ["web_search_result", "web_fetch_result", "open_result", "click_result", "find_result"],
        )

    def test_tool_registry_browser_result_uses_browser_bridge(self) -> None:
        registry = object.__new__(ToolRegistry)
        registry.browser = lambda action, **kwargs: ToolEvent(  # type: ignore[attr-defined]
            name="browser_status",
            ok=True,
            summary="active",
            payload={"ok": True, "status": "active", "profile": kwargs.get("profile")},
        )

        result = ToolRegistry.browser_result(registry, "status", profile="review")
        self.assertEqual(result.assistant_text, "active")
        self.assertEqual(result.tool_events[0].name, "browser_status")
        self.assertEqual(result.item_events[-1]["item"]["tool"], "browser")
        self.assertEqual(result.item_events[-1]["item"]["arguments"]["action"], "status")
        self.assertEqual(result.item_events[-1]["item"]["arguments"]["profile"], "review")

    def test_tool_registry_policy_doc_result_helpers_have_structured_fallback(self) -> None:
        class _PolicyTools:
            def policy_doc_import(self, path: str, *, library_root=None, recursive=True):
                return {
                    "ok": True,
                    "imported_count": 1,
                    "path": path,
                    "library_root": library_root,
                    "recursive": recursive,
                }

            def policy_doc_list(self, *, library_root=None, limit=50):
                return {
                    "ok": True,
                    "count": 1,
                    "items": [{"doc_id": "d1"}],
                    "library_root": library_root,
                    "limit": limit,
                }

            def policy_doc_search(self, query: str, *, library_root=None, limit=10):
                return {
                    "ok": True,
                    "count": 1,
                    "query": query,
                    "matches": [{"doc_id": "d1"}],
                    "library_root": library_root,
                    "limit": limit,
                }

            def policy_doc_read(
                self, *, doc_id=None, path=None, library_root=None, max_chars=12000
            ):
                return {
                    "ok": True,
                    "doc_id": doc_id or "d1",
                    "path": path,
                    "markdown": "# policy",
                    "library_root": library_root,
                    "max_chars": max_chars,
                }

        registry = object.__new__(ToolRegistry)
        registry._internal_policy_tools = _PolicyTools()

        import_result = ToolRegistry.policy_doc_import_result(registry, "policies/demo.docx")
        self.assertIsInstance(import_result, CommandExecutionResult)
        self.assertEqual(import_result.tool_events[0].name, "policy_doc_import")
        self.assertEqual(import_result.item_events[-1]["item"]["tool"], "policy_doc_import")

        list_result = ToolRegistry.policy_doc_list_result(registry, library_root="docs", limit=5)
        self.assertEqual(list_result.tool_events[0].name, "policy_doc_list")
        self.assertEqual(list_result.item_events[-1]["item"]["tool"], "policy_doc_list")

        search_result = ToolRegistry.policy_doc_search_result(
            registry, "audit", library_root="docs", limit=3
        )
        self.assertEqual(search_result.tool_events[0].name, "policy_doc_search")
        self.assertEqual(search_result.item_events[-1]["item"]["tool"], "policy_doc_search")

        read_result = ToolRegistry.policy_doc_read_result(registry, doc_id="d1", max_chars=3000)
        self.assertEqual(read_result.tool_events[0].name, "policy_doc_read")
        self.assertEqual(read_result.item_events[-1]["item"]["tool"], "policy_doc_read")

    def test_tool_registry_capabilities_delegates_to_shared_registry_helper(self) -> None:
        registry = object.__new__(ToolRegistry)
        manager = _FakePluginManager()
        registry._plugin_manager = manager

        expected = {
            "ok": True,
            "tools": [{"name": "fake_tool"}],
            "count": 1,
            "registry_error": None,
            "workspace_trust": "untrusted",
            "mcp_servers": {"sample": {"url": "https://example.com/mcp"}},
            "app_connectors": [{"name": "demo", "source": "plugin"}],
        }
        captured: dict[str, Any] = {}

        def _fake_build_capabilities_payload(*, plugin_manager_factory=None):
            captured["factory"] = plugin_manager_factory
            return expected

        with patch.object(
            tools_module, "build_capabilities_payload", side_effect=_fake_build_capabilities_payload
        ):
            payload = ToolRegistry.capabilities(registry)

        self.assertIs(payload, expected)
        factory = captured.get("factory")
        self.assertTrue(callable(factory))
        self.assertIs(factory(), manager)

    def test_tool_registry_public_contract_keeps_core_bound_entrypoints(self) -> None:
        expected_methods = {
            "set_workspace_root",
            "get_mcp_runtime",
            "apply_patch",
            "apply_patch_result",
            "file_list_result",
            "file_search_result",
            "file_read_result",
            "browser",
            "browser_result",
            "web_search_result",
            "capabilities",
        }

        for method_name in expected_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(callable(getattr(ToolRegistry, method_name, None)))

    def test_tool_registry_capabilities_adds_sorted_mcp_tool_contracts_from_runtime_patchpoint(
        self,
    ) -> None:
        registry = object.__new__(ToolRegistry)
        registry._plugin_manager = _FakePluginManager()
        registry._mcp_runtime = type(
            "_FakeRuntime",
            (),
            {
                "projected_tool_contracts": staticmethod(
                    lambda: [
                        {"name": "zeta_tool", "server": "atlas"},
                        {"name": "alpha_tool", "server": "atlas"},
                    ]
                )
            },
        )()

        with patch.object(
            tools_module,
            "build_capabilities_payload",
            return_value={
                "ok": True,
                "tools": [{"name": "fake_tool"}],
                "count": 1,
                "registry_error": None,
                "workspace_trust": "untrusted",
                "mcp_servers": {},
                "app_connectors": [],
            },
        ):
            payload = ToolRegistry.capabilities(registry)

        self.assertEqual(
            payload["mcp_tool_contracts"],
            [
                {"name": "alpha_tool", "server": "atlas"},
                {"name": "zeta_tool", "server": "atlas"},
            ],
        )

    def test_build_capabilities_payload_centralizes_capability_metadata(self) -> None:
        manager = _FakePluginManager()
        capability_specs = [{"name": "shell"}, {"name": "fake_tool"}]

        with patch(
            "cli.agent_cli.tools_core.registry.merged_capability_specs",
            return_value=capability_specs,
        ) as merged_specs:
            payload = build_capabilities_payload(plugin_manager_factory=lambda: manager)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tools"], capability_specs)
        self.assertEqual(payload["count"], 2)
        self.assertIsNone(payload["registry_error"])
        self.assertEqual(payload["workspace_trust"], "untrusted")
        self.assertEqual(payload["mcp_servers"], {"sample": {"url": "https://example.com/mcp"}})
        self.assertEqual(payload["app_connectors"], [{"name": "demo", "source": "plugin"}])
        merged_specs.assert_called_once()
        factory = merged_specs.call_args.kwargs.get("plugin_manager_factory")
        self.assertTrue(callable(factory))
        self.assertIs(factory(), manager)

    def test_runtime_registry_app_connector_entries_prefer_canonical_plugin_metadata(self) -> None:
        class _MetaManager:
            def gui_bridge_metadata(self):
                return {
                    "appConnectors": [
                        {
                            "connector_id": "canonical_connector",
                            "plugin_name": "canonical_plugin",
                            "display_name": "Canonical Connector",
                            "connector_kind": "app",
                        }
                    ]
                }

            def effective_app_connectors(self):
                return [{"connector_id": "fallback_connector", "plugin_name": "fallback_plugin"}]

        entries = runtime_registry_app_connector_entries(
            _MetaManager(),
            runtime_capabilities={"app_connectors": [{"connector_id": "runtime_connector"}]},
        )
        connector_ids = {item["connector_id"] for item in entries}
        self.assertIn("canonical_connector", connector_ids)
        self.assertNotIn("runtime_connector", connector_ids)
        self.assertNotIn("fallback_connector", connector_ids)

    def test_runtime_registry_mcp_server_entries_merge_runtime_status_over_canonical_metadata(
        self,
    ) -> None:
        class _MetaManager:
            @staticmethod
            def gui_bridge_metadata():
                return {
                    "mcpServers": [
                        {
                            "name": "atlas",
                            "source": "plugin",
                            "plugin_name": "atlas_plugin",
                            "config": {"url": "https://canonical.example/mcp"},
                        }
                    ]
                }

        entries = runtime_registry_mcp_server_entries(
            _MetaManager(),
            runtime_capabilities={
                "mcp_server_entries": [
                    {
                        "name": "atlas",
                        "source": "workspace",
                        "status": "connected",
                        "enabled": True,
                        "scope": "workspace",
                        "projection_state": "ready",
                        "config": {"url": "https://runtime.example/mcp"},
                    }
                ]
            },
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "atlas")
        self.assertEqual(entries[0]["source"], "workspace")
        self.assertEqual(entries[0]["status"], "connected")
        self.assertEqual(entries[0]["projection_state"], "ready")
        self.assertEqual(entries[0]["plugin_name"], "atlas_plugin")
        self.assertEqual(entries[0]["config"]["url"], "https://runtime.example/mcp")

    def test_app_connector_contract_item_derives_approval_and_enabled_state(self) -> None:
        connector = app_connector_contract_item(
            {
                "connector_id": "demo_connector",
                "plugin_name": "demo_plugin",
                "supports_actions": True,
                "enabled": True,
            },
            approval_policy="on-request",
            plugin_enabled=False,
        )

        self.assertIsNotNone(connector)
        payload = dict(connector or {})
        self.assertEqual(payload["connector_key"], "demo_connector")
        self.assertTrue(payload["approval_required"])
        self.assertEqual(payload["approval"]["resolver"], "approvals.resolve")
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["health"], "warning")

    def test_gateway_connector_contract_item_derives_approval_and_enabled_state(self) -> None:
        connector = gateway_connector_contract_item(
            {
                "connector_key": "github_webhook",
                "plugin_name": "github",
                "display_name": "GitHub Webhook",
                "connector_kind": "webhook",
                "supports_actions": True,
                "enabled_by_default": True,
                "event_types": ["issues.opened"],
            },
            approval_policy="on-request",
            plugin_enabled=False,
        )

        self.assertIsNotNone(connector)
        payload = dict(connector or {})
        self.assertEqual(payload["connector_id"], "github_webhook")
        self.assertEqual(payload["connector_key"], "github_webhook")
        self.assertTrue(payload["approval_required"])
        self.assertEqual(payload["approval"]["resolver"], "approvals.resolve")
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["health"], "warning")
        self.assertEqual(payload["source_kind"], "gateway")
