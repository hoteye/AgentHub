from __future__ import annotations

import threading
from typing import Any, Callable


InProcessMessage = dict[str, Any]
MessageHandler = Callable[[InProcessMessage], None]
CloseHandler = Callable[[], None]


class InProcessTransportClosedError(RuntimeError):
    pass


class InProcessTransportEndpoint:
    def __init__(self, *, label: str) -> None:
        self.label = str(label or "").strip() or "inprocess"
        self._lock = threading.RLock()
        self._peer: InProcessTransportEndpoint | None = None
        self._closed = False
        self._on_message: MessageHandler | None = None
        self._on_close: CloseHandler | None = None

    @property
    def is_closed(self) -> bool:
        with self._lock:
            return self._closed

    def set_message_handler(self, handler: MessageHandler | None) -> None:
        with self._lock:
            self._on_message = handler

    def set_close_handler(self, handler: CloseHandler | None) -> None:
        with self._lock:
            self._on_close = handler

    def send(self, message: InProcessMessage) -> None:
        if not isinstance(message, dict):
            raise TypeError("In-process transport message must be a dict")
        with self._lock:
            if self._closed:
                raise InProcessTransportClosedError("In-process transport endpoint is closed")
            peer = self._peer
        if peer is None:
            raise InProcessTransportClosedError("In-process transport endpoint is disconnected")
        peer._receive_from_peer(dict(message))

    def close(self) -> None:
        peer_to_close: InProcessTransportEndpoint | None
        on_close: CloseHandler | None
        with self._lock:
            if self._closed:
                return
            self._closed = True
            peer_to_close = self._peer
            self._peer = None
            on_close = self._on_close
        if peer_to_close is not None:
            peer_to_close._close_from_peer(self)
        if on_close is not None:
            on_close()

    def _bind_peer(self, peer: InProcessTransportEndpoint) -> None:
        with self._lock:
            self._peer = peer

    def _receive_from_peer(self, message: InProcessMessage) -> None:
        with self._lock:
            if self._closed:
                raise InProcessTransportClosedError("In-process transport peer is closed")
            on_message = self._on_message
        if on_message is not None:
            on_message(dict(message))

    def _close_from_peer(self, peer: InProcessTransportEndpoint) -> None:
        on_close: CloseHandler | None
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._peer is peer:
                self._peer = None
            on_close = self._on_close
        if on_close is not None:
            on_close()


def create_inprocess_transport_pair(
    *, left_label: str = "inprocess:left", right_label: str = "inprocess:right"
) -> tuple[InProcessTransportEndpoint, InProcessTransportEndpoint]:
    left = InProcessTransportEndpoint(label=left_label)
    right = InProcessTransportEndpoint(label=right_label)
    left._bind_peer(right)
    right._bind_peer(left)
    return left, right
