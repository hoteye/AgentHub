from __future__ import annotations

import json
import shlex
from pathlib import Path
from types import SimpleNamespace

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core.command_handlers import handle_known_command

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

class _FakeRuntime:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.tools = SimpleNamespace(_plugin_manager=None)

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
        command: str,
        *,
        cwd: str | None = None,
        login: bool = True,
        tty: bool = False,
        shell: str | None = None,
        max_output_chars: int = 12000,
    ) -> dict:
        if self.fail_start:
            raise RuntimeError("spawn denied by test runtime")
        return {
            "session_id": "sess-123",
            "process_id": "pid-456",
            "call_id": "call-789",
            "command": command,
            "cwd": cwd,
            "login": login,
            "tty": tty,
            "shell": shell,
            "max_output_chars": max_output_chars,
        }

    def write_shell_stdin_result(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        allow_extended_empty_poll: bool = False,
    ) -> CommandExecutionResult:
        del allow_extended_empty_poll
        event = ToolEvent(
            name="shell",
            ok=True,
            summary="shell rc=0",
            payload={
                "ok": True,
                "command": "pwd",
                "session_id": session_id,
                "call_id": "call-789",
                "process_id": "pid-456",
                "status": "ok",
                "stdout": "/workspace\n",
                "aggregated_output": "/workspace\n",
                "exit_code": 0,
                "returncode": 0,
                "yield_time_ms": yield_time_ms,
            },
        )
        return CommandExecutionResult(
            assistant_text="/workspace",
            tool_events=[event],
            item_events=[],
        )

def test_exec_command_writes_tool_trace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENTHUB_DEBUG_RESPONSES_TIMELINE", raising=False)
    monkeypatch.setenv("AGENTHUB_DEBUG_LOG_DIR", str(tmp_path))

    runtime = _FakeRuntime()
    result = handle_known_command(runtime, name="exec_command", arg_text="pwd --yield-time-ms 5", text="/exec_command pwd")

    assert isinstance(result, CommandExecutionResult)

    rows = _read_jsonl(tmp_path / "tool_trace.jsonl")
    stages = [row["stage"] for row in rows]

    assert "tool.exec_command.started" in stages
    assert "tool.exec_command.session_started" in stages
    assert "tool.exec_command.completed" in stages
    completed = next(row for row in rows if row["stage"] == "tool.exec_command.completed")
    assert completed["payload"]["command"] == "pwd"
    assert completed["payload"].get("session_id") in (None, "")
    assert completed["payload"]["exit_code"] == 0

def test_exec_command_failure_writes_error_reason_to_tool_trace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENTHUB_DEBUG_RESPONSES_TIMELINE", raising=False)
    monkeypatch.setenv("AGENTHUB_DEBUG_LOG_DIR", str(tmp_path))

    runtime = _FakeRuntime(fail_start=True)
    result = handle_known_command(runtime, name="exec_command", arg_text="pwd", text="/exec_command pwd")

    assert isinstance(result, CommandExecutionResult)
    assert result.tool_events
    assert result.tool_events[0].ok is False

    rows = _read_jsonl(tmp_path / "tool_trace.jsonl")
    failed = next(row for row in rows if row["stage"] == "tool.exec_command.failed")

    assert failed["payload"]["command"] == "pwd"
    assert failed["payload"]["error"] == "spawn denied by test runtime"
