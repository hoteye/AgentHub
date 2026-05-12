from __future__ import annotations

import threading
import unittest

from cli.agent_cli import thread_store_helpers_runtime as thread_helpers
from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse, ThreadHistoryTurn, ToolEvent
from cli.agent_cli.runtime_services import prompt_turn_projection_runtime as projection
from cli.agent_cli.ui.transcript_controller import TranscriptControllerMixin


class _BaseRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "test",
                "provider_model": "test-model",
                "provider_ready": "true",
            }

    def __init__(self) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.responses: list[dict[str, object] | None] = []

    @staticmethod
    def slash_command_matches(query: str) -> list[dict[str, str]]:
        del query
        return []

    @staticmethod
    def slash_command_completion(query: str) -> str | None:
        del query
        return None

    @staticmethod
    def interrupt_active_run() -> dict[str, object]:
        return {"ok": False, "interrupted": False}


class _RequestUserInputRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        payload = _payload()
        handler = getattr(self, "request_user_input_handler", None)
        response = handler(payload) if callable(handler) else None
        self.responses.append(dict(response) if isinstance(response, dict) else None)
        event = ToolEvent(
            name="request_user_input",
            ok=bool(isinstance(response, dict)),
            summary="request_user_input completed" if isinstance(response, dict) else "request_user_input cancelled",
            payload={
                "questions": payload["questions"],
                "response": dict(response or {}) if isinstance(response, dict) else {},
            },
        )
        return PromptResponse(
            user_text=text,
            assistant_text="request completed" if isinstance(response, dict) else "request cancelled",
            tool_events=[event],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class _TranscriptProbe(TranscriptControllerMixin):
    def __init__(self) -> None:
        self.notices: list[str] = []

    def _write_system_notice(self, content: str) -> None:  # type: ignore[override]
        self.notices.append(str(content))


def _payload() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes (Recommended)", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            }
        ]
    }


class RequestUserInputPendingResumeSemanticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_request_is_cancelled_on_shutdown_and_restart_round_trip_still_works(self) -> None:
        runtime = _RequestUserInputRuntime()
        app_first = AgentCliApp(runtime=runtime)

        # Accept the presenter surface but never resolve, forcing a pending request.
        app_first._request_user_input_modal_presenter = (
            lambda *, payload, on_submit, on_cancel: bool(payload or on_submit or on_cancel)
        )
        worker_result: dict[str, object] = {}

        def _invoke_pending_handler() -> None:
            worker_result["response"] = app_first._handle_request_user_input_from_runtime(_payload())

        async with app_first.run_test() as pilot:
            await pilot.pause()
            worker = threading.Thread(target=_invoke_pending_handler)
            worker.start()
            for _ in range(60):
                await pilot.pause()
                with app_first._request_user_input_pending_lock:
                    if app_first._request_user_input_pending is not None:
                        break
            with app_first._request_user_input_pending_lock:
                self.assertIsNotNone(app_first._request_user_input_pending)
            app_first._begin_shutdown()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertIsNone(worker_result.get("response"))
            with app_first._request_user_input_pending_lock:
                self.assertIsNone(app_first._request_user_input_pending)
            self.assertEqual(app_first.status_data.get("request_user_input_waiting"), "false")
            self.assertIsNone(getattr(runtime, "request_user_input_handler", None))

        app_second = AgentCliApp(runtime=runtime)

        def _submit_presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": {"confirm_path": "Yes (Recommended)"}})
            return True

        app_second._request_user_input_modal_presenter = _submit_presenter

        async with app_second.run_test() as pilot:
            await pilot.pause()
            await app_second._enqueue_runtime_request("restart round trip", [])
            await app_second._wait_for_runtime_idle()
            await pilot.pause()
            self.assertIsInstance(runtime.responses[-1], dict)
            assert isinstance(runtime.responses[-1], dict)
            self.assertEqual(
                runtime.responses[-1]["answers"]["confirm_path"]["answers"],
                ["Yes (Recommended)"],
            )
            with app_second._request_user_input_pending_lock:
                self.assertIsNone(app_second._request_user_input_pending)
            self.assertEqual(app_second.status_data.get("request_user_input_waiting"), "false")

    async def test_replay_completed_turn_and_cancelled_turn_keep_current_summary_boundary(self) -> None:
        completed_turn = ThreadHistoryTurn(
            turn_id="turn_completed",
            timestamp="2026-04-07T00:00:00+00:00",
            user_text="completed",
            assistant_text="done",
            tool_events=[
                ToolEvent(
                    name="request_user_input",
                    ok=True,
                    summary="request_user_input completed",
                    payload={
                        "response": {
                            "answers": {
                                "confirm_path": {"answers": ["Yes (Recommended)"]},
                            }
                        }
                    },
                )
            ],
        )
        cancelled_turn = ThreadHistoryTurn(
            turn_id="turn_cancelled",
            timestamp="2026-04-07T00:01:00+00:00",
            user_text="pending cancelled",
            assistant_text="cancelled",
            tool_events=[
                ToolEvent(
                    name="request_user_input",
                    ok=False,
                    summary="request_user_input cancelled",
                    payload={},
                )
            ],
        )

        completed_restored = ThreadHistoryTurn.from_dict(completed_turn.to_dict())
        cancelled_restored = ThreadHistoryTurn.from_dict(cancelled_turn.to_dict())

        self.assertTrue(thread_helpers.turn_replay_requires_structured_tool_output(completed_restored))
        self.assertTrue(thread_helpers.turn_replay_requires_structured_tool_output(cancelled_restored))
        self.assertTrue(
            projection.turn_replay_requires_structured_tool_output(
                [event.to_dict() for event in list(completed_restored.tool_events or [])]
            )
        )
        self.assertTrue(
            projection.turn_replay_requires_structured_tool_output(
                [event.to_dict() for event in list(cancelled_restored.tool_events or [])]
            )
        )

        completed_response = PromptResponse(
            user_text=completed_restored.user_text,
            assistant_text=completed_restored.assistant_text,
            tool_events=list(completed_restored.tool_events or []),
        )
        cancelled_response = PromptResponse(
            user_text=cancelled_restored.user_text,
            assistant_text=cancelled_restored.assistant_text,
            tool_events=list(cancelled_restored.tool_events or []),
        )

        probe = _TranscriptProbe()
        probe._write_request_user_input_summary(completed_response)
        probe._write_request_user_input_summary(cancelled_response)

        self.assertTrue(any("confirm_path" in line and "Yes (Recommended)" in line for line in probe.notices))
        self.assertIn("User input request was cancelled.", probe.notices)

