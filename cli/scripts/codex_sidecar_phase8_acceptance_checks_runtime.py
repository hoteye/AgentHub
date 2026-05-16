from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_kernels import (
    ForkSessionRequest,
    ResumeSessionRequest,
    StartSessionRequest,
)
from cli.agent_cli.runtime_kernels.codex_sidecar import (
    CodexSidecarKernel,
    CodexSidecarRuntimeAdapter,
)
from cli.scripts.codex_sidecar_phase8_acceptance_runner import _require


def check_fake_turn_lifecycle(
    *,
    codex_bin: Path,
    cwd: Path,
    request_timeout: float,
    extra_env: dict[str, str],
) -> dict[str, Any]:
    kernel = CodexSidecarKernel(
        codex_bin=codex_bin,
        request_timeout=request_timeout,
        extra_env=extra_env,
    )
    try:
        session = asyncio.run(
            kernel.start_session(StartSessionRequest(cwd=str(cwd), model_provider="fake-provider"))
        )
        runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
        response = runtime.handle_prompt("phase 8 lifecycle probe")
    finally:
        asyncio.run(kernel.aclose())

    methods = _response_sidecar_methods(response)
    _require_methods(
        methods,
        {
            "turn/started",
            "item/agentMessage/delta",
            "item/commandExecution/outputDelta",
            "thread/tokenUsage/updated",
            "turn/completed",
        },
    )
    _require(response.assistant_text == "fake sidecar reply", "unexpected assistant text")
    _require(_last_event_type(response.turn_events) == "turn.completed", "turn did not complete")
    return {
        "thread_id": session.thread_id,
        "assistant_text": response.assistant_text,
        "methods": methods,
    }


def check_fake_approval_roundtrip(
    *,
    codex_bin: Path,
    cwd: Path,
    request_timeout: float,
    extra_env: dict[str, str],
) -> dict[str, Any]:
    kernel = CodexSidecarKernel(
        codex_bin=codex_bin,
        request_timeout=request_timeout,
        extra_env=extra_env,
    )
    runtime: CodexSidecarRuntimeAdapter | None = None
    worker: threading.Thread | None = None
    result_holder: dict[str, Any] = {}
    try:
        session = asyncio.run(kernel.start_session(StartSessionRequest(cwd=str(cwd))))
        runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)

        def _run_prompt() -> None:
            try:
                result_holder["response"] = runtime.handle_prompt("phase 8 approval probe")
            except Exception as exc:  # pragma: no cover - surfaced in assertion path.
                result_holder["error"] = f"{type(exc).__name__}: {exc}"

        worker = threading.Thread(target=_run_prompt, daemon=True)
        worker.start()
        deadline = time.monotonic() + request_timeout
        ticket = None
        while time.monotonic() < deadline:
            ticket = runtime.gateway_state_store.get_approval_ticket("codex_fake_approval_1")
            if ticket is not None:
                break
            time.sleep(0.02)
        _require(ticket is not None, "approval ticket was not registered")

        decision = runtime.decide_approval(
            "codex_fake_approval_1",
            decision="accept",
            decided_by="phase8",
        )
        worker.join(timeout=request_timeout)
        _require(not worker.is_alive(), "approval prompt did not finish")
        _require("error" not in result_holder, str(result_holder.get("error") or ""))
        response = result_holder.get("response")
        _require(response is not None, "approval prompt returned no response")
    finally:
        asyncio.run(kernel.aclose())
        if worker is not None and worker.is_alive():
            worker.join(timeout=0.5)

    assert runtime is not None
    final_ticket = runtime.gateway_state_store.get_approval_ticket("codex_fake_approval_1")
    _require(final_ticket is not None, "approval ticket disappeared")
    _require(getattr(final_ticket, "status", "") == "approved", "approval was not approved")
    methods = _response_sidecar_methods(response)
    _require_methods(methods, {"item/commandExecution/requestApproval", "turn/completed"})
    return {
        "thread_id": runtime.thread_id,
        "ticket_status": getattr(final_ticket, "status", ""),
        "codex_response": decision.get("codex_sidecar_response"),
        "methods": methods,
    }


def check_fake_fork_resume(
    *,
    codex_bin: Path,
    cwd: Path,
    request_timeout: float,
    extra_env: dict[str, str],
) -> dict[str, Any]:
    kernel = CodexSidecarKernel(
        codex_bin=codex_bin,
        request_timeout=request_timeout,
        extra_env=extra_env,
    )
    try:
        source = asyncio.run(kernel.start_session(StartSessionRequest(cwd=str(cwd))))
        runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=source)
        runtime.handle_prompt("phase 8 fork source")
        forked = asyncio.run(
            kernel.fork_session(ForkSessionRequest(source_thread_id=source.thread_id, cwd=str(cwd)))
        )
        resumed = asyncio.run(
            kernel.resume_session(ResumeSessionRequest(thread_id=source.thread_id, cwd=str(cwd)))
        )
    finally:
        asyncio.run(kernel.aclose())

    fork_turns = list(forked.metadata.get("thread_turns") or [])
    resumed_turns = list(resumed.metadata.get("thread_turns") or [])
    _require(fork_turns, "forked session did not receive persisted turns")
    _require(resumed_turns, "resumed session did not receive persisted turns")
    _require(
        forked.metadata.get("forked_from_thread_id") == source.thread_id,
        "forked session metadata missed source thread id",
    )
    return {
        "source_thread_id": source.thread_id,
        "forked_thread_id": forked.thread_id,
        "forked_turn_count": len(fork_turns),
        "resumed_turn_count": len(resumed_turns),
    }


def check_fake_crash_reconnect_resume(
    *,
    codex_bin: Path,
    cwd: Path,
    request_timeout: float,
    extra_env: dict[str, str],
) -> dict[str, Any]:
    first_kernel = CodexSidecarKernel(
        codex_bin=codex_bin,
        request_timeout=request_timeout,
        extra_env=extra_env,
    )
    source_thread_id = ""
    try:
        source = asyncio.run(first_kernel.start_session(StartSessionRequest(cwd=str(cwd))))
        source_thread_id = source.thread_id
        runtime = CodexSidecarRuntimeAdapter(kernel=first_kernel, session=source)
        runtime.handle_prompt("phase 8 reconnect seed")
    finally:
        asyncio.run(first_kernel.aclose())

    second_kernel = CodexSidecarKernel(
        codex_bin=codex_bin,
        request_timeout=request_timeout,
        extra_env=extra_env,
    )
    try:
        resumed = asyncio.run(
            second_kernel.resume_session(
                ResumeSessionRequest(thread_id=source_thread_id, cwd=str(cwd))
            )
        )
        resumed_turns = list(resumed.metadata.get("thread_turns") or [])
        runtime = CodexSidecarRuntimeAdapter(kernel=second_kernel, session=resumed)
        response = runtime.handle_prompt("phase 8 reconnect follow-up")
    finally:
        asyncio.run(second_kernel.aclose())

    _require(resumed_turns, "reconnected kernel did not resume persisted turns")
    _require(response.assistant_text == "fake sidecar reply", "reconnected turn failed")
    return {
        "thread_id": source_thread_id,
        "resumed_turn_count": len(resumed_turns),
        "assistant_text": response.assistant_text,
    }


def check_real_agenthub_sidecar(
    *,
    codex_bin: Path,
    cwd: Path,
    request_timeout: float,
    turn_timeout: float,
    live_turn: str | None,
    real_fork: bool,
) -> dict[str, Any]:
    _require(codex_bin.exists(), f"real Codex binary not found: {codex_bin}")
    kernel = CodexSidecarKernel(codex_bin=codex_bin, request_timeout=request_timeout)
    try:
        session = asyncio.run(kernel.start_session(StartSessionRequest(cwd=str(cwd))))
        details: dict[str, Any] = {
            "thread_id": session.thread_id,
            "model": session.model,
            "model_provider": session.model_provider,
        }
        if live_turn:
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            response = _run_prompt_with_timeout(
                runtime,
                live_turn,
                timeout=max(0.1, turn_timeout),
            )
            details["assistant_text"] = response.assistant_text
            details["methods"] = _response_sidecar_methods(response)
            _require(
                _last_event_type(response.turn_events) == "turn.completed",
                "real AgentHub-sidecar live turn did not complete",
            )
        if real_fork:
            forked = asyncio.run(
                kernel.fork_session(
                    ForkSessionRequest(source_thread_id=session.thread_id, cwd=str(cwd))
                )
            )
            details["forked_thread_id"] = forked.thread_id
            details["forked_from_thread_id"] = forked.metadata.get("forked_from_thread_id")
    finally:
        asyncio.run(kernel.aclose())
    return details


def _run_prompt_with_timeout(
    runtime: CodexSidecarRuntimeAdapter,
    text: str,
    *,
    timeout: float,
) -> Any:
    result_holder: dict[str, Any] = {}

    def _run() -> None:
        try:
            result_holder["response"] = runtime.handle_prompt(text)
        except Exception as exc:  # pragma: no cover - live provider failure path.
            result_holder["error"] = f"{type(exc).__name__}: {exc}"

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout=timeout)
    _require(not worker.is_alive(), f"live turn timed out after {timeout:.1f}s")
    _require("error" not in result_holder, str(result_holder.get("error") or ""))
    response = result_holder.get("response")
    _require(response is not None, "live turn returned no response")
    return response


def _response_sidecar_methods(response: Any) -> list[str]:
    diagnostics = getattr(response, "protocol_diagnostics", {}) or {}
    events = diagnostics.get("codex_sidecar_events") or []
    methods: list[str] = []
    for event in events:
        if isinstance(event, dict):
            method = str(event.get("method") or "").strip()
            if method:
                methods.append(method)
    return methods


def _last_event_type(events: list[dict[str, Any]]) -> str:
    if not events:
        return ""
    return str(events[-1].get("type") or "")


def _require_methods(methods: list[str], expected: set[str]) -> None:
    missing = sorted(expected.difference(methods))
    _require(not missing, f"missing sidecar methods: {', '.join(missing)}")
