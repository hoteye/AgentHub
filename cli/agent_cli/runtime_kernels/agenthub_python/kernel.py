from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.runtime_kernels.base import (
    ForkSessionRequest,
    KernelEngine,
    KernelSession,
    ResumeSessionRequest,
    StartSessionRequest,
    StartTurnRequest,
    TurnHandle,
)
from cli.agent_cli.runtime_kernels.errors import RuntimeKernelSessionError

RuntimeFactory = Callable[[], Any]


class AgentHubPythonKernel:
    engine: KernelEngine = "agenthub_python"

    def __init__(
        self,
        runtime: Any | None = None,
        *,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        self._provided_runtime = runtime
        self._provided_runtime_used = False
        self._runtime_factory = runtime_factory
        self._sessions: dict[str, Any] = {}

    def _new_runtime(self) -> Any:
        if self._provided_runtime is not None and not self._provided_runtime_used:
            self._provided_runtime_used = True
            return self._provided_runtime
        return self._build_runtime()

    def _build_runtime(self) -> Any:
        if self._runtime_factory is not None:
            return self._runtime_factory()
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        return build_persistent_runtime(
            resume_active_thread=False,
            start_thread_if_unavailable=False,
        )

    def _runtime_for_session(self, session_id: str) -> Any:
        normalized = str(session_id or "").strip()
        if not normalized:
            raise RuntimeKernelSessionError("session_id is required")
        runtime = self._sessions.get(normalized)
        if runtime is None:
            raise RuntimeKernelSessionError(f"runtime session not found: {normalized}")
        return runtime

    def _session_from_runtime(
        self,
        runtime: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> KernelSession:
        thread_id = str(getattr(runtime, "thread_id", "") or "").strip()
        if not thread_id:
            raise RuntimeKernelSessionError("runtime did not provide a thread_id")
        status = _provider_status(runtime)
        return KernelSession(
            engine=self.engine,
            session_id=thread_id,
            thread_id=thread_id,
            thread_name=str(getattr(runtime, "thread_name", "") or ""),
            cwd=str(getattr(runtime, "cwd", "") or ""),
            model=str(status.get("provider_model") or ""),
            model_provider=str(status.get("provider_name") or ""),
            metadata=dict(metadata or {}),
        )

    async def start_session(self, request: StartSessionRequest) -> KernelSession:
        runtime = self._new_runtime()
        result = runtime.start_thread(name=request.name, cwd=request.cwd)
        thread_id = str(
            dict(result or {}).get("thread_id") or getattr(runtime, "thread_id", "") or ""
        )
        if thread_id:
            self._sessions[thread_id] = runtime
        return self._session_from_runtime(runtime, metadata=request.metadata)

    async def resume_session(self, request: ResumeSessionRequest) -> KernelSession:
        runtime = self._new_runtime()
        history = list(request.history) if request.history is not None else None
        result = runtime.resume_thread(
            request.thread_id or request.session_id,
            path=request.path,
            history=history,
        )
        thread = dict(dict(result or {}).get("thread") or {})
        thread_id = str(thread.get("thread_id") or getattr(runtime, "thread_id", "") or "")
        if thread_id:
            self._sessions[thread_id] = runtime
        return self._session_from_runtime(runtime, metadata=request.metadata)

    async def fork_session(self, request: ForkSessionRequest) -> KernelSession:
        from cli.agent_cli.runtime import AgentCliRuntime
        from cli.agent_cli.runtime_core.thread_fork import fork_thread_record

        source_runtime = self._runtime_for_session(
            request.source_session_id or request.source_thread_id or ""
        )
        thread_store = getattr(source_runtime, "thread_store", None)
        if thread_store is None:
            raise RuntimeKernelSessionError("thread store not configured")
        try:
            fork_result = fork_thread_record(
                thread_store=thread_store,
                source_thread_id=request.source_thread_id
                or request.source_session_id
                or str(getattr(source_runtime, "thread_id", "") or ""),
                source_path=request.source_path,
                cwd=request.cwd or str(getattr(source_runtime, "cwd", "") or ""),
                provider_status=_provider_status(source_runtime),
                runtime_policy_status=_runtime_policy_status(source_runtime),
                prefer_source_status=False,
            )
        except Exception as exc:
            raise RuntimeKernelSessionError(str(exc)) from exc

        fork_runtime = AgentCliRuntime(
            thread_store=thread_store,
            runtime_policy=_copy_runtime_policy(source_runtime),
            gateway_state_store=getattr(source_runtime, "gateway_state_store", None),
            gateway_broadcaster=getattr(source_runtime, "gateway_broadcaster", None),
        )
        fork_runtime.resume_thread(str(fork_result.get("thread_id") or ""))
        thread_id = str(getattr(fork_runtime, "thread_id", "") or "")
        if thread_id:
            self._sessions[thread_id] = fork_runtime
        return self._session_from_runtime(fork_runtime, metadata=request.metadata)

    async def start_turn(self, request: StartTurnRequest) -> TurnHandle:
        runtime = self._runtime_for_session(request.session_id)
        response = runtime.handle_prompt(request.text, attachments=list(request.attachments or ()))
        return TurnHandle(
            session_id=request.session_id,
            response=response,
            metadata=dict(request.metadata or {}),
        )

    async def cancel_turn(self, session_id: str, turn_id: str | None = None) -> None:
        del turn_id
        runtime = self._runtime_for_session(session_id)
        runtime.interrupt_active_run()

    async def close_session(self, session_id: str) -> None:
        self._sessions.pop(str(session_id or "").strip(), None)

    async def aclose(self) -> None:
        self._sessions.clear()


def _provider_status(runtime: Any) -> dict[str, Any]:
    agent = getattr(runtime, "agent", None)
    provider_status = getattr(agent, "provider_status", None)
    if not callable(provider_status):
        return {}
    try:
        return dict(provider_status() or {})
    except Exception:
        return {}


def _runtime_policy_status(runtime: Any) -> dict[str, Any]:
    runtime_policy_status = getattr(runtime, "runtime_policy_status", None)
    if not callable(runtime_policy_status):
        return {}
    try:
        return dict(runtime_policy_status() or {})
    except Exception:
        return {}


def _copy_runtime_policy(runtime: Any) -> Any:
    import copy

    try:
        return copy.deepcopy(getattr(runtime, "runtime_policy", None))
    except Exception:
        return getattr(runtime, "runtime_policy", None)
