from __future__ import annotations

import asyncio
import threading
import unittest
from dataclasses import dataclass

from unittest import mock

from cli.agent_cli.app import AgentCliApp, _PendingRequestUserInput
from cli.agent_cli.models import PromptResponse


def _payload(question_id: str) -> dict[str, object]:
    return {
        "questions": [
            {
                "id": question_id,
                "header": "Confirm",
                "question": f"Proceed for {question_id}?",
                "options": [
                    {"label": "Yes (Recommended)", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            }
        ]
    }


class _RaceRuntime:
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

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text="noop",
            tool_events=[],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


@dataclass
class _ThreadResult:
    response: dict[str, object] | None = None
    error: BaseException | None = None


class RequestUserInputThreadRaceTest(unittest.IsolatedAsyncioTestCase):
    async def _wait_for_presenter_calls(
        self,
        pilot,
        seen: list[object],
        *,
        expected: int,
        timeout: float = 8.0,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while len(seen) < expected:
            if asyncio.get_running_loop().time() >= deadline:
                self.fail(f"presenter did not receive {expected} calls in time")
            await pilot.pause()

    async def test_thread_race_rejects_second_concurrent_request_without_stranding(self) -> None:
        runtime = _RaceRuntime()
        app = AgentCliApp(runtime=runtime)
        seen: list[tuple[str, _PendingRequestUserInput | None]] = []
        created_pending: list[_PendingRequestUserInput] = []

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del on_submit, on_cancel
            question_id = str(((payload or {}).get("questions") or [{}])[0].get("id") or "")
            with app._request_user_input_pending_lock:
                current = app._request_user_input_pending
            seen.append((question_id, current))
            return True

        app._request_user_input_modal_presenter = _presenter
        results: dict[str, _ThreadResult] = {"q1": _ThreadResult(), "q2": _ThreadResult()}
        start_gate = threading.Barrier(2)

        def _invoke(question_id: str) -> None:
            try:
                start_gate.wait(timeout=2)
                results[question_id].response = app._handle_request_user_input_from_runtime(_payload(question_id))
            except BaseException as exc:  # pragma: no cover - defensive path
                results[question_id].error = exc

        def _capture_pending(*args, **kwargs):
            pending = _PendingRequestUserInput(*args, **kwargs)
            created_pending.append(pending)
            return pending

        async with app.run_test() as pilot:
            await pilot.pause()
            t1 = threading.Thread(target=_invoke, args=("q1",), daemon=True)
            t2 = threading.Thread(target=_invoke, args=("q2",), daemon=True)
            with mock.patch("cli.agent_cli.app._PendingRequestUserInput", side_effect=_capture_pending):
                t1.start()
                t2.start()

                # Single-pending semantics: second concurrent request is rejected.
                await self._wait_for_presenter_calls(pilot, seen, expected=1)
                self.assertEqual(app.status_data.get("request_user_input_waiting"), "true")
                with app._request_user_input_pending_lock:
                    current_pending = app._request_user_input_pending
                self.assertIsNotNone(current_pending)

                assert current_pending is not None
                current_question_id = str((current_pending.question_ids or ("",))[0] or "")
                app._on_request_user_input_submit({"answers": {current_question_id: current_question_id}})

                t1.join(timeout=2)
                t2.join(timeout=2)
                self.assertFalse(t1.is_alive())
                self.assertFalse(t2.is_alive())
                self.assertIsNone(results["q1"].error)
                self.assertIsNone(results["q2"].error)
                responses = [results["q1"].response, results["q2"].response]
                self.assertEqual(sum(isinstance(item, dict) for item in responses), 1)
                self.assertEqual(sum(item is None for item in responses), 1)
                self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
                with app._request_user_input_pending_lock:
                    self.assertIsNone(app._request_user_input_pending)

    async def test_followup_request_still_works_after_race_recovery(self) -> None:
        runtime = _RaceRuntime()
        app = AgentCliApp(runtime=runtime)
        seen: list[_PendingRequestUserInput] = []
        created_pending: list[_PendingRequestUserInput] = []

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit, on_cancel
            with app._request_user_input_pending_lock:
                pending = app._request_user_input_pending
            if pending is not None:
                seen.append(pending)
            return True

        app._request_user_input_modal_presenter = _presenter
        initial_results: dict[str, _ThreadResult] = {"q1": _ThreadResult(), "q2": _ThreadResult()}
        race_gate = threading.Barrier(2)

        def _invoke(result_slot: str, question_id: str) -> None:
            try:
                race_gate.wait(timeout=2)
                initial_results[result_slot].response = app._handle_request_user_input_from_runtime(
                    _payload(question_id)
                )
            except BaseException as exc:  # pragma: no cover - defensive path
                initial_results[result_slot].error = exc

        followup: _ThreadResult = _ThreadResult()

        def _invoke_followup() -> None:
            try:
                followup.response = app._handle_request_user_input_from_runtime(_payload("q3"))
            except BaseException as exc:  # pragma: no cover - defensive path
                followup.error = exc

        def _capture_pending(*args, **kwargs):
            pending = _PendingRequestUserInput(*args, **kwargs)
            created_pending.append(pending)
            return pending

        async with app.run_test() as pilot:
            await pilot.pause()
            t1 = threading.Thread(target=_invoke, args=("q1", "q1"), daemon=True)
            t2 = threading.Thread(target=_invoke, args=("q2", "q2"), daemon=True)
            with mock.patch("cli.agent_cli.app._PendingRequestUserInput", side_effect=_capture_pending):
                t1.start()
                t2.start()
                await self._wait_for_presenter_calls(pilot, seen, expected=1)

                with app._request_user_input_pending_lock:
                    active = app._request_user_input_pending
                assert active is not None
                active_id = str((active.question_ids or ("",))[0] or "")
                app._on_request_user_input_submit({"answers": {active_id: active_id}})

                t1.join(timeout=2)
                t2.join(timeout=2)
                self.assertFalse(t1.is_alive())
                self.assertFalse(t2.is_alive())
                initial_responses = [initial_results["q1"].response, initial_results["q2"].response]
                self.assertEqual(sum(isinstance(item, dict) for item in initial_responses), 1)
                self.assertEqual(sum(item is None for item in initial_responses), 1)

                t3 = threading.Thread(target=_invoke_followup, daemon=True)
                t3.start()
                await self._wait_for_presenter_calls(pilot, seen, expected=2)
                app._on_request_user_input_submit({"answers": {"q3": "Yes (Recommended)"}})
                t3.join(timeout=2)
                self.assertFalse(t3.is_alive())

                await pilot.pause()
                self.assertIsNone(initial_results["q1"].error)
                self.assertIsNone(initial_results["q2"].error)
                self.assertIsNone(followup.error)
                self.assertIsInstance(followup.response, dict)
                assert isinstance(followup.response, dict)
                self.assertEqual(
                    followup.response.get("answers", {}).get("q3", {}).get("answers"),
                    ["Yes (Recommended)"],
                )
                self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
                with app._request_user_input_pending_lock:
                    self.assertIsNone(app._request_user_input_pending)
