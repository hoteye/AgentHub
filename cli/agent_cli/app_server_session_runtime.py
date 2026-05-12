from __future__ import annotations

import threading
import time
from typing import Any

from cli.agent_cli.app_server_payloads import activity_event_to_dict as _activity_event_to_dict
from cli.agent_cli import app_server_session_runtime_helpers
from cli.agent_cli.app_server_shell_protocol import _command_response_shell_metadata, _exit_code_for_response
from cli.agent_cli.headless import prompt_response_to_dict
from cli.agent_cli.models import (
    ActivityEvent,
    PromptResponse,
    activity_dedupe_key,
    prompt_response_turn_events,
)


def handle_session_run(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    prompt = params.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        server._emit_error_response(
            request_id=request_id,
            code=-32602,
            message="Invalid params",
            data={"detail": "params.prompt must be a non-empty string"},
        )
        return
    stream = bool(params.get("stream"))
    try:
        response = run_prompt(
            server,
            prompt.strip(),
            request_id=request_id,
            stream=stream,
        )
    except RuntimeError as exc:
        server._emit_error_response(
            request_id=request_id,
            code=-32003,
            message="Runtime busy",
            data={"detail": str(exc)},
        )
        return
    server._emit_result(
        request_id,
        {
            **_command_response_shell_metadata(response),
            "response": prompt_response_to_dict(response),
            "exitCode": _exit_code_for_response(response),
        },
    )


def handle_session_start(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    prompt = params.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        server._emit_error_response(
            request_id=request_id,
            code=-32602,
            message="Invalid params",
            data={"detail": "params.prompt must be a non-empty string"},
        )
        return
    if has_active_job(server) or server.runtime.has_active_run():
        server._emit_error_response(
            request_id=request_id,
            code=-32003,
            message="Runtime busy",
        )
        return
    job_id = str(request_id)
    start_job(
        server,
        job_id=job_id,
        kind="session",
        prompt=prompt.strip(),
        stream=bool(params.get("stream", True)),
        completed_method="session/completed",
    )
    server._emit_result(
        request_id,
        {
            "accepted": True,
            "jobId": job_id,
            "kind": "session",
        },
    )


def handle_session_interrupt(server: Any, request_id: Any) -> None:
    payload = server.runtime.interrupt_active_run()
    server._emit_result(request_id, payload)


def start_job(
    server: Any,
    *,
    job_id: str,
    kind: str,
    prompt: str,
    stream: bool,
    completed_method: str,
) -> None:
    started_event = threading.Event()
    worker = threading.Thread(
        target=server._run_job,
        kwargs={
            "job_id": job_id,
            "kind": kind,
            "prompt": prompt,
            "stream": stream,
            "completed_method": completed_method,
            "started_event": started_event,
        },
        daemon=False,
    )
    with server._jobs_lock:
        server._jobs[job_id] = {
            "thread": worker,
            "kind": kind,
            "prompt": prompt,
        }
    worker.start()
    started_event.wait(timeout=0.5)
    deadline = time.monotonic() + 1.5
    while worker.is_alive() and time.monotonic() < deadline:
        if kind == "session" and server.runtime.has_active_run():
            break
        if kind == "command":
            with server._jobs_lock:
                entry = server._jobs.get(job_id) or {}
                if entry.get("cancel_event") is not None:
                    break
        time.sleep(0.01)


def run_job(
    server: Any,
    *,
    job_id: str,
    kind: str,
    prompt: str,
    stream: bool,
    completed_method: str,
    started_event: threading.Event,
) -> None:
    cancel_event: threading.Event | None = None
    try:
        started_event.set()
        if kind == "command":
            cancel_event = threading.Event()
            with server._jobs_lock:
                entry = server._jobs.get(job_id)
                if entry is not None:
                    entry["cancel_event"] = cancel_event
                server._active_command_job_id = job_id
                server._active_command_cancel_event = cancel_event
            response = server._run_direct_shell_command(
                prompt,
                request_id=job_id,
                stream=stream,
                cancel_event=cancel_event,
            )
        else:
            response = run_prompt(server, prompt, request_id=job_id, stream=stream)
        server._emit_notification(
            completed_method,
            {
                "requestId": job_id,
                "kind": kind,
                "response": prompt_response_to_dict(response),
                "exitCode": _exit_code_for_response(response),
            },
        )
    except Exception as exc:
        server._emit_notification(
            f"{kind}/failed",
            {
                "requestId": job_id,
                "kind": kind,
                "error": {
                    "message": f"{type(exc).__name__}: {exc}",
                },
            },
        )
    finally:
        with server._jobs_lock:
            if server._active_command_job_id == job_id:
                server._active_command_job_id = None
                server._active_command_cancel_event = None
            server._jobs.pop(job_id, None)


def wait_for_jobs(server: Any) -> None:
    while True:
        with server._jobs_lock:
            threads = [entry["thread"] for entry in server._jobs.values()]
        if not threads:
            return
        for thread in threads:
            thread.join(timeout=0.05)


def has_active_job(server: Any) -> bool:
    with server._jobs_lock:
        return bool(server._jobs)


def run_prompt(server: Any, prompt: str, *, request_id: Any, stream: bool) -> PromptResponse:
    if not stream:
        with app_server_session_runtime_helpers.temporary_request_user_input_handler(
            server.runtime,
            server._make_request_user_input_handler(request_id=request_id),
            replace_only_when_missing=True,
        ):
            return server.runtime.handle_prompt(prompt)

    emitted: set[tuple[str, str, str, str, str]] = set()
    emitted_turn_event_signatures: set[str] = set()
    emitted_turn_event_backfill_counts: dict[str, int] = {}

    def on_activity(event: ActivityEvent) -> None:
        key = activity_dedupe_key(event)
        emitted.add(key)
        server._emit_notification(
            "session/activity",
            {
                "requestId": request_id,
                "event": _activity_event_to_dict(event),
            },
        )

    def on_turn_event(event: dict[str, Any]) -> None:
        signature = app_server_session_runtime_helpers.turn_event_signature(event)
        if signature in emitted_turn_event_signatures:
            return
        emitted_turn_event_signatures.add(signature)
        backfill_signature = app_server_session_runtime_helpers.turn_event_backfill_signature(event)
        emitted_turn_event_backfill_counts[backfill_signature] = (
            int(emitted_turn_event_backfill_counts.get(backfill_signature) or 0) + 1
        )
        server._emit_notification(
            "session/turn_event",
            {
                "requestId": request_id,
                "event": dict(event),
            },
        )

    with app_server_session_runtime_helpers.temporary_activity_callback(server.runtime, on_activity):
        with app_server_session_runtime_helpers.temporary_turn_event_callback(server.runtime, on_turn_event):
            with app_server_session_runtime_helpers.temporary_request_user_input_handler(
                server.runtime,
                server._make_request_user_input_handler(request_id=request_id),
                replace_only_when_missing=True,
            ):
                response = server.runtime.handle_prompt(prompt)

    for event in response.activity_events:
        key = activity_dedupe_key(event)
        if key in emitted:
            continue
        server._emit_notification(
            "session/activity",
            {
                "requestId": request_id,
                "event": _activity_event_to_dict(event),
            },
        )
    for turn_event in list(response.turn_events or prompt_response_turn_events(response)):
        if not isinstance(turn_event, dict):
            continue
        signature = app_server_session_runtime_helpers.turn_event_backfill_signature(turn_event)
        remaining = int(emitted_turn_event_backfill_counts.get(signature) or 0)
        if remaining > 0:
            emitted_turn_event_backfill_counts[signature] = remaining - 1
            continue
        server._emit_notification(
            "session/turn_event",
            {
                "requestId": request_id,
                "event": dict(turn_event),
            },
        )
    return response
