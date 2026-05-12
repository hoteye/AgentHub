from __future__ import annotations

import unittest

from textual.widgets import Static

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse


class _OperatorSurfaceRuntime:
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
        command = str(text or "").strip()
        if command.startswith("/workflows"):
            assistant_text = (
                "workflows=2\n"
                "delegated_workflows=1\n"
                "orchestration_runs=1\n"
                "orchestration_ready=0\n"
                "orchestration_running=0\n"
                "orchestration_blocked=1\n"
                "orchestration_review_pending=1\n"
                "background_tasks=0\n"
                "background_tasks_enabled=true\n"
                "delegated_result_returned=0\n"
                "delegated_result_adopted=0\n"
                "delegated_result_pending_review=0\n"
                "background_result_returned=0\n"
                "background_result_adopted=0\n"
                "background_result_pending_review=0\n"
                "workflow_action_required=1\n"
                "execution_projection_runs=3\n"
                "execution_projection_running=1\n"
                "execution_projection_completed=1\n"
                "execution_projection_failed=1\n"
                "execution_projection_cancelled=0\n"
                "execution_projection_timed_out=0\n"
                "execution_projection_terminal=2\n"
                "execution_projection_attention=1\n"
                "workflow_policy_denied=1\n"
                "- delegated | ag_smoke_001 | queued | role=teammate | workflow=queued | completion=pending | next=resume_agent_to_continue\n"
                "- orchestration | run_smoke_001 | blocked | workflow=blocked | phase=review_pending | cards=3 | ready=0 | running=0 | blocked=1 | accepted=2 | latest_acceptance=CARD-003:block | review_reason=CARD-003:manual_review_required | policy=denied | policy_reason=test_scope_required | current=CARD-003:result_ready | replan_candidates=[{\"action\":\"replan_candidate\",\"card_id\":\"CARD-003\"}] | replan_pending=[{\"card_id\":\"CARD-003\",\"pending_state\":\"awaiting_operator_action\"}] | replan_pending_card_ids=[\"CARD-003\"] | operator_actions=[{\"action\":\"replan_taskbook\",\"status\":\"pending\",\"card_id\":\"CARD-003\",\"command_name\":\"/orchestrate_confirm\",\"command\":\"/orchestrate_confirm <updated taskbook markdown>\"}]\n"
            )
        elif command.startswith("/background_worker_status"):
            assistant_text = (
                "background worker status\n"
                "health=stale\n"
                "status=running\n"
                "mode=detached\n"
                "worker_pid=4567\n"
                "worker_code_version=sig:old\n"
                "current_worker_code_version=sig:new\n"
                "worker_code_version_match=false\n"
                "restart_required=true\n"
                "active_task_id=bg_smoke_001\n"
                "active_task_type=teammate\n"
                "stop_reason=worker_stop_timeout\n"
            )
        else:
            assistant_text = "unsupported"
        return PromptResponse(
            user_text=command,
            assistant_text=assistant_text,
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class UiOperatorSurfaceSmokeTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _status_line_plain(app: AgentCliApp) -> str:
        widget = app.query_one("#status_line", Static)
        renderable = getattr(widget, "renderable", None)
        if renderable is not None:
            return getattr(renderable, "plain", str(renderable))
        rendered = widget.render()
        return getattr(rendered, "plain", str(rendered))

    @staticmethod
    def _transcript_text(app: AgentCliApp) -> str:
        return app.query_one("#main_log").text

    async def test_operator_surface_smoke_workflows_projection_and_worker_supervision(self) -> None:
        app = AgentCliApp(runtime=_OperatorSurfaceRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(220, 24)
            await pilot.pause()

            await app._enqueue_runtime_request("/workflows --limit 5", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            transcript_after_workflows = self._transcript_text(app)
            self.assertEqual(self._status_line_plain(app), "")
            self.assertIn("workflows 2 · delegated 1 · orchestration 1 · background 0", transcript_after_workflows)
            self.assertIn("review pending 1", transcript_after_workflows)
            self.assertIn("blocked 1", transcript_after_workflows)
            self.assertIn("action required 1", transcript_after_workflows)
            self.assertIn("policy denied 1", transcript_after_workflows)
            self.assertIn("exec runs 3", transcript_after_workflows)
            self.assertIn("exec attention 1", transcript_after_workflows)
            self.assertIn("orchestration run_smoke_001 blocked", transcript_after_workflows)
            self.assertIn("phase review_pending", transcript_after_workflows)
            self.assertIn("cards 3", transcript_after_workflows)
            self.assertIn("blocked 1", transcript_after_workflows)
            self.assertIn("acceptance CARD-003:block", transcript_after_workflows)
            self.assertIn("review CARD-003:manual_review_required", transcript_after_workflows)
            self.assertIn("policy denied", transcript_after_workflows)
            self.assertIn("policy reason test_scope_required", transcript_after_workflows)
            self.assertIn("replan candidates 1", transcript_after_workflows)
            self.assertIn("replan pending 1", transcript_after_workflows)
            self.assertIn("replan cards CARD-003", transcript_after_workflows)
            self.assertIn("operator actions 1", transcript_after_workflows)
            self.assertIn("operator next /orchestrate_confirm", transcript_after_workflows)

            await app._enqueue_runtime_request("/background_worker_status", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            transcript_after_worker = self._transcript_text(app)
            self.assertEqual(self._status_line_plain(app), "")
            self.assertIn("worker · stale · running · mode detached · pid 4567", transcript_after_worker)
            self.assertIn("restart required", transcript_after_worker)
            self.assertIn("active bg smoke 001:teammate", transcript_after_worker)
            self.assertIn("stop worker stop timeout", transcript_after_worker)
