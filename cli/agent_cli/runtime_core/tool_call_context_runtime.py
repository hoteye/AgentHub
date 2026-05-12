from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_ACTIVE_APP_SERVER_TURN_ID: ContextVar[str] = ContextVar(
    "active_app_server_turn_id",
    default="",
)
_ACTIVE_PROVIDER_TOOL_CALL_ID: ContextVar[str] = ContextVar(
    "active_provider_tool_call_id",
    default="",
)


def current_app_server_turn_id() -> str:
    return str(_ACTIVE_APP_SERVER_TURN_ID.get() or "").strip()


def current_provider_tool_call_id() -> str:
    return str(_ACTIVE_PROVIDER_TOOL_CALL_ID.get() or "").strip()


@contextmanager
def active_app_server_turn_id(turn_id: str | None) -> Iterator[None]:
    token = _ACTIVE_APP_SERVER_TURN_ID.set(str(turn_id or "").strip())
    try:
        yield
    finally:
        _ACTIVE_APP_SERVER_TURN_ID.reset(token)


@contextmanager
def active_provider_tool_call_id(call_id: str | None) -> Iterator[None]:
    token = _ACTIVE_PROVIDER_TOOL_CALL_ID.set(str(call_id or "").strip())
    try:
        yield
    finally:
        _ACTIVE_PROVIDER_TOOL_CALL_ID.reset(token)
