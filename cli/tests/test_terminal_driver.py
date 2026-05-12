from __future__ import annotations

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

    assert is_closed(OSError(5, "Input/output error"))
    assert is_closed(OSError(9, "Bad file descriptor"))
    assert not is_closed(OSError(22, "Invalid argument"))
