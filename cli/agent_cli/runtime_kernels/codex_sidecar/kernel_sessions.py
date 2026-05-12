from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_kernels.base import KernelSession
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject
from cli.agent_cli.runtime_kernels.errors import RuntimeKernelSessionError


def _session_from_thread_result(
    result: JsonObject,
    *,
    metadata: dict[str, Any] | None = None,
) -> KernelSession:
    thread = dict(result.get("thread") or {})
    thread_id = str(
        thread.get("id") or thread.get("threadId") or result.get("threadId") or ""
    ).strip()
    if not thread_id:
        raise RuntimeKernelSessionError("codex sidecar did not return a thread id")
    session_metadata = {**dict(metadata or {}), "raw_result": result}
    thread_path = thread.get("path") or result.get("path")
    if thread_path:
        session_metadata["thread_path"] = str(thread_path)
    forked_from_id = thread.get("forkedFromId") or thread.get("forked_from_id")
    if forked_from_id:
        session_metadata["forked_from_thread_id"] = str(forked_from_id)
    turns = thread.get("turns")
    if isinstance(turns, list):
        session_metadata["thread_turns"] = list(turns)
    return KernelSession(
        engine="codex_sidecar",
        session_id=thread_id,
        thread_id=thread_id,
        thread_name=str(thread.get("name") or thread_id),
        cwd=str(result.get("cwd") or thread.get("cwd") or ""),
        model=str(result.get("model") or ""),
        model_provider=str(result.get("modelProvider") or ""),
        metadata=session_metadata,
    )
