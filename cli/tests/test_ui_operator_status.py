from __future__ import annotations

import json
import unittest

from textual.widgets import Static

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.ui import status_controller_hint_runtime
from cli.agent_cli.ui import status_controller_operator_runtime as operator_runtime
from cli.agent_cli.ui import status_controller_runtime
from cli.agent_cli.ui import transcript_history_runtime
from cli.agent_cli.ui.transcript_history import TranscriptEntry


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


class DelegatedWorkflowRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        event = ToolEvent(
            name="agent_workflow",
            ok=True,
            summary="workflow_state=queued",
            payload={
                "agent_id": "ag123",
                "role": "teammate",
                "status": "queued",
                "workflow_state": "queued",
                "scheduler_reason": "waiting for slot",
                "completion_state": "pending",
                "adoption_expectation": "resume_agent_to_continue",
                "adopted": False,
            },
        )
        return PromptResponse(
            user_text=text,
            assistant_text="delegated workflow\nagent_id=ag123\nstatus=queued\nscheduler_reason=waiting for slot",
            tool_events=[event],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class DelegatedWorkflowStateRuntime(_BaseRuntime):
    def __init__(self, *, payload: dict[str, object], assistant_text: str) -> None:
        super().__init__()
        self._payload = dict(payload)
        self._assistant_text = assistant_text

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        event = ToolEvent(
            name="agent_workflow",
            ok=True,
            summary=f"workflow_state={self._payload.get('workflow_state', '-')}",
            payload=dict(self._payload),
        )
        return PromptResponse(
            user_text=text,
            assistant_text=self._assistant_text,
            tool_events=[event],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class BackgroundTaskStatusRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "background task status\n"
                "task_id=bg123\n"
                "status=completed\n"
                "terminal_state=completed\n"
                "final_apply_state=pending\n"
                "summary=review ready\n"
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class BackgroundTaskLifecycleRuntime(_BaseRuntime):
    def __init__(self, *, assistant_text: str) -> None:
        super().__init__()
        self._assistant_text = assistant_text

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=self._assistant_text,
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class ExecCommandBackgroundRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        event = ToolEvent(
            name="exec_command",
            ok=True,
            summary="exec_command running sh_bg_1",
            payload={
                "task_id": "sh_bg_1",
                "status": "started",
                "workflow_state": "running",
                "completion_state": "pending",
                "notification_state": "pending",
                "summary": "background shell running",
            },
        )
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "Process running with session ID sh_bg_1\n"
                "Background task ID sh_bg_1\n"
                "Use write_stdin sh_bg_1 to poll for completion or send input"
            ),
            tool_events=[event],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class WriteStdinAdoptedRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        event = ToolEvent(
            name="write_stdin",
            ok=True,
            summary="write_stdin completed",
            payload={
                "task_id": "sh_bg_1",
                "status": "completed",
                "workflow_state": "completed",
                "completion_state": "adopted",
                "result_state": "adopted",
                "notification_state": "foreground_adopted",
                "adopted": True,
                "summary": "background shell result adopted",
            },
        )
        return PromptResponse(
            user_text=text,
            assistant_text="done",
            tool_events=[event],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class BackgroundTaskStateRuntime(_BaseRuntime):
    def __init__(self, *, payload: dict[str, object], assistant_text: str) -> None:
        super().__init__()
        self._payload = dict(payload)
        self._assistant_text = assistant_text

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        event = ToolEvent(
            name="background_task_status",
            ok=True,
            summary=f"status={self._payload.get('status', '-')}",
            payload=dict(self._payload),
        )
        return PromptResponse(
            user_text=text,
            assistant_text=self._assistant_text,
            tool_events=[event],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class BackgroundTaskPolicyRuntime(_BaseRuntime):
    def __init__(self, *, command_policies: list[dict[str, object]]) -> None:
        super().__init__()
        self._command_policies = list(command_policies)

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "background task status\n"
                "task_id=bg_policy\n"
                "status=completed\n"
                "terminal_state=completed\n"
                f"command_policies={json.dumps(self._command_policies, ensure_ascii=False)}\n"
                "summary=policy projected\n"
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class WorkflowsOverviewRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "workflows=3\n"
                "delegated_workflows=2\n"
                "background_tasks=1\n"
                "background_tasks_enabled=true\n"
                "mirrored_background_tasks=1\n"
                "- delegated | ag123 | queued | role=teammate | workflow=queued | completion=pending | next=resume_agent_to_continue | wait=blocking_join:250ms | current=step_1:running\n"
                "- delegated | ag456 | completed | role=subagent | workflow=completed | completion=adopted | terminal_state=completed\n"
                "- background | bg789 | completed | review ready | workflow=completed | terminal_state=completed | wait=status_snapshot:0ms | current=done:review patch\n"
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class WorkflowsOverviewWithOrchestrationRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "workflows=2\n"
                "delegated_workflows=1\n"
                "orchestration_runs=1\n"
                "orchestration_ready=1\n"
                "background_tasks=0\n"
                "background_tasks_enabled=true\n"
                "- delegated | ag123 | queued | role=teammate | workflow=queued | completion=pending | next=resume_agent_to_continue\n"
                "- orchestration | run_test_001 | ready | workflow=ready | phase=taskbook_ready | cards=2 | ready=1 | running=0 | blocked=1 | accepted=0 | blocker=CARD-002:intake_waiting_dependencies | current=CARD-001:ready\n"
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class WorkflowsOverviewWithReviewHintsRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "workflows=1\n"
                "delegated_workflows=0\n"
                "orchestration_runs=1\n"
                "orchestration_ready=0\n"
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
                "- orchestration | run_review_001 | blocked | workflow=blocked | phase=review_pending | "
                "latest=accept:block | reason=manual_review_required | current=CARD-002:result_ready\n"
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class WorkflowsResultContractCountersRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "workflows=4\n"
                "delegated_workflows=2\n"
                "orchestration_runs=1\n"
                "orchestration_ready=0\n"
                "orchestration_blocked=1\n"
                "orchestration_review_pending=1\n"
                "background_tasks=1\n"
                "background_tasks_enabled=true\n"
                "delegated_result_returned=1\n"
                "delegated_result_adopted=1\n"
                "delegated_result_pending_review=0\n"
                "background_result_returned=0\n"
                "background_result_adopted=0\n"
                "background_result_pending_review=1\n"
                "workflow_action_required=2\n"
                "workflow_policy_denied=1\n"
                "workflow_policy_rewrite=1\n"
                "workflow_policy_checked=3\n"
                "execution_projection_runs=4\n"
                "execution_projection_running=1\n"
                "execution_projection_completed=1\n"
                "execution_projection_failed=1\n"
                "execution_projection_cancelled=0\n"
                "execution_projection_timed_out=1\n"
                "execution_projection_terminal=3\n"
                "execution_projection_attention=2\n"
                "- delegated | ag321 | completed | role=teammate | workflow=completed | completion=adopted\n"
                "- delegated | ag654 | completed | role=subagent | workflow=completed | completion=ready_to_adopt\n"
                "- orchestration | run_projection_001 | blocked | workflow=blocked | phase=review_pending | current=CARD-010:result_ready\n"
                "- background | bg987 | completed | review ready | workflow=completed | review=pending\n"
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class WorkflowsOverviewWithReplanRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "workflows=1\n"
                "delegated_workflows=0\n"
                "orchestration_runs=1\n"
                "orchestration_ready=0\n"
                "orchestration_blocked=1\n"
                "orchestration_review_pending=1\n"
                "background_tasks=0\n"
                "background_tasks_enabled=true\n"
                "workflow_action_required=1\n"
                "- orchestration | run_replan_001 | blocked | workflow=blocked | phase=review_pending | "
                "current=CARD-009:result_failed | "
                "replan_candidates=[{\"action\":\"replan_candidate\",\"card_id\":\"CARD-009\"}] | "
                "replan_pending=[{\"card_id\":\"CARD-009\",\"pending_state\":\"awaiting_operator_action\"}] | "
                "replan_pending_card_ids=[\"CARD-009\"] | "
                "operator_actions=[{\"action\":\"replan_taskbook\",\"status\":\"pending\",\"card_id\":\"CARD-009\","
                "\"command_name\":\"/orchestrate_confirm\","
                "\"command\":\"/orchestrate_confirm <updated taskbook markdown>\"}] | "
                "replan_followup_actions=[{\"action\":\"replan_candidate\",\"scope\":\"card\","
                "\"trigger\":\"rework_escalated_after_retries\",\"card_id\":\"CARD-009\"}]\n"
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class WorkflowsOverviewWithNestedReplanPayloadRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "workflows=1\n"
                "delegated_workflows=0\n"
                "orchestration_runs=1\n"
                "orchestration_ready=0\n"
                "orchestration_blocked=1\n"
                "orchestration_review_pending=1\n"
                "background_tasks=0\n"
                "background_tasks_enabled=true\n"
                "workflow_action_required=1\n"
                "- orchestration | run_nested_001 | blocked | workflow=blocked | phase=review_pending | "
                "current=CARD-009:result_failed | "
                "progress_payload={\"replan_candidates\":[{\"action\":\"replan_candidate\",\"card_id\":\"CARD-009\"}],"
                "\"replan_pending\":[{\"card_id\":\"CARD-009\",\"pending_state\":\"awaiting_operator_action\"}],"
                "\"replan_pending_card_ids\":[\"CARD-009\"],"
                "\"operator_actions\":[{\"action\":\"replan_taskbook\",\"status\":\"pending\","
                "\"card_id\":\"CARD-009\",\"command_name\":\"/orchestrate_confirm\","
                "\"command\":\"/orchestrate_confirm <updated taskbook markdown>\"}],"
                "\"replan_followup_actions\":[{\"action\":\"replan_candidate\",\"scope\":\"card\","
                "\"trigger\":\"rework_escalated_after_retries\",\"card_id\":\"CARD-009\"}]}\n"
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class BackgroundTasksOverviewRuntime(_BaseRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                "background_tasks=4\n"
                "background_tasks_enabled=true\n"
                "background_worker_health=healthy\n"
                "background_worker_status=running\n"
                "background_worker_mode=detached\n"
                "- bg123 | running | indexing repo | type=teammate | workflow=running | review=pending | wait=blocking_join:800ms | current=running:index files\n"
                "- bg124 | completed | review ready | terminal_state=completed | review=pending | notify=posted\n"
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class BackgroundWorkerStatusRuntime(_BaseRuntime):
    def __init__(self, *, assistant_text: str | None = None) -> None:
        super().__init__()
        self._assistant_text = assistant_text

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        return PromptResponse(
            user_text=text,
            assistant_text=(
                self._assistant_text
                if self._assistant_text is not None
                else (
                    "background worker status\n"
                    "health=healthy\n"
                    "status=running\n"
                    "mode=detached\n"
                    "worker_pid=3210\n"
                )
            ),
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class RequestUserInputRuntime(_BaseRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.last_response: dict[str, object] | None = None

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        payload = {
            "questions": [
                {
                    "id": "confirm_path",
                    "header": "Confirm",
                    "question": "Proceed?",
                    "options": [
                        {"label": "Yes (Recommended)", "description": "Continue."},
                        {"label": "No", "description": "Stop."},
                    ],
                    "is_other": True,
                }
            ]
        }
        handler = getattr(self, "request_user_input_handler", None)
        response = handler(payload) if callable(handler) else None
        self.last_response = dict(response) if isinstance(response, dict) else None
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


class UiOperatorStatusTest(unittest.IsolatedAsyncioTestCase):
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

    def _assert_status_line_cleared(self, app: AgentCliApp) -> None:
        self.assertEqual(self._status_line_plain(app), "")

    async def test_status_line_summarizes_delegated_workflow_payload(self) -> None:
        app = AgentCliApp(runtime=DelegatedWorkflowRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/agent_workflow ag123", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("agent ag123 queued", transcript)
            self.assertNotIn("agent_id=ag123", transcript)
            self.assertNotIn("scheduler_reason=waiting for slot", transcript)

    async def test_request_user_input_submit_updates_transcript_projection(self) -> None:
        runtime = RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del on_cancel
            on_submit(
                {
                    "answers": {
                        "confirm_path": {"answers": ["Yes (Recommended)"]},
                    }
                }
            )
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("trigger request user input", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self.assertIsNotNone(runtime.last_response)
            assert runtime.last_response is not None
            self.assertEqual(
                runtime.last_response["answers"]["confirm_path"]["answers"],
                ["Yes (Recommended)"],
            )
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            transcript = self._transcript_text(app)
            self.assertIn("Model requested user input (1 question).", transcript)
            self.assertIn("User input confirm_path -> Yes (Recommended)", transcript)

    async def test_request_user_input_escape_cancels_pending_prompt(self) -> None:
        runtime = RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit, on_cancel
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("trigger request user input", [])
            await pilot.pause()

            status_line = self._status_line_plain(app)
            self.assertIn("waiting for user input", status_line)
            await pilot.press("escape")
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self.assertIsNone(runtime.last_response)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            transcript = self._transcript_text(app)
            self.assertIn("User cancelled input request.", transcript)

    async def test_status_line_summarizes_background_task_text_output(self) -> None:
        app = AgentCliApp(runtime=BackgroundTaskStatusRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/background_task_status bg123", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("task bg123 completed", transcript)
            self.assertIn("review pending", transcript)
            self.assertIn("final apply state pending", transcript)
            self.assertNotIn("task_id=bg123", transcript)
            self.assertNotIn("final_apply_state=pending", transcript)

    async def test_status_line_summarizes_exec_command_background_contract(self) -> None:
        app = AgentCliApp(runtime=ExecCommandBackgroundRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/exec_command 'python -i' --yield-time-ms 250 --tty", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)

    async def test_status_line_summarizes_write_stdin_foreground_adoption(self) -> None:
        app = AgentCliApp(runtime=WriteStdinAdoptedRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/write_stdin sh_bg_1 '' --yield-time-ms 250", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)

    async def test_status_line_summarizes_delegated_running_state(self) -> None:
        app = AgentCliApp(
            runtime=DelegatedWorkflowStateRuntime(
                payload={
                    "agent_id": "ag_running",
                    "role": "teammate",
                    "status": "running",
                    "workflow_state": "running",
                    "scheduler_reason": "processing child task",
                    "completion_state": "pending",
                    "adopted": False,
                },
                assistant_text=(
                    "delegated workflow\n"
                    "agent_id=ag_running\n"
                    "status=running\n"
                    "scheduler_reason=processing child task\n"
                ),
            )
        )

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/agent_workflow ag_running", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)

    async def test_status_line_summarizes_delegated_returned_and_adopted_states(self) -> None:
        returned_app = AgentCliApp(
            runtime=DelegatedWorkflowStateRuntime(
                payload={
                    "agent_id": "ag_returned",
                    "role": "teammate",
                    "status": "completed",
                    "workflow_state": "completed",
                    "completion_state": "ready_to_adopt",
                    "adoption_expectation": "resume_agent_to_continue",
                    "adopted": False,
                    "summary": "child returned result",
                },
                assistant_text=(
                    "delegated workflow\n"
                    "agent_id=ag_returned\n"
                    "status=completed\n"
                    "completion_state=ready_to_adopt\n"
                    "adopted=false\n"
                ),
            )
        )
        adopted_app = AgentCliApp(
            runtime=DelegatedWorkflowStateRuntime(
                payload={
                    "agent_id": "ag_adopted",
                    "role": "teammate",
                    "status": "completed",
                    "workflow_state": "completed",
                    "completion_state": "adopted",
                    "adopted": True,
                    "adopted_at": "2026-04-06T10:00:00+00:00",
                    "summary": "child response adopted",
                },
                assistant_text=(
                    "delegated workflow\n"
                    "agent_id=ag_adopted\n"
                    "status=completed\n"
                    "completion_state=adopted\n"
                    "adopted=true\n"
                ),
            )
        )

        async with returned_app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await returned_app._enqueue_runtime_request("/agent_workflow ag_returned", [])
            await returned_app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(returned_app)
            transcript = self._transcript_text(returned_app)
            self.assertIn("agent ag_returned · returned · review pending", transcript)

        async with adopted_app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await adopted_app._enqueue_runtime_request("/agent_workflow ag_adopted", [])
            await adopted_app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(adopted_app)
            transcript = self._transcript_text(adopted_app)
            self.assertIn("agent ag_adopted · adopted", transcript)

    async def test_status_line_prefers_structured_result_state_over_conflicting_text(self) -> None:
        app = AgentCliApp(
            runtime=DelegatedWorkflowStateRuntime(
                payload={
                    "agent_id": "ag_structured",
                    "role": "teammate",
                    "status": "completed",
                    "workflow_state": "completed",
                    "result_state": "adopted",
                },
                assistant_text=(
                    "delegated workflow\n"
                    "agent_id=ag_structured\n"
                    "status=completed\n"
                    "completion_state=ready_to_adopt\n"
                    "adopted=false\n"
                ),
            )
        )

        async with app.run_test() as pilot:
            await pilot.resize_terminal(140, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/agent_workflow ag_structured", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)

    async def test_status_line_prefers_structured_shell_background_adoption_over_conflicting_text(self) -> None:
        app = AgentCliApp(
            runtime=BackgroundTaskStateRuntime(
                payload={
                    "task_id": "sh_bg_structured",
                    "status": "completed",
                    "workflow_state": "completed",
                    "result_state": "adopted",
                    "summary": "background shell result adopted",
                },
                assistant_text=(
                    "background task status\n"
                    "task_id=sh_bg_structured\n"
                    "status=completed\n"
                    "completion_state=ready_to_adopt\n"
                    "adopted=false\n"
                    "adoption_expectation=resume_agent_to_continue\n"
                    "summary=background shell result adopted\n"
                ),
            )
        )

        async with app.run_test() as pilot:
            await pilot.resize_terminal(160, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/background_task_status sh_bg_structured", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)

    async def test_status_line_prefers_structured_final_apply_review_over_conflicting_text(self) -> None:
        app = AgentCliApp(
            runtime=BackgroundTaskStateRuntime(
                payload={
                    "task_id": "bg_review_blk",
                    "status": "completed",
                    "workflow_state": "completed",
                    "result_state": "pending_review",
                    "final_apply_state": "blocked",
                    "summary": "manual review blocked by policy",
                },
                assistant_text=(
                    "background task status\n"
                    "task_id=bg_review_blk\n"
                    "status=completed\n"
                    "result_state=pending_review\n"
                    "final_apply_state=pending\n"
                    "summary=manual review blocked by policy\n"
                ),
            )
        )

        async with app.run_test() as pilot:
            await pilot.resize_terminal(180, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/background_task_status bg_review_blk", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)

    async def test_status_and_transcript_surface_background_review_blocked(self) -> None:
        app = AgentCliApp(
            runtime=BackgroundTaskStateRuntime(
                payload={
                    "task_id": "bg_blocked",
                    "status": "completed",
                    "workflow_state": "completed",
                    "result_state": "pending_review",
                    "final_apply_state": "blocked",
                    "summary": "manual review blocked by policy",
                },
                assistant_text=(
                    "background task status\n"
                    "task_id=bg_blocked\n"
                    "status=completed\n"
                    "result_state=pending_review\n"
                    "final_apply_state=blocked\n"
                    "summary=manual review blocked by policy\n"
                ),
            )
        )

        async with app.run_test() as pilot:
            await pilot.resize_terminal(180, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/background_task_status bg_blocked", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("task bg_blocked · returned · review blocked", transcript)

    async def test_status_line_summarizes_background_returned_timed_out_and_failed_states(self) -> None:
        returned_app = AgentCliApp(
            runtime=BackgroundTaskLifecycleRuntime(
                assistant_text=(
                    "background task status\n"
                    "task_id=bg_returned\n"
                    "status=completed\n"
                    "completion_state=ready_to_adopt\n"
                    "adopted=false\n"
                    "adoption_expectation=resume_agent_to_continue\n"
                    "summary=background result ready\n"
                )
            )
        )
        timed_out_app = AgentCliApp(
            runtime=BackgroundTaskLifecycleRuntime(
                assistant_text=(
                    "background task status\n"
                    "task_id=bg_timeout\n"
                    "status=failed\n"
                    "terminal_state=timed_out\n"
                    "timed_out=true\n"
                    "summary=background teammate timed out\n"
                )
            )
        )
        failed_app = AgentCliApp(
            runtime=BackgroundTaskLifecycleRuntime(
                assistant_text=(
                    "background task status\n"
                    "task_id=bg_failed\n"
                    "status=failed\n"
                    "terminal_state=failed\n"
                    "summary=background teammate failed\n"
                )
            )
        )

        async with returned_app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await returned_app._enqueue_runtime_request("/background_task_status bg_returned", [])
            await returned_app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(returned_app)

        async with timed_out_app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await timed_out_app._enqueue_runtime_request("/background_task_status bg_timeout", [])
            await timed_out_app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(timed_out_app)

        async with failed_app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await failed_app._enqueue_runtime_request("/background_task_status bg_failed", [])
            await failed_app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(failed_app)

    async def test_status_line_summarizes_background_policy_rewrite(self) -> None:
        app = AgentCliApp(
            runtime=BackgroundTaskPolicyRuntime(
                command_policies=[
                    {
                        "command": "pytest -q tests/test_demo.py",
                        "effective_command": "python /tmp/lock.py -- pytest -q tests/test_demo.py",
                        "policy_denied": False,
                    }
                ]
            )
        )
        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/background_task_status bg_policy", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("policy rewrite", transcript)
            self.assertIn("python /tmp/lock.py", transcript)

    async def test_status_line_summarizes_background_policy_denied(self) -> None:
        app = AgentCliApp(
            runtime=BackgroundTaskPolicyRuntime(
                command_policies=[
                    {
                        "command": "rm -rf /tmp/demo",
                        "effective_command": "",
                        "policy_denied": True,
                    }
                ]
            )
        )
        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/background_task_status bg_policy", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("policy denied", transcript)
            self.assertIn("rm -rf /tmp/demo", transcript)

    async def test_status_line_surfaces_tenant_scope_profile_for_default_and_isolated(self) -> None:
        def _boolish(value: object) -> bool | None:
            if isinstance(value, bool):
                return value
            text = str(value or "").strip().lower()
            if text in {"true", "1", "yes", "on"}:
                return True
            if text in {"false", "0", "no", "off"}:
                return False
            return None

        default_hint = status_controller_hint_runtime.build_operator_surface_hint(
            {
                "task_id": "bg_default_scope",
                "status": "running",
                "tenant_id": "default",
                "workspace_scope": "default",
                "tenant_scope_profile": "default",
            },
            width=200,
            short_fn=lambda text, _: text,
            crop_one_line_fn=lambda text, _: text,
            tool_label_fn=lambda text: text,
            boolish_status_fn=_boolish,
        )
        isolated_hint = status_controller_hint_runtime.build_operator_surface_hint(
            {
                "task_id": "bg_isolated_scope",
                "status": "running",
                "tenant_id": "tenant_a",
                "workspace_scope": "workspace_x",
                "tenant_scope_profile": "isolated",
            },
            width=200,
            short_fn=lambda text, _: text,
            crop_one_line_fn=lambda text, _: text,
            tool_label_fn=lambda text: text,
            boolish_status_fn=_boolish,
        )

        self.assertIn("task bg_default_scope", default_hint)
        self.assertIn("scope default", default_hint)
        self.assertIn("task bg_isolated_scope", isolated_hint)
        self.assertIn("scope isolated", isolated_hint)

    async def test_status_line_summarizes_workflows_overview(self) -> None:
        app = AgentCliApp(runtime=WorkflowsOverviewRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/workflows", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("workflows 3 · delegated 2 · background 1", transcript)
            self.assertIn("delegated ag123 queued", transcript)
            self.assertIn("background bg789 completed", transcript)
            self.assertIn("wait blocking_join:250ms", transcript)
            self.assertNotIn("delegated_workflows=2", transcript)

    async def test_status_line_summarizes_background_tasks_overview(self) -> None:
        app = AgentCliApp(runtime=BackgroundTasksOverviewRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/background_tasks", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("background tasks 4 · worker healthy/running · mode detached", transcript)
            self.assertIn("task bg123 running", transcript)
            self.assertIn("review pending", transcript)
            self.assertIn("wait blocking_join:800ms", transcript)
            self.assertNotIn("background_worker_health=healthy", transcript)

    async def test_status_line_summarizes_workflows_with_orchestration(self) -> None:
        app = AgentCliApp(runtime=WorkflowsOverviewWithOrchestrationRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/workflows", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("workflows 2 · delegated 1 · orchestration 1 · ready 1 · background 0", transcript)
            self.assertIn("orchestration run_test_001 ready", transcript)
            self.assertIn("phase taskbook_ready", transcript)
            self.assertIn("blocked 1", transcript)
            self.assertIn("current CARD-001:ready", transcript)

    async def test_status_line_summarizes_workflows_orchestration_review_hints(self) -> None:
        app = AgentCliApp(runtime=WorkflowsOverviewWithReviewHintsRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(220, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/workflows", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("workflows 1", transcript)
            self.assertIn("orchestration 1", transcript)
            self.assertIn("review pending 1", transcript)
            self.assertIn("blocked 1", transcript)
            self.assertIn("action required 1", transcript)
            self.assertIn("latest accept:block", transcript)
            self.assertIn("review manual review required", transcript)
            self.assertIn("current CARD-002:result ready", transcript)

    async def test_status_line_summarizes_workflows_result_contract_counters(self) -> None:
        app = AgentCliApp(runtime=WorkflowsResultContractCountersRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(220, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/workflows", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("result returned 1", transcript)
            self.assertIn("result adopted 1", transcript)
            self.assertIn("review pending 2", transcript)
            self.assertIn("blocked 1", transcript)
            self.assertIn("action required 2", transcript)
            self.assertIn("policy denied 1", transcript)
            self.assertIn("policy rewrite 1", transcript)
            self.assertIn("exec runs 4", transcript)
            self.assertIn("exec attention 2", transcript)

    async def test_status_line_summarizes_workflows_replan_operator_surface(self) -> None:
        app = AgentCliApp(runtime=WorkflowsOverviewWithReplanRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(280, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/workflows", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)

            transcript = self._transcript_text(app)
            self.assertIn("orchestration run_replan_001 blocked", transcript)
            self.assertIn("replan candidates 1", transcript)
            self.assertIn("replan pending 1", transcript)
            self.assertIn("replan cards CARD-009", transcript)
            self.assertIn("operator actions 1", transcript)
            self.assertIn("operator next /orchestrate_confirm", transcript)
            self.assertIn("replan followup 1", transcript)
            self.assertIn("replan scope card", transcript)
            self.assertIn("replan trigger rework_escalated_after_retries", transcript)

    async def test_status_line_summarizes_workflows_nested_replan_operator_payload_surface(self) -> None:
        app = AgentCliApp(runtime=WorkflowsOverviewWithNestedReplanPayloadRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(280, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/workflows", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)

            transcript = self._transcript_text(app)
            self.assertIn("orchestration run_nested_001 blocked", transcript)
            self.assertIn("replan candidates 1", transcript)
            self.assertIn("replan pending 1", transcript)
            self.assertIn("replan cards CARD-009", transcript)
            self.assertIn("operator actions 1", transcript)
            self.assertIn("operator next /orchestrate_confirm", transcript)
            self.assertIn("replan followup 1", transcript)
            self.assertIn("replan scope card", transcript)
            self.assertIn("replan trigger rework_escalated_after_retries", transcript)

    async def test_status_line_summarizes_background_worker_status(self) -> None:
        app = AgentCliApp(runtime=BackgroundWorkerStatusRuntime())

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await app._enqueue_runtime_request("/background_worker_status", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(app)
            transcript = self._transcript_text(app)
            self.assertIn("worker · healthy · running · mode detached · pid 3210", transcript)
            self.assertNotIn("health=healthy", transcript)

    async def test_status_line_summarizes_background_worker_supervision_states(self) -> None:
        stale_mismatch_app = AgentCliApp(
            runtime=BackgroundWorkerStatusRuntime(
                assistant_text=(
                    "background worker status\n"
                    "health=stale\n"
                    "status=running\n"
                    "mode=detached\n"
                    "worker_pid=4567\n"
                    "worker_code_version=sig:old\n"
                    "current_worker_code_version=sig:new\n"
                    "worker_code_version_match=false\n"
                    "restart_required=true\n"
                    "active_task_id=bg_task_123\n"
                    "active_task_type=teammate\n"
                    "stop_reason=worker_stop_timeout\n"
                )
            )
        )
        stopped_app = AgentCliApp(
            runtime=BackgroundWorkerStatusRuntime(
                assistant_text=(
                    "background worker status\n"
                    "health=stopped\n"
                    "status=stopped\n"
                    "mode=detached\n"
                    "worker_pid=4567\n"
                    "stop_reason=worker_stopped\n"
                )
            )
        )

        async with stale_mismatch_app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await stale_mismatch_app._enqueue_runtime_request("/background_worker_status", [])
            await stale_mismatch_app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(stale_mismatch_app)

        async with stopped_app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            await stopped_app._enqueue_runtime_request("/background_worker_status", [])
            await stopped_app._wait_for_runtime_idle()
            await pilot.pause()

            self._assert_status_line_cleared(stopped_app)


class OperatorStatusHintHelperSpec(unittest.TestCase):
    @staticmethod
    def _boolish(value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
        return None

    @staticmethod
    def _operator_status(response: PromptResponse) -> dict[str, str]:
        return status_controller_runtime.operator_status_from_response(
            response,
            operator_command_name_fn=status_controller_runtime.operator_command_name,
            key_value_lines_fn=status_controller_runtime.key_value_lines,
            operator_status_from_mapping_fn=status_controller_runtime.operator_status_from_mapping,
            operator_status_from_text_fn=status_controller_runtime.operator_status_from_text,
            operator_hint_from_command_fn=lambda command_name, key_values, assistant_text: status_controller_hint_runtime.operator_hint_from_command(
                command_name,
                key_values=key_values,
                assistant_text=assistant_text,
                normalized_count_fn=status_controller_runtime.normalized_count,
                tool_label_fn=lambda text: text,
                flag_label_fn=lambda text: text,
            ),
        )

    def test_build_operator_surface_hint_prefers_operator_hint_when_no_structured_subject(self) -> None:
        hint = status_controller_hint_runtime.build_operator_surface_hint(
            {
                "operator_hint_text": "queued: waiting for runtime slot",
                "status": "",
                "task_id": "",
                "agent_id": "",
                "role": "",
            },
            width=160,
            short_fn=lambda text, _: text,
            crop_one_line_fn=lambda text, _: text,
            tool_label_fn=lambda text: text,
            boolish_status_fn=self._boolish,
        )

        self.assertEqual(hint, "• queued: waiting for runtime slot")

    def test_build_operator_surface_hint_applies_crop_in_operator_hint_fallback_path(self) -> None:
        crop_calls: list[tuple[str, int]] = []

        def _crop(text: str, width: int) -> str:
            crop_calls.append((text, width))
            return "cropped-hint"

        hint = status_controller_hint_runtime.build_operator_surface_hint(
            {
                "operator_hint_text": "queued: waiting for runtime slot",
                "status": "",
                "task_id": "",
                "agent_id": "",
                "role": "",
            },
            width=9,
            short_fn=lambda text, _: text,
            crop_one_line_fn=_crop,
            tool_label_fn=lambda text: text,
            boolish_status_fn=self._boolish,
        )

        self.assertEqual(hint, "cropped-hint")
        self.assertEqual(crop_calls, [("• queued: waiting for runtime slot", 9)])

    def test_build_operator_surface_hint_prefers_structured_subject_over_operator_hint_text(self) -> None:
        hint = status_controller_hint_runtime.build_operator_surface_hint(
            {
                "operator_hint_text": "legacy fallback hint should be ignored",
                "task_id": "bg123",
                "status": "running",
                "summary": "indexing files",
            },
            width=200,
            short_fn=lambda text, _: text,
            crop_one_line_fn=lambda text, _: text,
            tool_label_fn=lambda text: text,
            boolish_status_fn=self._boolish,
        )

        self.assertIn("task bg123", hint)
        self.assertIn("running", hint)
        self.assertIn("indexing files", hint)
        self.assertNotIn("legacy fallback hint should be ignored", hint)

    def test_operator_status_ignores_generic_non_operator_payload_status(self) -> None:
        response = PromptResponse(
            user_text="plain prompt",
            assistant_text="done",
            tool_events=[
                ToolEvent(
                    name="plugin_install",
                    ok=True,
                    summary="done",
                    payload={"status": "ok", "summary": "done"},
                )
            ],
        )

        status = self._operator_status(response)
        hint = status_controller_hint_runtime.build_operator_surface_hint(
            status,
            width=200,
            short_fn=lambda text, _: text,
            crop_one_line_fn=lambda text, _: text,
            tool_label_fn=lambda text: text,
            boolish_status_fn=self._boolish,
        )

        self.assertEqual(status, {})
        self.assertEqual(hint, "")

    def test_operator_status_keeps_structured_non_operator_payloads(self) -> None:
        response = PromptResponse(
            user_text="plain prompt",
            assistant_text="done",
            tool_events=[
                ToolEvent(
                    name="status_snapshot",
                    ok=True,
                    summary="indexing files",
                    payload={
                        "task_id": "bg123",
                        "status": "running",
                        "terminal_state": "running",
                        "summary": "indexing files",
                    },
                )
            ],
        )

        status = self._operator_status(response)
        hint = status_controller_hint_runtime.build_operator_surface_hint(
            status,
            width=200,
            short_fn=lambda text, _: text,
            crop_one_line_fn=lambda text, _: text,
            tool_label_fn=lambda text: text,
            boolish_status_fn=self._boolish,
        )

        self.assertEqual(status.get("task_id"), "bg123")
        self.assertEqual(status.get("status"), "running")
        self.assertEqual(status.get("terminal_state"), "running")
        self.assertIn("task bg123", hint)
        self.assertIn("running", hint)
        self.assertIn("indexing files", hint)

    def test_operator_status_hint_prefers_structured_teammate_adoption_over_conflicting_text(self) -> None:
        response = PromptResponse(
            user_text="/agent_workflow ag_structured",
            assistant_text=(
                "delegated workflow\n"
                "agent_id=ag_structured\n"
                "status=completed\n"
                "completion_state=ready_to_adopt\n"
                "adopted=false\n"
            ),
            tool_events=[
                ToolEvent(
                    name="agent_workflow",
                    ok=True,
                    summary="workflow_state=completed",
                    payload={
                        "agent_id": "ag_structured",
                        "status": "completed",
                        "workflow_state": "completed",
                        "result_state": "adopted",
                    },
                )
            ],
        )

        status = self._operator_status(response)
        self.assertEqual(status.get("result_state"), "adopted")
        self.assertIn("adopted", status.get("operator_hint_text", ""))
        self.assertNotIn("returned", status.get("operator_hint_text", ""))

    def test_operator_status_hint_prefers_structured_shell_adoption_over_conflicting_text(self) -> None:
        response = PromptResponse(
            user_text="/background_task_status sh_bg_structured",
            assistant_text=(
                "background task status\n"
                "task_id=sh_bg_structured\n"
                "status=completed\n"
                "completion_state=ready_to_adopt\n"
                "adopted=false\n"
                "adoption_expectation=resume_agent_to_continue\n"
                "summary=background shell result adopted\n"
            ),
            tool_events=[
                ToolEvent(
                    name="background_task_status",
                    ok=True,
                    summary="status=completed",
                    payload={
                        "task_id": "sh_bg_structured",
                        "status": "completed",
                        "workflow_state": "completed",
                        "result_state": "adopted",
                        "summary": "background shell result adopted",
                    },
                )
            ],
        )

        status = self._operator_status(response)
        self.assertEqual(status.get("result_state"), "adopted")
        self.assertIn("adopted", status.get("operator_hint_text", ""))
        self.assertNotIn("ready to adopt", status.get("operator_hint_text", ""))
        self.assertNotIn("next resume agent to continue", status.get("operator_hint_text", ""))

    def test_operator_status_hint_prefers_structured_final_apply_review_over_conflicting_text(self) -> None:
        response = PromptResponse(
            user_text="/background_task_status bg_review_structured",
            assistant_text=(
                "background task status\n"
                "task_id=bg_review_structured\n"
                "status=completed\n"
                "result_state=pending_review\n"
                "final_apply_state=pending\n"
                "summary=manual review blocked by policy\n"
            ),
            tool_events=[
                ToolEvent(
                    name="background_task_status",
                    ok=True,
                    summary="status=completed",
                    payload={
                        "task_id": "bg_review_structured",
                        "status": "completed",
                        "workflow_state": "completed",
                        "result_state": "pending_review",
                        "final_apply_state": "blocked",
                        "summary": "manual review blocked by policy",
                    },
                )
            ],
        )

        status = self._operator_status(response)
        self.assertEqual(status.get("final_apply_state"), "blocked")
        self.assertIn("review blocked", status.get("operator_hint_text", ""))
        self.assertNotIn("review pending", status.get("operator_hint_text", ""))

    def test_operator_status_surface_snapshot_exposes_stable_benchmark_evidence_fields(self) -> None:
        cases = (
            (
                "teammate_returned_review_pending",
                PromptResponse(
                    user_text="/agent_workflow ag_returned_structured",
                    assistant_text=(
                        "delegated workflow\n"
                        "agent_id=ag_returned_structured\n"
                        "status=completed\n"
                        "completion_state=adopted\n"
                        "adopted=true\n"
                    ),
                    tool_events=[
                        ToolEvent(
                            name="agent_workflow",
                            ok=True,
                            summary="workflow_state=completed",
                            payload={
                                "agent_id": "ag_returned_structured",
                                "role": "teammate",
                                "status": "completed",
                                "workflow_state": "completed",
                                "completion_state": "ready_to_adopt",
                                "adopted": False,
                                "summary": "child returned result",
                            },
                        )
                    ],
                ),
                {
                    "operator_evidence_subject_kind": "agent",
                    "operator_evidence_subject_id": "ag_returned_structured",
                    "operator_evidence_lifecycle_state": "returned",
                    "operator_evidence_review_state": "review_pending",
                    "operator_evidence_state_source": "structured",
                    "operator_evidence_subject_source": "structured",
                },
            ),
            (
                "shell_adopted",
                PromptResponse(
                    user_text="/background_task_status sh_bg_structured",
                    assistant_text=(
                        "background task status\n"
                        "task_id=sh_bg_structured\n"
                        "status=completed\n"
                        "completion_state=ready_to_adopt\n"
                        "adopted=false\n"
                        "adoption_expectation=resume_agent_to_continue\n"
                    ),
                    tool_events=[
                        ToolEvent(
                            name="background_task_status",
                            ok=True,
                            summary="status=completed",
                            payload={
                                "task_id": "sh_bg_structured",
                                "status": "completed",
                                "workflow_state": "completed",
                                "result_state": "adopted",
                                "summary": "background shell result adopted",
                            },
                        )
                    ],
                ),
                {
                    "operator_evidence_subject_kind": "task",
                    "operator_evidence_subject_id": "sh_bg_structured",
                    "operator_evidence_lifecycle_state": "adopted",
                    "operator_evidence_review_state": "",
                    "operator_evidence_state_source": "structured",
                    "operator_evidence_subject_source": "structured",
                },
            ),
            (
                "final_apply_review_blocked",
                PromptResponse(
                    user_text="/background_task_status bg_review_structured",
                    assistant_text=(
                        "background task status\n"
                        "task_id=bg_review_structured\n"
                        "status=completed\n"
                        "result_state=pending_review\n"
                        "final_apply_state=pending\n"
                    ),
                    tool_events=[
                        ToolEvent(
                            name="background_task_status",
                            ok=True,
                            summary="status=completed",
                            payload={
                                "task_id": "bg_review_structured",
                                "status": "completed",
                                "workflow_state": "completed",
                                "result_state": "pending_review",
                                "final_apply_state": "blocked",
                                "summary": "manual review blocked by policy",
                            },
                        )
                    ],
                ),
                {
                    "operator_evidence_subject_kind": "task",
                    "operator_evidence_subject_id": "bg_review_structured",
                    "operator_evidence_lifecycle_state": "returned",
                    "operator_evidence_review_state": "blocked",
                    "operator_evidence_state_source": "structured",
                    "operator_evidence_subject_source": "structured",
                },
            ),
        )

        for label, response, expected in cases:
            with self.subTest(label=label):
                status = self._operator_status(response)
                for key in operator_runtime.OPERATOR_EVIDENCE_KEYS:
                    self.assertEqual(status.get(key, ""), expected.get(key, ""))

    def test_assistant_message_entry_compacts_single_operator_projection_summary(self) -> None:
        entry = transcript_history_runtime.assistant_message_entry(
            TranscriptEntry,
            content=(
                "task bg123 · completed · review pending · review ready\n"
                "task bg123 completed · terminal state completed · final apply state pending · review ready"
            ),
            status="info",
            format_transcript_block_fn=lambda text, first_prefix, continuation_prefix: [
                f"{first_prefix}{line}" if index == 0 else f"{continuation_prefix}{line}"
                for index, line in enumerate(str(text or "").splitlines())
            ],
            transcript_message_prefix="• ",
            transcript_continuation_prefix="  ",
        )

        self.assertEqual(entry.raw_content, "task bg123 · completed · review pending · review ready")
        self.assertEqual(entry.lines, ["• task bg123 · completed · review pending · review ready"])

    def test_busy_label_for_queued_request_uses_command_mapping_then_default(self) -> None:
        translate_fn = lambda key: f"t:{key}"
        hint_keys = {"background_task_status": "status.loading_background_task"}

        mapped = status_controller_hint_runtime.busy_label_for_queued_request(
            "/background_task_status bg123",
            queued_request_busy_label_keys=hint_keys,
            translate_fn=translate_fn,
        )
        fallback_unknown = status_controller_hint_runtime.busy_label_for_queued_request(
            "/unknown_command",
            queued_request_busy_label_keys=hint_keys,
            translate_fn=translate_fn,
        )
        fallback_non_command = status_controller_hint_runtime.busy_label_for_queued_request(
            "plain prompt",
            queued_request_busy_label_keys=hint_keys,
            translate_fn=translate_fn,
        )

        self.assertEqual(mapped, "t:status.loading_background_task")
        self.assertEqual(fallback_unknown, "t:status.working")
        self.assertEqual(fallback_non_command, "t:status.working")

    def test_pending_approval_count_normalizes_invalid_or_negative_values(self) -> None:
        self.assertEqual(status_controller_hint_runtime.pending_approval_count({}), 0)
        self.assertEqual(status_controller_hint_runtime.pending_approval_count({"pending_approvals": "3"}), 3)
        self.assertEqual(status_controller_hint_runtime.pending_approval_count({"pending_approvals": " -2 "}), 0)
        self.assertEqual(status_controller_hint_runtime.pending_approval_count({"pending_approvals": "nan"}), 0)
