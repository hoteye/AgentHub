from __future__ import annotations

import json
from pathlib import Path

from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def test_log_timeline_routes_turn_actions_to_separate_file(monkeypatch, tmp_path: Path) -> None:
    timeline_path = tmp_path / "timeline.jsonl"
    monkeypatch.setenv("AGENTHUB_DEBUG_RESPONSES_TIMELINE", str(timeline_path))
    monkeypatch.delenv("AGENTHUB_DEBUG_LOG_DIR", raising=False)

    log_timeline("runtime.handle_prompt.started", user_text="你好")

    timeline_rows = _read_jsonl(timeline_path)
    action_rows = _read_jsonl(tmp_path / "turn_actions.jsonl")

    assert timeline_rows[-1]["stage"] == "runtime.handle_prompt.started"
    assert action_rows[-1]["stage"] == "runtime.handle_prompt.started"
    assert action_rows[-1]["payload"]["user_text"] == "你好"

def test_log_timeline_routes_llm_io_to_separate_file(monkeypatch, tmp_path: Path) -> None:
    timeline_path = tmp_path / "timeline.jsonl"
    monkeypatch.setenv("AGENTHUB_DEBUG_RESPONSES_TIMELINE", str(timeline_path))
    monkeypatch.delenv("AGENTHUB_DEBUG_LOG_DIR", raising=False)

    log_timeline("responses.send.request_raw", request={"model": "gpt-5.4", "input": [{"role": "user", "content": "hello"}]})

    timeline_rows = _read_jsonl(timeline_path)
    llm_rows = _read_jsonl(tmp_path / "llm_io.jsonl")
    action_rows = _read_jsonl(tmp_path / "turn_actions.jsonl")

    assert timeline_rows[-1]["stage"] == "responses.send.request_raw"
    assert llm_rows[-1]["stage"] == "responses.send.request_raw"
    assert llm_rows[-1]["payload"]["request"]["model"] == "gpt-5.4"
    assert not action_rows

def test_timeline_debug_enabled_when_only_log_dir_is_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENTHUB_DEBUG_RESPONSES_TIMELINE", raising=False)
    monkeypatch.setenv("AGENTHUB_DEBUG_LOG_DIR", str(tmp_path))

    assert timeline_debug_enabled() is True

    log_timeline("runtime.handle_prompt.started", user_text="hello")
    action_rows = _read_jsonl(tmp_path / "turn_actions.jsonl")
    assert action_rows[-1]["stage"] == "runtime.handle_prompt.started"

def test_log_timeline_routes_tool_stages_to_tool_trace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENTHUB_DEBUG_RESPONSES_TIMELINE", raising=False)
    monkeypatch.setenv("AGENTHUB_DEBUG_LOG_DIR", str(tmp_path))

    log_timeline("tool.exec_command.started", command="pwd", session_id="sess-1")

    tool_rows = _read_jsonl(tmp_path / "tool_trace.jsonl")

    assert tool_rows[-1]["stage"] == "tool.exec_command.started"
    assert tool_rows[-1]["payload"]["command"] == "pwd"
    assert tool_rows[-1]["payload"]["session_id"] == "sess-1"


def test_log_timeline_writes_claude_style_request_debug_file(monkeypatch, tmp_path: Path) -> None:
    debug_file = tmp_path / "agenthub.debug.log"
    monkeypatch.delenv("AGENTHUB_DEBUG_RESPONSES_TIMELINE", raising=False)
    monkeypatch.delenv("AGENTHUB_DEBUG_LOG_DIR", raising=False)
    monkeypatch.setenv("AGENTHUB_DEBUG_TEXT_LOG", str(debug_file))
    monkeypatch.delenv("AGENTHUB_DEBUG_FILTER", raising=False)

    log_timeline(
        "responses.send.request_raw",
        request={"model": "gpt-5.4", "messages": [{"role": "user", "content": "hello"}]},
    )

    content = debug_file.read_text(encoding="utf-8")
    assert "[DEBUG] [API REQUEST]" in content
    assert "responses.send model=gpt-5.4" in content
    assert "messages=1" in content


def test_log_timeline_writes_claude_style_tool_debug_file(monkeypatch, tmp_path: Path) -> None:
    debug_file = tmp_path / "agenthub.debug.log"
    monkeypatch.delenv("AGENTHUB_DEBUG_RESPONSES_TIMELINE", raising=False)
    monkeypatch.delenv("AGENTHUB_DEBUG_LOG_DIR", raising=False)
    monkeypatch.setenv("AGENTHUB_DEBUG_TEXT_LOG", str(debug_file))
    monkeypatch.delenv("AGENTHUB_DEBUG_FILTER", raising=False)

    log_timeline(
        "turn_engine.tool.execute.begin",
        tool_name="read_file",
        call_id="call_1",
        mode="structured",
        command_text="/read_file README.md --limit 1",
    )

    content = debug_file.read_text(encoding="utf-8")
    assert "[DEBUG] [TOOL]" in content
    assert "read_file started" in content
    assert "call_id=call_1" in content
    assert "command=/read_file README.md --limit 1" in content
