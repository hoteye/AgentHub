from __future__ import annotations

import shlex
import sys
import time
from typing import Any, Dict, List

from cli.agent_cli.host_platform import HostPlatform, current_host_platform
from cli.agent_cli.tools_core.shell_bridge import ShellSessionManager


def _wait_until(predicate: Any, *, timeout_seconds: float = 3.0) -> None:
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise TimeoutError("condition not met before timeout")


def _session_shell_override(host_platform: HostPlatform) -> str | None:
    if str(host_platform.os or "").strip().lower() == "windows":
        return "powershell"
    return None


def _python_shell_command(host_platform: HostPlatform, code: str, *, python_executable: str | None = None) -> str:
    executable = str(python_executable or sys.executable).strip() or sys.executable
    if str(host_platform.os or "").strip().lower() == "windows":
        escaped_executable = executable.replace("'", "''")
        escaped_code = str(code or "").replace("'", "''")
        return f"& '{escaped_executable}' -u -c '{escaped_code}'"
    return f"{shlex.quote(executable)} -u -c {shlex.quote(str(code or ''))}"


def _interactive_command(host_platform: HostPlatform, *, python_executable: str | None = None) -> str:
    code = (
        "import sys,time; "
        "print('ready'); sys.stdout.flush(); "
        "[(time.sleep(0.2), print('delayed:done'), sys.stdout.flush()) if (cmd:=raw.strip()) == 'delayed' "
        "else ((print('bye'), sys.stdout.flush(), (_ for _ in ()).throw(SystemExit)) if cmd == 'exit' "
        "else (print('echo:' + cmd), sys.stdout.flush())) for raw in sys.stdin]"
    )
    return _python_shell_command(host_platform, code, python_executable=python_executable)


def _long_running_command(host_platform: HostPlatform, *, python_executable: str | None = None) -> str:
    code = "import sys,time; print('alive'); sys.stdout.flush(); time.sleep(30)"
    return _python_shell_command(host_platform, code, python_executable=python_executable)


def _case_one_shot(manager: ShellSessionManager, host_platform: HostPlatform, *, python_executable: str | None = None) -> Dict[str, Any]:
    session = manager.start_session(
        command=_python_shell_command(host_platform, "print('wave02-one-shot')", python_executable=python_executable),
        shell=_session_shell_override(host_platform),
    )
    completed = manager.wait_for_completion(str(session.get("session_id") or ""), timeout_sec=3.0)
    stdout = str(completed.get("stdout") or "")
    passed = completed.get("status") == "ok" and "wave02-one-shot" in stdout
    return {
        "name": "one_shot",
        "passed": bool(passed),
        "status": str(completed.get("status") or ""),
        "stdout": stdout,
        "session_id": str(session.get("session_id") or ""),
        "call_id": str(session.get("call_id") or ""),
    }


def _case_interactive_session(
    manager: ShellSessionManager,
    host_platform: HostPlatform,
    *,
    python_executable: str | None = None,
) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    session = manager.start_session(
        command=_interactive_command(host_platform, python_executable=python_executable),
        shell=_session_shell_override(host_platform),
        on_activity=events.append,
    )
    session_id = str(session.get("session_id") or "")
    ready_poll = manager.write_stdin(session_id, "", yield_time_ms=500, on_activity=events.append)
    write = manager.write_stdin(session_id, "hello\n", yield_time_ms=500, on_activity=events.append)
    exit_event = manager.write_stdin(session_id, "exit\n", yield_time_ms=500, on_activity=events.append)
    if exit_event.payload.get("exit_code") is None:
        _wait_until(lambda: any(item.get("phase") == "completed" for item in events), timeout_seconds=3.0)
    completed = manager.wait_for_completion(session_id, timeout_sec=0.2)
    passed = (
        ready_poll.ok
        and "ready" in str(ready_poll.payload.get("aggregated_output") or "")
        and write.ok
        and "echo:hello" in str(write.payload.get("aggregated_output") or "")
        and completed.get("status") == "ok"
    )
    return {
        "name": "interactive_session",
        "passed": bool(passed),
        "session_id": session_id,
        "call_id": str(session.get("call_id") or ""),
        "ready_output": str(ready_poll.payload.get("aggregated_output") or ""),
        "write_output": str(write.payload.get("aggregated_output") or ""),
        "completed_status": str(completed.get("status") or ""),
        "completed_stdout": str(completed.get("stdout") or ""),
    }


def _case_empty_poll(
    manager: ShellSessionManager,
    host_platform: HostPlatform,
    *,
    python_executable: str | None = None,
) -> Dict[str, Any]:
    session = manager.start_session(
        command=_interactive_command(host_platform, python_executable=python_executable),
        shell=_session_shell_override(host_platform),
    )
    session_id = str(session.get("session_id") or "")
    manager.write_stdin(session_id, "", yield_time_ms=400)
    early = manager.write_stdin(session_id, "delayed\n", yield_time_ms=20)
    polled = manager.write_stdin(session_id, "", yield_time_ms=800)
    manager.write_stdin(session_id, "exit\n", yield_time_ms=400)
    completed = manager.wait_for_completion(session_id, timeout_sec=1.0)
    passed = (
        early.ok
        and "delayed:done" not in str(early.payload.get("aggregated_output") or "")
        and polled.ok
        and "delayed:done" in str(polled.payload.get("aggregated_output") or "")
        and str(completed.get("status") or "") == "ok"
    )
    return {
        "name": "empty_poll",
        "passed": bool(passed),
        "session_id": session_id,
        "early_output": str(early.payload.get("aggregated_output") or ""),
        "poll_output": str(polled.payload.get("aggregated_output") or ""),
        "completed_status": str(completed.get("status") or ""),
    }


def _case_terminate(
    manager: ShellSessionManager,
    host_platform: HostPlatform,
    *,
    python_executable: str | None = None,
) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    session = manager.start_session(
        command=_long_running_command(host_platform, python_executable=python_executable),
        shell=_session_shell_override(host_platform),
        on_activity=events.append,
    )
    session_id = str(session.get("session_id") or "")
    _wait_until(
        lambda: any(str(item.get("text") or "").strip() == "alive" for item in events if isinstance(item, dict)),
        timeout_seconds=3.0,
    )
    terminated = manager.terminate(session_id, on_activity=events.append)
    _wait_until(lambda: any(item.get("phase") == "completed" for item in events), timeout_seconds=3.0)
    completed = manager.wait_for_completion(session_id, timeout_sec=0.2)
    passed = (
        terminated.ok is False
        and str(terminated.payload.get("status") or "") == "interrupted"
        and str(completed.get("status") or "") == "interrupted"
    )
    return {
        "name": "terminate",
        "passed": bool(passed),
        "session_id": session_id,
        "terminate_status": str(terminated.payload.get("status") or ""),
        "completed_status": str(completed.get("status") or ""),
        "call_id": str(session.get("call_id") or ""),
    }


def run_command_execution_wave02_acceptance(
    *,
    host_platform: HostPlatform | None = None,
    python_executable: str | None = None,
) -> Dict[str, Any]:
    resolved_host = host_platform or current_host_platform()
    manager = ShellSessionManager(host_platform=resolved_host)
    cases = [
        _case_one_shot(manager, resolved_host, python_executable=python_executable),
        _case_interactive_session(manager, resolved_host, python_executable=python_executable),
        _case_empty_poll(manager, resolved_host, python_executable=python_executable),
        _case_terminate(manager, resolved_host, python_executable=python_executable),
    ]
    return {
        "suite": "command_execution_wave02_acceptance",
        "host": {
            "os": str(resolved_host.os or ""),
            "family": str(resolved_host.family or ""),
            "shell_kind": str(resolved_host.shell_kind or ""),
        },
        "python_executable": str(python_executable or sys.executable),
        "cases": cases,
        "passed": all(bool(item.get("passed")) for item in cases),
    }
