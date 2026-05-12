from __future__ import annotations

from typing import Any, Callable, TextIO

from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.models import PromptResponse
from cli.agent_cli.runtime import AgentCliRuntime


def stream_prompt_jsonl(
    runner: AgentCliRuntime,
    prompt: str,
    *,
    output_stream: TextIO,
    thread_id: str,
    request_id: str | None = None,
    emit_reference_jsonl_event_fn: Callable[..., None],
    turn_event_signature_fn: Callable[[dict[str, Any]], str],
    turn_event_backfill_signature_fn: Callable[[dict[str, Any]], str],
    temporary_turn_event_callback_fn: Callable[[AgentCliRuntime, Any], Any],
    canonical_turn_events_fn: Callable[[PromptResponse], list[dict[str, Any]]],
) -> PromptResponse:
    if timeline_debug_enabled():
        log_timeline(
            "headless.jsonl.begin",
            prompt=prompt,
            thread_id=thread_id,
            request_id=request_id,
        )

    emitted_signatures: set[str] = set()
    emitted_backfill_counts: dict[str, int] = {}
    emit_reference_jsonl_event_fn(
        output_stream,
        {"type": "thread.started", "thread_id": thread_id},
        request_id=request_id,
    )

    def on_turn_event(event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        signature = turn_event_signature_fn(event)
        if signature in emitted_signatures:
            return
        emitted_signatures.add(signature)
        backfill_signature = turn_event_backfill_signature_fn(event)
        emitted_backfill_counts[backfill_signature] = int(emitted_backfill_counts.get(backfill_signature) or 0) + 1
        _log_turn_event("headless.jsonl.turn_event", event)
        emit_reference_jsonl_event_fn(output_stream, event, request_id=request_id)

    with temporary_turn_event_callback_fn(runner, on_turn_event):
        response = runner.handle_prompt(prompt)

    if timeline_debug_enabled():
        log_timeline(
            "headless.jsonl.handle_prompt.completed",
            assistant_preview=str(response.assistant_text or "")[:160],
            tool_event_count=len(list(response.tool_events or [])),
            turn_event_count=len(list(response.turn_events or [])),
        )

    for event in canonical_turn_events_fn(response):
        if not isinstance(event, dict):
            continue
        signature = turn_event_backfill_signature_fn(event)
        remaining = int(emitted_backfill_counts.get(signature) or 0)
        if remaining > 0:
            emitted_backfill_counts[signature] = remaining - 1
            continue
        _log_turn_event("headless.jsonl.backfill_turn_event", event)
        emit_reference_jsonl_event_fn(output_stream, event, request_id=request_id)

    if timeline_debug_enabled():
        log_timeline("headless.jsonl.end", thread_id=thread_id, request_id=request_id)
    return response


def _log_turn_event(message: str, event: dict[str, Any]) -> None:
    if not timeline_debug_enabled():
        return
    item = event.get("item") if isinstance(event, dict) else None
    log_timeline(
        message,
        event_type=event.get("type") if isinstance(event, dict) else None,
        item_type=item.get("type") if isinstance(item, dict) else None,
        item_id=item.get("id") if isinstance(item, dict) else None,
        item_status=item.get("status") if isinstance(item, dict) else None,
        tool=item.get("tool") if isinstance(item, dict) else None,
    )
