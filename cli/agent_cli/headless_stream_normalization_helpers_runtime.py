from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from cli.agent_cli.runtime import AgentCliRuntime


def request_id_for_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    request_id = payload.get("id")
    if request_id is None:
        return None
    return str(request_id)


def resolve_serve_prompt(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
    if payload.get("provider_status"):
        return "/provider"
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        raise ValueError("request.prompt must be a string")
    if not prompt.strip():
        raise ValueError("request.prompt must not be empty")
    return prompt


def headless_thread_id(runner: AgentCliRuntime) -> str:
    existing = str(getattr(runner, "_headless_jsonl_thread_id", "") or "").strip()
    if existing:
        return existing
    thread_id = str(getattr(runner, "thread_id", "") or "").strip() or str(uuid4())
    setattr(runner, "_headless_jsonl_thread_id", thread_id)
    return thread_id
