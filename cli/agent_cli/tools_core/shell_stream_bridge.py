"""Shell stream bridge primitives used by unified exec sessions.

This module keeps stable public helper entry points and delegates heavier
implementation details to sibling helper modules when needed.
"""

from __future__ import annotations

import base64
import errno
import os
import select
import threading
import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli.tools_core import shell_event_payloads, shell_stream_bridge_helpers
from cli.agent_cli.tools_core.output_persistence_runtime import shell_background_contract_fields
from cli.agent_cli.tools_core.shell_session_state import _ShellSession


def join_aggregated_output(stdout_text: str, stderr_text: str) -> str:
    stdout = str(stdout_text or "")
    stderr = str(stderr_text or "")
    if stdout and stderr:
        return f"{stdout}{'' if stdout.endswith(chr(10)) else chr(10)}{stderr}"
    return stdout or stderr


def trim_output(text: str, *, limit: int) -> tuple[str, bool, int]:
    raw = str(text or "")
    total_chars = len(raw)
    if limit <= 0 or total_chars <= limit:
        return raw, False, total_chars
    left_chars = limit // 2
    right_chars = limit - left_chars
    omitted_chars = max(0, total_chars - left_chars - right_chars)
    return (
        f"{raw[:left_chars]}\u2026{omitted_chars} chars truncated\u2026{raw[total_chars - right_chars:]}",
        True,
        total_chars,
    )


def output_line_count(text: str) -> int:
    return len(str(text or "").splitlines())


def build_fallback_payload(session: _ShellSession) -> dict[str, Any]:
    stdout_raw = "".join(session.stdout_chunks)
    stderr_raw = "".join(session.stderr_chunks)
    stdout_trimmed, stdout_truncated, stdout_total_chars = trim_output(
        stdout_raw,
        limit=session.max_output_chars,
    )
    stderr_trimmed, stderr_truncated, stderr_total_chars = trim_output(
        stderr_raw,
        limit=session.max_output_chars,
    )
    aggregated_raw = join_aggregated_output(stdout_raw, stderr_raw)
    aggregated_output = join_aggregated_output(stdout_trimmed, stderr_trimmed)
    returncode = session.process.poll()
    if returncode is None:
        returncode = -1 if session._interrupted or session._timed_out else 0
    if session._pruned:
        status = "pruned"
    elif session._interrupted:
        status = "interrupted"
    elif session._timed_out:
        status = "timeout"
    else:
        status = "ok" if int(returncode) == 0 else "error"
    payload = {
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
        "stdout_total_lines": output_line_count(stdout_raw),
        "stderr_total_lines": output_line_count(stderr_raw),
        "aggregated_output_total_lines": output_line_count(aggregated_raw),
        "timed_out": bool(session._timed_out),
        "interrupted": bool(session._interrupted),
        "reason": (
            session._interrupt_reason
            if session._interrupted and session._interrupt_reason
            else None
        ),
        "duration_ms": int((time.monotonic() - session.started_at) * 1000),
        "status": status,
        "cwd": session.cwd,
        "login": session.login,
        "tty": session.tty,
        "shell": session.shell,
        "started_at_ms": session.started_at_ms,
        "finished_at_ms": int(time.time() * 1000),
        "ok": int(returncode) == 0 and not session._interrupted and not session._timed_out,
        "source": "shell_session_manager",
        "lifecycle": shell_event_payloads.lifecycle_payload(
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
            foreground_adopted=False,
        )
    )
    return payload


def start_reader(session: _ShellSession, stream_name: str, stream: Any) -> None:
    def _reader() -> None:
        try:
            for line in iter(stream.readline, ""):
                session.append_output(stream_name=stream_name, text=line)
                preview = line.rstrip("\r\n")
                if preview.strip():
                    chunk = base64.b64encode(line.encode("utf-8", errors="replace")).decode("ascii")
                    session.emit(
                        shell_event_payloads.event_payload(
                            session,
                            phase="output",
                            kind="output_delta",
                            stream=stream_name,
                            extra={
                                "stream": stream_name,
                                "chunk": chunk,
                                "output_chunk": chunk,
                                "text": preview,
                                "output_text": preview,
                            },
                        )
                    )
        finally:
            try:
                stream.close()
            except Exception:
                pass

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    session.add_reader_thread(thread)


def start_pty_reader(session: _ShellSession) -> None:
    def _reader() -> None:
        while True:
            fd = session.pty_master_fd
            if fd is None:
                break
            try:
                ready, _, _ = select.select([fd], [], [], 0.1)
            except OSError as exc:
                if exc.errno in {errno.EBADF, errno.EIO}:
                    break
                continue
            if not ready:
                if session.process.poll() is not None:
                    # Give the PTY one more chance to drain any pending output.
                    continue
                continue
            try:
                chunk_bytes = os.read(fd, 4096)
            except OSError as exc:
                if exc.errno in {errno.EBADF, errno.EIO}:
                    break
                continue
            if not chunk_bytes:
                if session.process.poll() is not None:
                    break
                continue
            text = chunk_bytes.decode("utf-8", errors="replace")
            session.append_output(stream_name="stdout", text=text)
            preview = text.rstrip("\r\n")
            if preview.strip():
                chunk = base64.b64encode(chunk_bytes).decode("ascii")
                session.emit(
                    shell_event_payloads.event_payload(
                        session,
                        phase="output",
                        kind="output_delta",
                        stream="stdout",
                        extra={
                            "stream": "stdout",
                            "chunk": chunk,
                            "output_chunk": chunk,
                            "text": preview,
                            "output_text": preview,
                        },
                    )
                )
        session.close_pty_master()

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    session.add_reader_thread(thread)


def watch_session(
    session: _ShellSession,
    *,
    record_completed_payload: Callable[[str, dict[str, Any], list[dict[str, Any]]], None],
    remove_session: Callable[[str], None],
) -> None:
    """Wait for session completion.

    Finalize payload, persist history, and clean up session bookkeeping.
    """
    shell_stream_bridge_helpers.watch_session_impl(
        session,
        record_completed_payload=record_completed_payload,
        remove_session=remove_session,
        trim_output_fn=trim_output,
        join_aggregated_output_fn=join_aggregated_output,
        lifecycle_payload_fn=shell_event_payloads.lifecycle_payload,
    )


def normalize_write_yield_time_ms(
    value: int | float | None,
    *,
    empty_input: bool,
    allow_extended_empty_poll: bool = False,
) -> int:
    if empty_input and allow_extended_empty_poll:
        if value is None:
            return 10000
        try:
            normalized = int(float(value))
        except (TypeError, ValueError):
            normalized = 10000
        normalized = max(250, normalized)
        return min(normalized, 30000)
    if value is None:
        return 250 if empty_input else 100
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        normalized = 250 if empty_input else 100
    normalized = max(10, normalized)
    return min(normalized, 2000)


def output_snapshot_payload(
    session: _ShellSession,
    incremental: dict[str, str],
    *,
    max_output_chars: int | None = None,
) -> dict[str, Any]:
    stdout_raw = incremental.get("stdout") or ""
    stderr_raw = incremental.get("stderr") or ""
    output_limit = session.max_output_chars
    if max_output_chars is not None:
        try:
            output_limit = max(0, int(max_output_chars))
        except (TypeError, ValueError):
            output_limit = session.max_output_chars
    stdout_trimmed, stdout_truncated, stdout_total_chars = trim_output(
        stdout_raw,
        limit=output_limit,
    )
    stderr_trimmed, stderr_truncated, stderr_total_chars = trim_output(
        stderr_raw,
        limit=output_limit,
    )
    aggregated_raw = join_aggregated_output(stdout_raw, stderr_raw)
    aggregated_output = join_aggregated_output(stdout_trimmed, stderr_trimmed)
    payload = {
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
        "stdout_total_lines": output_line_count(stdout_raw),
        "stderr_total_lines": output_line_count(stderr_raw),
        "aggregated_output_total_lines": output_line_count(aggregated_raw),
    }
    session_id = str(getattr(session, "session_id", "") or "").strip()
    if session_id:
        payload.update(
            shell_background_contract_fields(
                {
                    "session_id": session_id,
                    "call_id": getattr(session, "call_id", ""),
                    "process_id": getattr(session, "process_id", session_id),
                    "command": getattr(session, "command", ""),
                    "cwd": getattr(session, "cwd", None),
                    "login": getattr(session, "login", None),
                    "tty": getattr(session, "tty", None),
                    "shell": getattr(session, "shell", None),
                    "started_at_ms": getattr(session, "started_at_ms", None),
                    **payload,
                },
                workspace_root=getattr(session, "workspace_root", None),
                task_id=getattr(session, "task_id", session_id),
                persist=True,
                foreground_adopted=False,
            )
        )
    return payload


def final_status_fields(session: _ShellSession) -> dict[str, Any]:
    payload = session.final_payload() or {}
    return {
        "returncode": payload.get("returncode"),
        "exit_code": payload.get("exit_code"),
        "timed_out": bool(payload.get("timed_out")),
        "interrupted": bool(payload.get("interrupted")),
        "ok": bool(payload.get("ok")),
        "finished_at_ms": payload.get("finished_at_ms"),
        "status": payload.get("status"),
    }


def drain_incremental_output(
    session: _ShellSession,
    *,
    yield_time_ms: int,
    max_output_chars: int | None = None,
    cancel_event: threading.Event | None = None,
    interrupt_session: Callable[[_ShellSession, str], None],
) -> dict[str, Any]:
    """Drain incremental stdout/stderr for the polling window.

    Attach final status fields when a terminal payload is available.
    """
    payload = shell_stream_bridge_helpers.drain_incremental_output_impl(
        session,
        yield_time_ms=yield_time_ms,
        cancel_event=cancel_event,
        interrupt_session=interrupt_session,
        output_snapshot_payload_fn=lambda target_session, incremental: output_snapshot_payload(
            target_session,
            incremental,
            max_output_chars=max_output_chars,
        ),
        final_status_fields_fn=final_status_fields,
    )
    payload.update(
        shell_background_contract_fields(
            {
                "session_id": session.session_id,
                "call_id": session.call_id,
                "process_id": session.process_id,
                "command": session.command,
                "cwd": session.cwd,
                "login": session.login,
                "tty": session.tty,
                "shell": session.shell,
                "started_at_ms": session.started_at_ms,
                **payload,
            },
            workspace_root=session.workspace_root,
            task_id=session.task_id,
            persist=True,
            foreground_adopted=session.final_payload() is not None,
        )
    )
    return payload
