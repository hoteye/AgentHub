from __future__ import annotations

from typing import Any

from cli.agent_cli.app_server_payloads import (
    reference_thread_payload as _reference_thread_payload,
)


def _codex_sidecar_metadata_from_runtime(runtime: Any, params: dict[str, Any]) -> dict[str, Any]:
    runtime_policy_getter = getattr(runtime, "runtime_policy_status", None)
    runtime_policy = dict(runtime_policy_getter() or {}) if callable(runtime_policy_getter) else {}
    metadata: dict[str, Any] = {
        "runtime_policy": runtime_policy,
    }
    approval_policy = (
        str(params.get("approvalPolicy") or "").strip()
        or str(runtime_policy.get("approval_policy") or "").strip()
    )
    sandbox = (
        str(params.get("sandbox") or "").strip()
        or str(runtime_policy.get("sandbox_mode") or "").strip()
    )
    if approval_policy:
        metadata["approvalPolicy"] = approval_policy
    if sandbox:
        metadata["sandbox"] = sandbox
    return metadata


def _codex_sidecar_thread_payload(
    runtime: Any,
    *,
    thread: Any,
    include_turns: bool,
) -> dict[str, Any]:
    raw_thread = dict(thread or {})
    provider_status = dict(runtime.agent.provider_status() or {})
    thread_id = str(
        raw_thread.get("id")
        or raw_thread.get("threadId")
        or raw_thread.get("thread_id")
        or runtime.thread_id
        or ""
    ).strip()
    turns = (
        [_codex_sidecar_history_turn(item) for item in list(raw_thread.get("turns") or [])]
        if include_turns
        else []
    )
    normalized = {
        "id": thread_id,
        "thread_id": thread_id,
        "name": str(raw_thread.get("name") or runtime.thread_name or thread_id),
        "preview": str(raw_thread.get("preview") or ""),
        "ephemeral": False,
        "model_provider": str(
            raw_thread.get("modelProvider")
            or raw_thread.get("model_provider")
            or provider_status.get("provider_name")
            or ""
        ),
        "created_at_unix": int(raw_thread.get("createdAt") or raw_thread.get("created_at") or 0),
        "updated_at_unix": int(raw_thread.get("updatedAt") or raw_thread.get("updated_at") or 0),
        "status": "idle",
        "path": str(raw_thread.get("path") or "") or None,
        "cwd": str(raw_thread.get("cwd") or runtime.cwd or ""),
        "cli_version": "",
        "source": "agenthub",
        "turns": turns,
        "metadata": {
            "provider_status": provider_status,
            "runtime_policy": runtime.runtime_policy_status(),
            "runtime_kernel": "codex_sidecar",
        },
    }
    return _reference_thread_payload(normalized, include_turns=include_turns)


def _codex_sidecar_history_turn(raw_turn: Any) -> dict[str, Any]:
    turn = dict(raw_turn or {}) if isinstance(raw_turn, dict) else {}
    items = [dict(item) for item in list(turn.get("items") or []) if isinstance(item, dict)]
    user_text = ""
    assistant_text = ""
    for item in items:
        item_type = str(item.get("type") or "").strip()
        if item_type == "userMessage" and not user_text:
            user_text = _codex_sidecar_item_text(item)
        elif item_type == "agentMessage" and not assistant_text:
            assistant_text = _codex_sidecar_item_text(item)
    status_text = str(turn.get("status") or "").strip().lower()
    status: dict[str, Any] = {}
    if status_text and status_text not in {"completed", "complete", "success"}:
        status["error"] = status_text
    return {
        "turn_id": str(turn.get("id") or turn.get("turnId") or ""),
        "user_text": user_text,
        "assistant_text": assistant_text,
        "status": status,
        "turn_events": [],
    }


def _codex_sidecar_item_text(item: dict[str, Any]) -> str:
    text = str(item.get("text") or "").strip()
    if text:
        return text
    content = item.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                part_text = str(part.get("text") or "").strip()
                if part_text:
                    parts.append(part_text)
        return "\n".join(parts).strip()
    return ""
