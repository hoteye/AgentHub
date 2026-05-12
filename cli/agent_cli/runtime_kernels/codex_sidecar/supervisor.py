from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Iterable, Mapping
from pathlib import Path
from queue import Empty, Queue

from cli.agent_cli.runtime_kernels.codex_sidecar.errors import CodexSidecarProcessError


class CodexSidecarSupervisor:
    def __init__(
        self,
        *,
        codex_bin: str | Path,
        extra_args: Iterable[str] = (),
        extra_env: Mapping[str, str] | None = None,
        remove_env_keys: Iterable[str] = (),
    ) -> None:
        self.codex_bin = Path(codex_bin)
        self.extra_args = tuple(str(arg) for arg in extra_args)
        self.extra_env = {str(key): str(value) for key, value in dict(extra_env or {}).items()}
        self.remove_env_keys = tuple(
            dict.fromkeys(str(key) for key in remove_env_keys if str(key or "").strip())
        )
        self._proc: subprocess.Popen[str] | None = None
        self._stderr_lines: Queue[str] = Queue()

    @property
    def process(self) -> subprocess.Popen[str] | None:
        return self._proc

    @property
    def is_running(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    def start(self) -> subprocess.Popen[str]:
        if self.is_running:
            assert self._proc is not None
            return self._proc
        if not self.codex_bin.exists():
            raise CodexSidecarProcessError(f"codex binary not found: {self.codex_bin}")
        self._clear_stderr_lines()
        command = [
            str(self.codex_bin),
            "--listen",
            "stdio://",
            *self.extra_args,
        ]
        try:
            env = self._build_process_env()
            self._proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise CodexSidecarProcessError(str(exc)) from exc
        threading.Thread(target=self._read_stderr, daemon=True).start()
        return self._proc

    def close(self, *, terminate_timeout: float = 3.0) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=terminate_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=terminate_timeout)

    def stderr_tail(self, limit: int = 20) -> list[str]:
        lines: list[str] = []
        while True:
            try:
                lines.append(self._stderr_lines.get_nowait())
            except Empty:
                break
        return lines[-limit:]

    def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            self._stderr_lines.put(line.rstrip("\n"))

    def _clear_stderr_lines(self) -> None:
        while True:
            try:
                self._stderr_lines.get_nowait()
            except Empty:
                return

    def _build_process_env(self) -> dict[str, str] | None:
        if not self.extra_env and not self.remove_env_keys:
            return None
        env = {str(key): str(value) for key, value in os.environ.items()}
        for key in self.remove_env_keys:
            env.pop(key, None)
        env.update(self.extra_env)
        return env
