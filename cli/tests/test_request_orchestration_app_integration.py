from __future__ import annotations

import asyncio
import json
import threading
import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.runtime_core import run_command_text_result


class _RequestOrchestrationAppRuntime:
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
        self.request_user_input_handler = None
        self.preview_calls: list[dict[str, object]] = []
        self.create_calls: list[dict[str, object]] = []

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

    def preview_orchestration_run(
        self,
        source_text: str,
        *,
        planning_adjustments: dict[str, object] | None = None,
        relaxed_taskbook: bool = False,
    ) -> dict[str, object]:
        del relaxed_taskbook
        normalized_adjustments = dict(planning_adjustments or {})
        self.preview_calls.append(
            {
                "source_text": source_text,
                "planning_adjustments": normalized_adjustments,
            }
        )
        return {
            "preview_id": "preview_app_001",
            "objective": "拆分编排入口",
            "routing_mode": "orchestrated",
            "taskbook_version": 1,
            "card_count": 2,
            "ready_card_ids": ["CARD-001"],
            "blocked_card_ids": ["CARD-002"],
            "planning_adjustment_lines": [
                f"{key}={value}"
                for key, value in normalized_adjustments.items()
                if str(key).strip()
            ],
        }

    def create_orchestration_run(
        self,
        source_text: str,
        *,
        planning_adjustments: dict[str, object] | None = None,
        relaxed_taskbook: bool = False,
    ) -> dict[str, object]:
        del relaxed_taskbook
        normalized_adjustments = dict(planning_adjustments or {})
        self.create_calls.append(
            {
                "source_text": source_text,
                "planning_adjustments": normalized_adjustments,
            }
        )
        return {
            "run_id": "run_app_001",
            "mode": "interactive",
            "routing_mode": "orchestrated",
            "status": "created",
            "current_phase": "created",
            "taskbook_source": "preview",
            "taskbook_version": 1,
            "card_count": 2,
            "ready_card_ids": ["CARD-001"],
            "blocked_card_ids": ["CARD-002"],
            "running_card_ids": [],
            "completed_card_ids": [],
            "run_path": "/tmp/run_app_001",
            "projection_path": "/tmp/run_app_001/projection.md",
        }


class RequestOrchestrationAppIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def _wait_event(self, event: threading.Event, pilot, *, timeout: float = 8.0, label: str) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if event.is_set():
                return
            if asyncio.get_running_loop().time() >= deadline:
                self.fail(f"{label} not observed within {timeout:.1f}s")
            await pilot.pause()

    async def test_request_orchestration_preview_enters_interactive_confirmation_modal(self) -> None:
        runtime = _RequestOrchestrationAppRuntime()
        app = AgentCliApp(runtime=runtime)
        command = "/__request_orchestration " + json.dumps(
            {
                "source_text": "把大文件拆成模块并补回归测试",
                "goal": "完成编排入口改造",
                "reason": "多阶段任务",
                "needs_confirmation": True,
                "planning_adjustments": {"max_parallel_cards": 2},
            },
            ensure_ascii=True,
        )
        result_holder: dict[str, object] = {}
        command_finished = threading.Event()
        modal_seen = threading.Event()
        presented_questions: list[str] = []

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del on_cancel
            questions = list((payload or {}).get("questions") or [])
            if questions:
                presented_questions.append(str(questions[0].get("question") or ""))
            modal_seen.set()
            on_submit({"answers": {"taskbook_action": "Confirm and start"}})
            return True

        def _run_command() -> None:
            try:
                result_holder["result"] = run_command_text_result(runtime, command)
            finally:
                command_finished.set()

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            worker = threading.Thread(target=_run_command, daemon=True)
            worker.start()
            await self._wait_event(modal_seen, pilot, label="request_orchestration modal")
            await self._wait_event(command_finished, pilot, label="request_orchestration command completion")
            await pilot.pause()
            worker.join(timeout=1.0)

        result = result_holder.get("result")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(presented_questions), 1)
        self.assertIn("Taskbook preview", presented_questions[0])
        self.assertIn("max_parallel_cards=2", presented_questions[0])
        self.assertIn("orchestration confirmation accepted", result.assistant_text)
        self.assertEqual(
            runtime.create_calls,
            [
                {
                    "source_text": "把大文件拆成模块并补回归测试",
                    "planning_adjustments": {"max_parallel_cards": 2},
                }
            ],
        )
