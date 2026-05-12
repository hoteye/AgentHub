from __future__ import annotations

import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli import app_server_protocol_turn_flow_runtime
from cli.agent_cli.models import PromptResponse


@contextmanager
def _null_context(*_args, **_kwargs):
    yield


class _FakeServer:
    def __init__(self, *, response: PromptResponse | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self._notifications: list[dict[str, object]] = []
        self._jobs_lock = threading.Lock()
        self._jobs = {"job-turn-1": {"kind": "turn"}}
        self.runtime = SimpleNamespace(handle_prompt=self._handle_prompt)

    def _handle_prompt(self, prompt: str, *, attachments=None):
        del prompt, attachments
        if self._error is not None:
            raise self._error
        return self._response

    def _emit_notification(self, method: str, params: dict[str, object]) -> None:
        self._notifications.append({"method": method, "params": dict(params)})

    def _make_request_user_input_handler(self, *, request_id):
        return {"request_id": request_id}


class _FakeTurnHelpers:
    def __init__(self) -> None:
        self.streamed_events: list[dict[str, object]] = []
        self.raw_item_notifications: list[tuple[str, str]] = []

    def emit_turn_stream_event(
        self,
        server,
        *,
        thread_id: str,
        turn_id: str,
        event: dict[str, object],
        item_text_state: dict[str, str],
        plan_state: dict[str, str],
    ) -> None:
        del server, item_text_state, plan_state
        self.streamed_events.append({"thread_id": thread_id, "turn_id": turn_id, "event": dict(event)})

    def emit_raw_response_item_completed_notifications(
        self,
        server,
        *,
        thread_id: str,
        turn_id: str,
        response,
    ) -> None:
        del server, response
        self.raw_item_notifications.append((thread_id, turn_id))


def _session_runtime_helpers():
    return SimpleNamespace(
        turn_event_signature=lambda event: repr(sorted(dict(event).items())),
        turn_event_backfill_signature=lambda event: repr(sorted(dict(event).items())),
        temporary_turn_event_callback=_null_context,
        temporary_request_user_input_handler=_null_context,
    )


@contextmanager
def _active_turn(_turn_id: str):
    yield


def test_run_turn_start_job_logs_timeline_stages_for_successful_turn() -> None:
    server = _FakeServer(
        response=PromptResponse(
            user_text="hello",
            assistant_text="done",
            response_items=[{"type": "message", "role": "assistant"}],
            turn_events=[{"type": "turn.completed"}],
        )
    )
    turn_helpers = _FakeTurnHelpers()
    timeline_events: list[tuple[str, dict[str, object]]] = []

    with patch(
        "cli.agent_cli.app_server_protocol_turn_flow_runtime.timeline_debug_enabled",
        return_value=True,
    ), patch(
        "cli.agent_cli.app_server_protocol_turn_flow_runtime.log_timeline",
        side_effect=lambda stage, **payload: timeline_events.append((stage, payload)),
    ):
        app_server_protocol_turn_flow_runtime.run_turn_start_job(
            server,
            job_id="job-turn-1",
            request_id="req-1",
            thread_id="thread-1",
            turn_id="turn-1",
            prompt="hello",
            attachments=[],
            session_runtime_helpers=_session_runtime_helpers(),
            turn_helpers=turn_helpers,
            reference_turn_runtime_payload_fn=lambda *, turn_id, status: {"id": turn_id, "status": status},
            completed_turn_payload_from_response_fn=lambda *, turn_id, response: {
                "id": turn_id,
                "status": "completed",
                "response_items": len(list(getattr(response, "response_items", []) or [])),
            },
            failed_turn_payload_fn=lambda *, turn_id, message: {
                "id": turn_id,
                "status": "failed",
                "error": {"message": message},
            },
            prompt_response_turn_events_fn=lambda response: list(getattr(response, "turn_events", []) or []),
            active_app_server_turn_id_fn=_active_turn,
        )

    assert [item["method"] for item in server._notifications] == ["turn/started", "turn/completed"]
    assert server._notifications[-1]["params"]["turn"]["status"] == "completed"
    assert [stage for stage, _payload in timeline_events] == [
        "app_server.turn.prompt.completed",
        "app_server.turn.replay.begin",
        "app_server.turn.replay.end",
        "app_server.turn.raw_response_items.begin",
        "app_server.turn.raw_response_items.end",
        "app_server.turn.completed.emit.begin",
        "app_server.turn.completed.emit.end",
    ]
    assert timeline_events[0][1]["response_item_count"] == 1
    assert timeline_events[0][1]["turn_event_count"] == 1
    assert timeline_events[-2][1]["status"] == "completed"
    assert timeline_events[-1][1]["status"] == "completed"
    assert turn_helpers.raw_item_notifications == [("thread-1", "turn-1")]
    assert server._jobs == {}


def test_run_turn_start_job_logs_failed_timeline_stage_on_exception() -> None:
    server = _FakeServer(error=RuntimeError("boom"))
    turn_helpers = _FakeTurnHelpers()
    timeline_events: list[tuple[str, dict[str, object]]] = []

    with patch(
        "cli.agent_cli.app_server_protocol_turn_flow_runtime.timeline_debug_enabled",
        return_value=True,
    ), patch(
        "cli.agent_cli.app_server_protocol_turn_flow_runtime.log_timeline",
        side_effect=lambda stage, **payload: timeline_events.append((stage, payload)),
    ):
        app_server_protocol_turn_flow_runtime.run_turn_start_job(
            server,
            job_id="job-turn-1",
            request_id="req-1",
            thread_id="thread-1",
            turn_id="turn-1",
            prompt="hello",
            attachments=[],
            session_runtime_helpers=_session_runtime_helpers(),
            turn_helpers=turn_helpers,
            reference_turn_runtime_payload_fn=lambda *, turn_id, status: {"id": turn_id, "status": status},
            completed_turn_payload_from_response_fn=lambda *, turn_id, response: {"id": turn_id, "status": "completed"},
            failed_turn_payload_fn=lambda *, turn_id, message: {
                "id": turn_id,
                "status": "failed",
                "error": {"message": message},
            },
            prompt_response_turn_events_fn=lambda response: list(getattr(response, "turn_events", []) or []),
            active_app_server_turn_id_fn=_active_turn,
        )

    assert [item["method"] for item in server._notifications] == ["turn/started", "turn/completed"]
    assert server._notifications[-1]["params"]["turn"]["status"] == "failed"
    assert server._notifications[-1]["params"]["turn"]["error"]["message"] == "RuntimeError: boom"
    assert [stage for stage, _payload in timeline_events] == ["app_server.turn.failed"]
    assert timeline_events[0][1]["error_type"] == "RuntimeError"
    assert timeline_events[0][1]["error_text"] == "boom"
    assert turn_helpers.raw_item_notifications == []
    assert server._jobs == {}
