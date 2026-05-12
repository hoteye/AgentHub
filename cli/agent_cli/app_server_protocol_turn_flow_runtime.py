from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled


def _emit_invalid_params(server: Any, *, request_id: Any, detail: str) -> None:
    server._emit_error_response(
        request_id=request_id,
        code=-32602,
        message="Invalid params",
        data={"detail": detail},
    )


def _emit_runtime_error(server: Any, *, request_id: Any, code: int, message: str, exc: Exception) -> None:
    server._emit_error_response(
        request_id=request_id,
        code=code,
        message=message,
        data={"detail": f"{type(exc).__name__}: {exc}"},
    )


def run_turn_start_job(
    server: Any,
    *,
    job_id: str,
    request_id: Any,
    thread_id: str,
    turn_id: str,
    prompt: str,
    attachments: list[Any],
    session_runtime_helpers: Any,
    turn_helpers: Any,
    reference_turn_runtime_payload_fn: Callable[..., dict[str, Any]],
    completed_turn_payload_from_response_fn: Callable[..., dict[str, Any]],
    failed_turn_payload_fn: Callable[..., dict[str, Any]],
    prompt_response_turn_events_fn: Callable[[Any], list[dict[str, Any]]],
    active_app_server_turn_id_fn: Callable[[str], Any],
) -> None:
    emitted_turn_event_signatures: set[str] = set()
    emitted_turn_event_backfill_counts: dict[str, int] = {}
    item_text_state: dict[str, str] = {}
    plan_state: dict[str, str] = {}
    try:
        server._emit_notification(
            "turn/started",
            {
                "threadId": thread_id,
                "turn": reference_turn_runtime_payload_fn(turn_id=turn_id, status="in_progress"),
            },
        )

        def on_turn_event(event: dict[str, Any]) -> None:
            if not isinstance(event, dict):
                return
            signature = session_runtime_helpers.turn_event_signature(event)
            if signature in emitted_turn_event_signatures:
                return
            emitted_turn_event_signatures.add(signature)
            backfill_signature = session_runtime_helpers.turn_event_backfill_signature(event)
            emitted_turn_event_backfill_counts[backfill_signature] = (
                int(emitted_turn_event_backfill_counts.get(backfill_signature) or 0) + 1
            )
            turn_helpers.emit_turn_stream_event(
                server,
                thread_id=thread_id,
                turn_id=turn_id,
                event=event,
                item_text_state=item_text_state,
                plan_state=plan_state,
            )

        with session_runtime_helpers.temporary_turn_event_callback(server.runtime, on_turn_event):
            with session_runtime_helpers.temporary_request_user_input_handler(
                server.runtime,
                server._make_request_user_input_handler(request_id=request_id),
                replace_only_when_missing=True,
            ):
                with active_app_server_turn_id_fn(turn_id):
                    response = server.runtime.handle_prompt(prompt, attachments=attachments)
        if timeline_debug_enabled():
            log_timeline(
                "app_server.turn.prompt.completed",
                thread_id=thread_id,
                turn_id=turn_id,
                response_item_count=len(list(getattr(response, "response_items", []) or [])),
                tool_event_count=len(list(getattr(response, "tool_events", []) or [])),
                turn_event_count=len(list(getattr(response, "turn_events", []) or [])),
            )

        if timeline_debug_enabled():
            log_timeline(
                "app_server.turn.replay.begin",
                thread_id=thread_id,
                turn_id=turn_id,
            )
        for turn_event in list(response.turn_events or prompt_response_turn_events_fn(response)):
            if not isinstance(turn_event, dict):
                continue
            signature = session_runtime_helpers.turn_event_backfill_signature(turn_event)
            remaining = int(emitted_turn_event_backfill_counts.get(signature) or 0)
            if remaining > 0:
                emitted_turn_event_backfill_counts[signature] = remaining - 1
                continue
            turn_helpers.emit_turn_stream_event(
                server,
                thread_id=thread_id,
                turn_id=turn_id,
                event=turn_event,
                item_text_state=item_text_state,
                plan_state=plan_state,
            )
        if timeline_debug_enabled():
            log_timeline(
                "app_server.turn.replay.end",
                thread_id=thread_id,
                turn_id=turn_id,
            )

        if timeline_debug_enabled():
            log_timeline(
                "app_server.turn.raw_response_items.begin",
                thread_id=thread_id,
                turn_id=turn_id,
                response_item_count=len(list(getattr(response, "response_items", []) or [])),
            )
        turn_helpers.emit_raw_response_item_completed_notifications(
            server,
            thread_id=thread_id,
            turn_id=turn_id,
            response=response,
        )
        if timeline_debug_enabled():
            log_timeline(
                "app_server.turn.raw_response_items.end",
                thread_id=thread_id,
                turn_id=turn_id,
            )
        completed_turn_payload = completed_turn_payload_from_response_fn(turn_id=turn_id, response=response)
        if timeline_debug_enabled():
            log_timeline(
                "app_server.turn.completed.emit.begin",
                thread_id=thread_id,
                turn_id=turn_id,
                status=str(completed_turn_payload.get("status") or ""),
            )
        server._emit_notification(
            "turn/completed",
            {
                "threadId": thread_id,
                "turn": completed_turn_payload,
            },
        )
        if timeline_debug_enabled():
            log_timeline(
                "app_server.turn.completed.emit.end",
                thread_id=thread_id,
                turn_id=turn_id,
                status=str(completed_turn_payload.get("status") or ""),
            )
    except Exception as exc:
        if timeline_debug_enabled():
            log_timeline(
                "app_server.turn.failed",
                thread_id=thread_id,
                turn_id=turn_id,
                error_type=type(exc).__name__,
                error_text=str(exc),
            )
        server._emit_notification(
            "turn/completed",
            {
                "threadId": thread_id,
                "turn": failed_turn_payload_fn(turn_id=turn_id, message=f"{type(exc).__name__}: {exc}"),
            },
        )
    finally:
        with server._jobs_lock:
            server._jobs.pop(job_id, None)


def start_turn_start_job(
    server: Any,
    *,
    request_id: Any,
    thread_id: str,
    turn_id: str,
    prompt: str,
    attachments: list[Any],
    job_runner_fn: Callable[..., None],
) -> None:
    job_id = f"turn:{turn_id}"
    worker = threading.Thread(
        target=job_runner_fn,
        kwargs={
            "server": server,
            "job_id": job_id,
            "request_id": request_id,
            "thread_id": thread_id,
            "turn_id": turn_id,
            "prompt": prompt,
            "attachments": list(attachments or []),
        },
        daemon=False,
    )
    with server._jobs_lock:
        server._jobs[job_id] = {
            "thread": worker,
            "kind": "turn",
            "prompt": prompt,
            "thread_id": thread_id,
            "turn_id": turn_id,
        }
    worker.start()


def handle_turn_start(
    server: Any,
    request_id: Any,
    params: dict[str, Any],
    *,
    first_text_fn: Callable[..., str],
    turn_prompt_from_input_items_fn: Callable[[dict[str, Any]], tuple[str, list[Any]]],
    reference_turn_runtime_payload_fn: Callable[..., dict[str, Any]],
    start_turn_start_job_fn: Callable[..., None],
) -> None:
    thread_id = first_text_fn(params, "threadId", "thread_id")
    if not thread_id:
        _emit_invalid_params(server, request_id=request_id, detail="params.threadId must be a non-empty string")
        return
    try:
        prompt, attachments = turn_prompt_from_input_items_fn(params)
    except ValueError as exc:
        _emit_invalid_params(server, request_id=request_id, detail=str(exc))
        return
    if server._has_active_job() or server.runtime.has_active_run():
        server._emit_error_response(
            request_id=request_id,
            code=-32003,
            message="Runtime busy",
        )
        return
    try:
        if str(getattr(server.runtime, "thread_id", "") or "").strip() != thread_id:
            server.runtime.resume_thread(thread_id)
    except ValueError as exc:
        _emit_invalid_params(server, request_id=request_id, detail=str(exc))
        return
    except RuntimeError as exc:
        server._emit_error_response(
            request_id=request_id,
            code=-32003,
            message="Runtime busy",
            data={"detail": str(exc)},
        )
        return
    except Exception as exc:
        _emit_runtime_error(
            server,
            request_id=request_id,
            code=-32014,
            message="Turn start failed",
            exc=exc,
        )
        return
    turn_id = f"turn_{uuid.uuid4().hex}"
    started_turn = reference_turn_runtime_payload_fn(turn_id=turn_id, status="in_progress")
    server._emit_result(
        request_id,
        {
            "turn": started_turn,
        },
    )
    start_turn_start_job_fn(
        server,
        request_id=request_id,
        thread_id=thread_id,
        turn_id=turn_id,
        prompt=prompt,
        attachments=attachments,
    )
