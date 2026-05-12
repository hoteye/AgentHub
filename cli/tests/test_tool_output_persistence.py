from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.core.provider_session import default_tool_result_items
from cli.agent_cli.models import FunctionCallOutputPayload, ToolEvent
from cli.agent_cli.thread_store import ThreadStore
from cli.agent_cli.tools_core.output_persistence_runtime import (
    LARGE_OUTPUT_PERSIST_THRESHOLD_CHARS,
    PERSISTED_OUTPUT_STALE_TTL_SECONDS,
    ToolOutputPersistenceContext,
    persist_large_tool_output,
    persist_shell_background_artifact,
    prune_stale_persisted_outputs,
)


def _large_text() -> str:
    return "PREVIEW_START\n" + ("a" * 5000) + "POST_PREVIEW_MARKER" + ("b" * 30000)


def _text_item(text: str) -> dict[str, str]:
    return {"type": "input_text", "text": text}


def _assert_output_snapshot(
    item: dict[str, object],
    *,
    call_id: str,
    output: list[dict[str, str]] | str,
    text: str,
    success: bool,
) -> None:
    assert item == {
        "type": "function_call_output",
        "call_id": call_id,
        "output": output,
        "success": success,
    }
    payload = FunctionCallOutputPayload.from_output(item["output"], success=item.get("success"))
    assert payload.wire_value() == output
    assert payload.to_text() == text
    if isinstance(output, list):
        assert payload.text_segments() == [str(entry["text"]) for entry in output]


def test_function_call_output_payload_from_text_segments_roundtrips_wire_shape_and_text() -> None:
    payload = FunctionCallOutputPayload.from_text_segments([" line 1 ", "", "line 2"], success=False)

    assert payload.wire_value() == [_text_item("line 1"), _text_item("line 2")]
    assert payload.to_text() == "line 1\nline 2"
    assert payload.text_segments() == ["line 1", "line 2"]
    assert payload.success is False


def test_default_tool_result_items_formats_claude_like_shell_stdout_and_stderr() -> None:
    items = default_tool_result_items(
        call_id="call_shell_1",
        command_text="/exec_command pwd",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command exited",
                payload={
                    "stdout": "\n/repo\n",
                    "stderr": "warning: ignored\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            )
            ],
            tool_result_projection_policy="claude_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_1",
        output=[_text_item("/repo"), _text_item("warning: ignored")],
        text="/repo\nwarning: ignored",
        success=True,
    )


def test_default_tool_result_items_formats_claude_like_shell_failure_with_error_tag() -> None:
    items = default_tool_result_items(
        call_id="call_shell_2",
        command_text="/exec_command 'ls /missing'",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=False,
                summary="exec_command exited",
                payload={
                    "stdout": "",
                    "stderr": "ls: cannot access '/missing': No such file or directory\n",
                    "exit_code": 2,
                    "status": "completed",
                },
            )
        ],
        tool_result_projection_policy="claude_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_2",
        output=[
            _text_item("ls: cannot access '/missing': No such file or directory"),
            _text_item("<error>Command exited with code 2</error>"),
        ],
        text=(
            "ls: cannot access '/missing': No such file or directory\n"
            "<error>Command exited with code 2</error>"
        ),
        success=False,
    )


def test_default_tool_result_items_formats_claude_like_shell_interrupted() -> None:
    items = default_tool_result_items(
        call_id="call_shell_3",
        command_text="/write_stdin session_1",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="write_stdin",
                ok=False,
                summary="shell interrupted",
                payload={
                    "stdout": "partial output\n",
                    "interrupted": True,
                    "status": "interrupted",
                    "session_id": "session_1",
                },
            )
        ],
        tool_result_projection_policy="claude_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_3",
        output=[
            _text_item("partial output"),
            _text_item("<error>Command was aborted before completion</error>"),
        ],
        text="partial output\n<error>Command was aborted before completion</error>",
        success=False,
    )


def test_default_tool_result_items_formats_claude_like_shell_background_summary() -> None:
    items = default_tool_result_items(
        call_id="call_shell_4",
        command_text="/exec_command 'sleep 30'",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command running",
                payload={
                    "stdout": "started\n",
                    "session_id": "session_1",
                    "task_id": "session_1",
                    "status": "written",
                    "yield_time_ms": 15000,
                },
            )
        ],
        tool_result_projection_policy="claude_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_4",
        output=[
            _text_item("started"),
            _text_item(
                "Command is still running in the background. task_id: session_1. "
                "Use write_stdin with session_id session_1 to wait for more output or send input."
            ),
        ],
        text=(
            "started\n"
            "Command is still running in the background. task_id: session_1. "
            "Use write_stdin with session_id session_1 to wait for more output or send input."
        ),
        success=True,
    )


def test_default_tool_result_items_emits_shell_call_output_for_provider_native_shell_payload() -> None:
    items = default_tool_result_items(
        call_id="call_shell_native_1",
        command_text="/shell pwd",
        assistant_text="Run native shell call.",
        events=[
            ToolEvent(
                name="shell",
                ok=True,
                summary="shell rc=0",
                payload={
                    "provider_tool_type": "shell_call",
                    "provider_raw_item": {
                        "type": "shell_call",
                        "call_id": "call_shell_native_1",
                        "action": {
                            "type": "exec",
                            "command": ["pwd"],
                            "timeout_ms": 1000,
                            "max_output_length": 12000,
                        },
                    },
                    "stdout": "/repo\n",
                    "stderr": "",
                    "exit_code": 0,
                    "status": "completed",
                },
            )
        ],
    )

    assert items == [
        {
            "type": "shell_call_output",
            "call_id": "call_shell_native_1",
            "output": [
                {
                    "stdout": "/repo\n",
                    "stderr": "",
                    "outcome": {"type": "exit", "exit_code": 0},
                }
            ],
            "max_output_length": 12000,
            "status": "completed",
        }
    ]


def test_default_tool_result_items_formats_codex_like_shell_ok_stdout_only() -> None:
    items = default_tool_result_items(
        call_id="call_shell_codex_1",
        command_text="/exec_command pwd",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command exited",
                payload={
                    "stdout": "\n/repo\n",
                    "stderr": "warning: ignored\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            )
        ],
        tool_result_projection_policy="codex_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_codex_1",
        output=[_text_item("/repo"), _text_item("warning: ignored")],
        text="/repo\nwarning: ignored",
        success=True,
    )


def test_default_tool_result_items_formats_codex_like_shell_stderr_only_without_error_tag() -> None:
    items = default_tool_result_items(
        call_id="call_shell_codex_2",
        command_text="/exec_command 'ls /missing'",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=False,
                summary="exec_command exited",
                payload={
                    "stdout": "",
                    "stderr": "ls: cannot access '/missing': No such file or directory\n",
                    "exit_code": 2,
                    "status": "completed",
                },
            )
        ],
        tool_result_projection_policy="codex_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_codex_2",
        output=[_text_item("ls: cannot access '/missing': No such file or directory")],
        text="ls: cannot access '/missing': No such file or directory",
        success=False,
    )


def test_default_tool_result_items_formats_codex_like_shell_interrupted_without_abort_marker() -> None:
    items = default_tool_result_items(
        call_id="call_shell_codex_3",
        command_text="/write_stdin session_1",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="write_stdin",
                ok=False,
                summary="shell interrupted",
                payload={
                    "stdout": "partial output\n",
                    "interrupted": True,
                    "status": "interrupted",
                    "session_id": "session_1",
                },
            )
        ],
        tool_result_projection_policy="codex_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_codex_3",
        output=[
            _text_item("partial output"),
            _text_item("Command interrupted."),
        ],
        text="partial output\nCommand interrupted.",
        success=False,
    )


def test_default_tool_result_items_formats_codex_like_shell_background_summary_without_background_metadata() -> None:
    items = default_tool_result_items(
        call_id="call_shell_codex_4",
        command_text="/exec_command 'sleep 30'",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command running",
                payload={
                    "stdout": "started\n",
                    "session_id": "session_1",
                    "task_id": "session_1",
                    "status": "written",
                    "yield_time_ms": 15000,
                },
            )
        ],
        tool_result_projection_policy="codex_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_codex_4",
        output=[
            _text_item("started"),
            _text_item("Command is still running in the background."),
        ],
        text="started\nCommand is still running in the background.",
        success=True,
    )


def test_default_tool_result_items_formats_codex_like_shell_stderr_heavy_without_claude_suffix() -> None:
    items = default_tool_result_items(
        call_id="call_shell_codex_5",
        command_text="/exec_command 'python build.py'",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=False,
                summary="exec_command exited",
                payload={
                    "stdout": "build started\n",
                    "stderr": "line 1\nline 2\nline 3\n",
                    "exit_code": 1,
                    "status": "completed",
                },
            )
        ],
        tool_result_projection_policy="codex_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_codex_5",
        output=[
            _text_item("build started"),
            _text_item("line 1\nline 2\nline 3"),
        ],
        text="build started\nline 1\nline 2\nline 3",
        success=False,
    )


def test_default_tool_result_items_formats_codex_like_shell_plain_fallback_when_no_output() -> None:
    items = default_tool_result_items(
        call_id="call_shell_codex_6",
        command_text="/exec_command 'exit 17'",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=False,
                summary="exec_command exited",
                payload={
                    "stdout": "",
                    "stderr": "",
                    "exit_code": 17,
                    "status": "completed",
                },
            )
        ],
        tool_result_projection_policy="codex_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_codex_6",
        output=[_text_item("Command exited with code 17.")],
        text="Command exited with code 17.",
        success=False,
    )


def test_default_tool_result_items_keeps_codex_like_inline_apply_patch_passthrough_output() -> None:
    items = default_tool_result_items(
        call_id="call_shell_codex_apply_patch_1",
        command_text=(
            "/exec_command \"apply_patch <<'PATCH'\n"
            "*** Begin Patch\n"
            "*** Add File: demo.txt\n"
            "+hello\n"
            "*** End Patch\n"
            "PATCH\""
        ),
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command completed",
                payload={
                    "status": "completed",
                    "exit_code": 0,
                    "duration_ms": 0,
                    "inline_apply_patch_intercepted": True,
                    "function_call_output": (
                        "Success. Updated the following files:\n"
                        "A demo.txt"
                    ),
                    "function_call_output_model_visible": True,
                },
            )
        ],
        tool_result_projection_policy="codex_like",
    )

    assert len(items) == 2
    assert items[0]["type"] == "message"
    _assert_output_snapshot(
        items[1],
        call_id="call_shell_codex_apply_patch_1",
        output="Exit code: 0\nWall time: 0 seconds\nOutput:\nSuccess. Updated the following files:\nA demo.txt",
        text="Exit code: 0\nWall time: 0 seconds\nOutput:\nSuccess. Updated the following files:\nA demo.txt",
        success=True,
    )


def test_default_tool_result_items_rounds_codex_like_inline_apply_patch_wall_time_to_single_decimal() -> None:
    items = default_tool_result_items(
        call_id="call_shell_codex_apply_patch_2",
        command_text=(
            "/exec_command \"apply_patch <<'PATCH'\n"
            "*** Begin Patch\n"
            "*** Add File: demo.txt\n"
            "+hello\n"
            "*** End Patch\n"
            "PATCH\""
        ),
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command completed",
                payload={
                    "status": "completed",
                    "exit_code": 0,
                    "duration_ms": 149,
                    "inline_apply_patch_intercepted": True,
                    "function_call_output": (
                        "Success. Updated the following files:\n"
                        "A demo.txt"
                    ),
                    "function_call_output_model_visible": True,
                },
            )
        ],
        tool_result_projection_policy="codex_like",
    )

    _assert_output_snapshot(
        items[1],
        call_id="call_shell_codex_apply_patch_2",
        output="Exit code: 0\nWall time: 0.1 seconds\nOutput:\nSuccess. Updated the following files:\nA demo.txt",
        text="Exit code: 0\nWall time: 0.1 seconds\nOutput:\nSuccess. Updated the following files:\nA demo.txt",
        success=True,
    )


def test_default_tool_result_items_formats_claude_like_shell_error_tag_fallback_when_no_output() -> None:
    items = default_tool_result_items(
        call_id="call_shell_5",
        command_text="/exec_command 'exit 17'",
        assistant_text="Run shell command.",
        events=[
            ToolEvent(
                name="exec_command",
                ok=False,
                summary="exec_command exited",
                payload={
                    "stdout": "",
                    "stderr": "",
                    "exit_code": 17,
                    "status": "completed",
                },
            )
        ],
        tool_result_projection_policy="claude_like",
    )

    assert len(items) == 1
    _assert_output_snapshot(
        items[0],
        call_id="call_shell_5",
        output=[_text_item("<error>Command exited with code 17</error>")],
        text="<error>Command exited with code 17</error>",
        success=False,
    )


def test_persist_large_tool_output_writes_workspace_local_cache_for_claude_like() -> None:
    large_text = _large_text()
    assert len(large_text) > LARGE_OUTPUT_PERSIST_THRESHOLD_CHARS

    with tempfile.TemporaryDirectory() as temp_dir:
        persisted = persist_large_tool_output(
            large_text,
            call_id="call:big/1",
            context=ToolOutputPersistenceContext(
                tool_result_projection_policy="claude_like",
                workspace_root=temp_dir,
                thread_id="thread:demo",
            ),
        )

        assert persisted.persisted is True
        assert persisted.original_size == len(large_text)
        assert "<persisted-output>" in persisted.model_output
        assert "filepath: .config/tool_output_cache/thread_demo/call_big_1.txt" in persisted.model_output
        assert "originalSize:" in persisted.model_output
        assert "hasMore: true" in persisted.model_output

        stored_path = Path(temp_dir) / ".config" / "tool_output_cache" / "thread_demo" / "call_big_1.txt"
        assert stored_path.read_text(encoding="utf-8") == large_text


def test_persist_shell_background_artifact_writes_private_cache_outside_workspace() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        with tempfile.TemporaryDirectory() as temp_home:
            with patch.dict(os.environ, {"AGENT_CLI_HOME": temp_home}, clear=False):
                persisted = persist_shell_background_artifact(
                    {
                        "session_id": "session:1",
                        "call_id": "call_1",
                        "process_id": "proc_1",
                        "command": "sleep 30",
                        "status": "written",
                        "stdout": "started\n",
                        "aggregated_output": "started\n",
                    },
                    workspace_root=temp_dir,
                )

            assert persisted.persisted is True
            assert persisted.task_id == "session:1"
            assert persisted.artifact_path == ""

            stored_path = Path(temp_home) / "tool_output_cache" / "background_shell" / "session_1.json"
            artifact_payload = json.loads(stored_path.read_text(encoding="utf-8"))
            assert artifact_payload["task_id"] == "session:1"
            assert artifact_payload["completion_notification_available"] is True
            assert artifact_payload["completion_poll_tool"] == "write_stdin"
            assert artifact_payload["status"] == "written"
            assert artifact_payload["workflow_state"] == "running"
            assert artifact_payload["completion_state"] == "pending"
            assert artifact_payload["notification_state"] == "pending"
            assert artifact_payload["summary"] == "background shell running"
            assert not (Path(temp_dir) / ".config" / "tool_output_cache" / "background_shell").exists()


def test_prune_stale_persisted_outputs_removes_old_files() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_root = Path(temp_dir) / ".config" / "tool_output_cache"
        stale_file = cache_root / "thread_a" / "old.txt"
        fresh_file = cache_root / "thread_a" / "fresh.txt"
        stale_file.parent.mkdir(parents=True, exist_ok=True)
        stale_file.write_text("old", encoding="utf-8")
        fresh_file.write_text("fresh", encoding="utf-8")
        cutoff_now = time.time()
        stale_at = cutoff_now - PERSISTED_OUTPUT_STALE_TTL_SECONDS - 60
        fresh_at = cutoff_now - 60
        os.utime(stale_file, (stale_at, stale_at))
        os.utime(fresh_file, (fresh_at, fresh_at))

        prune_stale_persisted_outputs(cache_root, now=cutoff_now)

        assert not stale_file.exists()
        assert fresh_file.exists()


def test_default_tool_result_items_persist_large_claude_like_payloads() -> None:
    large_text = _large_text()

    with tempfile.TemporaryDirectory() as temp_dir:
        items = default_tool_result_items(
            call_id="call_big_1",
            command_text="/read_file big.txt",
            assistant_text="Read workspace file.",
            events=[
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"text": large_text},
                )
            ],
            tool_result_projection_policy="claude_like",
            workspace_root=temp_dir,
            tool_output_thread_id="thread_1",
        )

        assert items[0]["type"] == "function_call_output"
        assert items[0]["success"] is True
        assert isinstance(items[0]["output"], str)
        assert items[0]["output"].startswith("<persisted-output>\n")
        assert large_text[:4096] in items[0]["output"]
        assert "POST_PREVIEW_MARKER" not in items[0]["output"]


def test_default_tool_result_items_persist_large_claude_like_shell_payloads() -> None:
    large_text = _large_text()

    with tempfile.TemporaryDirectory() as temp_dir:
        items = default_tool_result_items(
            call_id="call_shell_big_1",
            command_text="/exec_command 'cat big.txt'",
            assistant_text="Run shell command.",
            events=[
                ToolEvent(
                    name="exec_command",
                    ok=True,
                    summary="exec_command exited",
                    payload={"stdout": "\n" + large_text, "exit_code": 0, "status": "completed"},
                )
            ],
            tool_result_projection_policy="claude_like",
            workspace_root=temp_dir,
            tool_output_thread_id="thread_1",
        )

        assert items[0]["type"] == "function_call_output"
        assert items[0]["success"] is True
        assert isinstance(items[0]["output"], str)
        assert items[0]["output"].startswith("<persisted-output>\n")
        assert large_text[:4096] in items[0]["output"]
        assert "POST_PREVIEW_MARKER" not in items[0]["output"]


def test_default_tool_result_items_falls_back_to_truncated_text_on_persist_error() -> None:
    large_text = _large_text()

    with tempfile.TemporaryDirectory() as temp_dir, patch(
        "cli.agent_cli.tools_core.output_persistence_runtime._write_persisted_output",
        side_effect=OSError("disk full"),
    ):
        items = default_tool_result_items(
            call_id="call_big_1",
            command_text="/read_file big.txt",
            assistant_text="Read workspace file.",
            events=[
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"text": large_text},
                )
            ],
            tool_result_projection_policy="claude_like",
            workspace_root=temp_dir,
            tool_output_thread_id="thread_1",
        )

        output = str(items[0]["output"])
        assert "persist-to-disk unavailable" in output
        assert "<persisted-output>" not in output
        assert len(output) < len(large_text)


def test_thread_store_resume_round_trips_persisted_wrapper_text() -> None:
    large_text = _large_text()

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "workspace"
        workspace.mkdir()
        items = default_tool_result_items(
            call_id="call_big_1",
            command_text="/read_file big.txt",
            assistant_text="Read workspace file.",
            events=[
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"text": large_text},
                )
            ],
            tool_result_projection_policy="claude_like",
            workspace_root=str(workspace),
            tool_output_thread_id="thread_1",
        )
        wrapper = str(items[0]["output"])

        store = ThreadStore(Path(temp_dir) / "state")
        thread = store.start_thread(name="persist replay", cwd=str(workspace.resolve()))
        from cli.agent_cli.models import PromptResponse, ResponseInputItem

        store.append_turn(
            thread.thread_id,
            PromptResponse(
                user_text="show me the file",
                assistant_text="large output available",
                response_items=[
                    ResponseInputItem.from_dict(
                        {"type": "function_call", "call_id": "call_big_1", "name": "read_file", "arguments": "{}"}
                    ),
                    ResponseInputItem.from_dict(
                        {"type": "function_call_output", "call_id": "call_big_1", "output": wrapper, "success": True}
                    ),
                ],
            ),
        )

        resumed = store.resume_thread(thread.thread_id)
        function_outputs = [
            item
            for item in list(resumed.get("planner_input_items") or [])
            if isinstance(item, dict) and str(item.get("type") or "").strip() == "function_call_output"
        ]

        assert len(function_outputs) == 1
        assert function_outputs[0]["output"] == wrapper
        assert "POST_PREVIEW_MARKER" not in str(function_outputs[0]["output"])
