from __future__ import annotations

import pytest

from cli.agent_cli.mcp.inprocess_transport import (
    InProcessTransportClosedError,
    create_inprocess_transport_pair,
)


def test_inprocess_transport_pair_delivers_message_to_peer_handler() -> None:
    left, right = create_inprocess_transport_pair()
    received: list[dict[str, object]] = []
    right.set_message_handler(lambda message: received.append(message))

    left.send({"type": "ping", "seq": 1})

    assert received == [{"type": "ping", "seq": 1}]


def test_inprocess_transport_close_propagates_to_peer() -> None:
    left, right = create_inprocess_transport_pair()
    closed: list[str] = []
    left.set_close_handler(lambda: closed.append("left"))
    right.set_close_handler(lambda: closed.append("right"))

    left.close()

    assert left.is_closed is True
    assert right.is_closed is True
    assert closed == ["right", "left"]


def test_inprocess_transport_send_after_close_raises() -> None:
    left, right = create_inprocess_transport_pair()
    right.close()

    with pytest.raises(InProcessTransportClosedError):
        left.send({"type": "ping"})
