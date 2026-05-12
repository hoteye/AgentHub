"""Mixin for codex-sidecar thread lifecycle methods extracted from AgentCliAppServer."""

from __future__ import annotations

from typing import Any

from cli.agent_cli.app_server_codex_sidecar_runtime import (
    _codex_sidecar_metadata_from_runtime,
    _codex_sidecar_thread_payload,
)
from cli.agent_cli.app_server_payloads import (
    thread_response_payload as _thread_response_payload,
)
from cli.agent_cli.runtime_kernels.base import (
    ForkSessionRequest,
    ResumeSessionRequest,
    StartSessionRequest,
)
from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter import (
    CodexSidecarRuntimeAdapter,
)

# Lazy / conditional imports kept local to avoid circular or heavy loads
# at module level.
_app_server_normalize: Any = None
_app_server_project: Any = None


def _ensure_normalize() -> Any:
    global _app_server_normalize
    if _app_server_normalize is None:
        from cli.agent_cli import (
            app_server_protocol_normalization_helpers_runtime as mod,
        )

        _app_server_normalize = mod
    return _app_server_normalize


def _ensure_project() -> Any:
    global _app_server_project
    if _app_server_project is None:
        from cli.agent_cli import (
            app_server_protocol_projection_helpers_runtime as mod,
        )

        _app_server_project = mod
    return _app_server_project


class CodexSidecarThreadMixin:
    """Codex sidecar thread start / resume / fork / read / close helpers.

    Designed to be mixed into ``AgentCliAppServer`` and relies on instance
    attributes set there:
      * ``self._codex_sidecar_kernel``
      * ``self._runtime_by_thread_id``
      * ``self._primary_runtime``
      * ``self.runtime``
      * ``self._emit_error_response``
      * ``self._emit_result``
      * ``self._emit_notification``
    """

    def _start_codex_sidecar_thread(self, *, request_id: Any, params: dict[str, Any]) -> None:
        import asyncio

        try:
            kernel = self._codex_sidecar_kernel  # type: ignore[attr-defined]
            if kernel is None:
                kernel = CodexSidecarKernel(cwd=str(params.get("cwd") or "").strip() or None)
                self._codex_sidecar_kernel = kernel  # type: ignore[attr-defined]
            metadata = _codex_sidecar_metadata_from_runtime(self.runtime, params)  # type: ignore[attr-defined]
            session = asyncio.run(
                kernel.start_session(
                    StartSessionRequest(
                        cwd=str(params.get("cwd") or "").strip() or None,
                        name=str(params.get("name") or "").strip() or None,
                        model=str(params.get("model") or "").strip() or None,
                        model_provider=str(params.get("modelProvider") or "").strip() or None,
                        metadata=metadata,
                    )
                )
            )
            session.metadata.update(metadata)
            sidecar_runtime = CodexSidecarRuntimeAdapter(
                kernel=kernel,
                session=session,
                gateway_state_store=getattr(self.runtime, "gateway_state_store", None),  # type: ignore[attr-defined]
            )
            thread_id = str(sidecar_runtime.thread_id or session.thread_id or "").strip()
            if thread_id:
                self._runtime_by_thread_id[thread_id] = sidecar_runtime  # type: ignore[attr-defined]
                self.runtime = sidecar_runtime  # type: ignore[attr-defined]
            thread = {
                "id": thread_id,
                "thread_id": thread_id,
                "name": session.thread_name,
                "preview": "",
                "ephemeral": False,
                "model_provider": session.model_provider or "openai",
                "created_at_unix": 0,
                "updated_at_unix": 0,
                "status": "idle",
                "path": str(session.metadata.get("thread_path") or "") or None,
                "cwd": session.cwd,
                "cli_version": "",
                "source": "agenthub",
                "metadata": {
                    "provider_status": sidecar_runtime.agent.provider_status(),
                    "runtime_policy": sidecar_runtime.runtime_policy_status(),
                    "runtime_kernel": "codex_sidecar",
                },
            }
        except Exception as exc:
            self._emit_error_response(  # type: ignore[attr-defined]
                request_id=request_id,
                code=-32010,
                message="Thread start failed",
                data={"detail": f"{type(exc).__name__}: {exc}"},
            )
            return
        self._emit_result(request_id, _thread_response_payload(sidecar_runtime, thread))  # type: ignore[attr-defined]

    def _close_codex_sidecar_kernel(self) -> None:
        kernel = self._codex_sidecar_kernel  # type: ignore[attr-defined]
        if kernel is None:
            return
        import asyncio

        try:
            asyncio.run(kernel.aclose())
        finally:
            self._codex_sidecar_kernel = None  # type: ignore[attr-defined]
            self._runtime_by_thread_id.clear()  # type: ignore[attr-defined]

    def _handle_codex_sidecar_thread_read(
        self,
        *,
        request_id: Any,
        params: dict[str, Any],
    ) -> bool:
        thread_id = str(params.get("threadId") or params.get("thread_id") or "").strip()
        sidecar_runtime = self._runtime_by_thread_id.get(thread_id)  # type: ignore[attr-defined]
        if sidecar_runtime is None:
            return False
        try:
            payload = sidecar_runtime.kernel.read_thread(
                thread_id,
                include_turns=bool(params.get("includeTurns", params.get("include_turns", False))),
            )
            thread = _codex_sidecar_thread_payload(
                sidecar_runtime,
                thread=dict(payload.get("thread") or {}),
                include_turns=bool(params.get("includeTurns", params.get("include_turns", False))),
            )
        except Exception as exc:
            self._emit_error_response(  # type: ignore[attr-defined]
                request_id=request_id,
                code=-32013,
                message="Thread read failed",
                data={"detail": f"{type(exc).__name__}: {exc}"},
            )
            return True
        self._emit_result(request_id, {"thread": thread})  # type: ignore[attr-defined]
        return True

    def _handle_codex_sidecar_thread_fork(
        self,
        *,
        request_id: Any,
        params: dict[str, Any],
    ) -> bool:
        import asyncio

        source_thread_id = str(params.get("threadId") or params.get("thread_id") or "").strip()
        source_runtime = self._runtime_by_thread_id.get(source_thread_id)  # type: ignore[attr-defined]
        if source_runtime is None:
            return False
        try:
            session = asyncio.run(
                source_runtime.kernel.fork_session(
                    ForkSessionRequest(
                        source_thread_id=source_thread_id,
                        source_path=str(params.get("path") or "").strip() or None,
                        cwd=str(params.get("cwd") or "").strip() or None,
                        name=str(params.get("name") or "").strip() or None,
                        metadata=_codex_sidecar_metadata_from_runtime(source_runtime, params),
                    )
                )
            )
            sidecar_runtime = CodexSidecarRuntimeAdapter(
                kernel=source_runtime.kernel,
                session=session,
                gateway_state_store=getattr(source_runtime, "gateway_state_store", None),
            )
            thread_id = str(sidecar_runtime.thread_id or session.thread_id or "").strip()
            if thread_id:
                self._runtime_by_thread_id[thread_id] = sidecar_runtime  # type: ignore[attr-defined]
                self.runtime = sidecar_runtime  # type: ignore[attr-defined]
            thread = _codex_sidecar_thread_payload(
                sidecar_runtime,
                thread=dict(session.metadata.get("raw_result") or {}).get("thread"),
                include_turns=True,
            )
        except Exception as exc:
            self._emit_error_response(  # type: ignore[attr-defined]
                request_id=request_id,
                code=-32012,
                message="Thread fork failed",
                data={"detail": f"{type(exc).__name__}: {exc}"},
            )
            return True
        runtime_policy = (
            dict(session.metadata.get("runtime_policy") or {})
            if isinstance(session.metadata.get("runtime_policy"), dict)
            else {}
        )
        self._emit_result(  # type: ignore[attr-defined]
            request_id,
            {
                "thread": thread,
                "model": str(sidecar_runtime.agent.provider_status().get("provider_model") or ""),
                "modelProvider": str(thread.get("modelProvider") or ""),
                "cwd": str(thread.get("cwd") or ""),
                "approvalPolicy": _ensure_normalize().reference_approval_policy_value(
                    session.metadata.get("approvalPolicy")
                ),
                "sandbox": _ensure_project().reference_sandbox_policy_payload(
                    sandbox_mode=session.metadata.get("sandbox"),
                    cwd=str(thread.get("cwd") or ""),
                    network_access=session.metadata.get("network_access_enabled")
                    or runtime_policy.get("network_access_enabled"),
                ),
            },
        )
        self._emit_notification("thread/started", {"thread": thread})  # type: ignore[attr-defined]
        return True

    def _handle_codex_sidecar_thread_resume(
        self,
        *,
        request_id: Any,
        params: dict[str, Any],
    ) -> bool:
        import asyncio

        if params.get("engine") is None:
            return False
        from cli.agent_cli.runtime_kernels.routing import normalize_kernel_engine

        if normalize_kernel_engine(params.get("engine")) != "codex_sidecar":
            return False
        kernel = self._codex_sidecar_kernel  # type: ignore[attr-defined]
        if kernel is None:
            kernel = CodexSidecarKernel(cwd=str(params.get("cwd") or "").strip() or None)
            self._codex_sidecar_kernel = kernel  # type: ignore[attr-defined]
        try:
            session = asyncio.run(
                kernel.resume_session(
                    ResumeSessionRequest(
                        thread_id=str(
                            params.get("threadId") or params.get("thread_id") or ""
                        ).strip()
                        or None,
                        path=str(params.get("path") or "").strip() or None,
                        history=(
                            [
                                dict(item)
                                for item in list(params.get("history") or [])
                                if isinstance(item, dict)
                            ]
                            if isinstance(params.get("history"), list)
                            else None
                        ),
                        cwd=str(params.get("cwd") or "").strip() or None,
                        metadata=_codex_sidecar_metadata_from_runtime(self.runtime, params),  # type: ignore[attr-defined]
                    )
                )
            )
            sidecar_runtime = CodexSidecarRuntimeAdapter(
                kernel=kernel,
                session=session,
                gateway_state_store=getattr(self.runtime, "gateway_state_store", None),  # type: ignore[attr-defined]
            )
            thread_id = str(sidecar_runtime.thread_id or session.thread_id or "").strip()
            if thread_id:
                self._runtime_by_thread_id[thread_id] = sidecar_runtime  # type: ignore[attr-defined]
                self.runtime = sidecar_runtime  # type: ignore[attr-defined]
            thread = _codex_sidecar_thread_payload(
                sidecar_runtime,
                thread=dict(session.metadata.get("raw_result") or {}).get("thread"),
                include_turns=True,
            )
        except Exception as exc:
            self._emit_error_response(  # type: ignore[attr-defined]
                request_id=request_id,
                code=-32012,
                message="Thread resume failed",
                data={"detail": f"{type(exc).__name__}: {exc}"},
            )
            return True
        self._emit_result(  # type: ignore[attr-defined]
            request_id,
            {
                **_thread_response_payload(sidecar_runtime, thread),
                "turns": list(thread.get("turns") or []),
            },
        )
        return True
