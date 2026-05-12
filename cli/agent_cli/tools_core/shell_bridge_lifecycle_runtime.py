from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from cli.agent_cli.tools_core import (
    shell_bridge_process_runtime,
    shell_bridge_runtime,
    shell_event_payloads,
    shell_stream_bridge,
)
from cli.agent_cli.tools_core.shell_session_state import _ShellSession


def start_session(
    manager: Any,
    *,
    command: str,
    cwd: str | None = None,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    pty_module: Any,
    shell_exec_args_builder,
) -> dict[str, Any]:
    started = shell_bridge_runtime.build_started_shell_session(
        host_platform=manager._host_platform,
        command=command,
        cwd=cwd,
        workspace_root=manager._workspace_root(),
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        cancel_event=cancel_event,
        pty_module=pty_module,
        shell_exec_args_builder=shell_exec_args_builder,
    )
    session_id = started.session_id
    session = started.session
    session.add_callback(on_activity)
    with manager._lock:
        manager._sessions[session_id] = session
    for pruned_session in manager._sessions_to_prune_after_start(keep_session_id=session_id):
        manager._prune_session(pruned_session)

    session.emit(
        shell_event_payloads.event_payload(
            session,
            phase="started",
            kind="begin",
            status="started",
        )
    )

    if session.pty_master_fd is not None:
        manager._start_pty_reader(session)
    else:
        manager._start_reader(session, "stdout", session.process.stdout)
        manager._start_reader(session, "stderr", session.process.stderr)
    watcher = threading.Thread(target=manager._watch_session, args=(session,), daemon=True)
    watcher.start()
    return shell_bridge_runtime.build_started_session_payload(
        started,
        login=bool(login),
        tty=bool(tty),
    )


def interrupt_session(cls: type[Any], session: _ShellSession, *, reason: str) -> None:
    shell_bridge_process_runtime.interrupt_session(
        session,
        reason=reason,
        terminate_process_fn=cls._terminate_process,
    )


def terminate_process(session: _ShellSession) -> None:
    shell_bridge_process_runtime.terminate_process(session)


def start_reader(session: _ShellSession, stream_name: str, stream: Any) -> None:
    shell_stream_bridge.start_reader(session, stream_name, stream)


def start_pty_reader(session: _ShellSession) -> None:
    shell_stream_bridge.start_pty_reader(session)


def watch_session(manager: Any, session: _ShellSession) -> None:
    shell_stream_bridge.watch_session(
        session,
        record_completed_payload=lambda sid, payload, history: manager._record_completed_payload(
            sid,
            payload,
            event_history=history,
        ),
        remove_session=manager._remove_live_session,
    )


def drain_incremental_output(
    manager: Any,
    session: _ShellSession,
    *,
    yield_time_ms: int,
    max_output_chars: int | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    return shell_stream_bridge.drain_incremental_output(
        session,
        yield_time_ms=yield_time_ms,
        max_output_chars=max_output_chars,
        cancel_event=cancel_event,
        interrupt_session=lambda target, reason: manager._interrupt_session(target, reason=reason),
    )
