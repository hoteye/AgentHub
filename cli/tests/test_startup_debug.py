from __future__ import annotations

from pathlib import Path

from cli.agent_cli import startup_debug


def test_startup_log_writes_claude_style_label(monkeypatch, tmp_path: Path) -> None:
    debug_file = tmp_path / "startup.debug.log"
    monkeypatch.setenv("AGENTHUB_START_DEBUG_LOG", str(debug_file))
    startup_debug._STARTUP_DEBUG_STREAM = None

    startup_debug.startup_log("main.enter argv=None")

    content = debug_file.read_text(encoding="utf-8")
    assert "[DEBUG] [STARTUP]" in content
    assert "main.enter argv=None" in content

    stream = startup_debug._STARTUP_DEBUG_STREAM
    if stream is not None and not stream.closed:
        stream.close()
    startup_debug._STARTUP_DEBUG_STREAM = None
