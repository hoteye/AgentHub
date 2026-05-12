from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli.tools_core.output_persistence_runtime import shell_background_contract_fields


def watch_session_impl(
    session: Any,
    *,
    record_completed_payload: Callable[[str, dict[str, Any], list[dict[str, Any]]], None],
    remove_session: Callable[[str], None],
    trim_output_fn: Callable[..., tuple[str, bool, int]],
    join_aggregated_output_fn: Callable[[str, str], str],
    lifecycle_payload_fn: Callable[..., dict[str, Any]],
) -> None:
    returncode = session.process.wait()
    for thread in session.reader_threads():
        thread.join(timeout=0.5)
    session.close_pty_master()
    stdout_raw = "".join(session.stdout_chunks)
    stderr_raw = "".join(session.stderr_chunks)
    stdout_trimmed, stdout_truncated, stdout_total_chars = trim_output_fn(
        stdout_raw,
        limit=session.max_output_chars,
    )
    stderr_trimmed, stderr_truncated, stderr_total_chars = trim_output_fn(
        stderr_raw,
        limit=session.max_output_chars,
    )
    aggregated_raw = join_aggregated_output_fn(stdout_raw, stderr_raw)
    aggregated_output = join_aggregated_output_fn(stdout_trimmed, stderr_trimmed)
    status = (
        "pruned"
        if session._pruned
        else (
            "interrupted"
            if session._interrupted
            else ("timeout" if session._timed_out else ("ok" if returncode == 0 else "error"))
        )
    )
    payload = {
        "phase": "completed",
        "command": session.command,
        "session_id": session.session_id,
        "call_id": session.call_id,
        "process_id": session.process_id,
        "io_mode": session.io_mode,
        "returncode": int(returncode),
        "exit_code": int(returncode),
        "stdout": stdout_trimmed,
        "stderr": stderr_trimmed,
        "aggregated_output": aggregated_output,
        "output_text": stdout_trimmed,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "aggregated_output_truncated": stdout_truncated or stderr_truncated,
        "stdout_total_chars": stdout_total_chars,
        "stderr_total_chars": stderr_total_chars,
        "aggregated_output_total_chars": len(aggregated_raw),
        "stdout_total_lines": len(stdout_raw.splitlines()),
        "stderr_total_lines": len(stderr_raw.splitlines()),
        "aggregated_output_total_lines": len(aggregated_raw.splitlines()),
        "duration_ms": int((time.monotonic() - session.started_at) * 1000),
        "interrupted": bool(session._interrupted),
        "reason": (
            session._interrupt_reason
            if session._interrupted and session._interrupt_reason
            else None
        ),
        "timed_out": bool(session._timed_out),
        "ok": returncode == 0 and not session._interrupted and not session._timed_out,
        "status": status,
        "cwd": session.cwd,
        "login": session.login,
        "tty": session.tty,
        "shell": session.shell,
        "started_at_ms": session.started_at_ms,
        "finished_at_ms": int(time.time() * 1000),
        "source": "shell_session_manager",
        "lifecycle": lifecycle_payload_fn(
            phase="completed",
            kind="end",
            call_id=session.call_id,
            session_id=session.session_id,
            process_id=session.process_id,
            status=status,
        ),
    }
    payload.update(
        shell_background_contract_fields(
            payload,
            workspace_root=session.workspace_root,
            task_id=session.task_id,
            persist=True,
        )
    )
    session.mark_completed(payload)
    session._output_ready.set()
    session.emit(payload)
    _, history = session.snapshot_event_history()
    record_completed_payload(session.session_id, payload, history)
    remove_session(session.session_id)


def drain_incremental_output_impl(
    session: Any,
    *,
    yield_time_ms: int,
    cancel_event: Any = None,
    interrupt_session: Callable[[Any, str], None],
    output_snapshot_payload_fn: Callable[[Any, dict[str, str]], dict[str, Any]],
    final_status_fields_fn: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    deadline = time.monotonic() + (max(0, int(yield_time_ms)) / 1000.0)
    collected_stdout: list[str] = []
    collected_stderr: list[str] = []
    while True:
        if cancel_event is not None and cancel_event.is_set() and session.final_payload() is None:
            interrupt_session(session, "user_interrupt")
        incremental = session.consume_incremental_output()
        if incremental["stdout"]:
            collected_stdout.append(incremental["stdout"])
        if incremental["stderr"]:
            collected_stderr.append(incremental["stderr"])
        remaining = deadline - time.monotonic()
        if remaining <= 0 and session.final_payload() is not None:
            break
        if remaining <= 0:
            final_incremental = session.consume_incremental_output()
            if final_incremental["stdout"]:
                collected_stdout.append(final_incremental["stdout"])
            if final_incremental["stderr"]:
                collected_stderr.append(final_incremental["stderr"])
            break
        did_wait = session.wait_for_output(min(remaining, 0.05))
        if session.final_payload() is not None and not did_wait:
            final_incremental = session.consume_incremental_output()
            if final_incremental["stdout"]:
                collected_stdout.append(final_incremental["stdout"])
            if final_incremental["stderr"]:
                collected_stderr.append(final_incremental["stderr"])
            break
    payload = output_snapshot_payload_fn(
        session,
        {
            "stdout": "".join(collected_stdout),
            "stderr": "".join(collected_stderr),
        },
    )
    if session.final_payload() is None and (payload.get("stdout") or payload.get("stderr")):
        session._completed.wait(timeout=0.1)
    if session.final_payload() is not None:
        payload.update(final_status_fields_fn(session))
    else:
        returncode = session.process.poll()
        payload.update(
            {
                "returncode": int(returncode) if returncode is not None else None,
                "exit_code": int(returncode) if returncode is not None else None,
                "timed_out": False,
                "interrupted": False,
                "ok": returncode in (None, 0),
            }
        )
    return payload
