from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from cli.agent_cli.models import PromptAttachment, PromptResponse

KernelEngine = Literal["agenthub_python", "codex_sidecar"]


@dataclass(frozen=True, slots=True)
class StartSessionRequest:
    cwd: str | None = None
    name: str | None = None
    model: str | None = None
    model_provider: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResumeSessionRequest:
    session_id: str | None = None
    thread_id: str | None = None
    path: str | None = None
    history: Sequence[dict[str, Any]] | None = None
    cwd: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ForkSessionRequest:
    source_session_id: str | None = None
    source_thread_id: str | None = None
    source_path: str | None = None
    cwd: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StartTurnRequest:
    session_id: str
    text: str
    attachments: Sequence[PromptAttachment] = field(default_factory=tuple)
    input_items: Sequence[dict[str, Any]] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KernelSession:
    engine: KernelEngine
    session_id: str
    thread_id: str = ""
    thread_name: str = ""
    cwd: str = ""
    model: str = ""
    model_provider: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TurnHandle:
    session_id: str
    turn_id: str = ""
    response: PromptResponse | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeKernel(Protocol):
    engine: KernelEngine

    async def start_session(self, request: StartSessionRequest) -> KernelSession: ...

    async def resume_session(self, request: ResumeSessionRequest) -> KernelSession: ...

    async def fork_session(self, request: ForkSessionRequest) -> KernelSession: ...

    async def start_turn(self, request: StartTurnRequest) -> TurnHandle: ...

    async def cancel_turn(self, session_id: str, turn_id: str | None = None) -> None: ...

    async def close_session(self, session_id: str) -> None: ...

    async def aclose(self) -> None: ...
