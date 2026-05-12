from __future__ import annotations

import os
import shlex
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core.command_handlers import handle_known_command
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.runtime_core.shell_command_handlers_runtime import canonical_exec_output_text
from cli.agent_cli.tools_core.shell_bridge import (
    ShellSessionManager,
    execute_shell,
    execute_shell_result,
)


class UnifiedExecAlignmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = ShellSessionManager(host_platform=current_host_platform())

    @staticmethod
    def _command(tag: str) -> str:
        return (
            f"{shlex.quote(sys.executable)} -u -c "
            f'"import sys; '
            f"print('{tag}:ready'); sys.stdout.flush(); "
            f"line = sys.stdin.readline().strip(); "
            f"print('{tag}:' + line); sys.stdout.flush()\""
        )

    @staticmethod
    def _interactive_command() -> str:
        code = (
            "import sys,time; "
            "print('ready'); "
            "sys.stdout.flush(); "
            "[((time.sleep(0.2), print('delayed:done'), sys.stdout.flush()) "
            "if (cmd:=raw.strip()) == 'delayed' "
            "else ((print('bye'), sys.stdout.flush(), (_ for _ in ()).throw(SystemExit)) "
            "if cmd == 'exit' "
            "else (print('echo:' + cmd), sys.stdout.flush()))) for raw in sys.stdin]"
        )
        return f"{shlex.quote(sys.executable)} -u -c {shlex.quote(code)}"

    @staticmethod
    def _wait_until(predicate, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        raise AssertionError("condition not met before timeout")

    def test_natural_completion_removes_session_and_rejects_late_stdin(self) -> None:
        events: list[dict[str, object]] = []
        session = self.manager.start_session(
            command=self._command("one"), on_activity=events.append
        )

        written = self.manager.write_stdin(
            str(session["session_id"]), "ping\n", on_activity=events.append
        )
        self.assertTrue(written.ok, written.payload)

        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events))

        late_write = self.manager.write_stdin(
            str(session["session_id"]), "late\n", on_activity=events.append
        )
        late_terminate = self.manager.terminate(
            str(session["session_id"]), on_activity=events.append
        )

        self.assertFalse(late_write.ok)
        self.assertEqual(late_write.payload["status"], "completed")
        self.assertEqual(late_write.payload.get("final_status"), "ok")
        self.assertEqual(
            str(late_write.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )
        self.assertTrue(late_terminate.ok)
        self.assertEqual(late_terminate.payload["status"], "ok")
        self.assertEqual(
            str(late_terminate.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )

    def test_multiple_sessions_keep_output_isolated_by_session_id(self) -> None:
        events_a: list[dict[str, object]] = []
        events_b: list[dict[str, object]] = []
        session_a = self.manager.start_session(
            command=self._command("A"), on_activity=events_a.append
        )
        session_b = self.manager.start_session(
            command=self._command("B"), on_activity=events_b.append
        )

        result_a = self.manager.write_stdin(
            str(session_a["session_id"]), "alpha\n", on_activity=events_a.append
        )
        result_b = self.manager.write_stdin(
            str(session_b["session_id"]), "beta\n", on_activity=events_b.append
        )
        self.assertTrue(result_a.ok, result_a.payload)
        self.assertTrue(result_b.ok, result_b.payload)

        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events_a))
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events_b))

        output_a = [
            str(item.get("text") or "") for item in events_a if item.get("phase") == "output"
        ]
        output_b = [
            str(item.get("text") or "") for item in events_b if item.get("phase") == "output"
        ]

        self.assertTrue(any(text == "A:ready" for text in output_a))
        self.assertTrue(any(text == "A:alpha" for text in output_a))
        self.assertFalse(any("B:" in text for text in output_a))
        self.assertTrue(any(text == "B:ready" for text in output_b))
        self.assertTrue(any(text == "B:beta" for text in output_b))
        self.assertFalse(any("A:" in text for text in output_b))

    def test_session_callbacks_observe_started_output_completed_order(self) -> None:
        events: list[dict[str, object]] = []
        session = self.manager.start_session(
            command=self._command("order"), on_activity=events.append
        )
        written = self.manager.write_stdin(
            str(session["session_id"]), "pong\n", on_activity=events.append
        )
        self.assertTrue(written.ok, written.payload)

        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events))

        phases = [str(item.get("phase") or "") for item in events]
        self.assertEqual(phases[0], "started")
        self.assertIn("input", phases[1:-1])
        self.assertIn("output", phases[1:-1])
        self.assertEqual(phases[-1], "completed")
        self.assertTrue(
            any(item.get("phase") == "input" and item.get("stdin") == "pong\n" for item in events)
        )
        self.assertTrue(
            any(
                item.get("phase") == "output" and str(item.get("chunk") or "").strip()
                for item in events
            )
        )
        self.assertTrue(
            all(
                str(item.get("call_id") or "").strip() == str(session.get("call_id") or "").strip()
                for item in events
                if item.get("phase") in {"started", "input", "output", "completed"}
            )
        )
        self.assertTrue(
            any(
                item.get("phase") == "input" and item.get("interaction_input") == "pong\n"
                for item in events
            )
        )
        self.assertTrue(
            any(
                item.get("phase") == "output"
                and str(item.get("output_text") or "").strip()
                and str(item.get("output_chunk") or "").strip()
                for item in events
            )
        )
        lifecycle_call_ids = {
            str(dict(item.get("lifecycle") or {}).get("call_id") or "").strip()
            for item in events
            if dict(item.get("lifecycle") or {}).get("call_id")
        }
        self.assertEqual(len(lifecycle_call_ids), 1)
        self.assertEqual(next(iter(lifecycle_call_ids)), str(session.get("call_id") or "").strip())

    def test_explicit_terminate_removes_session_and_rejects_followups(self) -> None:
        events: list[dict[str, object]] = []
        # Long-running process so terminate path is exercised.
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"import time,sys; print('alive'); sys.stdout.flush(); time.sleep(30)\""
        )
        session = self.manager.start_session(command=command, on_activity=events.append)

        terminate_event = self.manager.terminate(
            str(session["session_id"]), on_activity=events.append
        )
        self.assertFalse(terminate_event.ok)
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events))

        late_write = self.manager.write_stdin(
            str(session["session_id"]), "later\n", on_activity=events.append
        )
        late_terminate = self.manager.terminate(
            str(session["session_id"]), on_activity=events.append
        )

        self.assertFalse(late_write.ok)
        self.assertEqual(late_write.payload.get("status"), "completed")
        self.assertEqual(late_write.payload.get("final_status"), "interrupted")
        self.assertEqual(
            str(late_write.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )
        self.assertFalse(late_terminate.ok)
        self.assertEqual(late_terminate.payload.get("status"), "interrupted")
        self.assertEqual(
            str(late_terminate.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )

    def test_write_stdin_returns_incremental_output_from_same_session(self) -> None:
        events: list[dict[str, object]] = []
        session = self.manager.start_session(
            command=self._interactive_command(), on_activity=events.append
        )

        self._wait_until(
            lambda: any(str(item.get("text") or "").strip() == "ready" for item in events)
        )

        write_event = self.manager.write_stdin(
            str(session["session_id"]),
            "hello\n",
            yield_time_ms=500,
            on_activity=events.append,
        )

        self.assertTrue(write_event.ok, write_event.payload)
        self.assertEqual(write_event.payload.get("status"), "written")
        self.assertIn("echo:hello", str(write_event.payload.get("output_text") or ""))
        self.assertIn("echo:hello", str(write_event.payload.get("aggregated_output") or ""))
        self.assertEqual(
            str(write_event.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )

    def test_empty_write_can_poll_delayed_output(self) -> None:
        events: list[dict[str, object]] = []
        session = self.manager.start_session(
            command=self._interactive_command(), on_activity=events.append
        )

        self._wait_until(
            lambda: any(str(item.get("text") or "").strip() == "ready" for item in events)
        )

        early = self.manager.write_stdin(
            str(session["session_id"]),
            "delayed\n",
            yield_time_ms=20,
            on_activity=events.append,
        )
        self.assertTrue(early.ok, early.payload)
        self.assertNotIn("delayed:done", str(early.payload.get("aggregated_output") or ""))

        poll = self.manager.write_stdin(
            str(session["session_id"]),
            "",
            yield_time_ms=800,
            on_activity=events.append,
        )
        self.assertTrue(poll.ok, poll.payload)
        self.assertEqual(poll.payload.get("status"), "noop")
        self.assertIn("delayed:done", str(poll.payload.get("aggregated_output") or ""))

        exit_event = self.manager.write_stdin(
            str(session["session_id"]),
            "exit\n",
            yield_time_ms=500,
            on_activity=events.append,
        )
        self.assertTrue(exit_event.ok, exit_event.payload)
        self.assertIn("bye", str(exit_event.payload.get("aggregated_output") or ""))
        if exit_event.payload.get("exit_code") is None:
            self._wait_until(lambda: any(item.get("phase") == "completed" for item in events))
            completed = next(item for item in events if item.get("phase") == "completed")
            self.assertEqual(completed.get("exit_code"), 0)
        else:
            self.assertEqual(exit_event.payload.get("exit_code"), 0)

    def test_empty_poll_returns_completed_snapshot_after_session_removed(self) -> None:
        events: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('completed-snapshot'); import sys; sys.stdout.flush()\""
        )
        session = self.manager.start_session(command=command, on_activity=events.append)
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events))

        polled = self.manager.write_stdin(
            str(session["session_id"]),
            "",
            yield_time_ms=50,
            on_activity=events.append,
        )
        self.assertTrue(polled.ok, polled.payload)
        self.assertEqual(
            str(polled.payload.get("session_id") or ""), str(session.get("session_id") or "")
        )
        self.assertEqual(
            str(polled.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )
        self.assertIn("completed-snapshot", str(polled.payload.get("stdout") or ""))
        self.assertEqual(str(polled.payload.get("status") or ""), "ok")

    def test_completed_live_session_replays_readonly_write_before_cache_promotion(self) -> None:
        events: list[dict[str, object]] = []
        late_payloads: list[dict[str, object]] = []
        session_id_holder = {"value": ""}
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('completed-live'); import sys; sys.stdout.flush()\""
        )

        def _on_activity(payload: dict[str, object]) -> None:
            events.append(payload)
            if payload.get("phase") == "completed" and not late_payloads:
                late_payloads.append(
                    self.manager.write_stdin(
                        session_id_holder["value"],
                        "late\n",
                    ).payload
                )

        session = self.manager.start_session(command=command, on_activity=_on_activity)
        session_id_holder["value"] = str(session["session_id"])
        self._wait_until(lambda: bool(late_payloads))

        late = late_payloads[0]
        self.assertEqual(str(late.get("status") or ""), "completed")
        self.assertEqual(str(late.get("final_status") or ""), "ok")
        lifecycle = dict(late.get("lifecycle") or {})
        self.assertEqual(str(lifecycle.get("kind") or ""), "end")
        self.assertEqual(str(lifecycle.get("status") or ""), "completed")
        self.assertEqual(
            str(late.get("call_id") or "").strip(), str(session.get("call_id") or "").strip()
        )

    def test_one_shot_shell_events_match_session_activity(self) -> None:
        python_executable = str(sys.executable)
        if " " in python_executable:
            python_executable = f'"{python_executable}"'
        command = (
            f"{python_executable} -u -c "
            "\"print('unified exec alignment output'); import sys; sys.stdout.flush()\""
        )

        one_shot_events: list[dict[str, object]] = []
        tool_event = execute_shell(
            host_platform=current_host_platform(),
            command=command,
            on_activity=one_shot_events.append,
        )
        self.assertTrue(tool_event.ok, tool_event.payload)
        self.assertGreaterEqual(len(one_shot_events), 2)

        session_events: list[dict[str, object]] = []
        self.manager.start_session(command=command, on_activity=session_events.append)
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in session_events))

        one_shot_phases = [
            str(item.get("phase") or "") for item in one_shot_events if item.get("phase")
        ]
        session_phases = [
            str(item.get("phase") or "") for item in session_events if item.get("phase")
        ]
        self.assertEqual(one_shot_phases[0], "started")
        self.assertEqual(session_phases[0], "started")
        self.assertEqual(one_shot_phases[-1], "completed")
        self.assertEqual(session_phases[-1], "completed")
        self.assertTrue(any(phase == "output" for phase in one_shot_phases[1:-1]))
        self.assertTrue(any(phase == "output" for phase in session_phases[1:-1]))
        one_shot_call_ids = {
            str(dict(item.get("lifecycle") or {}).get("call_id") or "").strip()
            for item in one_shot_events
            if dict(item.get("lifecycle") or {}).get("call_id")
        }
        session_call_ids = {
            str(dict(item.get("lifecycle") or {}).get("call_id") or "").strip()
            for item in session_events
            if dict(item.get("lifecycle") or {}).get("call_id")
        }
        self.assertEqual(len(one_shot_call_ids), 1)
        self.assertEqual(len(session_call_ids), 1)

        completed_one_shot = next(
            item for item in one_shot_events if item.get("phase") == "completed"
        )
        completed_session = next(
            item for item in session_events if item.get("phase") == "completed"
        )
        self.assertEqual(completed_one_shot.get("status"), completed_session.get("status"))
        self.assertEqual(bool(completed_one_shot.get("ok")), bool(completed_session.get("ok")))
        stdout_one_shot = str(completed_one_shot.get("stdout") or "").strip()
        stdout_session = str(completed_session.get("stdout") or "").strip()
        self.assertEqual(stdout_one_shot, stdout_session)
        self.assertIn("unified exec alignment output", stdout_one_shot)

    def test_one_shot_shell_result_emits_command_execution_items(self) -> None:
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('result-items'); import sys; sys.stdout.flush()\""
        )
        result = execute_shell_result(
            host_platform=current_host_platform(),
            command=command,
        )

        self.assertEqual(result.assistant_text, "Run shell command.")
        self.assertEqual(len(result.tool_events), 1)
        item_types = [str(event.get("type") or "") for event in result.item_events]
        self.assertEqual(item_types, ["item.started", "item.updated", "item.completed"])
        completed_item = dict(result.item_events[-1].get("item") or {})
        self.assertEqual(str(completed_item.get("type") or ""), "command_execution")
        self.assertEqual(completed_item.get("exit_code"), 0)
        self.assertEqual(str(completed_item.get("status") or ""), "completed")
        self.assertIn("result-items", str(completed_item.get("aggregated_output") or ""))

    def test_exec_command_short_lived_process_does_not_expose_session_id_after_initial_poll(
        self,
    ) -> None:
        class _Runtime:
            def __init__(self) -> None:
                self.tools = type(
                    "Tools", (), {"_plugin_manager": None, "shell_start": manager.start_session}
                )()

            @staticmethod
            def _parse_args(arg_text: str):
                tokens = shlex.split(str(arg_text or ""))
                positionals: list[str] = []
                options: dict[str, object] = {}
                index = 0
                while index < len(tokens):
                    token = tokens[index]
                    if token == "--tty":
                        options["tty"] = True
                        index += 1
                        continue
                    if token.startswith("--") and index + 1 < len(tokens):
                        options[token[2:]] = tokens[index + 1]
                        index += 2
                        continue
                    positionals.append(token)
                    index += 1
                return positionals, options

            @staticmethod
            def _normalize_shell_override(shell: str | None) -> str | None:
                return str(shell or "").strip() or None

            @staticmethod
            def patch_requires_approval() -> bool:
                return False

            @staticmethod
            def _is_interrupt_requested() -> bool:
                return False

            def start_shell_session(
                self,
                command,
                *,
                cwd=None,
                login=True,
                tty=False,
                shell=None,
                max_output_chars=12000,
                on_activity=None,
            ):
                return manager.start_session(
                    command=command,
                    cwd=cwd,
                    login=login,
                    tty=tty,
                    shell=shell,
                    max_output_chars=max_output_chars,
                    on_activity=on_activity,
                )

            def write_shell_stdin_result(
                self,
                session_id,
                chars,
                *,
                yield_time_ms=None,
                allow_extended_empty_poll=False,
                on_activity=None,
                cancel_event=None,
            ):
                return manager.write_stdin_result(
                    session_id,
                    chars,
                    yield_time_ms=yield_time_ms,
                    allow_extended_empty_poll=allow_extended_empty_poll,
                    on_activity=on_activity,
                    cancel_event=cancel_event,
                )

        manager = ShellSessionManager(host_platform=current_host_platform())
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('short-lived'); import sys; sys.stdout.flush()\""
        )
        runtime = _Runtime()

        result = handle_known_command(
            runtime,
            name="exec_command",
            arg_text=f"{shlex.quote(command)} --yield-time-ms 500",
            text=f"/exec_command {command}",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.tool_events[0].name, "exec_command")
        self.assertIsNone(result.tool_events[0].payload.get("session_id"))
        self.assertIsNone(result.tool_events[0].payload.get("process_id"))
        self.assertEqual(result.tool_events[0].payload.get("exit_code"), 0)
        self.assertIn("short-lived", str(result.tool_events[0].payload.get("stdout") or ""))

    def test_exec_command_initial_poll_uses_requested_yield_for_silent_process(self) -> None:
        class _Runtime:
            def __init__(self) -> None:
                self.tools = type(
                    "Tools", (), {"_plugin_manager": None, "shell_start": manager.start_session}
                )()

            @staticmethod
            def _parse_args(arg_text: str):
                tokens = shlex.split(str(arg_text or ""))
                positionals: list[str] = []
                options: dict[str, object] = {}
                index = 0
                while index < len(tokens):
                    token = tokens[index]
                    if token == "--tty":
                        options["tty"] = True
                        index += 1
                        continue
                    if token.startswith("--") and index + 1 < len(tokens):
                        options[token[2:]] = tokens[index + 1]
                        index += 2
                        continue
                    positionals.append(token)
                    index += 1
                return positionals, options

            @staticmethod
            def _normalize_shell_override(shell: str | None) -> str | None:
                return str(shell or "").strip() or None

            @staticmethod
            def patch_requires_approval() -> bool:
                return False

            @staticmethod
            def _is_interrupt_requested() -> bool:
                return False

            def start_shell_session(
                self,
                command,
                *,
                cwd=None,
                login=True,
                tty=False,
                shell=None,
                max_output_chars=12000,
                on_activity=None,
            ):
                return manager.start_session(
                    command=command,
                    cwd=cwd,
                    login=login,
                    tty=tty,
                    shell=shell,
                    max_output_chars=max_output_chars,
                    on_activity=on_activity,
                )

            def write_shell_stdin_result(
                self,
                session_id,
                chars,
                *,
                yield_time_ms=None,
                allow_extended_empty_poll=False,
                on_activity=None,
                cancel_event=None,
            ):
                return manager.write_stdin_result(
                    session_id,
                    chars,
                    yield_time_ms=yield_time_ms,
                    allow_extended_empty_poll=allow_extended_empty_poll,
                    on_activity=on_activity,
                    cancel_event=cancel_event,
                )

        manager = ShellSessionManager(host_platform=current_host_platform())
        command = f"{shlex.quote(sys.executable)} -u -c " '"import time; time.sleep(2.5)"'
        runtime = _Runtime()

        result = handle_known_command(
            runtime,
            name="exec_command",
            arg_text=f"{shlex.quote(command)} --yield-time-ms 5000",
            text=f"/exec_command {command}",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.tool_events[0].name, "exec_command")
        self.assertIsNone(result.tool_events[0].payload.get("session_id"))
        self.assertIsNone(result.tool_events[0].payload.get("process_id"))
        self.assertEqual(result.tool_events[0].payload.get("exit_code"), 0)

    def test_exec_command_payload_preserves_timeout_budget_separately_from_yield(self) -> None:
        manager = self.manager

        class _Runtime:
            def __init__(self) -> None:
                self.tools = type(
                    "Tools", (), {"_plugin_manager": None, "shell_start": manager.start_session}
                )()

            @staticmethod
            def _parse_args(arg_text: str):
                tokens = shlex.split(str(arg_text or ""))
                positionals: list[str] = []
                options: dict[str, object] = {}
                index = 0
                while index < len(tokens):
                    token = tokens[index]
                    if token == "--tty":
                        options["tty"] = True
                        index += 1
                        continue
                    if token.startswith("--") and index + 1 < len(tokens):
                        options[token[2:]] = tokens[index + 1]
                        index += 2
                        continue
                    positionals.append(token)
                    index += 1
                return positionals, options

            @staticmethod
            def _normalize_shell_override(shell: str | None) -> str | None:
                return str(shell or "").strip() or None

            @staticmethod
            def patch_requires_approval() -> bool:
                return False

            @staticmethod
            def _is_interrupt_requested() -> bool:
                return False

            def start_shell_session(
                self,
                command,
                *,
                cwd=None,
                login=True,
                tty=False,
                shell=None,
                max_output_chars=12000,
                on_activity=None,
            ):
                return manager.start_session(
                    command=command,
                    cwd=cwd,
                    login=login,
                    tty=tty,
                    shell=shell,
                    max_output_chars=max_output_chars,
                    on_activity=on_activity,
                )

            def write_shell_stdin_result(
                self,
                session_id,
                chars,
                *,
                yield_time_ms=None,
                allow_extended_empty_poll=False,
                on_activity=None,
                cancel_event=None,
            ):
                return manager.write_stdin_result(
                    session_id,
                    chars,
                    yield_time_ms=yield_time_ms,
                    allow_extended_empty_poll=allow_extended_empty_poll,
                    on_activity=on_activity,
                    cancel_event=cancel_event,
                )

        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"import time; time.sleep(0.4); print('done')\""
        )
        runtime = _Runtime()

        result = handle_known_command(
            runtime,
            name="exec_command",
            arg_text=f"{shlex.quote(command)} --yield-time-ms 250 --timeout-ms 30000",
            text=f"/exec_command {command}",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.tool_events[0].name, "exec_command")
        self.assertEqual(result.tool_events[0].payload.get("yield_time_ms"), 250)
        self.assertEqual(result.tool_events[0].payload.get("timeout_ms"), 30000)
        self.assertEqual(
            dict(result.tool_events[0].payload.get("function_call_arguments") or {}).get(
                "timeout_ms"
            ),
            30000,
        )

    def test_relative_cwd_one_shot_and_session_outputs_match(self) -> None:
        command = f"{shlex.quote(sys.executable)} -u -c " '"import os; print(os.getcwd())"'
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir).resolve()
            nested = workspace_root / "relative-cwd"
            nested.mkdir()
            old_cwd = Path.cwd()
            os.chdir(workspace_root)
            try:
                one_shot_event = execute_shell(
                    host_platform=current_host_platform(),
                    command=command,
                    cwd="relative-cwd",
                )
                self.assertTrue(one_shot_event.ok, one_shot_event.payload)
                stdout_one_shot = str(one_shot_event.payload.get("stdout") or "").strip()
                self.assertIn(str(nested), stdout_one_shot)

                session_events: list[dict[str, object]] = []
                session = self.manager.start_session(
                    command=command,
                    cwd="relative-cwd",
                    on_activity=session_events.append,
                )
                self.assertTrue(str(session.get("session_id")))
                self._wait_until(
                    lambda: any(item.get("phase") == "completed" for item in session_events)
                )
                completed_session = next(
                    item for item in session_events if item.get("phase") == "completed"
                )
                stdout_session = str(completed_session.get("stdout") or "").strip()
                self.assertEqual(stdout_one_shot, stdout_session)
                self.assertEqual(str(completed_session.get("cwd") or ""), "relative-cwd")
            finally:
                os.chdir(old_cwd)

    def test_tty_session_unix_exposes_pty_mode_and_combines_stderr(self) -> None:
        if current_host_platform().family != "unix":
            self.skipTest("PTY semantics are only verified on unix hosts")
        events: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            '"import sys; '
            "sys.stderr.write('ERR\\\\n'); sys.stderr.flush(); "
            "line = sys.stdin.readline().strip(); "
            "print('OUT:' + line); sys.stdout.flush()\""
        )

        session = self.manager.start_session(command=command, tty=True, on_activity=events.append)
        self.assertEqual(str(session.get("io_mode") or ""), "pty")

        write_event = self.manager.write_stdin(
            str(session["session_id"]),
            "pong\n",
            yield_time_ms=500,
            on_activity=events.append,
        )
        self.assertTrue(write_event.ok, write_event.payload)
        self.assertEqual(str(write_event.payload.get("io_mode") or ""), "pty")
        self.assertEqual(str(write_event.payload.get("stderr") or ""), "")
        self.assertIn("ERR", str(write_event.payload.get("aggregated_output") or ""))
        self.assertIn("OUT:pong", str(write_event.payload.get("aggregated_output") or ""))
        output_streams = {
            str(item.get("stream") or "") for item in events if item.get("phase") == "output"
        }
        self.assertIn("stdout", output_streams)
        self.assertNotIn("stderr", output_streams)

    def test_completed_payload_includes_aggregated_output(self) -> None:
        events: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            '"import sys; '
            "sys.stdout.write('out'); sys.stdout.flush(); "
            "sys.stderr.write('err'); sys.stderr.flush()\""
        )
        session = self.manager.start_session(command=command, on_activity=events.append)
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events))

        completed = next(item for item in events if item.get("phase") == "completed")
        stdout_text = str(completed.get("stdout") or "")
        stderr_text = str(completed.get("stderr") or "")
        aggregated = str(completed.get("aggregated_output") or "")

        self.assertIn("out", stdout_text)
        self.assertIn("err", stderr_text)
        self.assertIn("out", aggregated)
        self.assertIn("err", aggregated)
        self.assertEqual(str(completed.get("output_text") or ""), stdout_text)
        self.assertEqual(
            str(completed.get("call_id") or "").strip(), str(session.get("call_id") or "").strip()
        )

    def test_subscribe_attaches_callback_to_existing_session(self) -> None:
        late_events: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"import sys,time; print('boot'); sys.stdout.flush(); time.sleep(0.2); print('done'); sys.stdout.flush()\""
        )
        session = self.manager.start_session(command=command)

        subscribed = self.manager.subscribe(
            str(session["session_id"]), on_activity=late_events.append
        )
        self.assertTrue(subscribed.ok, subscribed.payload)

        self._wait_until(lambda: any(item.get("phase") == "completed" for item in late_events))

        phases = [str(item.get("phase") or "") for item in late_events]
        self.assertIn("subscribe", phases)
        self.assertEqual(phases[-1], "completed")
        self.assertEqual(phases[0], "subscribe")
        self.assertIn("output", phases)

    def test_subscribe_replays_completed_snapshot_from_cache(self) -> None:
        completed_events: list[dict[str, object]] = []
        late_events: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('cached-finish'); import sys; sys.stdout.flush()\""
        )
        session = self.manager.start_session(command=command, on_activity=completed_events.append)
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in completed_events))

        subscribed = self.manager.subscribe(
            str(session["session_id"]), on_activity=late_events.append
        )

        self.assertTrue(subscribed.ok, subscribed.payload)
        self.assertEqual(str(subscribed.payload.get("status") or ""), "subscribed")
        phases = [str(item.get("phase") or "") for item in late_events]
        self.assertEqual(phases[0], "subscribe")
        self.assertEqual(phases[-1], "completed")
        self.assertIn("started", phases)
        self.assertIn("output", phases)
        completed = next(item for item in late_events if item.get("phase") == "completed")
        self.assertEqual(
            str(completed.get("call_id") or "").strip(), str(session.get("call_id") or "").strip()
        )
        self.assertIn("cached-finish", str(completed.get("stdout") or ""))

    def test_subscribe_replays_live_history_before_new_output(self) -> None:
        late_events: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"import sys,time; print('boot'); sys.stdout.flush(); "
            "time.sleep(0.2); "
            "line = sys.stdin.readline().strip(); "
            "print('echo:' + line); sys.stdout.flush()\""
        )
        session = self.manager.start_session(command=command)
        time.sleep(0.25)

        subscribed = self.manager.subscribe(
            str(session["session_id"]),
            on_activity=late_events.append,
        )
        self.assertTrue(subscribed.ok, subscribed.payload)
        self.assertEqual(str(subscribed.payload.get("status") or ""), "subscribed")

        self.assertTrue(late_events)
        self.assertEqual(str(late_events[0].get("phase") or ""), "subscribe")
        self.assertTrue(any(str(item.get("phase") or "") == "started" for item in late_events))
        self.assertTrue(any(str(item.get("text") or "").strip() == "boot" for item in late_events))

        wrote = self.manager.write_stdin(
            str(session["session_id"]),
            "ping\n",
            yield_time_ms=500,
            on_activity=late_events.append,
        )
        self.assertTrue(wrote.ok, wrote.payload)
        self.assertIn("echo:ping", str(wrote.payload.get("aggregated_output") or ""))

    def test_immediate_completion_write_never_reports_write_failed(self) -> None:
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('immediate-done'); import sys; sys.stdout.flush()\""
        )
        session = self.manager.start_session(command=command)
        session_id = str(session["session_id"])

        first = self.manager.write_stdin(session_id, "late\n")
        self.assertNotEqual(str(first.payload.get("status") or ""), "write_failed")

        self._wait_until(
            lambda: bool(
                str(
                    self.manager.wait_for_completion(session_id, timeout_sec=0.1).get("status")
                    or ""
                )
                in {"ok", "error", "interrupted", "timeout", "pruned"}
            )
        )
        second = self.manager.write_stdin(session_id, "late\n")
        self.assertFalse(second.ok)
        self.assertEqual(str(second.payload.get("status") or ""), "completed")

    def test_completed_cache_write_and_terminate_emit_activity_callbacks(self) -> None:
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('callback-cache'); import sys; sys.stdout.flush()\""
        )
        session = self.manager.start_session(command=command)
        session_id = str(session["session_id"])
        self._wait_until(
            lambda: bool(
                str(
                    self.manager.wait_for_completion(session_id, timeout_sec=0.1).get("status")
                    or ""
                )
                in {"ok", "error", "interrupted", "timeout", "pruned"}
            )
        )

        replay_events: list[dict[str, object]] = []
        polled = self.manager.write_stdin(
            session_id,
            "",
            on_activity=replay_events.append,
        )
        readonly = self.manager.write_stdin(
            session_id,
            "late\n",
            on_activity=replay_events.append,
        )
        terminated = self.manager.terminate(
            session_id,
            on_activity=replay_events.append,
        )

        self.assertTrue(polled.ok, polled.payload)
        self.assertFalse(readonly.ok, readonly.payload)
        self.assertTrue(terminated.ok, terminated.payload)
        self.assertEqual(len(replay_events), 3)
        self.assertTrue(all(str(item.get("phase") or "") == "completed" for item in replay_events))
        self.assertEqual(str(replay_events[0].get("status") or ""), "ok")
        self.assertEqual(str(replay_events[1].get("status") or ""), "completed")
        self.assertEqual(str(replay_events[2].get("status") or ""), "ok")
        self.assertTrue(
            all("callback-cache" in str(item.get("stdout") or "") for item in replay_events)
        )

    def test_session_write_result_emits_command_execution_items(self) -> None:
        events: list[dict[str, object]] = []
        session = self.manager.start_session(
            command=self._interactive_command(), on_activity=events.append
        )

        self._wait_until(
            lambda: any(str(item.get("text") or "").strip() == "ready" for item in events)
        )

        result = self.manager.write_stdin_result(
            str(session["session_id"]),
            "hello\n",
            yield_time_ms=500,
            on_activity=events.append,
        )

        self.assertEqual(result.assistant_text, "Write shell stdin.")
        self.assertEqual(len(result.tool_events), 1)
        item_types = [str(event.get("type") or "") for event in result.item_events]
        self.assertEqual(item_types, ["item.started", "item.updated", "item.completed"])
        completed_item = dict(result.item_events[-1].get("item") or {})
        self.assertEqual(str(completed_item.get("type") or ""), "command_execution")
        self.assertEqual(str(completed_item.get("status") or ""), "completed")
        self.assertIn("echo:hello", str(completed_item.get("aggregated_output") or ""))

    def test_write_stdin_cancel_event_interrupts_live_session_poll(self) -> None:
        events: list[dict[str, object]] = []
        session = self.manager.start_session(
            command=self._interactive_command(), on_activity=events.append
        )
        self._wait_until(
            lambda: any(str(item.get("text") or "").strip() == "ready" for item in events)
        )

        cancel_event = threading.Event()
        holder: dict[str, object] = {}

        def _run_write() -> None:
            holder["event"] = self.manager.write_stdin(
                str(session["session_id"]),
                "delayed\n",
                yield_time_ms=1500,
                on_activity=events.append,
                cancel_event=cancel_event,
            )

        worker = threading.Thread(target=_run_write, daemon=True)
        worker.start()
        time.sleep(0.1)
        cancel_event.set()
        worker.join(timeout=3)

        self.assertFalse(worker.is_alive(), "write_stdin should finish after cancel_event is set")
        write_event = holder.get("event")
        self.assertIsNotNone(write_event)
        assert write_event is not None
        self.assertFalse(write_event.ok, write_event.payload)
        self.assertEqual(str(write_event.payload.get("status") or ""), "interrupted")
        self.assertTrue(bool(write_event.payload.get("interrupted")))
        self._wait_until(
            lambda: any(
                item.get("phase") == "completed"
                and str(item.get("status") or "").strip() == "interrupted"
                for item in events
            )
        )

    def test_session_limit_prunes_oldest_active_session(self) -> None:
        manager = ShellSessionManager(
            host_platform=current_host_platform(),
            max_live_sessions=1,
        )
        events_a: list[dict[str, object]] = []
        events_b: list[dict[str, object]] = []
        session_a = manager.start_session(
            command=self._interactive_command(), on_activity=events_a.append
        )
        self._wait_until(
            lambda: any(str(item.get("text") or "").strip() == "ready" for item in events_a)
        )

        session_b = manager.start_session(
            command=self._interactive_command(), on_activity=events_b.append
        )
        self._wait_until(
            lambda: any(
                item.get("phase") == "completed"
                and str(item.get("status") or "").strip() == "pruned"
                for item in events_a
            )
        )

        pruned_write = manager.write_stdin(
            str(session_a["session_id"]), "old\n", on_activity=events_a.append
        )
        self.assertFalse(pruned_write.ok)
        self.assertEqual(pruned_write.payload.get("status"), "completed")
        self.assertEqual(pruned_write.payload.get("final_status"), "pruned")

        active_write = manager.write_stdin(
            str(session_b["session_id"]),
            "new\n",
            yield_time_ms=500,
            on_activity=events_b.append,
        )
        self.assertTrue(active_write.ok, active_write.payload)
        self.assertIn("echo:new", str(active_write.payload.get("aggregated_output") or ""))

        terminate_b = manager.terminate(str(session_b["session_id"]), on_activity=events_b.append)
        self.assertFalse(terminate_b.ok)
        self.assertIn(str(terminate_b.payload.get("status") or ""), {"pruned", "interrupted"})

    def test_completed_payload_cache_is_bounded(self) -> None:
        manager = ShellSessionManager(
            host_platform=current_host_platform(),
            completed_cache_limit=1,
        )
        command_one = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('cache-one'); import sys; sys.stdout.flush()\""
        )
        command_two = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('cache-two'); import sys; sys.stdout.flush()\""
        )
        events_one: list[dict[str, object]] = []
        events_two: list[dict[str, object]] = []

        session_one = manager.start_session(command=command_one, on_activity=events_one.append)
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events_one))
        session_two = manager.start_session(command=command_two, on_activity=events_two.append)
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events_two))

        older = manager.wait_for_completion(str(session_one["session_id"]), timeout_sec=0.1)
        newer = manager.wait_for_completion(str(session_two["session_id"]), timeout_sec=0.1)

        self.assertEqual(str(older.get("status") or ""), "missing")
        self.assertTrue(bool(newer.get("ok")))
        self.assertIn("cache-two", str(newer.get("stdout") or ""))

    def test_wait_for_completion_is_repeatable_while_cached(self) -> None:
        manager = ShellSessionManager(
            host_platform=current_host_platform(),
            completed_cache_limit=4,
        )
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('repeatable-cache'); import sys; sys.stdout.flush()\""
        )
        events: list[dict[str, object]] = []
        session = manager.start_session(command=command, on_activity=events.append)
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events))

        first = manager.wait_for_completion(str(session["session_id"]), timeout_sec=0.1)
        second = manager.wait_for_completion(str(session["session_id"]), timeout_sec=0.1)

        self.assertTrue(bool(first.get("ok")))
        self.assertTrue(bool(second.get("ok")))
        self.assertEqual(str(first.get("session_id") or ""), str(second.get("session_id") or ""))
        self.assertEqual(
            str(first.get("call_id") or "").strip(), str(second.get("call_id") or "").strip()
        )
        self.assertEqual(str(first.get("status") or ""), str(second.get("status") or ""))
        self.assertIn("repeatable-cache", str(first.get("stdout") or ""))
        self.assertIn("repeatable-cache", str(second.get("stdout") or ""))

    def test_terminate_replays_completed_payload_repeatably(self) -> None:
        events: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('terminate-replay'); import sys; sys.stdout.flush()\""
        )
        session = self.manager.start_session(command=command, on_activity=events.append)
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events))

        first = self.manager.terminate(str(session["session_id"]), on_activity=events.append)
        second = self.manager.terminate(str(session["session_id"]), on_activity=events.append)

        self.assertTrue(first.ok, first.payload)
        self.assertTrue(second.ok, second.payload)
        self.assertEqual(
            str(first.payload.get("session_id") or ""), str(second.payload.get("session_id") or "")
        )
        self.assertEqual(
            str(first.payload.get("call_id") or "").strip(),
            str(second.payload.get("call_id") or "").strip(),
        )
        self.assertEqual(str(first.payload.get("status") or ""), "ok")
        self.assertEqual(str(second.payload.get("status") or ""), "ok")
        self.assertIn("terminate-replay", str(first.payload.get("stdout") or ""))

    def test_tty_completed_replay_preserves_io_mode_metadata(self) -> None:
        if current_host_platform().family != "unix":
            self.skipTest("PTY semantics are only verified on unix hosts")
        events: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('pty-finish'); import sys; sys.stdout.flush()\""
        )
        session = self.manager.start_session(command=command, tty=True, on_activity=events.append)
        self.assertEqual(str(session.get("io_mode") or ""), "pty")
        self._wait_until(lambda: any(item.get("phase") == "completed" for item in events))

        replay = self.manager.terminate(str(session["session_id"]), on_activity=events.append)
        self.assertTrue(replay.ok, replay.payload)
        self.assertEqual(str(replay.payload.get("io_mode") or ""), "pty")
        self.assertTrue(bool(replay.payload.get("tty")))
        self.assertEqual(
            str(replay.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )

    def test_exec_command_payload_records_shell_override_and_resolved_shell(self) -> None:
        class _Runtime:
            def __init__(self) -> None:
                self.tools = type("Tools", (), {"_plugin_manager": None})()

            @staticmethod
            def _parse_args(arg_text: str):
                return parse_args(arg_text)

            @staticmethod
            def _normalize_shell_override(shell: str | None) -> str | None:
                normalized = str(shell or "").strip()
                return f"/resolved/{normalized}" if normalized else None

            @staticmethod
            def patch_requires_approval() -> bool:
                return False

            @staticmethod
            def _is_interrupt_requested() -> bool:
                return False

            def start_shell_session(
                self,
                command,
                *,
                cwd=None,
                login=True,
                tty=False,
                shell=None,
                max_output_chars=12000,
            ):
                return {
                    "session_id": "session_1",
                    "process_id": "proc_1",
                    "call_id": "call_1",
                    "command": command,
                    "cwd": cwd,
                    "login": login,
                    "tty": tty,
                    "shell": shell,
                }

            def write_shell_stdin_result(
                self,
                session_id,
                chars,
                *,
                yield_time_ms=None,
                allow_extended_empty_poll=False,
            ):
                del chars, allow_extended_empty_poll
                return CommandExecutionResult(
                    assistant_text="",
                    tool_events=[
                        ToolEvent(
                            name="write_stdin",
                            ok=True,
                            summary="write ok",
                            payload={
                                "session_id": session_id,
                                "call_id": "call_1",
                                "stdout": "ok\n",
                                "aggregated_output": "ok\n",
                                "status": "completed",
                                "exit_code": 0,
                                "yield_time_ms": yield_time_ms,
                            },
                        )
                    ],
                    item_events=[],
                )

        runtime = _Runtime()
        result = handle_known_command(
            runtime,
            name="exec_command",
            arg_text="'python -V' --shell powershell --yield-time-ms 250",
            text="/exec_command 'python -V' --shell powershell --yield-time-ms 250",
        )

        self.assertIsInstance(result, CommandExecutionResult)
        assert isinstance(result, CommandExecutionResult)
        payload = result.tool_events[0].payload
        self.assertEqual(payload["shell"], "/resolved/powershell")
        self.assertEqual(payload["shell_override"], "powershell")
        self.assertEqual(payload["resolved_shell"], "/resolved/powershell")
        self.assertEqual(payload["function_call_arguments"]["shell"], "/resolved/powershell")
        self.assertEqual(payload["function_call_arguments"]["shell_override"], "powershell")
        self.assertEqual(
            payload["function_call_arguments"]["resolved_shell"], "/resolved/powershell"
        )

    def test_canonical_exec_output_includes_codex_like_metadata_and_truncates_middle(self) -> None:
        text = "".join(f"line-{index:03d} abcdefghijklmnopqrstuvwxyz\n" for index in range(1, 81))

        output = canonical_exec_output_text(
            {
                "command": "emit many lines",
                "call_id": "call_metadata",
                "duration_ms": 250,
                "exit_code": 0,
                "aggregated_output": text,
                "aggregated_output_total_chars": len(text),
                "aggregated_output_total_lines": 80,
                "max_output_tokens": 32,
            }
        )

        self.assertRegex(output, r"^Chunk ID: [0-9a-f]{6}\n")
        self.assertIn("Wall time: 0.2500 seconds\n", output)
        self.assertIn("Process exited with code 0\n", output)
        self.assertIn("Original token count: ", output)
        self.assertIn("Output:\nTotal output lines: 80\n\n", output)
        self.assertIn("line-001", output)
        self.assertIn("line-080", output)
        self.assertIn("tokens truncated", output)

    def test_exec_command_uses_token_budget_for_shell_capture_and_model_visible_output(
        self,
    ) -> None:
        captured: dict[str, object] = {}

        class _Runtime:
            def __init__(self) -> None:
                self.tools = type("Tools", (), {"_plugin_manager": None})()

            @staticmethod
            def _parse_args(arg_text: str):
                return parse_args(arg_text)

            @staticmethod
            def _normalize_shell_override(shell: str | None) -> str | None:
                return str(shell or "").strip() or None

            @staticmethod
            def patch_requires_approval() -> bool:
                return False

            @staticmethod
            def _is_interrupt_requested() -> bool:
                return False

            def start_shell_session(
                self,
                command,
                *,
                cwd=None,
                login=True,
                tty=False,
                shell=None,
                max_output_chars=12000,
            ):
                captured["max_output_chars"] = max_output_chars
                return {
                    "session_id": "session_1",
                    "process_id": "proc_1",
                    "call_id": "call_1",
                    "command": command,
                    "cwd": cwd,
                    "login": login,
                    "tty": tty,
                    "shell": shell,
                }

            def write_shell_stdin_result(
                self,
                session_id,
                chars,
                *,
                yield_time_ms=None,
                allow_extended_empty_poll=False,
            ):
                del chars, allow_extended_empty_poll
                long_output = "".join(
                    f"row-{index:03d} zzzzzzzzzzzzzzzzzzzz\n" for index in range(1, 101)
                )
                return CommandExecutionResult(
                    assistant_text="",
                    tool_events=[
                        ToolEvent(
                            name="write_stdin",
                            ok=True,
                            summary="write ok",
                            payload={
                                "session_id": session_id,
                                "call_id": "call_1",
                                "stdout": long_output,
                                "aggregated_output": long_output,
                                "aggregated_output_total_chars": len(long_output),
                                "aggregated_output_total_lines": 100,
                                "status": "completed",
                                "exit_code": 0,
                                "yield_time_ms": yield_time_ms,
                            },
                        )
                    ],
                    item_events=[],
                )

        result = handle_known_command(
            _Runtime(),
            name="exec_command",
            arg_text="'emit rows' --yield-time-ms 250 --max-output-tokens 20",
            text="/exec_command 'emit rows' --yield-time-ms 250 --max-output-tokens 20",
        )

        self.assertIsInstance(result, CommandExecutionResult)
        assert isinstance(result, CommandExecutionResult)
        self.assertEqual(captured["max_output_chars"], 80)
        output = str(result.tool_events[0].payload.get("function_call_output") or "")
        self.assertIn("Chunk ID:", output)
        self.assertIn("Original token count:", output)
        self.assertIn("Total output lines: 100", output)
        self.assertIn("row-001", output)
        self.assertIn("row-100", output)
        self.assertIn("tokens truncated", output)

    def test_write_stdin_uses_requested_token_budget_without_polluting_session_default(
        self,
    ) -> None:
        manager = ShellSessionManager(host_platform=current_host_platform())
        long_line = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        code = (
            "import sys,time; "
            "print('ready'); sys.stdout.flush(); "
            "cmd = sys.stdin.read(4); "
            f"[(print('row-%03d ' % i + {long_line!r}), sys.stdout.flush()) for i in range(1, 30)] "
            "if cmd == 'dump' else None; "
            "time.sleep(10)"
        )

        class _Runtime:
            def __init__(self) -> None:
                self.tools = type("Tools", (), {"_plugin_manager": None})()

            @staticmethod
            def _parse_args(arg_text: str):
                return parse_args(arg_text)

            @staticmethod
            def _is_interrupt_requested() -> bool:
                return False

            def write_shell_stdin_result(
                self,
                session_id,
                chars,
                *,
                yield_time_ms=None,
                allow_extended_empty_poll=False,
                max_output_chars=None,
                on_activity=None,
                cancel_event=None,
            ):
                return manager.write_stdin_result(
                    session_id,
                    chars,
                    yield_time_ms=yield_time_ms,
                    allow_extended_empty_poll=allow_extended_empty_poll,
                    max_output_chars=max_output_chars,
                    on_activity=on_activity,
                    cancel_event=cancel_event,
                )

        session = manager.start_session(
            command=f"{shlex.quote(sys.executable)} -u -c {shlex.quote(code)}",
            max_output_chars=4000,
        )
        session_id = str(session["session_id"])
        self._wait_until(
            lambda: "ready"
            in str(
                manager.write_stdin(session_id, "", yield_time_ms=250).payload.get("stdout") or ""
            )
        )

        try:
            result = handle_known_command(
                _Runtime(),
                name="write_stdin",
                arg_text=f"{session_id} dump --yield-time-ms 500 --max-output-tokens 12",
                text=f"/write_stdin {session_id} dump --yield-time-ms 500 --max-output-tokens 12",
            )

            self.assertIsInstance(result, CommandExecutionResult)
            assert isinstance(result, CommandExecutionResult)
            payload = result.tool_events[0].payload
            self.assertEqual(payload.get("max_output_tokens"), 12)
            self.assertTrue(payload.get("stdout_truncated"))
            self.assertGreater(int(payload.get("stdout_total_chars") or 0), 48)
            self.assertIn("chars truncated", str(payload.get("stdout") or ""))
            output = str(payload.get("function_call_output") or "")
            self.assertIn("Total output lines:", output)
            self.assertIn("tokens truncated", output)

            stored_session = manager._get_session(session_id)
            self.assertIsNotNone(stored_session)
            assert stored_session is not None
            self.assertEqual(stored_session.max_output_chars, 4000)
        finally:
            manager.terminate(session_id)

    def test_exec_command_approval_payload_records_shell_override_and_resolved_shell(self) -> None:
        class _Runtime:
            def __init__(self) -> None:
                self.tools = type("Tools", (), {"_plugin_manager": None})()

            @staticmethod
            def _parse_args(arg_text: str):
                return parse_args(arg_text)

            @staticmethod
            def _normalize_shell_override(shell: str | None) -> str | None:
                normalized = str(shell or "").strip()
                return f"/resolved/{normalized}" if normalized else None

            @staticmethod
            def patch_requires_approval() -> bool:
                return True

            @staticmethod
            def _is_interrupt_requested() -> bool:
                return False

            def request_shell_approval(
                self, command, *, exec_mode, cwd, login, tty, shell, max_output_chars
            ):
                return ToolEvent(
                    name="shell_approval_requested",
                    ok=True,
                    summary="approval pending",
                    payload={
                        "command": command,
                        "exec_mode": exec_mode,
                        "cwd": cwd,
                        "login": login,
                        "tty": tty,
                        "shell": shell,
                        "max_output_chars": max_output_chars,
                        "status": "pending",
                    },
                )

        runtime = _Runtime()
        result = handle_known_command(
            runtime,
            name="exec_command",
            arg_text="'python -V' --shell bash --yield-time-ms 250",
            text="/exec_command 'python -V' --shell bash --yield-time-ms 250",
        )

        self.assertIsInstance(result, CommandExecutionResult)
        assert isinstance(result, CommandExecutionResult)
        payload = result.tool_events[0].payload
        self.assertEqual(payload["shell"], "/resolved/bash")
        self.assertEqual(payload["shell_override"], "bash")
        self.assertEqual(payload["resolved_shell"], "/resolved/bash")
