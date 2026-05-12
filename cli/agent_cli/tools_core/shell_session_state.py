from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from typing import Any, Callable, Dict, List


def _callback_key(callback: Callable[[Dict[str, Any]], None]) -> tuple[Any, ...]:
    owner = getattr(callback, "__self__", None)
    func = getattr(callback, "__func__", None)
    name = getattr(callback, "__name__", None)
    if owner is not None and (func is not None or name is not None):
        return ("bound", id(owner), id(func) if func is not None else None, str(name or ""))
    return ("callable", id(callback))


class _ShellSession:
    def __init__(
        self,
        *,
        session_id: str,
        command: str,
        cwd: str | None,
        login: bool,
        tty: bool,
        shell: str | None,
        max_output_chars: int,
        process: subprocess.Popen[str],
        pty_master_fd: int | None = None,
        cancel_event: threading.Event | None = None,
        terminate_as_process_group: bool = False,
        workspace_root: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.call_id = uuid.uuid4().hex
        self.command = command
        self.cwd = str(cwd or "").strip() or None
        self.login = bool(login)
        self.tty = bool(tty)
        self.shell = str(shell or "").strip() or None
        self.max_output_chars = max(0, int(max_output_chars))
        self.process = process
        self.cancel_event = cancel_event
        self.terminate_as_process_group = bool(terminate_as_process_group)
        self.workspace_root = str(workspace_root or "").strip() or None
        self.started_at = time.monotonic()
        self.started_at_ms = int(time.time() * 1000)
        self.stdout_chunks: List[str] = []
        self.stderr_chunks: List[str] = []
        self._callbacks: List[tuple[Callable[[Dict[str, Any]], None], int]] = []
        self._callback_keys: set[tuple[Any, ...]] = set()
        self._lock = threading.Lock()
        self._completed = threading.Event()
        self._interrupted = False
        self._interrupt_reason: str | None = None
        self._timed_out = False
        self._pruned = False
        self._final_payload: Dict[str, Any] | None = None
        self._reader_threads: List[threading.Thread] = []
        self._output_ready = threading.Event()
        self._stdout_consumed_chars = 0
        self._stderr_consumed_chars = 0
        self._pty_master_fd = pty_master_fd
        self._io_mode = "pty" if pty_master_fd is not None else "pipes"
        self._event_seq = 0
        self._event_history: List[tuple[int, Dict[str, Any]]] = []
        self._event_history_limit = 4096

    @property
    def process_id(self) -> str:
        return str(self.process.pid or self.session_id)

    @property
    def task_id(self) -> str:
        return self.session_id

    @property
    def pty_master_fd(self) -> int | None:
        with self._lock:
            return self._pty_master_fd

    @property
    def io_mode(self) -> str:
        return self._io_mode

    def add_callback(
        self,
        callback: Callable[[Dict[str, Any]], None] | None,
        *,
        replay_after_seq: int = 0,
    ) -> None:
        if callback is None:
            return
        key = _callback_key(callback)
        with self._lock:
            if key in self._callback_keys:
                return
            self._callback_keys.add(key)
            self._callbacks.append((callback, max(0, int(replay_after_seq))))

    def snapshot_event_history(self) -> tuple[int, List[Dict[str, Any]]]:
        with self._lock:
            cutoff_seq = int(self._event_seq)
            payloads = [dict(payload) for _, payload in self._event_history]
        return cutoff_seq, payloads

    def add_callback_with_history(
        self,
        callback: Callable[[Dict[str, Any]], None] | None,
    ) -> tuple[int, List[Dict[str, Any]]]:
        with self._lock:
            cutoff_seq = int(self._event_seq)
            payloads = [dict(payload) for _, payload in self._event_history]
            if callback is not None:
                key = _callback_key(callback)
                if key not in self._callback_keys:
                    self._callback_keys.add(key)
                    self._callbacks.append((callback, cutoff_seq))
        return cutoff_seq, payloads

    def emit(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._event_seq += 1
            seq = self._event_seq
            payload_copy = dict(payload)
            self._event_history.append((seq, payload_copy))
            if len(self._event_history) > self._event_history_limit:
                self._event_history = self._event_history[-self._event_history_limit :]
            callbacks = list(self._callbacks)
        for callback, min_seq in callbacks:
            if seq <= min_seq:
                continue
            try:
                callback(dict(payload_copy))
            except Exception:
                continue

    def mark_completed(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._final_payload = dict(payload)
        self._completed.set()

    def final_payload(self) -> Dict[str, Any] | None:
        with self._lock:
            return None if self._final_payload is None else dict(self._final_payload)

    def add_reader_thread(self, thread: threading.Thread) -> None:
        with self._lock:
            self._reader_threads.append(thread)

    def reader_threads(self) -> List[threading.Thread]:
        with self._lock:
            return list(self._reader_threads)

    def append_output(self, *, stream_name: str, text: str) -> None:
        with self._lock:
            if stream_name == "stdout":
                self.stdout_chunks.append(text)
            else:
                self.stderr_chunks.append(text)
            self._output_ready.set()

    def consume_incremental_output(self) -> Dict[str, str]:
        with self._lock:
            stdout_text = "".join(self.stdout_chunks)
            stderr_text = "".join(self.stderr_chunks)
            stdout_incremental = stdout_text[self._stdout_consumed_chars :]
            stderr_incremental = stderr_text[self._stderr_consumed_chars :]
            self._stdout_consumed_chars = len(stdout_text)
            self._stderr_consumed_chars = len(stderr_text)
            self._output_ready.clear()
        return {
            "stdout": stdout_incremental,
            "stderr": stderr_incremental,
        }

    def wait_for_output(self, timeout_sec: float) -> bool:
        return self._output_ready.wait(timeout=max(0.0, float(timeout_sec)))

    def wake_waiters(self) -> None:
        self._output_ready.set()

    def write_pty_input(self, text: str) -> None:
        fd = self.pty_master_fd
        if fd is None:
            raise OSError("pty master unavailable")
        os.write(fd, str(text or "").encode("utf-8", errors="replace"))

    def close_pty_master(self) -> None:
        fd: int | None
        with self._lock:
            fd = self._pty_master_fd
            self._pty_master_fd = None
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            pass
