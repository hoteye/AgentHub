from __future__ import annotations

import json
import shlex
import unittest
from types import SimpleNamespace
from typing import Any

from cli.agent_cli.core.provider_session import (
    ProviderSession,
    ProviderSessionResult,
    ProviderToolCall,
)
from cli.agent_cli.core.turn_engine import TurnEngine, _structured_tool_fallback_text
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    ResponseInputItem,
    ToolEvent,
    response_items_with_tool_outputs,
    response_message_item,
    shell_tool_call_item_events,
)
from cli.agent_cli.providers.delegation_policy import planner_tool_execution_target
from cli.agent_cli.providers.tool_calls import command_for_tool_call
from cli.agent_cli.providers.tool_execution_loop import ToolExecutionLoopMixin
from cli.agent_cli.runtime_core.command_handlers import handle_known_command
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.runtime_structured_runtime import StructuredToolExecutor


class _FakeSession(ProviderSession):
    def __init__(self, scripted: list[ProviderSessionResult]):
        self.scripted = list(scripted)
        self.calls: list[dict[str, Any]] = []
        self.incremental_continuation = False

    def send(
        self,
        *,
        input_items: list[dict[str, Any]],
        allow_tools: bool,
        previous_response_id: str | None = None,
        prompt_cache_key: str | None = None,
        turn_event_callback: Any = None,
    ) -> ProviderSessionResult:
        self.calls.append(
            {
                "input": input_items,
                "allow_tools": allow_tools,
                "previous_response_id": previous_response_id,
                "prompt_cache_key": prompt_cache_key,
                "turn_event_callback": turn_event_callback,
            }
        )
        if not self.scripted:
            raise RuntimeError("no scripted response")
        result = self.scripted.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def uses_incremental_continuation(self) -> bool:
        return bool(self.incremental_continuation)


def _tool_call_runtime_command(name: str, arguments: dict[str, Any]) -> str | None:
    return command_for_tool_call(
        name,
        arguments,
        current_host_platform(),
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
    )


def _runtime_command_result(runtime: Any, command_text: str) -> CommandExecutionResult:
    if not str(command_text or "").startswith("/"):
        raise AssertionError(f"expected slash command, got: {command_text!r}")
    slash_body = command_text[1:]
    name, _, arg_text = slash_body.partition(" ")
    result = handle_known_command(
        runtime,
        name=name,
        arg_text=arg_text,
        text=command_text,
    )
    if result is None:
        raise AssertionError(f"runtime did not handle command: {command_text!r}")
    if isinstance(result, CommandExecutionResult):
        return result
    assistant_text, tool_events = result
    return CommandExecutionResult(
        assistant_text=str(assistant_text or ""),
        tool_events=list(tool_events or []),
    )


def _request_user_input_runtime(*, handler: Any) -> Any:
    return SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=handler,
        _is_interrupt_requested=lambda: False,
        _interrupt_tuple=lambda: (
            "interrupted",
            [
                ToolEvent(
                    name="interrupted",
                    ok=False,
                    summary="interrupted",
                    payload={"reason": "user_interrupt"},
                )
            ],
        ),
        tools=SimpleNamespace(_plugin_manager=None),
    )


def _function_call_output_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    return json.dumps(output, ensure_ascii=False)


def _request_user_input_output_payload(output: Any) -> dict[str, Any]:
    parsed = json.loads(output) if isinstance(output, str) else dict(output or {})
    if isinstance(parsed, dict) and isinstance(parsed.get("response"), dict):
        return dict(parsed["response"])
    return dict(parsed)


class _BatchToolLoopHarness(ToolExecutionLoopMixin):
    def __init__(self) -> None:
        self.supports_parallel_tool_calls = False
        self.host_platform = current_host_platform()
        self.plugin_manager_factory = None
        self._tool_loop_command_for_tool_call = (
            lambda _tool_name, arguments, _host_platform, plugin_manager_factory=None: str(
                arguments.get("cmd") or ""
            )
        )

    @staticmethod
    def _parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
        return json.loads(raw_arguments)


class TurnEngineTests(unittest.TestCase):
    def test_structured_tool_fallback_text_supports_canonical_read_file(self) -> None:
        text = _structured_tool_fallback_text(
            [
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"file_path": "README.md", "path": "README.md"},
                )
            ]
        )

        self.assertEqual(text, "已读取文件：README.md")

    def test_structured_tool_fallback_text_supports_canonical_grep_files_soft_failure(self) -> None:
        text = _structured_tool_fallback_text(
            [
                ToolEvent(
                    name="grep_files",
                    ok=False,
                    summary="No matches found.",
                    payload={
                        "result_success": False,
                        "pattern": "needle",
                        "text": "No matches found.",
                    },
                )
            ]
        )

        self.assertEqual(text, "No matches found.")

    def test_tool_loop_success_path(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="file_list", arguments={"path": ".", "limit": 5}
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        observed_commands: list[str] = []

        def tool_executor(command_text: str):
            observed_commands.append(command_text)
            return "ok", [
                ToolEvent(
                    name="file_list", ok=True, summary="files=1", payload={"files": ["README.md"]}
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent: AgentIntent = engine.run(
            user_text="list files", initial_input=[{"role": "user", "content": "list"}]
        )

        self.assertEqual(intent.assistant_text, "done")
        self.assertEqual(intent.response_items[0].extra["phase"], "final_answer")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)
        self.assertEqual(
            observed_commands,
            [
                json.dumps(
                    {"name": "file_list", "arguments": {"path": ".", "limit": 5}},
                    ensure_ascii=False,
                )
            ],
        )
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1]["previous_response_id"], "r1")
        self.assertEqual(session.calls[1]["input"][0]["call_id"], "c1")
        self.assertTrue(session.calls[0]["allow_tools"])
        self.assertTrue(session.calls[1]["allow_tools"])
        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_decision"], "none")
        self.assertEqual(trace["delegation_policy_decision"], "stay_local")
        self.assertEqual(trace["delegation_policy_source"], "delegation_policy")
        self.assertEqual(trace["delegation_stay_local_source"], "planner_tool_calls")
        self.assertEqual(trace["delegation_stay_local_reason"], "non_delegation_tools_only")
        self.assertEqual(trace["delegation_stay_local_counterexamples"], ["file_list"])
        self.assertEqual(trace["delegation_control_action"], "stay_local")
        self.assertEqual(trace["delegation_control_reason"], "non_delegation_tools_only")
        self.assertTrue(trace["delegation_control_continue_main_thread"])
        self.assertFalse(trace["delegation_control_wait_for_child"])
        self.assertFalse(trace["delegation_control_stop_early"])

    def test_unmapped_provider_tool_call_returns_failed_tool_output(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="call_unknown_1",
                            name="missing_agenthub_tool",
                            arguments={"task": "inspect README"},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="handled",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "handled", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        observed_commands: list[str] = []

        def tool_executor(command_text: str):
            observed_commands.append(command_text)
            return "unexpected", []

        engine = TurnEngine(
            session,
            tool_executor=tool_executor,
            command_builder=lambda _name, _arguments: None,
        )
        intent = engine.run(
            user_text="use unknown tool",
            initial_input=[{"role": "user", "content": "use unknown tool"}],
        )

        self.assertEqual(intent.assistant_text, "handled")
        self.assertEqual(observed_commands, [])
        self.assertEqual(len(intent.tool_events), 1)
        self.assertFalse(intent.tool_events[0].ok)
        self.assertEqual(intent.tool_events[0].payload["provider_call_id"], "call_unknown_1")
        self.assertEqual(session.calls[1]["input"][0]["type"], "function_call_output")
        self.assertEqual(session.calls[1]["input"][0]["call_id"], "call_unknown_1")
        self.assertIn("could not be executed", session.calls[1]["input"][0]["output"])

    def test_turn_engine_emits_tool_started_event_before_structured_tool_execution(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(call_id="c1", name="list_dir", arguments={"dir_path": "."})
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )
        trace: list[str] = []

        class _StructuredExecutor:
            def __call__(self, command_text: str):
                return "compat", [
                    ToolEvent(
                        name="list_dir", ok=True, summary="entries=1", payload={"dir_path": "."}
                    )
                ]

            def run_structured(self, command_text: str) -> CommandExecutionResult:
                trace.append("executor_invoked")
                return CommandExecutionResult(
                    assistant_text="ok",
                    tool_events=[
                        ToolEvent(
                            name="list_dir",
                            ok=True,
                            summary="entries=1",
                            payload={"dir_path": ".", "count": 1},
                        )
                    ],
                    item_events=[
                        {
                            "type": "item.started",
                            "item": {
                                "id": "item_0",
                                "type": "mcp_tool_call",
                                "server": "local",
                                "tool": "list_dir",
                                "arguments": {"dir_path": "."},
                                "result": None,
                                "error": None,
                                "status": "in_progress",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_0",
                                "type": "mcp_tool_call",
                                "server": "local",
                                "tool": "list_dir",
                                "arguments": {"dir_path": "."},
                                "result": {
                                    "content": [{"type": "text", "text": "E1: [file] README.md"}],
                                    "structured_content": {"dir_path": ".", "count": 1},
                                },
                                "error": None,
                                "status": "completed",
                            },
                        },
                    ],
                )

        def on_turn_event(event: dict[str, Any]) -> None:
            item = event.get("item") if isinstance(event, dict) else None
            if isinstance(item, dict):
                trace.append(f"{event['type']}:{item.get('type')}:{item.get('status')}")
            else:
                trace.append(str(event.get("type")))

        engine = TurnEngine(
            session, tool_executor=_StructuredExecutor(), turn_event_callback=on_turn_event
        )
        engine.run(user_text="list", initial_input=[{"role": "user", "content": "list"}])

        self.assertGreaterEqual(len(trace), 4)
        self.assertEqual(trace[0], "turn.started")
        self.assertEqual(trace[1], "item.completed:agent_message:None")
        self.assertEqual(trace[2], "item.started:mcp_tool_call:in_progress")
        self.assertEqual(trace[3], "executor_invoked")

    def test_turn_engine_uses_command_execution_for_exec_mapped_tool_calls(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(call_id="c1", name="list_dir", arguments={"dir_path": "."})
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )
        trace: list[str] = []

        class _StructuredExecutor:
            def __call__(self, command_text: str):
                return "compat", [
                    ToolEvent(
                        name="exec_command",
                        ok=True,
                        summary="exec completed",
                        payload={"command": command_text},
                    )
                ]

            def run_structured(self, command_text: str) -> CommandExecutionResult:
                trace.append("executor_invoked")
                return CommandExecutionResult(
                    assistant_text="ok",
                    tool_events=[
                        ToolEvent(
                            name="exec_command",
                            ok=True,
                            summary="exec completed",
                            payload={
                                "command": command_text,
                                "aggregated_output": "a\tf",
                                "exit_code": 0,
                            },
                        )
                    ],
                    item_events=[
                        {
                            "type": "item.started",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "aggregated_output": "",
                                "exit_code": None,
                                "status": "in_progress",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "aggregated_output": "a\tf",
                                "exit_code": 0,
                                "status": "completed",
                            },
                        },
                    ],
                )

        def on_turn_event(event: dict[str, Any]) -> None:
            item = event.get("item") if isinstance(event, dict) else None
            if isinstance(item, dict):
                trace.append(f"{event['type']}:{item.get('type')}:{item.get('status')}")
            else:
                trace.append(str(event.get("type")))

        engine = TurnEngine(
            session,
            tool_executor=_StructuredExecutor(),
            command_builder=lambda _name, _arguments: "/exec_command 'find . -mindepth 1 -maxdepth 1 -printf '\"'\"'%f\\t%y\\n'\"'\"' | sort'",
            turn_event_callback=on_turn_event,
        )
        engine.run(user_text="list", initial_input=[{"role": "user", "content": "list"}])

        self.assertGreaterEqual(len(trace), 4)
        self.assertEqual(trace[0], "turn.started")
        self.assertEqual(trace[1], "item.completed:agent_message:None")
        self.assertEqual(trace[2], "item.started:command_execution:in_progress")
        self.assertEqual(trace[3], "executor_invoked")

    def test_turn_engine_coalesces_provisional_exec_started_with_runtime_lifecycle(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="call_exec_1",
                            name="exec_command",
                            arguments={"cmd": "pwd"},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )
        streamed: list[dict[str, Any]] = []

        class _StructuredExecutor:
            def run_structured(self, command_text: str) -> CommandExecutionResult:
                return CommandExecutionResult(
                    assistant_text="ok",
                    tool_events=[
                        ToolEvent(
                            name="exec_command",
                            ok=True,
                            summary="exec completed",
                            payload={
                                "command": command_text,
                                "aggregated_output": "/tmp/project\n",
                                "exit_code": 0,
                            },
                        )
                    ],
                    item_events=[
                        {
                            "type": "item.started",
                            "item": {
                                "id": "local_exec_1",
                                "type": "command_execution",
                                "call_id": "call_exec_1",
                                "command": command_text,
                                "aggregated_output": "",
                                "exit_code": None,
                                "status": "in_progress",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "local_exec_1",
                                "type": "command_execution",
                                "call_id": "call_exec_1",
                                "command": command_text,
                                "aggregated_output": "/tmp/project\n",
                                "exit_code": 0,
                                "status": "completed",
                            },
                        },
                    ],
                )

        engine = TurnEngine(
            session,
            tool_executor=_StructuredExecutor(),
            command_builder=lambda _name, arguments: f"/exec_command --cmd {shlex.quote(str(arguments.get('cmd') or ''))}",
            turn_event_callback=lambda event: streamed.append(dict(event)),
        )
        intent = engine.run(user_text="pwd", initial_input=[{"role": "user", "content": "pwd"}])

        started = [
            event
            for event in streamed
            if event.get("type") == "item.started"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "command_execution"
        ]
        completed = [
            event
            for event in streamed
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "command_execution"
        ]
        intent_started = [
            event
            for event in intent.turn_events
            if event.get("type") == "item.started"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "command_execution"
        ]

        self.assertEqual(len(started), 1)
        self.assertEqual(started[0]["item"]["id"], "call_exec_1")
        self.assertEqual(started[0]["item"]["call_id"], "call_exec_1")
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["item"]["call_id"], "call_exec_1")
        self.assertEqual(len(intent_started), 1)
        self.assertEqual(intent_started[0]["item"]["call_id"], "call_exec_1")

    def test_turn_engine_provisional_exec_started_uses_runtime_resolved_shell(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="call_exec_1",
                            name="exec_command",
                            arguments={
                                "cmd": "pwd",
                                "login": True,
                            },
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )
        streamed: list[dict[str, Any]] = []
        runtime = SimpleNamespace(
            _parse_args=parse_args,
            _normalize_shell_override=lambda shell: (
                "/usr/bin/bash" if str(shell or "").strip() == "bash" else None
            ),
            _host_platform=lambda: SimpleNamespace(
                resolve_shell_program=lambda shell=None: "/usr/bin/bash"
            ),
        )

        def _run_command(command_text: str) -> CommandExecutionResult:
            event = ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec completed",
                payload={
                    "command": "pwd",
                    "shell": "/usr/bin/bash",
                    "resolved_shell": "/usr/bin/bash",
                    "login": True,
                    "aggregated_output": "/tmp/project\n",
                    "exit_code": 0,
                },
            )
            return CommandExecutionResult(
                assistant_text="ok",
                tool_events=[event],
                item_events=shell_tool_call_item_events(event, command="pwd"),
            )

        engine = TurnEngine(
            session,
            tool_executor=StructuredToolExecutor(
                run_command_text_result_fn=_run_command,
                interrupt_requested_fn=lambda: False,
                interrupt_result_fn=lambda: ("", []),
                runtime_owner=runtime,
            ),
            command_builder=lambda _name, arguments: (
                f"/exec_command --cmd {shlex.quote(str(arguments.get('cmd') or ''))} "
                f"--login {str(bool(arguments.get('login'))).lower()}"
            ),
            turn_event_callback=lambda event: streamed.append(dict(event)),
        )
        engine.run(user_text="pwd", initial_input=[{"role": "user", "content": "pwd"}])

        command_events = [
            event
            for event in streamed
            if isinstance(event.get("item"), dict)
            and event["item"].get("type") == "command_execution"
        ]

        self.assertEqual(command_events[0]["type"], "item.started")
        self.assertEqual(command_events[1]["type"], "item.completed")
        self.assertEqual(command_events[0]["item"]["command"], "/usr/bin/bash -lc pwd")
        self.assertEqual(command_events[1]["item"]["command"], "/usr/bin/bash -lc pwd")

    def test_turn_engine_provisional_exec_started_parses_boolean_flags(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="call_exec_1",
                            name="exec_command",
                            arguments={
                                "cmd": "pwd -P",
                                "tty": True,
                                "login": True,
                            },
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )
        streamed: list[dict[str, Any]] = []
        runtime = SimpleNamespace(
            _parse_args=parse_args,
            _normalize_shell_override=lambda shell: "/bin/bash",
            _host_platform=lambda: SimpleNamespace(
                resolve_shell_program=lambda shell=None: "/bin/bash"
            ),
        )

        def _run_command(command_text: str) -> CommandExecutionResult:
            del command_text
            event = ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec completed",
                payload={
                    "command": "pwd -P",
                    "shell": "/bin/bash",
                    "resolved_shell": "/bin/bash",
                    "login": True,
                    "tty": True,
                    "aggregated_output": "/tmp/project\n",
                    "exit_code": 0,
                },
            )
            return CommandExecutionResult(
                assistant_text="ok",
                tool_events=[event],
                item_events=shell_tool_call_item_events(event, command="pwd -P"),
            )

        engine = TurnEngine(
            session,
            tool_executor=StructuredToolExecutor(
                run_command_text_result_fn=_run_command,
                interrupt_requested_fn=lambda: False,
                interrupt_result_fn=lambda: ("", []),
                runtime_owner=runtime,
            ),
            command_builder=lambda _name, arguments: (
                f"/exec_command {shlex.quote(str(arguments.get('cmd') or ''))} "
                f"--tty --login {str(bool(arguments.get('login'))).lower()}"
            ),
            turn_event_callback=lambda event: streamed.append(dict(event)),
        )
        engine.run(user_text="pwd", initial_input=[{"role": "user", "content": "pwd"}])

        command_events = [
            event
            for event in streamed
            if isinstance(event.get("item"), dict)
            and event["item"].get("type") == "command_execution"
        ]

        self.assertEqual(command_events[0]["type"], "item.started")
        self.assertEqual(command_events[1]["type"], "item.completed")
        self.assertEqual(command_events[0]["item"]["command"], "/bin/bash -lc 'pwd -P'")
        self.assertEqual(command_events[1]["item"]["command"], "/bin/bash -lc 'pwd -P'")

    def test_turn_engine_coalesces_update_plan_into_single_todo_list_lifecycle(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="update_plan",
                            arguments={
                                "plan": [
                                    {"step": "inspect", "status": "pending"},
                                    {"step": "patch", "status": "in_progress"},
                                ]
                            },
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c2",
                            name="update_plan",
                            arguments={
                                "plan": [
                                    {"step": "inspect", "status": "completed"},
                                    {"step": "patch", "status": "in_progress"},
                                ]
                            },
                        )
                    ],
                    response_id="r2",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r3",
                ),
            ]
        )
        observed_live_todo_events: list[dict[str, Any]] = []

        class _StructuredExecutor:
            def __call__(self, command_text: str):
                payload = json.loads(command_text)
                arguments = dict(payload.get("arguments") or {})
                return "Plan updated", [
                    ToolEvent(
                        name="update_plan", ok=True, summary="Plan updated", payload=arguments
                    )
                ]

            def run_structured(self, command_text: str) -> CommandExecutionResult:
                payload = json.loads(command_text)
                arguments = dict(payload.get("arguments") or {})
                return CommandExecutionResult(
                    assistant_text="Plan updated",
                    tool_events=[
                        ToolEvent(
                            name="update_plan", ok=True, summary="Plan updated", payload=arguments
                        )
                    ],
                    item_events=[],
                )

        def on_turn_event(event: dict[str, Any]) -> None:
            item = event.get("item") if isinstance(event, dict) else None
            if isinstance(item, dict) and item.get("type") == "todo_list":
                observed_live_todo_events.append(dict(event))

        engine = TurnEngine(
            session,
            tool_executor=_StructuredExecutor(),
            turn_event_callback=on_turn_event,
        )
        intent = engine.run(user_text="plan", initial_input=[{"role": "user", "content": "plan"}])

        live_signatures: list[str] = []
        for event in observed_live_todo_events:
            signature = json.dumps(event, ensure_ascii=False, sort_keys=True)
            if signature not in live_signatures:
                live_signatures.append(signature)
        deduped_live_todo_events = [json.loads(signature) for signature in live_signatures]

        self.assertEqual(
            [event["type"] for event in deduped_live_todo_events], ["item.started", "item.updated"]
        )
        live_item_ids = [event["item"]["id"] for event in deduped_live_todo_events]
        self.assertEqual(live_item_ids[0], live_item_ids[1])

        todo_turn_events = [
            event
            for event in intent.turn_events
            if isinstance(event.get("item"), dict) and event["item"].get("type") == "todo_list"
        ]
        self.assertEqual(
            [event["type"] for event in todo_turn_events],
            ["item.started", "item.updated", "item.completed"],
        )
        self.assertEqual(todo_turn_events[0]["item"]["id"], todo_turn_events[1]["item"]["id"])
        self.assertEqual(todo_turn_events[1]["item"]["id"], todo_turn_events[2]["item"]["id"])
        self.assertEqual(
            todo_turn_events[2]["item"]["items"],
            [
                {"text": "inspect", "completed": True},
                {"text": "patch", "completed": False},
            ],
        )

    def test_turn_engine_skips_synthetic_preamble_when_provider_already_sent_message(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="我先查看当前目录。",
                    tool_calls=[
                        ProviderToolCall(call_id="c1", name="list_dir", arguments={"dir_path": "."})
                    ],
                    response_items=[
                        response_message_item("assistant", "我先查看当前目录。", phase="commentary")
                    ],
                    trace={"streamed_message_count": 1},
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )
        observed: list[dict[str, Any]] = []

        def tool_executor(command_text: str):
            return "ok", [
                ToolEvent(name="list_dir", ok=True, summary="entries=1", payload={"dir_path": "."})
            ]

        engine = TurnEngine(
            session, tool_executor=tool_executor, turn_event_callback=observed.append
        )
        engine.run(user_text="list", initial_input=[{"role": "user", "content": "list"}])

        agent_messages = [
            event
            for event in observed
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "agent_message"
        ]
        self.assertEqual(agent_messages, [])

    def test_tool_loop_sends_textual_function_call_output_to_next_round(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="read_file", arguments={"file_path": "README.md"}
                        )
                    ],
                    continuation_input_items=[
                        {"role": "user", "content": "read"},
                        {
                            "type": "function_call",
                            "call_id": "c1",
                            "name": "read_file",
                            "arguments": '{"file_path":"README.md"}',
                        },
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={
                        "file_path": "README.md",
                        "text": "L1: hello\\nL2: world",
                        "line_count": 2,
                    },
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        engine.run(user_text="read file", initial_input=[{"role": "user", "content": "read"}])

        self.assertEqual(session.calls[1]["previous_response_id"], "r1")
        self.assertEqual(
            session.calls[1]["input"][-1],
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": "L1: hello\\nL2: world",
                "success": True,
            },
        )
        self.assertEqual(
            session.calls[1]["input"][:2],
            [
                {"role": "user", "content": "read"},
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "read_file",
                    "arguments": '{"file_path":"README.md"}',
                },
            ],
        )

    def test_tool_loop_uses_incremental_continuation_when_session_supports_it(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="read_file", arguments={"file_path": "README.md"}
                        )
                    ],
                    continuation_input_items=[
                        {"role": "user", "content": "read"},
                        {
                            "type": "function_call",
                            "call_id": "c1",
                            "name": "read_file",
                            "arguments": '{"file_path":"README.md"}',
                        },
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )
        session.incremental_continuation = True

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"file_path": "README.md", "text": "L1: hello"},
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        engine.run(user_text="read file", initial_input=[{"role": "user", "content": "read"}])

        self.assertEqual(session.calls[1]["previous_response_id"], "r1")
        self.assertEqual(
            session.calls[1]["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "L1: hello",
                    "success": True,
                }
            ],
        )

    def test_tool_loop_request_user_input_without_handler_cancels_immediately(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="request_user_input",
                            arguments={
                                "questions": [
                                    {
                                        "id": "confirm_path",
                                        "header": "Confirm",
                                        "question": "Proceed?",
                                        "options": [
                                            {
                                                "label": "Yes (Recommended)",
                                                "description": "Continue.",
                                            },
                                            {"label": "No", "description": "Stop."},
                                        ],
                                    }
                                ]
                            },
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )
        runtime = _request_user_input_runtime(handler=None)

        class _StructuredExecutor:
            def __call__(self, command_text: str):
                raise AssertionError("structured runner should be used")

            def run_structured(self, command_text: str) -> CommandExecutionResult:
                return _runtime_command_result(runtime, command_text)

        engine = TurnEngine(
            session,
            tool_executor=_StructuredExecutor(),
            command_builder=_tool_call_runtime_command,
        )
        intent = engine.run(
            user_text="please confirm",
            initial_input=[{"role": "user", "content": "please confirm"}],
        )

        self.assertEqual(intent.assistant_text, "done")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1]["previous_response_id"], "r1")
        output_item = session.calls[1]["input"][0]
        self.assertEqual(output_item["type"], "function_call_output")
        self.assertEqual(output_item["call_id"], "c1")
        self.assertFalse(output_item["success"])
        self.assertIn(
            "request_user_input was cancelled before receiving a response",
            _function_call_output_text(output_item["output"]),
        )
        self.assertEqual(intent.tool_events[0].name, "request_user_input")
        self.assertFalse(intent.tool_events[0].ok)
        self.assertEqual(
            intent.tool_events[0].payload["error"],
            "request_user_input was cancelled before receiving a response",
        )
        completed_item = next(
            event
            for event in intent.turn_events
            if event["type"] == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("tool") == "request_user_input"
        )
        self.assertEqual(completed_item["item"]["status"], "failed")
        self.assertEqual(
            completed_item["item"]["error"]["message"],
            "request_user_input was cancelled before receiving a response",
        )

    def test_tool_loop_request_user_input_with_handler_preserves_canonical_answers(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="request_user_input",
                            arguments={
                                "questions": [
                                    {
                                        "id": "confirm_path",
                                        "header": "Confirm",
                                        "question": "Proceed?",
                                        "options": [
                                            {
                                                "label": "Yes (Recommended)",
                                                "description": "Continue.",
                                            },
                                            {"label": "No", "description": "Stop."},
                                        ],
                                    }
                                ]
                            },
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )
        runtime = _request_user_input_runtime(
            handler=lambda _payload: {
                "answers": {
                    "confirm_path": {"answers": ["yes"]},
                }
            }
        )

        class _StructuredExecutor:
            def __call__(self, command_text: str):
                raise AssertionError("structured runner should be used")

            def run_structured(self, command_text: str) -> CommandExecutionResult:
                return _runtime_command_result(runtime, command_text)

        engine = TurnEngine(
            session,
            tool_executor=_StructuredExecutor(),
            command_builder=_tool_call_runtime_command,
        )
        intent = engine.run(
            user_text="please confirm",
            initial_input=[{"role": "user", "content": "please confirm"}],
        )

        self.assertEqual(intent.assistant_text, "done")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1]["previous_response_id"], "r1")
        output_item = session.calls[1]["input"][0]
        self.assertEqual(output_item["type"], "function_call_output")
        self.assertEqual(output_item["call_id"], "c1")
        self.assertTrue(output_item["success"])
        output_payload = _request_user_input_output_payload(output_item["output"])
        self.assertEqual(
            output_payload["answers"]["confirm_path"]["answers"],
            ["yes"],
        )
        completed_item = next(
            event
            for event in intent.turn_events
            if event["type"] == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("tool") == "request_user_input"
        )
        self.assertEqual(completed_item["item"]["status"], "completed")
        self.assertEqual(
            completed_item["item"]["result"]["structured_content"]["response"]["answers"][
                "confirm_path"
            ]["answers"],
            ["yes"],
        )

    def test_continuation_failure_uses_followup(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="file_read", arguments={"path": "README.md"}
                        )
                    ],
                    response_id="r1",
                ),
                RuntimeError("proxy_unavailable"),
            ]
        )

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(name="file_read", ok=True, summary="read", payload={"path": "README.md"})
            ]

        def followup_handler(user_text: str, events: list[ToolEvent]) -> AgentIntent:
            return AgentIntent(
                assistant_text="fallback answer",
                command_text=None,
                status_hint="tool",
                tool_events=events,
            )

        engine = TurnEngine(session, tool_executor=tool_executor, followup_handler=followup_handler)
        intent = engine.run(
            user_text="read file", initial_input=[{"role": "user", "content": "read"}]
        )

        self.assertEqual(intent.assistant_text, "fallback answer")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1]["previous_response_id"], "r1")

    def test_empty_final_output_uses_followup_after_tool_loop(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="file_read", arguments={"path": "README.md"}
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(output_text="", tool_calls=[], response_id="r2"),
            ]
        )

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(name="file_read", ok=True, summary="read", payload={"path": "README.md"})
            ]

        def terminal_handler(user_text: str, events: list[ToolEvent]) -> AgentIntent:
            return AgentIntent(
                assistant_text="synthesized answer",
                command_text=None,
                status_hint="tool",
                tool_events=events,
                timings={"synthesis_model_ms": 12, "synthesis_rounds": 1},
            )

        engine = TurnEngine(session, tool_executor=tool_executor, terminal_handler=terminal_handler)
        intent = engine.run(
            user_text="read file", initial_input=[{"role": "user", "content": "read"}]
        )

        self.assertEqual(intent.assistant_text, "synthesized answer")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)
        self.assertEqual(intent.timings["synthesis_rounds"], 1)

    def test_turn_engine_stops_current_round_after_shell_approval_request(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="exec_command", arguments={"cmd": "write-file"}
                        ),
                        ProviderToolCall(
                            call_id="c2",
                            name="exec_command",
                            arguments={"cmd": "which apply_patch"},
                        ),
                    ],
                    response_id="r1",
                ),
            ]
        )
        observed_commands: list[str] = []

        def tool_executor(command_text: str):
            observed_commands.append(command_text)
            if command_text == "write-file":
                return CommandExecutionResult(
                    assistant_text="Request shell approval.",
                    tool_events=[
                        ToolEvent(
                            name="shell_approval_requested",
                            ok=True,
                            summary="shell approval requested appr_1",
                            payload={
                                "approval_id": "appr_1",
                                "command": "printf 'print(\"Hello, world!\")\\n' > helloworld.py",
                                "available_decisions": [
                                    {"type": "accept"},
                                    {"type": "accept_for_session"},
                                    {"type": "decline"},
                                ],
                            },
                        )
                    ],
                )
            return CommandExecutionResult(
                assistant_text="should not run",
                tool_events=[
                    ToolEvent(
                        name="exec_command",
                        ok=True,
                        summary="unexpected followup execution",
                        payload={"command": command_text},
                    )
                ],
            )

        engine = TurnEngine(
            session,
            tool_executor=tool_executor,
            command_builder=lambda _name, arguments: str(arguments.get("cmd") or ""),
        )

        intent = engine.run(
            user_text="create helloworld",
            initial_input=[{"role": "user", "content": "create"}],
        )

        self.assertEqual(observed_commands, ["write-file"])
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(intent.tool_events[-1].name, "shell_approval_requested")
        self.assertIn("已提交命令审批：appr_1", intent.assistant_text)
        self.assertIn("/approve appr_1", intent.assistant_text)

    def test_tool_execution_loop_batch_stops_after_approval_request(self) -> None:
        harness = _BatchToolLoopHarness()
        observed_commands: list[str] = []

        def tool_executor(command_text: str):
            observed_commands.append(command_text)
            if command_text == "write-file":
                return CommandExecutionResult(
                    assistant_text="Request shell approval.",
                    tool_events=[
                        ToolEvent(
                            name="shell_approval_requested",
                            ok=True,
                            summary="shell approval requested appr_2",
                            payload={"approval_id": "appr_2"},
                        )
                    ],
                )
            return CommandExecutionResult(
                assistant_text="should not run",
                tool_events=[
                    ToolEvent(
                        name="exec_command",
                        ok=True,
                        summary="unexpected followup execution",
                        payload={"command": command_text},
                    )
                ],
            )

        tool_calls = [
            SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(
                    name="exec_command",
                    arguments=json.dumps({"cmd": "write-file"}, ensure_ascii=False),
                ),
            ),
            SimpleNamespace(
                id="call_2",
                function=SimpleNamespace(
                    name="exec_command",
                    arguments=json.dumps({"cmd": "which apply_patch"}, ensure_ascii=False),
                ),
            ),
        ]

        results, _elapsed_ms = harness._execute_tool_call_batch(
            tool_calls, tool_executor=tool_executor
        )

        self.assertEqual(observed_commands, ["write-file"])
        self.assertEqual(len(results), 1)
        self.assertEqual(
            [event.name for event in results[0]["events"]], ["shell_approval_requested"]
        )

    def test_non_text_response_items_after_tool_loop_still_use_terminal_handler(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="file_read", arguments={"path": "README.md"}
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[],
                    response_items=[
                        ResponseInputItem.from_dict(
                            {
                                "type": "function_call_output",
                                "call_id": "c1",
                                "output": '{"ok": true}',
                            }
                        )
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(name="file_read", ok=True, summary="read", payload={"path": "README.md"})
            ]

        def terminal_handler(user_text: str, events: list[ToolEvent]) -> AgentIntent:
            return AgentIntent(
                assistant_text="synthesized answer",
                command_text=None,
                status_hint="tool",
                tool_events=events,
                timings={"synthesis_model_ms": 9, "synthesis_rounds": 1},
            )

        engine = TurnEngine(session, tool_executor=tool_executor, terminal_handler=terminal_handler)
        intent = engine.run(
            user_text="read file", initial_input=[{"role": "user", "content": "read"}]
        )

        self.assertEqual(intent.assistant_text, "synthesized answer")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)
        self.assertEqual(intent.timings["synthesis_rounds"], 1)

    def test_followup_handler_can_receive_executed_item_events(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(call_id="c1", name="shell", arguments={"cmd": "pwd"})
                    ],
                    response_id="r1",
                ),
                RuntimeError("proxy_unavailable"),
            ]
        )
        observed_item_events: list[dict[str, Any]] = []

        class _StructuredExecutor:
            def __call__(self, command_text: str):
                return "compat", [
                    ToolEvent(
                        name="shell",
                        ok=True,
                        summary="shell rc=0",
                        payload={"command": command_text},
                    )
                ]

            def run_structured(self, command_text: str) -> CommandExecutionResult:
                return CommandExecutionResult(
                    assistant_text="compat",
                    tool_events=[
                        ToolEvent(
                            name="shell",
                            ok=True,
                            summary="shell rc=0",
                            payload={"command": command_text},
                        )
                    ],
                    item_events=[
                        {
                            "type": "item.started",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "aggregated_output": "",
                                "exit_code": None,
                                "status": "in_progress",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "aggregated_output": "/tmp",
                                "exit_code": 0,
                                "status": "completed",
                            },
                        },
                    ],
                )

        def followup_handler(
            user_text: str,
            events: list[ToolEvent],
            executed_item_events: list[dict[str, Any]],
        ) -> AgentIntent:
            observed_item_events.extend(executed_item_events)
            return AgentIntent(
                assistant_text="fallback answer",
                command_text=None,
                status_hint="tool",
                tool_events=events,
            )

        engine = TurnEngine(
            session, tool_executor=_StructuredExecutor(), followup_handler=followup_handler
        )
        intent = engine.run(user_text="pwd", initial_input=[{"role": "user", "content": "pwd"}])

        self.assertEqual(intent.assistant_text, "fallback answer")
        self.assertTrue(observed_item_events)
        completed = next(
            event
            for event in observed_item_events
            if event["type"] == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "command_execution"
        )
        self.assertEqual(completed["item"]["aggregated_output"], "/tmp")

    def test_followup_handler_can_receive_native_continuation_state(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="read_file", arguments={"file_path": "README.md"}
                        )
                    ],
                    response_id="resp_prev",
                ),
                RuntimeError("proxy_unavailable"),
            ]
        )
        observed_previous_response_id: str | None = None
        observed_input_items: list[dict[str, Any]] = []

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"file_path": "README.md", "text": "L1: hello"},
                )
            ]

        def followup_handler(
            user_text: str,
            events: list[ToolEvent],
            executed_item_events: list[dict[str, Any]],
            previous_response_id: str | None,
            continuation_input_items: list[dict[str, Any]],
        ) -> AgentIntent:
            nonlocal observed_previous_response_id, observed_input_items
            observed_previous_response_id = previous_response_id
            observed_input_items = list(continuation_input_items)
            return AgentIntent(
                assistant_text="fallback answer",
                command_text=None,
                status_hint="tool",
                tool_events=events,
            )

        engine = TurnEngine(session, tool_executor=tool_executor, followup_handler=followup_handler)
        intent = engine.run(
            user_text="read file", initial_input=[{"role": "user", "content": "read"}]
        )

        self.assertEqual(intent.assistant_text, "fallback answer")
        self.assertEqual(observed_previous_response_id, "resp_prev")
        self.assertEqual(
            observed_input_items,
            [
                {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "L1: hello",
                    "success": True,
                }
            ],
        )

    def test_followup_handler_receives_full_replay_items_when_incremental_retry_fails(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="read_file", arguments={"file_path": "README.md"}
                        )
                    ],
                    response_id="resp_prev",
                    continuation_input_items=[
                        {
                            "type": "function_call",
                            "call_id": "c1",
                            "name": "read_file",
                            "arguments": json.dumps({"file_path": "README.md"}),
                        }
                    ],
                ),
                RuntimeError("unsupported parameter: previous_response_id"),
            ]
        )
        session.incremental_continuation = True
        observed_input_items: list[dict[str, Any]] = []

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"file_path": "README.md", "text": "L1: hello"},
                )
            ]

        def followup_handler(
            user_text: str,
            events: list[ToolEvent],
            executed_item_events: list[dict[str, Any]],
            previous_response_id: str | None,
            continuation_input_items: list[dict[str, Any]],
        ) -> AgentIntent:
            del user_text, events, executed_item_events, previous_response_id
            nonlocal observed_input_items
            observed_input_items = list(continuation_input_items)
            return AgentIntent(
                assistant_text="fallback answer", command_text=None, status_hint="tool"
            )

        engine = TurnEngine(session, tool_executor=tool_executor, followup_handler=followup_handler)
        intent = engine.run(
            user_text="read file", initial_input=[{"role": "user", "content": "read"}]
        )

        self.assertEqual(intent.assistant_text, "fallback answer")
        self.assertEqual(
            observed_input_items,
            [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "read_file",
                    "arguments": json.dumps({"file_path": "README.md"}),
                },
                {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "L1: hello",
                    "success": True,
                },
            ],
        )

    def test_followup_handler_can_receive_initial_send_error_on_incremental_failure(self) -> None:
        send_error = RuntimeError("unsupported parameter: previous_response_id")
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="read_file", arguments={"file_path": "README.md"}
                        )
                    ],
                    response_id="resp_prev",
                ),
                send_error,
            ]
        )
        session.incremental_continuation = True
        observed_error: Exception | None = None

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"file_path": "README.md", "text": "L1: hello"},
                )
            ]

        def followup_handler(
            user_text: str,
            events: list[ToolEvent],
            executed_item_events: list[dict[str, Any]],
            previous_response_id: str | None,
            continuation_input_items: list[dict[str, Any]],
            initial_send_error: Exception | None,
        ) -> AgentIntent:
            del (
                user_text,
                events,
                executed_item_events,
                previous_response_id,
                continuation_input_items,
            )
            nonlocal observed_error
            observed_error = initial_send_error
            return AgentIntent(
                assistant_text="fallback answer", command_text=None, status_hint="tool"
            )

        engine = TurnEngine(session, tool_executor=tool_executor, followup_handler=followup_handler)
        intent = engine.run(
            user_text="read file", initial_input=[{"role": "user", "content": "read"}]
        )

        self.assertEqual(intent.assistant_text, "fallback answer")
        self.assertIs(observed_error, send_error)

    def test_terminal_handler_receives_rescue_events_when_send_fails_without_followup_handler(
        self,
    ) -> None:
        send_error = RuntimeError("provider 503")
        initial_event = ToolEvent(
            name="exec_command",
            ok=True,
            summary="exec_command exited",
            payload={"command": "rg --files"},
        )
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c2",
                            name="apply_patch",
                            arguments={
                                "patch": "*** Begin Patch\n*** Add File: helloworld.py\n+print('hi')\n*** End Patch"
                            },
                        )
                    ],
                    response_id="resp_patch",
                ),
                send_error,
            ]
        )
        observed_events: list[ToolEvent] = []
        observed_error: Exception | None = None

        def tool_executor(command_text: str):
            del command_text
            return "patch applied", [
                ToolEvent(
                    name="apply_patch",
                    ok=True,
                    summary="apply_patch files=1",
                    payload={
                        "file_count": 1,
                        "changes": [{"path": "helloworld.py", "change_type": "add"}],
                    },
                )
            ]

        def terminal_handler(
            user_text: str,
            events: list[ToolEvent],
            executed_item_events: list[dict[str, Any]],
            previous_response_id: str | None,
            continuation_input_items: list[dict[str, Any]],
            initial_send_error: Exception | None,
        ) -> AgentIntent:
            del user_text, executed_item_events, previous_response_id, continuation_input_items
            nonlocal observed_events, observed_error
            observed_events = list(events)
            observed_error = initial_send_error
            return AgentIntent(
                assistant_text="fallback answer",
                command_text=None,
                status_hint="tool",
                tool_events=list(events),
            )

        engine = TurnEngine(
            session,
            tool_executor=tool_executor,
            command_builder=lambda name, arguments: f"/{name}",
            terminal_handler=terminal_handler,
        )
        intent = engine.run(
            user_text="create file",
            initial_input=[{"role": "user", "content": "create"}],
            initial_previous_response_id="resp_rg",
            initial_executed_events=[initial_event],
        )

        self.assertEqual(intent.assistant_text, "fallback answer")
        self.assertIs(observed_error, send_error)
        self.assertEqual([event.name for event in observed_events], ["exec_command", "apply_patch"])
        self.assertEqual(
            [event.name for event in intent.tool_events], ["exec_command", "apply_patch"]
        )

    def test_provider_native_incomplete_round_continues_without_local_tool_calls(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="我来查一下北京今天的天气。",
                    tool_calls=[],
                    response_items=[],
                    continuation_input_items=[
                        {"role": "user", "content": "北京今天天气怎么样？"},
                        {
                            "type": "web_search_call",
                            "status": "completed",
                            "action": {"type": "search", "query": "北京 今天天气"},
                        },
                    ],
                    response_id="resp_partial",
                    trace={
                        "tool_calls": [],
                        "tool_call_count": 0,
                        "answered": False,
                        "answer_preview": "",
                        "provider_native_item_types": ["web_search_call"],
                        "provider_native_item_count": 1,
                        "provider_native_continuation_pending": True,
                        "response_status": "incomplete",
                        "has_final_message": False,
                    },
                ),
                ProviderSessionResult(
                    output_text="北京今天多云，16°C。",
                    tool_calls=[],
                    response_items=[
                        response_message_item(
                            "assistant", "北京今天多云，16°C。", phase="final_answer"
                        )
                    ],
                    response_id="resp_final",
                ),
            ]
        )

        engine = TurnEngine(session, tool_executor=lambda command_text: ("ok", []))
        intent = engine.run(
            user_text="北京今天天气怎么样？",
            initial_input=[{"role": "user", "content": "北京今天天气怎么样？"}],
        )

        self.assertEqual(intent.assistant_text, "北京今天多云，16°C。")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1]["previous_response_id"], "resp_partial")
        self.assertEqual(
            session.calls[1]["input"],
            [
                {"role": "user", "content": "北京今天天气怎么样？"},
                {
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {"type": "search", "query": "北京 今天天气"},
                },
            ],
        )

    def test_turn_engine_projects_write_stdin_followup_as_native_write_stdin(self) -> None:
        write_arguments = {
            "session_id": "session_1",
            "chars": "",
            "yield_time_ms": 1000,
            "max_output_tokens": 4000,
        }
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="call_write_provider_1",
                            name="write_stdin",
                            arguments=dict(write_arguments),
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def command_builder(name: str, arguments: dict[str, Any]) -> str | None:
            if name != "write_stdin":
                return None
            chars = str(arguments.get("chars") or "")
            return (
                f"/write_stdin {arguments['session_id']} {json.dumps(chars)} "
                f"--yield-time-ms {arguments['yield_time_ms']} --max-output-tokens {arguments['max_output_tokens']}"
            )

        def tool_executor(command_text: str) -> CommandExecutionResult:
            del command_text
            event = ToolEvent(
                name="write_stdin",
                ok=True,
                summary="write_stdin running session_1",
                payload={
                    "session_id": "session_1",
                    "call_id": "session_shell_call_1",
                    "process_id": None,
                    "status": "missing",
                    "command": "",
                    "function_call_output": "Process running with session ID session_1\nOutput:\n",
                },
            )
            return CommandExecutionResult(
                assistant_text="",
                tool_events=[event],
                item_events=shell_tool_call_item_events(event, command=""),
            )

        engine = TurnEngine(session, tool_executor=tool_executor, command_builder=command_builder)
        intent = engine.run(
            user_text="poll session",
            initial_input=[{"role": "user", "content": "poll session"}],
        )

        projected = response_items_with_tool_outputs(
            [item.to_dict() for item in list(intent.response_items or [])],
            list(intent.turn_events or []),
            list(intent.tool_events or []),
        )

        write_call = next(
            item
            for item in projected
            if item.get("type") == "function_call" and item.get("name") == "write_stdin"
        )
        write_output = next(
            item
            for item in projected
            if item.get("type") == "function_call_output"
            and item.get("call_id") == write_call.get("call_id")
        )

        self.assertEqual(write_call["call_id"], "call_write_provider_1")
        self.assertEqual(
            write_call["arguments"],
            '{"session_id": "session_1", "chars": "", "yield_time_ms": 1000, "max_output_tokens": 4000}',
        )
        self.assertEqual(
            write_output["output"],
            "Process running with session ID session_1\nOutput:\n",
        )

    def test_provider_native_continuation_with_response_id_preserves_mixed_replay_items_for_incremental_transport(
        self,
    ) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="我先查一下。",
                    tool_calls=[],
                    response_items=[
                        ResponseInputItem(
                            item_type="message",
                            role="assistant",
                            content=[{"type": "output_text", "text": "我先查一下。"}],
                            extra={"id": "msg_1", "phase": "commentary"},
                        ),
                        ResponseInputItem(
                            item_type="web_search_call",
                            content="",
                            extra={
                                "id": "ws_1",
                                "status": "completed",
                                "action": {"type": "search", "query": "北京 今天天气"},
                            },
                        ),
                    ],
                    continuation_input_items=[
                        {
                            "type": "message",
                            "id": "msg_1",
                            "role": "assistant",
                            "phase": "commentary",
                            "content": [{"type": "output_text", "text": "我先查一下。"}],
                        },
                        {
                            "type": "web_search_call",
                            "id": "ws_1",
                            "status": "completed",
                            "action": {"type": "search", "query": "北京 今天天气"},
                        },
                    ],
                    response_id="resp_partial",
                    trace={
                        "tool_calls": [],
                        "tool_call_count": 0,
                        "answered": False,
                        "answer_preview": "",
                        "provider_native_item_types": ["web_search_call"],
                        "provider_native_item_count": 1,
                        "provider_native_continuation_pending": True,
                        "provider_native_continuation_reason": "native_item_incomplete",
                        "provider_native_interrupted": True,
                        "provider_native_outcome": "native_interrupted",
                        "provider_native_retryable": True,
                        "response_status": "incomplete",
                        "has_final_message": False,
                    },
                ),
                ProviderSessionResult(
                    output_text="北京今天多云，16°C。",
                    tool_calls=[],
                    response_items=[
                        response_message_item(
                            "assistant", "北京今天多云，16°C。", phase="final_answer"
                        )
                    ],
                    response_id="resp_final",
                ),
            ]
        )
        session.incremental_continuation = True

        engine = TurnEngine(session, tool_executor=lambda command_text: ("ok", []))
        intent = engine.run(
            user_text="北京今天天气怎么样？",
            initial_input=[{"role": "user", "content": "北京今天天气怎么样？"}],
        )

        self.assertEqual(intent.assistant_text, "北京今天多云，16°C。")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1]["previous_response_id"], "resp_partial")
        self.assertEqual(
            session.calls[1]["input"],
            [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "我先查一下。"}],
                },
                {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                    "action": {"type": "search", "query": "北京 今天天气"},
                },
            ],
        )

    def test_provider_native_continuation_with_response_id_preserves_partial_mixed_resume_snapshot(
        self,
    ) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="我先查一下。",
                    tool_calls=[],
                    response_items=[
                        ResponseInputItem(
                            item_type="message",
                            role="assistant",
                            content=[{"type": "output_text", "text": "我先查一下。"}],
                            extra={"id": "msg_1", "phase": "commentary"},
                        ),
                        ResponseInputItem(
                            item_type="web_search_call",
                            content="",
                            extra={
                                "id": "ws_1",
                                "status": "in_progress",
                                "action": {"type": "search", "query": "北京 今天天气"},
                            },
                        ),
                    ],
                    continuation_input_items=[
                        {
                            "type": "message",
                            "id": "msg_1",
                            "role": "assistant",
                            "phase": "commentary",
                            "content": [{"type": "output_text", "text": "我先查一下。"}],
                        },
                        {
                            "type": "web_search_call",
                            "id": "ws_1",
                            "status": "in_progress",
                            "action": {"type": "search", "query": "北京 今天天气"},
                        },
                    ],
                    response_id="resp_partial",
                    trace={
                        "tool_calls": [],
                        "tool_call_count": 0,
                        "answered": False,
                        "answer_preview": "",
                        "provider_native_item_types": ["web_search_call"],
                        "provider_native_item_count": 1,
                        "provider_native_continuation_pending": True,
                        "provider_native_continuation_reason": "native_item_incomplete",
                        "provider_native_interrupted": True,
                        "provider_native_outcome": "native_interrupted",
                        "provider_native_retryable": True,
                        "response_status": "interrupted",
                        "has_final_message": False,
                    },
                ),
                ProviderSessionResult(
                    output_text="北京今天多云，16°C。",
                    tool_calls=[],
                    response_items=[
                        response_message_item(
                            "assistant", "北京今天多云，16°C。", phase="final_answer"
                        )
                    ],
                    response_id="resp_final",
                ),
            ]
        )
        session.incremental_continuation = True

        engine = TurnEngine(session, tool_executor=lambda command_text: ("ok", []))
        intent = engine.run(
            user_text="北京今天天气怎么样？",
            initial_input=[{"role": "user", "content": "北京今天天气怎么样？"}],
        )

        self.assertEqual(intent.assistant_text, "北京今天多云，16°C。")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1]["previous_response_id"], "resp_partial")
        self.assertEqual(
            session.calls[1]["input"],
            [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "我先查一下。"}],
                },
                {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "in_progress",
                    "action": {"type": "search", "query": "北京 今天天气"},
                },
            ],
        )

    def test_provider_native_continuation_without_response_id_replays_full_input_even_when_incremental_transport_is_available(
        self,
    ) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[],
                    response_items=[
                        ResponseInputItem(
                            item_type="web_search_call",
                            content="",
                            extra={
                                "id": "ws_1",
                                "status": "completed",
                                "action": {"type": "search", "query": "北京 今天天气"},
                            },
                        )
                    ],
                    continuation_input_items=[
                        {"role": "user", "content": "北京今天天气怎么样？"},
                        {
                            "type": "web_search_call",
                            "id": "ws_1",
                            "status": "completed",
                            "action": {"type": "search", "query": "北京 今天天气"},
                        },
                    ],
                    response_id=None,
                    trace={
                        "tool_calls": [],
                        "tool_call_count": 0,
                        "answered": False,
                        "answer_preview": "",
                        "provider_native_item_types": ["web_search_call"],
                        "provider_native_item_count": 1,
                        "provider_native_continuation_pending": True,
                        "provider_native_continuation_reason": "native_item_incomplete",
                        "provider_native_interrupted": True,
                        "provider_native_outcome": "native_interrupted",
                        "provider_native_retryable": True,
                        "response_status": "interrupted",
                        "has_final_message": False,
                    },
                ),
                ProviderSessionResult(
                    output_text="北京今天多云，16°C。",
                    tool_calls=[],
                    response_items=[
                        response_message_item(
                            "assistant", "北京今天多云，16°C。", phase="final_answer"
                        )
                    ],
                    response_id="resp_final",
                ),
            ]
        )
        session.incremental_continuation = True

        engine = TurnEngine(session, tool_executor=lambda command_text: ("ok", []))
        intent = engine.run(
            user_text="北京今天天气怎么样？",
            initial_input=[{"role": "user", "content": "北京今天天气怎么样？"}],
        )

        self.assertEqual(intent.assistant_text, "北京今天多云，16°C。")
        self.assertEqual(len(session.calls), 2)
        self.assertIsNone(session.calls[1]["previous_response_id"])
        self.assertEqual(
            session.calls[1]["input"],
            [
                {"role": "user", "content": "北京今天天气怎么样？"},
                {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                    "action": {"type": "search", "query": "北京 今天天气"},
                },
            ],
        )

    def test_followup_fallback_total_ms_uses_wall_clock_elapsed_time(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="read_file", arguments={"file_path": "README.md"}
                        )
                    ],
                    response_id="resp_prev",
                ),
                RuntimeError("proxy_unavailable"),
            ]
        )

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={
                        "file_path": "README.md",
                        "text": "L1: hello",
                        "command": command_text,
                    },
                )
            ]

        perf_values = iter([0, 1, 11, 12, 13, 18, 20, 21, 100])

        def perf_counter() -> float:
            return float(next(perf_values))

        def followup_handler(
            user_text: str,
            events: list[ToolEvent],
            executed_item_events: list[dict[str, Any]],
            previous_response_id: str | None,
            continuation_input_items: list[dict[str, Any]],
        ) -> AgentIntent:
            del user_text, executed_item_events, previous_response_id, continuation_input_items
            return AgentIntent(
                assistant_text="fallback answer",
                command_text=None,
                status_hint="tool",
                tool_events=events,
                timings={"synthesis_model_ms": 7, "synthesis_rounds": 1},
            )

        engine = TurnEngine(
            session,
            tool_executor=tool_executor,
            followup_handler=followup_handler,
            perf_counter_fn=perf_counter,
        )
        intent = engine.run(
            user_text="read file", initial_input=[{"role": "user", "content": "read"}]
        )

        self.assertEqual(intent.assistant_text, "fallback answer")
        self.assertEqual(intent.timings["initial_model_ms"], 10000)
        self.assertEqual(intent.timings["tool_execution_ms"], 8000)
        self.assertEqual(intent.timings["total_ms"], 100000)
        self.assertGreaterEqual(intent.timings["synthesis_model_ms"], 7)

    def test_max_rounds_exhaustion_uses_followup_before_tool_summary_fallback(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1", name="file_search", arguments={"query": "provider"}
                        )
                    ],
                    response_id="r1",
                )
            ]
        )

        def tool_executor(command_text: str):
            return "search ok", [
                ToolEvent(
                    name="file_search", ok=True, summary="search", payload={"query": "provider"}
                )
            ]

        def terminal_handler(user_text: str, events: list[ToolEvent]) -> AgentIntent:
            return AgentIntent(
                assistant_text="final from followup",
                command_text=None,
                status_hint="tool",
                tool_events=events,
            )

        engine = TurnEngine(
            session,
            tool_executor=tool_executor,
            terminal_handler=terminal_handler,
            max_rounds=1,
        )
        intent = engine.run(
            user_text="find provider", initial_input=[{"role": "user", "content": "find"}]
        )

        self.assertEqual(intent.assistant_text, "final from followup")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)

    def test_final_response_items_become_assistant_text_when_output_text_empty(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[],
                    response_items=[
                        response_message_item(
                            "assistant", "provider native answer", phase="final_answer"
                        )
                    ],
                    response_id="r1",
                )
            ]
        )

        engine = TurnEngine(session, tool_executor=lambda _command_text: ("", []))
        intent = engine.run(user_text="hello", initial_input=[{"role": "user", "content": "hello"}])

        self.assertEqual(intent.assistant_text, "provider native answer")
        self.assertEqual(intent.response_items[0].extra["phase"], "final_answer")
        self.assertEqual(intent.status_hint, "llm")

    def test_turn_engine_prefers_structured_tool_executor_item_events(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(call_id="c1", name="shell", arguments={"cmd": "pwd"})
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        class _StructuredExecutor:
            def __call__(self, command_text: str):
                return "compat", [
                    ToolEvent(
                        name="shell",
                        ok=True,
                        summary="shell rc=0",
                        payload={"command": command_text},
                    )
                ]

            def run_structured(self, command_text: str) -> CommandExecutionResult:
                return CommandExecutionResult(
                    assistant_text="compat",
                    tool_events=[
                        ToolEvent(
                            name="shell",
                            ok=True,
                            summary="shell rc=0",
                            payload={"command": command_text},
                        )
                    ],
                    item_events=[
                        {
                            "type": "item.started",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "aggregated_output": "",
                                "exit_code": None,
                                "status": "in_progress",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "aggregated_output": "/tmp",
                                "exit_code": 0,
                                "status": "completed",
                            },
                        },
                    ],
                )

        engine = TurnEngine(session, tool_executor=_StructuredExecutor())
        intent = engine.run(user_text="pwd", initial_input=[{"role": "user", "content": "pwd"}])

        self.assertEqual(intent.turn_events[0]["type"], "turn.started")
        command_completed = next(
            event
            for event in intent.turn_events
            if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
        )
        self.assertEqual(command_completed["item"]["aggregated_output"], "/tmp")

    def test_turn_engine_rebases_item_ids_across_multiple_tool_calls(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(call_id="c1", name="shell", arguments={"cmd": "pwd"}),
                        ProviderToolCall(call_id="c2", name="shell", arguments={"cmd": "ls"}),
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        class _StructuredExecutor:
            def __call__(self, command_text: str):
                return "compat", [
                    ToolEvent(
                        name="shell",
                        ok=True,
                        summary="shell rc=0",
                        payload={"command": command_text},
                    )
                ]

            def run_structured(self, command_text: str) -> CommandExecutionResult:
                return CommandExecutionResult(
                    assistant_text="compat",
                    tool_events=[
                        ToolEvent(
                            name="shell",
                            ok=True,
                            summary="shell rc=0",
                            payload={"command": command_text},
                        )
                    ],
                    item_events=[
                        {
                            "type": "item.started",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "aggregated_output": "",
                                "exit_code": None,
                                "status": "in_progress",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "aggregated_output": command_text,
                                "exit_code": 0,
                                "status": "completed",
                            },
                        },
                    ],
                )

        engine = TurnEngine(session, tool_executor=_StructuredExecutor())
        intent = engine.run(
            user_text="two calls", initial_input=[{"role": "user", "content": "two"}]
        )

        completed_ids = [
            event["item"]["id"]
            for event in intent.turn_events
            if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
        ]
        self.assertEqual(len(completed_ids), 2)
        self.assertEqual(len(set(completed_ids)), 2)
        parsed_ids = [int(item_id.split("_", 1)[1]) for item_id in completed_ids]
        self.assertEqual(parsed_ids[1], parsed_ids[0] + 1)

    def test_structured_turn_events_without_item_events_get_regridded(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(call_id="c1", name="shell", arguments={"cmd": "echo hi"})
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        class _StructuredExecutor:
            def __call__(self, command_text: str):
                return "compat", [
                    ToolEvent(
                        name="shell",
                        ok=True,
                        summary="shell rc=0",
                        payload={"command": command_text},
                    )
                ]

            def run_structured(self, command_text: str) -> CommandExecutionResult:
                return CommandExecutionResult(
                    assistant_text="compat",
                    tool_events=[
                        ToolEvent(
                            name="shell",
                            ok=True,
                            summary="shell rc=0",
                            payload={"command": command_text},
                        )
                    ],
                    item_events=[],
                    turn_events=[
                        {
                            "type": "turn.started",
                        },
                        {
                            "type": "item.started",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "status": "in_progress",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": command_text,
                                "aggregated_output": "echo hi",
                                "status": "completed",
                            },
                        },
                        {
                            "type": "turn.completed",
                        },
                    ],
                )

        engine = TurnEngine(session, tool_executor=_StructuredExecutor())
        intent = engine.run(
            user_text="echo hi", initial_input=[{"role": "user", "content": "echo hi"}]
        )

        self.assertEqual(intent.turn_events[0]["type"], "turn.started")
        completed_event = next(
            event
            for event in intent.turn_events
            if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
        )
        self.assertEqual(completed_event["item"]["aggregated_output"], "echo hi")

    def test_planning_trace_includes_spawn_agent_delegation_summary(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="spawn_agent",
                            arguments={
                                "task": "运行 benchmark 收集 provider 延迟数据",
                                "role": "subagent",
                                "async": True,
                            },
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "delegated", [
                ToolEvent(
                    name="spawn_agent",
                    ok=True,
                    summary="spawned",
                    payload={"command": command_text},
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(user_text="bench", initial_input=[{"role": "user", "content": "bench"}])

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_decision"], "delegate")
        self.assertEqual(trace["delegation_policy_decision"], "delegate_async")
        self.assertEqual(trace["delegation_policy_source"], "delegation_policy")
        self.assertEqual(trace["delegation_policy_reason"], "spawn_agent")
        self.assertEqual(trace["delegation_execution_mode"], "parallel")
        self.assertEqual(trace["delegation_execution_reason"], "task_shape:long_running")
        self.assertEqual(trace["delegation_control_action"], "continue")
        self.assertEqual(trace["delegation_control_reason"], "spawn_agent")
        self.assertTrue(trace["delegation_control_continue_main_thread"])
        self.assertFalse(trace["delegation_control_wait_for_child"])
        self.assertFalse(trace["delegation_control_stop_early"])
        self.assertEqual(trace["delegation_reason"], "long_running_exec")
        self.assertEqual(trace["delegation_mode"], "background")
        self.assertFalse(trace["wait_required"])
        self.assertEqual(trace["task_shape"], "long_running")
        self.assertEqual(trace["delegation_actions"][0]["tool_name"], "spawn_agent")
        self.assertEqual(trace["delegation_actions"][0]["execution_tool"], "spawn_agent")
        self.assertEqual(trace["delegation_actions"][0]["execution_mode"], "parallel")
        self.assertEqual(trace["delegation_actions"][0]["delegation_control_action"], "continue")
        self.assertTrue(trace["delegation_actions"][0]["async"])
        self.assertEqual(trace["delegation_actions"][0]["planner_policy"], "delegate_async")
        self.assertEqual(
            trace["delegation_actions"][0]["defaulted_fields"],
            ["reason", "mode", "wait_required", "task_shape"],
        )
        self.assertEqual(
            trace["delegation_actions"][0]["policy_basis"],
            "task_text_inference+delegation_policy_defaults",
        )

    def test_planning_trace_defaults_context_sensitive_teammate_to_delegate_sync(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="spawn_agent",
                            arguments={
                                "task": "Continue current task using current context and above conversation",
                                "role": "teammate",
                            },
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "delegated", [
                ToolEvent(
                    name="spawn_agent",
                    ok=True,
                    summary="spawned",
                    payload={"command": command_text},
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(
            user_text="followup", initial_input=[{"role": "user", "content": "followup"}]
        )

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_policy_decision"], "delegate_sync")
        self.assertEqual(trace["delegation_execution_mode"], "serial")
        self.assertEqual(trace["delegation_execution_reason"], "task_shape:context_sensitive")
        self.assertEqual(trace["delegation_control_action"], "downgrade")
        self.assertTrue(trace["delegation_control_continue_main_thread"])
        self.assertEqual(trace["delegation_actions"][0]["planner_policy"], "delegate_sync")
        self.assertEqual(trace["delegation_actions"][0]["execution_mode"], "serial")
        self.assertEqual(trace["delegation_actions"][0]["delegation_control_action"], "downgrade")
        self.assertEqual(trace["delegation_actions"][0]["task_shape"], "context_sensitive")

    def test_planning_trace_defaults_long_running_subagent_to_delegate_async(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="spawn_agent",
                            arguments={
                                "task": "运行 benchmark 收集 provider 延迟数据",
                                "role": "subagent",
                            },
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "delegated", [
                ToolEvent(
                    name="spawn_agent",
                    ok=True,
                    summary="spawned",
                    payload={"command": command_text},
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(user_text="bench", initial_input=[{"role": "user", "content": "bench"}])

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_policy_decision"], "delegate_async")
        self.assertEqual(trace["delegation_execution_mode"], "parallel")
        self.assertEqual(trace["delegation_execution_reason"], "task_shape:long_running")
        self.assertEqual(trace["delegation_actions"][0]["planner_policy"], "delegate_async")
        self.assertEqual(trace["delegation_actions"][0]["execution_mode"], "parallel")
        self.assertEqual(trace["delegation_actions"][0]["task_shape"], "long_running")
        self.assertIn("async", trace["delegation_actions"][0]["defaulted_fields"])

    def test_planning_trace_includes_wait_agent_summary(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="wait_agent",
                            arguments={"target": "agent_1"},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "joined", [
                ToolEvent(
                    name="wait_agent", ok=True, summary="joined", payload={"command": command_text}
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(user_text="join", initial_input=[{"role": "user", "content": "join"}])

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_decision"], "wait_now")
        self.assertEqual(trace["delegation_policy_decision"], "wait_now")
        self.assertEqual(trace["delegation_policy_source"], "delegation_policy")
        self.assertEqual(trace["delegation_policy_reason"], "wait_agent_blocking_join")
        self.assertEqual(trace["delegation_execution_mode"], "serial")
        self.assertEqual(trace["delegation_execution_reason"], "wait_required:true")
        self.assertEqual(trace["delegation_control_action"], "wait")
        self.assertFalse(trace["delegation_control_continue_main_thread"])
        self.assertTrue(trace["delegation_control_wait_for_child"])
        self.assertEqual(trace["wait_reason"], "wait_for_child_result")
        self.assertTrue(trace["wait_required"])
        self.assertEqual(trace["delegation_actions"][0]["tool_name"], "wait_agent")
        self.assertEqual(trace["delegation_actions"][0]["target"], "agent_1")
        self.assertEqual(trace["delegation_actions"][0]["execution_tool"], "wait_agent")
        self.assertEqual(trace["delegation_actions"][0]["execution_mode"], "serial")
        self.assertEqual(trace["delegation_actions"][0]["planner_policy"], "wait_now")
        self.assertEqual(trace["delegation_actions"][0]["delegation_control_action"], "wait")
        self.assertEqual(
            trace["delegation_actions"][0]["defaulted_fields"], ["reason", "wait_required"]
        )
        self.assertEqual(
            trace["delegation_actions"][0]["policy_basis"],
            "wait_reason_default+blocking_join_default",
        )

    def test_planning_trace_observes_wait_timeout_and_budget(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="wait_agent",
                            arguments={"target": "agent_1", "timeout_ms": 250},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "pending", [
                ToolEvent(
                    name="wait_agent",
                    ok=False,
                    summary="wait timed out",
                    payload={
                        "command": command_text,
                        "status": "pending",
                        "wait_timed_out": True,
                        "wait_blocked_ms": 250,
                        "timeout_ms": 250,
                        "timeout_reason": "wait_timeout",
                    },
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(user_text="join", initial_input=[{"role": "user", "content": "join"}])

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["wait_timeout_ms"], 250)
        self.assertEqual(trace["delegation_budget_source"], "planner_arguments")
        self.assertEqual(trace["delegation_observation_source"], "tool_execution")
        self.assertEqual(trace["delegation_outcome"], "timed_out")
        self.assertTrue(trace["delegation_timeout_hit"])
        self.assertEqual(trace["delegation_timeout_reason"], "wait_timeout")
        self.assertEqual(trace["delegation_wait_observed_ms"], 250)
        self.assertEqual(trace["delegation_budget_snapshot"]["wait_timeout_ms"], 250)
        self.assertEqual(trace["delegation_budget_snapshot"]["wait_observed_ms"], 250)
        self.assertEqual(trace["delegation_strategy"], "stop_and_return")
        self.assertEqual(trace["delegation_strategy_reason"], "wait_timeout")
        self.assertFalse(trace["delegation_continue_main_thread"])
        self.assertTrue(trace["delegation_budget_hit"])
        self.assertEqual(len(session.calls), 1)

    def test_planning_trace_budget_hit_stops_followup_busy_wait(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="wait_agent",
                            arguments={"target": "agent_1", "timeout_ms": 200},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "pending", [
                ToolEvent(
                    name="wait_agent",
                    ok=True,
                    summary="still pending",
                    payload={
                        "command": command_text,
                        "status": "pending",
                        "wait_timed_out": False,
                        "wait_blocked_ms": 250,
                        "timeout_ms": 200,
                    },
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(user_text="join", initial_input=[{"role": "user", "content": "join"}])

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_outcome"], "completed")
        self.assertEqual(trace["delegation_strategy"], "stop_and_return")
        self.assertEqual(trace["delegation_strategy_reason"], "wait_timeout_budget_hit")
        self.assertFalse(trace["delegation_continue_main_thread"])
        self.assertTrue(trace["delegation_budget_hit"])
        self.assertEqual(trace["delegation_budget_snapshot"]["wait_timeout_ms"], 200)
        self.assertEqual(trace["delegation_budget_snapshot"]["wait_observed_ms"], 250)
        self.assertEqual(len(session.calls), 1)

    def test_planning_trace_observes_cancellation(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="spawn_agent",
                            arguments={"task": "收集 provider 差异", "role": "teammate"},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "cancelled", [
                ToolEvent(
                    name="spawn_agent",
                    ok=False,
                    summary="cancelled by request",
                    payload={
                        "command": command_text,
                        "status": "cancelled",
                        "cancel_requested": True,
                        "terminal_reason": "close_requested",
                    },
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(
            user_text="delegate", initial_input=[{"role": "user", "content": "delegate"}]
        )

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_observation_source"], "tool_execution")
        self.assertEqual(trace["delegation_outcome"], "cancelled")
        self.assertTrue(trace["delegation_cancelled"])
        self.assertFalse(bool(trace.get("delegation_failed")))
        self.assertTrue(trace["delegation_outcomes"][0]["cancel_requested"])

    def test_planning_trace_observes_failure_reason(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="recover_agent",
                            arguments={"target": "agent_1"},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "failed", [
                ToolEvent(
                    name="recover_agent",
                    ok=False,
                    summary="temporary failure",
                    payload={
                        "command": command_text,
                        "status": "failed",
                        "error": "temporary failure",
                    },
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(
            user_text="recover", initial_input=[{"role": "user", "content": "recover"}]
        )

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_observation_source"], "tool_execution")
        self.assertEqual(trace["delegation_outcome"], "failed")
        self.assertTrue(trace["delegation_failed"])
        self.assertEqual(trace["delegation_failure_reason"], "temporary failure")
        self.assertTrue(trace["delegation_outcomes"][0]["failed"])

    def test_non_blocking_wait_agent_preserves_original_tool_name_and_execution_tool(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="wait_agent",
                            arguments={"target": "agent_1", "wait_required": False},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def command_builder(name: str, arguments: dict[str, Any]) -> str | None:
            effective_name, effective_arguments = planner_tool_execution_target(name, arguments)
            if effective_name == "agent_workflow":
                return f"/agent_workflow {effective_arguments['target']}"
            return None

        def tool_executor(command_text: str):
            return "workflow", [
                ToolEvent(
                    name="agent_workflow",
                    ok=True,
                    summary="workflow",
                    payload={"command": command_text},
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor, command_builder=command_builder)
        intent = engine.run(
            user_text="workflow", initial_input=[{"role": "user", "content": "workflow"}]
        )

        payload = intent.tool_events[0].payload
        self.assertEqual(payload["function_call_name"], "wait_agent")
        self.assertEqual(payload["planner_execution_tool"], "agent_workflow")
        self.assertEqual(payload["command"], "/agent_workflow agent_1")

    def test_planning_trace_includes_agent_workflow_summary(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="agent_workflow",
                            arguments={"target": "agent_1", "steps": 3},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "workflow", [
                ToolEvent(
                    name="agent_workflow",
                    ok=True,
                    summary="workflow",
                    payload={"command": command_text},
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(
            user_text="workflow", initial_input=[{"role": "user", "content": "workflow"}]
        )

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_decision"], "none")
        self.assertEqual(trace["delegation_policy_decision"], "wait_later")
        self.assertEqual(trace["delegation_policy_source"], "delegation_policy")
        self.assertEqual(trace["delegation_policy_reason"], "agent_workflow_snapshot")
        self.assertEqual(trace["delegation_execution_mode"], "parallel")
        self.assertEqual(trace["delegation_execution_reason"], "decision:wait_later")
        self.assertEqual(trace["delegation_control_action"], "continue")
        self.assertTrue(trace["delegation_control_continue_main_thread"])
        self.assertFalse(trace["delegation_control_wait_for_child"])
        self.assertEqual(trace["observed_tool_count"], 1)
        self.assertEqual(trace["observed_delegation_tool_count"], 1)
        self.assertEqual(trace["observed_non_delegation_tool_count"], 0)
        self.assertEqual(trace["delegation_actions"][0]["tool_name"], "agent_workflow")
        self.assertEqual(trace["delegation_actions"][0]["target"], "agent_1")
        self.assertEqual(trace["delegation_actions"][0]["execution_tool"], "agent_workflow")
        self.assertEqual(trace["delegation_actions"][0]["execution_mode"], "parallel")
        self.assertEqual(trace["delegation_actions"][0]["planner_policy"], "wait_later")
        self.assertEqual(trace["delegation_actions"][0]["delegation_control_action"], "continue")
        self.assertEqual(trace["delegation_actions"][0]["policy_basis"], "explicit_arguments")

    def test_planning_trace_includes_recover_agent_summary(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="recover_agent",
                            arguments={"target": "agent_1"},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "recovered", [
                ToolEvent(
                    name="recover_agent",
                    ok=True,
                    summary="recovered",
                    payload={"command": command_text},
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(
            user_text="recover", initial_input=[{"role": "user", "content": "recover"}]
        )

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_decision"], "retry_child")
        self.assertEqual(trace["delegation_policy_decision"], "retry_child")
        self.assertEqual(trace["delegation_policy_source"], "delegation_policy")
        self.assertEqual(trace["delegation_policy_reason"], "recover_agent")
        self.assertEqual(trace["delegation_control_action"], "continue")
        self.assertTrue(trace["delegation_control_continue_main_thread"])
        self.assertEqual(trace["recovery_action"], "retry_step")
        self.assertEqual(trace["delegation_actions"][0]["tool_name"], "recover_agent")
        self.assertEqual(trace["delegation_actions"][0]["target"], "agent_1")
        self.assertEqual(trace["delegation_actions"][0]["recovery_action"], "retry_step")
        self.assertEqual(trace["delegation_actions"][0]["execution_tool"], "recover_agent")
        self.assertEqual(trace["delegation_actions"][0]["execution_mode"], "serial")
        self.assertEqual(trace["delegation_actions"][0]["planner_policy"], "retry_child")
        self.assertEqual(trace["delegation_actions"][0]["delegation_control_action"], "continue")
        self.assertEqual(trace["delegation_actions"][0]["defaulted_fields"], ["action"])
        self.assertEqual(trace["delegation_actions"][0]["policy_basis"], "retry_step_default")

    def test_planning_trace_marks_close_child_as_stop_control_action(self) -> None:
        session = _FakeSession(
            [
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[
                        ProviderToolCall(
                            call_id="c1",
                            name="recover_agent",
                            arguments={"target": "agent_1", "action": "close_session"},
                        )
                    ],
                    response_id="r1",
                ),
                ProviderSessionResult(
                    output_text="done",
                    tool_calls=[],
                    response_items=[
                        response_message_item("assistant", "done", phase="final_answer")
                    ],
                    response_id="r2",
                ),
            ]
        )

        def tool_executor(command_text: str):
            return "closed", [
                ToolEvent(
                    name="recover_agent",
                    ok=True,
                    summary="closed",
                    payload={"command": command_text},
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent = engine.run(user_text="close", initial_input=[{"role": "user", "content": "close"}])

        trace = intent.timings["planning_trace"][0]
        self.assertEqual(trace["delegation_decision"], "close_child")
        self.assertEqual(trace["delegation_policy_decision"], "close_child")
        self.assertEqual(trace["delegation_control_action"], "stop")
        self.assertFalse(trace["delegation_control_continue_main_thread"])
        self.assertFalse(trace["delegation_control_wait_for_child"])
        self.assertTrue(trace["delegation_control_stop_early"])
        self.assertEqual(trace["delegation_actions"][0]["planner_policy"], "close_child")
        self.assertEqual(trace["delegation_actions"][0]["delegation_control_action"], "stop")
