from __future__ import annotations

import threading
from concurrent.futures import Future
from time import monotonic, sleep

from cli.agent_cli import terminal_driver


def test_safe_terminal_utf8_decoder_replaces_invalid_bytes() -> None:
    decoder_factory = getattr(terminal_driver, "_safe_terminal_utf8_decoder", None)
    if decoder_factory is None:
        return
    decode = decoder_factory()

    assert decode(b"ok", final=False) == "ok"
    assert decode(b"\x81", final=False) == "\ufffd"
    assert decode("中文".encode(), final=False) == "中文"


def test_terminal_input_closed_errors_are_suppressed() -> None:
    is_closed = getattr(terminal_driver, "_is_terminal_input_closed_error", None)
    if is_closed is None:
        return

    assert is_closed(OSError(9, "Bad file descriptor"))
    assert not is_closed(OSError(5, "Input/output error"))
    assert not is_closed(OSError(22, "Invalid argument"))


def test_terminal_input_eio_is_treated_as_transient() -> None:
    is_transient = getattr(terminal_driver, "_is_terminal_input_transient_error", None)
    if is_transient is None:
        return

    assert is_transient(OSError(5, "Input/output error"))
    assert not is_transient(OSError(9, "Bad file descriptor"))
    assert not is_transient(OSError(22, "Invalid argument"))


def test_terminal_foreground_recovery_runs_on_event_loop_from_input_thread() -> None:
    driver_cls = getattr(terminal_driver, "AgentHubLinuxDriver", None)
    if not hasattr(driver_cls, "_recover_terminal_foreground"):
        return

    scheduled: list[object] = []

    class FakeLoop:
        def is_closed(self) -> bool:
            return False

        def call_soon_threadsafe(self, callback) -> None:
            scheduled.append(callback)

    driver = object.__new__(driver_cls)
    driver._agenthub_event_loop = FakeLoop()
    called: list[bool] = []

    def recover_now() -> bool:
        called.append(True)
        return True

    driver._recover_terminal_foreground_now = recover_now

    future = Future()

    def run_recovery() -> None:
        future.set_result(driver._recover_terminal_foreground())

    thread = threading.Thread(target=run_recovery)
    thread.start()
    deadline = monotonic() + 1.0
    while not scheduled:
        if monotonic() >= deadline:
            break
        sleep(0.001)
    assert scheduled
    scheduled.pop()()
    thread.join(timeout=1.0)

    assert future.result(timeout=0.1) is True
    assert called == [True]
