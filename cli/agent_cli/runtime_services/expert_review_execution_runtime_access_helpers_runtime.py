from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from cli.agent_cli.models import CommandExecutionResult


def provider_status(runtime: Any) -> dict[str, Any]:
    status_getter = getattr(getattr(runtime, "agent", None), "provider_status", None)
    if not callable(status_getter):
        return {}
    try:
        payload = status_getter() or {}
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def provider_status_text(
    runtime: Any,
    key: str,
    *,
    provider_status_fn: Callable[[Any], dict[str, Any]],
    normalized_text_fn: Callable[[Any], str],
) -> str:
    return normalized_text_fn(provider_status_fn(runtime).get(key))


def provider_public_name(
    runtime: Any,
    gate_payload: Mapping[str, Any],
    *,
    provider_status_text_fn: Callable[[Any, str], str],
    normalized_text_fn: Callable[[Any], str],
) -> str:
    return (
        normalized_text_fn(gate_payload.get("primary_provider_name"))
        or provider_status_text_fn(runtime, "provider_label")
        or provider_status_text_fn(runtime, "provider_name")
    )


def provider_review_gate(
    runtime: Any,
    *,
    provider_status_fn: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    gate_getter = getattr(getattr(runtime, "agent", None), "provider_review_gate", None)
    if not callable(gate_getter):
        return provider_status_fn(runtime)
    try:
        payload = gate_getter() or {}
    except Exception:
        return provider_status_fn(runtime)
    return dict(payload) if isinstance(payload, Mapping) else {}


def available_provider_items(runtime: Any) -> list[dict[str, Any]]:
    getter = getattr(getattr(runtime, "agent", None), "available_providers", None)
    if not callable(getter):
        return []
    try:
        payload = getter() or []
    except Exception:
        return []
    return [dict(item) for item in list(payload) if isinstance(item, Mapping)]


def runtime_state_snapshot(runtime: Any) -> dict[str, Any]:
    snapshotter = getattr(runtime, "_snapshot_thread_state", None)
    if not callable(snapshotter):
        return {}
    try:
        payload = snapshotter() or {}
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def wait_timeout_ms(resolution: Any) -> int | None:
    timeout = getattr(resolution, "timeout", None)
    if timeout in (None, ""):
        return None
    try:
        timeout_seconds = int(timeout)
    except (TypeError, ValueError):
        return None
    return max(0, timeout_seconds * 1000)


def first_tool_payload(result: CommandExecutionResult) -> dict[str, Any]:
    if not result.tool_events:
        return {}
    payload = result.tool_events[0].payload or {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def reviewer_output_text(
    wait_result: CommandExecutionResult,
    wait_payload: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    return normalized_text_fn(wait_result.assistant_text) or normalized_text_fn(wait_payload.get("text"))


def wait_failure_detail(
    wait_result: CommandExecutionResult,
    wait_payload: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    status = normalized_text_fn(wait_payload.get("status")).lower() or "unknown"
    summary = ""
    if wait_result.tool_events:
        summary = normalized_text_fn(wait_result.tool_events[0].summary)
    error = normalized_text_fn(wait_payload.get("error"))
    timed_out = bool(wait_payload.get("wait_timed_out"))
    detail_parts = [f"wait_status={status}"]
    if timed_out:
        detail_parts.append("wait_timed_out=true")
    if summary:
        detail_parts.append(f"summary={summary}")
    if error:
        detail_parts.append(f"error={error}")
    return ", ".join(detail_parts)


__all__ = [
    "available_provider_items",
    "first_tool_payload",
    "provider_public_name",
    "provider_review_gate",
    "provider_status",
    "provider_status_text",
    "reviewer_output_text",
    "runtime_state_snapshot",
    "wait_failure_detail",
    "wait_timeout_ms",
]
