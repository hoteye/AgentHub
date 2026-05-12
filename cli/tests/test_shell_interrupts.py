from __future__ import annotations

import errno
import os
from pathlib import Path
import shlex
import signal
import sys
import tempfile
import threading
import time
import unittest

from cli.agent_cli.tools import ToolRegistry


@unittest.skipUnless(os.name != "nt", "process-group interruption is verified on unix hosts")
class ShellInterruptsTest(unittest.TestCase):
    @staticmethod
    def _wait_until(predicate, *, timeout: float = 3.0, interval: float = 0.02) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(interval)
        return predicate()

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError as exc:
            return exc.errno != errno.ESRCH
        return True

    def test_shell_interrupt_terminates_spawned_child_process_group(self) -> None:
        registry = ToolRegistry()
        cancel_event = threading.Event()
        holder: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as temp_dir:
            child_pid_path = Path(temp_dir) / "child.pid"
            child_code = "import time; time.sleep(30)"
            parent_code = (
                "import pathlib, subprocess, sys, time; "
                f"child = subprocess.Popen([{sys.executable!r}, '-c', {child_code!r}]); "
                f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid), encoding='utf-8'); "
                "print('ready', flush=True); "
                "time.sleep(30)"
            )
            command = f"{shlex.quote(sys.executable)} -u -c {shlex.quote(parent_code)}"

            def worker() -> None:
                holder["event"] = registry.shell(
                    command,
                    timeout_sec=10,
                    cancel_event=cancel_event,
                )

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()

            self.assertTrue(
                self._wait_until(child_pid_path.exists),
                "child pid file was not written before interrupt",
            )
            child_pid = int(child_pid_path.read_text(encoding="utf-8").strip())
            self.assertTrue(self._pid_exists(child_pid))

            cancel_event.set()
            thread.join(timeout=5)

            self.assertFalse(thread.is_alive(), "shell worker did not stop after interrupt")
            event = holder.get("event")
            self.assertIsNotNone(event)
            assert event is not None
            self.assertTrue(bool(event.payload.get("interrupted")))
            self.assertEqual(str(event.payload.get("status") or ""), "interrupted")
            self.assertTrue(
                self._wait_until(lambda: not self._pid_exists(child_pid), timeout=2.0),
                "spawned child process survived shell interrupt",
            )

            if self._pid_exists(child_pid):
                os.kill(child_pid, signal.SIGKILL)

