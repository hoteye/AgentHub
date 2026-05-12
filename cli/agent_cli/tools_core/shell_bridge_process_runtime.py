from __future__ import annotations

import os
import signal
import subprocess
from typing import Any


def interrupt_session(session: Any, *, reason: str, terminate_process_fn) -> None:
    if session.final_payload() is not None:
        return
    session._interrupted = True
    session._interrupt_reason = str(reason or "user_interrupt")
    session.wake_waiters()
    terminate_process_fn(session)


def terminate_process(session: Any) -> None:
    process = session.process
    terminated = False
    if session.terminate_as_process_group:
        try:
            process_group_id = os.getpgid(process.pid)
        except Exception:
            process_group_id = None
        if process_group_id is not None:
            try:
                os.killpg(process_group_id, signal.SIGTERM)
                terminated = True
            except Exception:
                terminated = False
    try:
        if not terminated:
            process.terminate()
    except Exception:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        killed = False
        if session.terminate_as_process_group:
            try:
                process_group_id = os.getpgid(process.pid)
            except Exception:
                process_group_id = None
            if process_group_id is not None:
                try:
                    os.killpg(process_group_id, signal.SIGKILL)
                    killed = True
                except Exception:
                    killed = False
        try:
            if not killed:
                process.kill()
        except Exception:
            pass
