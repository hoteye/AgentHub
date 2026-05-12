from __future__ import annotations

# ruff: noqa: E402
import json
import os
import shlex
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.app_server_shell_protocol import _shell_protocol_fields
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.tools import ToolRegistry
from cli.agent_cli.tools_core import shell_result_runtime
from cli.agent_cli.tools_core.shell_bridge import execute_shell


class ToolRegistryShellTest(unittest.TestCase):
    @staticmethod
    def _assert_policy_snapshot_schema(snapshot: dict[str, object] | None) -> None:
        normalized = dict(snapshot or {})
        expected_keys = {
            "approvalPolicy",
            "sandboxMode",
            "networkAccessEnabled",
            "requestPermissionEnabled",
        }
        assert_keys = set(normalized.keys())
        if assert_keys != expected_keys:
            raise AssertionError(f"policySnapshot keys mismatch: {assert_keys} != {expected_keys}")
        approval_policy = normalized.get("approvalPolicy")
        sandbox_mode = normalized.get("sandboxMode")
        network_access_enabled = normalized.get("networkAccessEnabled")
        request_permission_enabled = normalized.get("requestPermissionEnabled")
        if approval_policy is not None and not isinstance(approval_policy, str):
            raise AssertionError(f"approvalPolicy type mismatch: {type(approval_policy)}")
        if sandbox_mode is not None and not isinstance(sandbox_mode, str):
            raise AssertionError(f"sandboxMode type mismatch: {type(sandbox_mode)}")
        if network_access_enabled is not None and not isinstance(network_access_enabled, bool):
            raise AssertionError(
                f"networkAccessEnabled type mismatch: {type(network_access_enabled)}"
            )
        if request_permission_enabled is not None and not isinstance(
            request_permission_enabled, bool
        ):
            raise AssertionError(
                f"requestPermissionEnabled type mismatch: {type(request_permission_enabled)}"
            )

    def test_shell_result_runtime_builds_started_session_payload(self) -> None:
        session = SimpleNamespace(
            call_id="call-123",
            process_id="proc-456",
            io_mode="pipes",
            started_at_ms=789,
        )

        payload = shell_result_runtime.build_started_session_payload(
            session=session,
            session_id="session-abc",
            command="echo test",
            cwd="/tmp/demo",
            login=False,
            tty=True,
            shell="/bin/sh",
        )

        self.assertEqual(payload["session_id"], "session-abc")
        self.assertEqual(payload["call_id"], "call-123")
        self.assertEqual(payload["process_id"], "proc-456")
        self.assertEqual(payload["command"], "echo test")
        self.assertEqual(payload["cwd"], "/tmp/demo")
        self.assertFalse(payload["login"])
        self.assertTrue(payload["tty"])
        self.assertEqual(payload["shell"], "/bin/sh")
        self.assertEqual(payload["io_mode"], "pipes")
        self.assertEqual(payload["started_at_ms"], 789)
        self.assertEqual(payload["phase"], "started")
        self.assertEqual(dict(payload["lifecycle"])["status"], "started")

    def test_shell_result_runtime_projects_output_and_final_status(self) -> None:
        output_payload = shell_result_runtime.output_snapshot_payload(
            SimpleNamespace(max_output_chars=5),
            {"stdout": "123456789", "stderr": "xy"},
        )

        self.assertEqual(output_payload["stdout"], "12…4 chars truncated…789")
        self.assertEqual(output_payload["stderr"], "xy")
        self.assertEqual(output_payload["aggregated_output"], "12…4 chars truncated…789\nxy")
        self.assertTrue(output_payload["stdout_truncated"])
        self.assertFalse(output_payload["stderr_truncated"])
        self.assertTrue(output_payload["aggregated_output_truncated"])

        class _CompletedSession:
            @staticmethod
            def final_payload() -> dict[str, object]:
                return {
                    "returncode": 0,
                    "exit_code": 0,
                    "timed_out": False,
                    "interrupted": True,
                    "ok": False,
                    "finished_at_ms": 100,
                    "status": "interrupted",
                }

        self.assertEqual(
            shell_result_runtime.final_status_fields(_CompletedSession()),
            {
                "returncode": 0,
                "exit_code": 0,
                "timed_out": False,
                "interrupted": True,
                "ok": False,
                "finished_at_ms": 100,
                "status": "interrupted",
            },
        )

    def test_builtin_shell_command_executes_on_current_platform(self) -> None:
        registry = ToolRegistry()
        platform = current_host_platform()

        event = registry.shell(platform.print_working_dir_command, timeout_sec=10)

        self.assertEqual(event.name, "shell")
        self.assertTrue(event.ok, event.payload.get("stderr"))
        self.assertEqual(event.payload["returncode"], 0)
        self.assertTrue(str(event.payload.get("stdout") or "").strip())

    def test_shell_command_can_be_interrupted(self) -> None:
        registry = ToolRegistry()
        cancel_event = threading.Event()
        result: dict[str, object] = {}
        platform = current_host_platform()
        command = "Start-Sleep -Seconds 5" if platform.os == "windows" else "sleep 5"

        def worker() -> None:
            result["event"] = registry.shell(
                command,
                timeout_sec=10,
                cancel_event=cancel_event,
            )

        started_at = time.monotonic()
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        time.sleep(0.25)
        cancel_event.set()
        thread.join(timeout=5)

        self.assertFalse(thread.is_alive(), "shell worker did not stop after interrupt")
        elapsed = time.monotonic() - started_at
        event = result["event"]
        self.assertFalse(event.ok)
        self.assertEqual(event.name, "shell")
        self.assertTrue(event.payload.get("interrupted"))
        self.assertEqual(event.summary, "shell interrupted")
        self.assertLess(elapsed, 4.0)

    def test_execute_shell_supports_explicit_cwd(self) -> None:
        platform = current_host_platform()
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir).resolve()
            event = execute_shell(
                host_platform=platform,
                command=platform.print_working_dir_command,
                cwd=str(target),
                timeout_sec=10,
            )

        self.assertTrue(event.ok, event.payload.get("stderr") or event.payload.get("error"))
        self.assertEqual(event.payload.get("cwd"), str(target))
        stdout_text = str(event.payload.get("stdout") or "").strip().lower().replace("\\", "/")
        expected = str(target).lower().replace("\\", "/")
        self.assertIn(expected, stdout_text)

    def test_shell_resolves_relative_cwd_against_workspace_root(self) -> None:
        registry = ToolRegistry()
        platform = current_host_platform()
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir).resolve()
            target = workspace_root / "nested"
            target.mkdir()
            registry.set_workspace_root(workspace_root)

            event = registry.shell(
                platform.print_working_dir_command,
                cwd="nested",
                timeout_sec=10,
            )

        self.assertTrue(event.ok, event.payload.get("stderr") or event.payload.get("error"))
        self.assertEqual(Path(str(event.payload.get("cwd") or "")).resolve(), target.resolve())
        stdout_text = str(event.payload.get("stdout") or "").strip().lower().replace("\\", "/")
        self.assertIn(str(target).lower().replace("\\", "/"), stdout_text)

    def test_shell_start_resolves_relative_cwd_against_workspace_root(self) -> None:
        registry = ToolRegistry()
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir).resolve()
            target = workspace_root / "nested-workdir"
            target.mkdir()
            registry.set_workspace_root(workspace_root)

            events: list[dict[str, object]] = []
            command = f"{shlex.quote(sys.executable)} -u -c " '"import os; print(os.getcwd())"'

            session = registry.shell_start(command, cwd="nested-workdir", on_activity=events.append)
            self.assertTrue(str(session.get("session_id")))

            start_deadline = time.monotonic() + 3.0
            while time.monotonic() < start_deadline:
                if any(item.get("phase") == "started" for item in events):
                    break
                time.sleep(0.02)
            started_event = next(item for item in events if item.get("phase") == "started")
            self.assertEqual(Path(str(started_event.get("cwd") or "")).resolve(), target.resolve())
            self.assertEqual(
                str(started_event.get("call_id") or "").strip(),
                str(session.get("call_id") or "").strip(),
            )
            self.assertEqual(str(started_event.get("source") or ""), "shell_session_manager")
            self.assertEqual(dict(started_event.get("lifecycle") or {}).get("kind"), "begin")

            completion_deadline = time.monotonic() + 3.0
            while time.monotonic() < completion_deadline:
                if any(item.get("phase") == "completed" for item in events):
                    break
                time.sleep(0.02)
            self.assertTrue(any(item.get("phase") == "completed" for item in events))

    def test_shell_session_surfaces_background_contract_and_persists_artifact(self) -> None:
        registry = ToolRegistry()
        with tempfile.TemporaryDirectory() as temp_dir:
            with tempfile.TemporaryDirectory() as temp_home:
                with patch.dict(os.environ, {"AGENT_CLI_HOME": temp_home}, clear=False):
                    workspace_root = Path(temp_dir).resolve()
                    registry.set_workspace_root(workspace_root)
                    outputs: list[dict[str, object]] = []
                    command = (
                        f"{shlex.quote(sys.executable)} -u -c "
                        "\"import time,sys; print('ready'); sys.stdout.flush(); time.sleep(30)\""
                    )

                    session = registry.shell_start(command, on_activity=outputs.append)
                    session_id = str(session["session_id"])
                    self.assertEqual(str(session.get("task_id") or ""), session_id)
                    self.assertEqual(str(session.get("background_artifact_path") or ""), "")
                    self.assertTrue(bool(session.get("completion_notification_available")))

                    started_event = next(item for item in outputs if item.get("phase") == "started")
                    self.assertEqual(str(started_event.get("task_id") or ""), session_id)
                    self.assertEqual(str(started_event.get("background_artifact_path") or ""), "")

                    artifact_path = (
                        Path(temp_home)
                        / "tool_output_cache"
                        / "background_shell"
                        / f"{session_id}.json"
                    )
                    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
                    self.assertEqual(artifact_payload["task_id"], session_id)
                    self.assertEqual(artifact_payload["completion_poll_tool"], "write_stdin")
                    self.assertEqual(artifact_payload["status"], "started")
                    self.assertEqual(artifact_payload["workflow_state"], "running")
                    self.assertEqual(artifact_payload["completion_state"], "pending")
                    self.assertEqual(artifact_payload["notification_state"], "pending")
                    self.assertEqual(artifact_payload["summary"], "background shell running")
                    self.assertFalse(
                        (
                            workspace_root
                            / ".config"
                            / "tool_output_cache"
                            / "background_shell"
                            / f"{session_id}.json"
                        ).exists()
                    )

                    poll = registry.shell_write_stdin(
                        session_id, "", yield_time_ms=50, on_activity=outputs.append
                    )
                    self.assertTrue(poll.ok, poll.payload)
                    self.assertEqual(str(poll.payload.get("task_id") or ""), session_id)
                    self.assertEqual(str(poll.payload.get("background_artifact_path") or ""), "")
                    self.assertEqual(
                        str(poll.payload.get("completion_notification_status") or ""), "pending"
                    )
                    self.assertEqual(str(poll.payload.get("completion_state") or ""), "pending")
                    self.assertEqual(
                        str(poll.payload.get("summary") or ""), "background shell running"
                    )

                    terminate_event = registry.shell_terminate(
                        session_id, on_activity=outputs.append
                    )
                    self.assertFalse(terminate_event.ok)
                    self.assertEqual(str(terminate_event.payload.get("task_id") or ""), session_id)

                    updated_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
                    self.assertEqual(updated_payload["task_id"], session_id)
                    self.assertEqual(updated_payload["status"], "interrupted")
                    self.assertEqual(updated_payload["completion_notification_status"], "completed")
            self.assertEqual(updated_payload["completion_state"], "ready_to_adopt")
            self.assertEqual(updated_payload["result_state"], "returned")
            self.assertEqual(updated_payload["terminal_state"], "interrupted")
            self.assertEqual(updated_payload["notification_state"], "ready")
            self.assertEqual(updated_payload["summary"], "background shell interrupted")

    def test_execute_shell_reports_unified_exec_metadata_and_truncation(self) -> None:
        platform = current_host_platform()
        event = execute_shell(
            host_platform=platform,
            command="echo 1234567890",
            timeout_sec=10,
            max_output_chars=6,
            login=False,
            tty=False,
            shell="/bin/sh",
        )

        self.assertTrue(event.ok, event.payload.get("stderr") or event.payload.get("error"))
        self.assertEqual(event.payload.get("status"), "ok")
        self.assertEqual(event.payload.get("exit_code"), 0)
        self.assertTrue(event.payload.get("stdout_truncated"))
        self.assertGreaterEqual(int(event.payload.get("stdout_total_chars") or 0), 6)
        self.assertEqual(dict(event.payload.get("lifecycle") or {}).get("phase"), "completed")
        self.assertEqual(dict(event.payload.get("lifecycle") or {}).get("kind"), "end")
        self.assertTrue(
            str(dict(event.payload.get("lifecycle") or {}).get("call_id") or "").strip()
        )
        self.assertIn("started_at_ms", event.payload)
        self.assertIn("finished_at_ms", event.payload)
        self.assertFalse(event.payload.get("login"))
        self.assertFalse(event.payload.get("tty"))
        self.assertEqual(
            str(event.payload.get("aggregated_output") or ""),
            str(event.payload.get("stdout") or ""),
        )
        self.assertEqual(
            str(event.payload.get("output_text") or ""), str(event.payload.get("stdout") or "")
        )
        self.assertEqual(str(event.payload.get("io_mode") or ""), "pipes")

    def test_execute_shell_stderr_only_preserves_projection_source_fields(self) -> None:
        platform = current_host_platform()
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"import sys; sys.stderr.write('ERR\\\\n'); sys.stderr.flush(); raise SystemExit(2)\""
        )

        event = execute_shell(
            host_platform=platform,
            command=command,
            timeout_sec=10,
            login=False,
            tty=False,
            shell="/bin/sh" if platform.os != "windows" else None,
        )

        self.assertFalse(event.ok)
        self.assertEqual(event.payload.get("exit_code"), 2)
        self.assertEqual(str(event.payload.get("stdout") or ""), "")
        self.assertEqual(str(event.payload.get("stderr") or ""), "ERR\n")
        self.assertEqual(str(event.payload.get("aggregated_output") or ""), "ERR\n")
        self.assertEqual(str(event.payload.get("output_text") or ""), "")

    def test_execute_shell_projects_policy_readout_fields(self) -> None:
        event = execute_shell(
            host_platform=current_host_platform(),
            command="echo policy",
            timeout_sec=10,
        )

        self.assertTrue(event.ok, event.payload)
        fields = _shell_protocol_fields(dict(event.payload or {}))
        self.assertEqual(fields.get("policyDecision"), "allowed")
        self.assertEqual(fields.get("policyDecisionReason"), "policy_allowed")
        self._assert_policy_snapshot_schema(dict(fields.get("policySnapshot") or {}))

    def test_execute_shell_policy_readout_field_names_guard(self) -> None:
        event = execute_shell(
            host_platform=current_host_platform(),
            command="echo policy-name-guard",
            timeout_sec=10,
        )

        self.assertTrue(event.ok, event.payload)
        fields = _shell_protocol_fields(dict(event.payload or {}))
        self.assertIn("policyDecision", fields)
        self.assertIn("policyDecisionReason", fields)
        self.assertIn("policySnapshot", fields)
        self.assertNotIn("policy_decision", fields)
        self.assertNotIn("policy_decision_reason", fields)
        self.assertNotIn("policy_snapshot", fields)
        self.assertEqual(str(fields.get("policyDecision") or ""), "allowed")
        self.assertEqual(str(fields.get("policyDecisionReason") or ""), "policy_allowed")
        snapshot = dict(fields.get("policySnapshot") or {})
        self._assert_policy_snapshot_schema(snapshot)
        self.assertEqual(
            set(snapshot.keys()),
            {"approvalPolicy", "sandboxMode", "networkAccessEnabled", "requestPermissionEnabled"},
        )

    def test_policy_snapshot_schema_guard_keys_and_types_for_projection_payload_variants(
        self,
    ) -> None:
        expected_keys = {
            "approvalPolicy",
            "sandboxMode",
            "networkAccessEnabled",
            "requestPermissionEnabled",
        }
        payload_variants = [
            {
                "status": "ok",
                "approval_policy": "never",
                "sandbox_mode": "workspace-write",
                "network_access_enabled": True,
                "request_permission_enabled": False,
            },
            {
                "status": "policy_denied",
                "error_code": "test_scope_required",
                "approval_policy": "on-request",
                "sandbox_mode": "read-only",
                "network_access_enabled": "disabled",
                "request_permission_enabled": "1",
            },
            {
                "status": "ok",
                "approval_policy": "",
                "sandbox_mode": "",
                "network_access_enabled": "invalid",
                "request_permission_enabled": "invalid",
            },
        ]
        for payload in payload_variants:
            fields = _shell_protocol_fields(dict(payload))
            snapshot = dict(fields.get("policySnapshot") or {})
            self.assertEqual(set(snapshot.keys()), expected_keys)
            self.assertEqual(len(snapshot), len(expected_keys))
            self.assertTrue(
                snapshot.get("approvalPolicy") is None
                or isinstance(snapshot.get("approvalPolicy"), str)
            )
            self.assertTrue(
                snapshot.get("sandboxMode") is None or isinstance(snapshot.get("sandboxMode"), str)
            )
            self.assertTrue(
                snapshot.get("networkAccessEnabled") is None
                or isinstance(snapshot.get("networkAccessEnabled"), bool)
            )
            self.assertTrue(
                snapshot.get("requestPermissionEnabled") is None
                or isinstance(snapshot.get("requestPermissionEnabled"), bool)
            )

    def test_shell_session_tty_unix_merges_stderr_into_stdout_stream(self) -> None:
        platform = current_host_platform()
        if platform.family != "unix":
            self.skipTest("PTY semantics are only verified on unix hosts")
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            '"import sys; '
            "sys.stderr.write('ERR\\\\n'); sys.stderr.flush(); "
            "line = sys.stdin.readline().strip(); "
            "print('OUT:' + line); sys.stdout.flush()\""
        )

        session = registry.shell_start(command, tty=True, on_activity=outputs.append)
        self.assertEqual(str(session.get("io_mode") or ""), "pty")

        write_event = registry.shell_write_stdin(
            str(session["session_id"]),
            "ping\n",
            yield_time_ms=500,
            on_activity=outputs.append,
        )
        self.assertTrue(write_event.ok, write_event.payload)
        self.assertEqual(str(write_event.payload.get("io_mode") or ""), "pty")
        self.assertEqual(str(write_event.payload.get("stderr") or ""), "")
        combined = str(write_event.payload.get("aggregated_output") or "")
        self.assertIn("ERR", combined)
        self.assertIn("OUT:ping", combined)
        output_streams = {
            str(item.get("stream") or "") for item in outputs if item.get("phase") == "output"
        }
        self.assertIn("stdout", output_streams)
        self.assertNotIn("stderr", output_streams)

    def test_execute_shell_rejects_empty_command(self) -> None:
        event = execute_shell(
            host_platform=current_host_platform(),
            command="   ",
        )
        self.assertFalse(event.ok)
        self.assertEqual(event.summary, "shell invalid command")
        self.assertEqual(event.payload.get("status"), "invalid")

    def test_shell_session_supports_write_stdin_and_terminate(self) -> None:
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            f'"import sys, time; '
            f"print('ready'); sys.stdout.flush(); "
            f"line = sys.stdin.readline().strip(); "
            f"print('echo:' + line); sys.stdout.flush(); "
            f'time.sleep(5)"'
        )

        session = registry.shell_start(command, on_activity=outputs.append)
        session_id = str(session["session_id"])
        process_id = str(session["process_id"])
        self.assertTrue(session_id)

        write_event = registry.shell_write_stdin(session_id, "ping\n", on_activity=outputs.append)
        self.assertTrue(write_event.ok, write_event.payload)
        self.assertEqual(write_event.payload.get("process_id"), process_id)
        self.assertEqual(write_event.payload.get("session_id"), session_id)
        self.assertEqual(write_event.payload.get("stdin"), "ping\n")
        self.assertEqual(write_event.payload.get("interaction_input"), "ping\n")
        self.assertEqual(write_event.payload.get("status"), "written")
        self.assertEqual(dict(write_event.payload.get("lifecycle") or {}).get("phase"), "input")
        self.assertEqual(
            dict(write_event.payload.get("lifecycle") or {}).get("call_id"), session.get("call_id")
        )
        self.assertTrue(
            any(item.get("phase") == "input" and item.get("stdin") == "ping\n" for item in outputs)
        )

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if any(str(item.get("text") or "").strip() == "echo:ping" for item in outputs):
                break
            time.sleep(0.05)

        self.assertTrue(any(str(item.get("text") or "").strip() == "ready" for item in outputs))
        self.assertTrue(any(str(item.get("text") or "").strip() == "echo:ping" for item in outputs))
        self.assertTrue(
            any(
                item.get("phase") == "output"
                and str(item.get("chunk") or "").strip()
                and str(item.get("call_id") or "").strip()
                == str(session.get("call_id") or "").strip()
                for item in outputs
            )
        )
        self.assertTrue(
            any(
                item.get("phase") == "output"
                and str(item.get("output_text") or "").strip() == "echo:ping"
                and str(item.get("output_chunk") or "").strip()
                for item in outputs
            )
        )

        terminate_event = registry.shell_terminate(session_id, on_activity=outputs.append)
        self.assertFalse(terminate_event.ok)
        self.assertTrue(terminate_event.payload.get("interrupted"))
        self.assertEqual(terminate_event.payload.get("session_id"), session_id)
        self.assertEqual(terminate_event.payload.get("process_id"), process_id)
        self.assertEqual(terminate_event.payload.get("status"), "interrupted")
        self.assertEqual(
            dict(terminate_event.payload.get("lifecycle") or {}).get("phase"), "completed"
        )
        self.assertEqual(
            dict(terminate_event.payload.get("lifecycle") or {}).get("call_id"),
            session.get("call_id"),
        )

    def test_shell_session_rejects_followups_after_terminate(self) -> None:
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"import time; print('ready'); time.sleep(30)\""
        )

        session = registry.shell_start(command, on_activity=outputs.append)
        session_id = str(session["session_id"])

        terminate_event = registry.shell_terminate(session_id, on_activity=outputs.append)
        self.assertFalse(terminate_event.ok)

        late_write = registry.shell_write_stdin(session_id, "late\n", on_activity=outputs.append)
        late_terminate = registry.shell_terminate(session_id, on_activity=outputs.append)

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

    def test_shell_write_stdin_empty_chars_is_noop(self) -> None:
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"import time; print('ready'); time.sleep(30)\""
        )

        session = registry.shell_start(command, on_activity=outputs.append)
        session_id = str(session["session_id"])

        noop_event = registry.shell_write_stdin(session_id, "", on_activity=outputs.append)
        self.assertTrue(noop_event.ok, noop_event.payload)
        self.assertEqual(noop_event.payload.get("status"), "noop")
        self.assertEqual(noop_event.payload.get("stdin"), "")
        self.assertEqual(dict(noop_event.payload.get("lifecycle") or {}).get("phase"), "input")
        self.assertEqual(
            dict(noop_event.payload.get("lifecycle") or {}).get("call_id"), session.get("call_id")
        )

        terminate_event = registry.shell_terminate(session_id, on_activity=outputs.append)
        self.assertFalse(terminate_event.ok)

    def test_shell_write_stdin_can_poll_incremental_output(self) -> None:
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        code = (
            "import sys,time; "
            "print('ready'); "
            "sys.stdout.flush(); "
            "[((time.sleep(0.2), print('delayed:done'), sys.stdout.flush()) "
            "if (cmd:=raw.strip()) == 'delayed' "
            "else ((print('bye'), sys.stdout.flush(), (_ for _ in ()).throw(SystemExit)) "
            "if cmd == 'exit' "
            "else (None,))) for raw in sys.stdin]"
        )
        command = f"{shlex.quote(sys.executable)} -u -c {shlex.quote(code)}"

        session = registry.shell_start(command, on_activity=outputs.append)
        session_id = str(session["session_id"])
        self.assertTrue(session_id)

        initial = registry.shell_write_stdin(
            session_id,
            "delayed\n",
            yield_time_ms=20,
            on_activity=outputs.append,
        )
        self.assertTrue(initial.ok, initial.payload)
        self.assertNotIn("delayed:done", str(initial.payload.get("aggregated_output") or ""))

        poll = registry.shell_write_stdin(
            session_id,
            "",
            yield_time_ms=800,
            on_activity=outputs.append,
        )
        self.assertTrue(poll.ok, poll.payload)
        self.assertEqual(poll.payload.get("status"), "noop")
        self.assertIn("delayed:done", str(poll.payload.get("aggregated_output") or ""))

    def test_shell_session_callback_registration_is_idempotent_for_same_callable(self) -> None:
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"import sys; print('ready'); sys.stdout.flush(); "
            "line = sys.stdin.readline().strip(); "
            "print('echo:' + line); sys.stdout.flush()\""
        )

        session = registry.shell_start(command, on_activity=outputs.append)
        session_id = str(session["session_id"])
        write_event = registry.shell_write_stdin(session_id, "once\n", on_activity=outputs.append)
        self.assertTrue(write_event.ok, write_event.payload)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            completed = [item for item in outputs if item.get("phase") == "completed"]
            if completed:
                break
            time.sleep(0.02)

        input_events = [
            item
            for item in outputs
            if item.get("phase") == "input" and item.get("stdin") == "once\n"
        ]
        completed_events = [item for item in outputs if item.get("phase") == "completed"]
        echoed_output = [
            item for item in outputs if str(item.get("text") or "").strip() == "echo:once"
        ]

        self.assertEqual(len(input_events), 1)
        self.assertEqual(len(completed_events), 1)
        self.assertEqual(len(echoed_output), 1)

    def test_shell_session_blocks_followups_after_natural_completion(self) -> None:
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('natural completion'); import sys; sys.stdout.flush()\""
        )

        session = registry.shell_start(command, on_activity=outputs.append)
        session_id = str(session["session_id"])
        self.assertTrue(session_id)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if any(item.get("phase") == "completed" for item in outputs):
                break
            time.sleep(0.02)
        self.assertTrue(any(item.get("phase") == "completed" for item in outputs))

        late_write = registry.shell_write_stdin(session_id, "late\n", on_activity=outputs.append)
        late_terminate = registry.shell_terminate(session_id, on_activity=outputs.append)

        self.assertFalse(late_write.ok)
        self.assertEqual(late_write.payload.get("status"), "completed")
        self.assertEqual(late_write.payload.get("final_status"), "ok")
        self.assertEqual(
            str(late_write.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )
        self.assertTrue(late_terminate.ok)
        self.assertEqual(late_terminate.payload.get("status"), "ok")
        self.assertEqual(
            str(late_terminate.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )
        self.assertEqual(late_write.payload.get("phase"), "completed")
        lifecycle = dict(late_write.payload.get("lifecycle") or {})
        self.assertEqual(lifecycle.get("kind"), "end")
        self.assertEqual(lifecycle.get("status"), "completed")

    def test_shell_empty_poll_returns_completed_snapshot(self) -> None:
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('snapshot-ready'); import sys; sys.stdout.flush()\""
        )

        session = registry.shell_start(command, on_activity=outputs.append)
        session_id = str(session["session_id"])
        self.assertTrue(session_id)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if any(item.get("phase") == "completed" for item in outputs):
                break
            time.sleep(0.02)
        self.assertTrue(any(item.get("phase") == "completed" for item in outputs))

        poll = registry.shell_write_stdin(
            session_id,
            "",
            yield_time_ms=50,
            on_activity=outputs.append,
        )
        self.assertTrue(poll.ok, poll.payload)
        self.assertEqual(str(poll.payload.get("session_id") or ""), session_id)
        self.assertEqual(
            str(poll.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )
        self.assertEqual(str(poll.payload.get("status") or ""), "ok")
        self.assertIn("snapshot-ready", str(poll.payload.get("stdout") or ""))

    def test_shell_subscribe_replays_cached_history_with_stable_order(self) -> None:
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        late_events: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('subscribe-cache'); import sys; sys.stdout.flush()\""
        )

        session = registry.shell_start(command, on_activity=outputs.append)
        session_id = str(session["session_id"])
        self.assertTrue(session_id)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if any(item.get("phase") == "completed" for item in outputs):
                break
            time.sleep(0.02)
        self.assertTrue(any(item.get("phase") == "completed" for item in outputs))

        subscribed = registry.shell_subscribe(session_id, on_activity=late_events.append)
        self.assertTrue(subscribed.ok, subscribed.payload)
        self.assertEqual(str(subscribed.payload.get("status") or ""), "subscribed")
        self.assertTrue(late_events)
        phases = [str(item.get("phase") or "") for item in late_events]
        self.assertEqual(phases[0], "subscribe")
        self.assertEqual(phases[-1], "completed")
        self.assertIn("started", phases)
        self.assertIn("output", phases)
        completed = next(item for item in late_events if item.get("phase") == "completed")
        self.assertEqual(
            str(completed.get("call_id") or "").strip(), str(session.get("call_id") or "").strip()
        )
        self.assertIn("subscribe-cache", str(completed.get("stdout") or ""))

    def test_shell_write_stdin_immediate_completion_never_returns_write_failed(self) -> None:
        registry = ToolRegistry()
        outputs: list[dict[str, object]] = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            "\"print('write-race'); import sys; sys.stdout.flush()\""
        )

        session = registry.shell_start(command, on_activity=outputs.append)
        session_id = str(session["session_id"])
        self.assertTrue(session_id)

        early_write = registry.shell_write_stdin(session_id, "late\n", on_activity=outputs.append)
        self.assertNotEqual(str(early_write.payload.get("status") or ""), "write_failed")

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if any(item.get("phase") == "completed" for item in outputs):
                break
            time.sleep(0.02)
        self.assertTrue(any(item.get("phase") == "completed" for item in outputs))

        late_write = registry.shell_write_stdin(session_id, "late\n", on_activity=outputs.append)
        self.assertFalse(late_write.ok)
        self.assertEqual(str(late_write.payload.get("status") or ""), "completed")
        self.assertEqual(
            str(late_write.payload.get("call_id") or "").strip(),
            str(session.get("call_id") or "").strip(),
        )
        self.assertEqual(str(late_write.payload.get("completion_state") or ""), "adopted")
        self.assertEqual(str(late_write.payload.get("result_state") or ""), "adopted")
        self.assertEqual(
            str(late_write.payload.get("notification_state") or ""), "foreground_adopted"
        )
        self.assertEqual(
            str(late_write.payload.get("summary") or ""), "background shell result adopted"
        )
