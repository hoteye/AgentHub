from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.orchestration import taskbook_runtime as taskbook_runtime_service
from cli.agent_cli.orchestration.taskbook_models import ComplexTaskRun, ExecutionRef, TaskCard, TaskCardState
from cli.agent_cli.orchestration.taskbook_state import (
    ComplexTaskRunStatus,
    ExecutionRefKind,
    TaskCardExecutionMode,
    TaskCardDependencyStatus,
    TaskCardKind,
    TaskCardStatus,
)
from cli.agent_cli.runtime_core import parse_args, run_command_text_result


TASKBOOK_MARKDOWN = """# Demo orchestration run

### CARD-001: Research workflow surface
- goal: research current workflow surface and summarize gaps
- owned_files: docs/research_notes.md
- acceptance_criteria: capture the workflow findings

### CARD-002: Update runtime wiring
- goal: patch runtime orchestration wiring after research completes
- owned_files: cli/agent_cli/runtime.py
- acceptance_criteria: runtime wiring updated
- depends_on: CARD-001
"""


READ_ONLY_MARKDOWN = """# Dispatch one read-only card

### CARD-001: Research command behavior
- goal: research current command behavior and summarize findings
- owned_files: docs/research_dispatch.md
- acceptance_criteria: capture findings for the command behavior
"""


READ_ONLY_CHAIN_MARKDOWN = """# Continue read-only chain

### CARD-001: Research workflow surface
- goal: research current workflow surface and summarize gaps
- owned_files: docs/research_chain_1.md
- acceptance_criteria: capture research findings

### CARD-002: Summarize workflow findings
- goal: research the next-step workflow summary
- owned_files: docs/research_chain_2.md
- acceptance_criteria: capture summary findings
- depends_on: CARD-001
"""


class _RuntimeStub:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "openai",
                "provider_model": "gpt-5.4",
                "provider_reasoning_effort": "-",
            }

    def __init__(self, root: Path) -> None:
        self.cwd = Path(root)
        self.thread_id = "thread_test"
        self.agent = self._Agent()
        self._orchestration_runtime_services_cache = None
        self._orchestration_runtime_services_cwd = ""
        self._spawn_count = 0

    @staticmethod
    def _parse_args(arg_text: str):
        return parse_args(arg_text)

    @staticmethod
    def _delegated_agent_state_snapshot():
        return []

    def create_orchestration_run(self, source_text: str) -> dict[str, object]:
        return taskbook_runtime_service.create_orchestration_run(self, source_text)

    def dispatch_orchestration_run(self, run_id: str) -> dict[str, object]:
        return taskbook_runtime_service.dispatch_orchestration_run(self, run_id)

    def progress_orchestration_run(self, run_id: str) -> dict[str, object]:
        return taskbook_runtime_service.progress_orchestration_run(self, run_id)

    def continue_orchestration_run(self, run_id: str, *, max_passes: int = 8, dispatch_ready: bool = True) -> dict[str, object]:
        return taskbook_runtime_service.continue_orchestration_run(
            self,
            run_id,
            max_passes=max_passes,
            dispatch_ready=dispatch_ready,
        )

    def apply_orchestration_card(self, run_id: str, card_id: str) -> dict[str, object]:
        return taskbook_runtime_service.apply_orchestration_card(self, run_id, card_id)

    def reject_orchestration_card(self, run_id: str, card_id: str) -> dict[str, object]:
        return taskbook_runtime_service.reject_orchestration_card(self, run_id, card_id)

    def list_orchestration_workflows(self, *, limit: int = 20) -> tuple[list[str], int]:
        return taskbook_runtime_service.list_orchestration_workflows(self, limit=limit)

    def spawn_agent_result(self, **kwargs) -> CommandExecutionResult:
        self._spawn_count += 1
        tool_event = ToolEvent(
            name="spawn_agent",
            ok=True,
            summary="spawned read-only orchestration card",
            payload={
                "agent_id": f"ag_orch_{self._spawn_count:03d}",
                "provider_name": str(kwargs.get("provider") or "openai"),
                "model": str(kwargs.get("model") or "gpt-5.4"),
            },
        )
        return CommandExecutionResult(
            assistant_text="spawned read-only orchestration card",
            tool_events=[tool_event],
            item_events=[],
            turn_events=[],
        )


def _line_value(text: str, key: str) -> str:
    prefix = f"{key}="
    for raw_line in str(text or "").splitlines():
        line = str(raw_line or "").strip()
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


class WorkflowsOrchestrationViewTest(unittest.TestCase):
    def test_orchestrate_command_creates_run_visible_in_workflows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _RuntimeStub(Path(tmpdir))
            create_result = run_command_text_result(runtime, f"/orchestrate {TASKBOOK_MARKDOWN}")

            self.assertIn("orchestration run created", create_result.assistant_text)
            run_id = _line_value(create_result.assistant_text, "run_id")
            run_path = Path(_line_value(create_result.assistant_text, "run_path"))
            projection_path = Path(_line_value(create_result.assistant_text, "projection_path"))

            self.assertTrue(run_id.startswith("run_"))
            self.assertTrue(run_path.exists())
            self.assertTrue(projection_path.exists())

            workflows_result = run_command_text_result(runtime, "/workflows --limit 5")
            self.assertIn("workflows=1", workflows_result.assistant_text)
            self.assertIn("delegated_workflows=0", workflows_result.assistant_text)
            self.assertIn("orchestration_runs=1", workflows_result.assistant_text)
            self.assertIn("background_tasks=0", workflows_result.assistant_text)
            self.assertIn("delegated_result_returned=0", workflows_result.assistant_text)
            self.assertIn("delegated_result_adopted=0", workflows_result.assistant_text)
            self.assertIn("delegated_result_pending_review=0", workflows_result.assistant_text)
            self.assertIn("background_result_returned=0", workflows_result.assistant_text)
            self.assertIn("background_result_adopted=0", workflows_result.assistant_text)
            self.assertIn("background_result_pending_review=0", workflows_result.assistant_text)
            self.assertIn(f"- orchestration | {run_id} | ready", workflows_result.assistant_text)
            self.assertIn("| phase=taskbook_ready", workflows_result.assistant_text)
            self.assertIn("| cards=2", workflows_result.assistant_text)
            self.assertIn("| ready=1", workflows_result.assistant_text)
            self.assertIn("| blocked=1", workflows_result.assistant_text)
            self.assertIn("| blocker=CARD-002:intake_waiting_dependencies", workflows_result.assistant_text)
            self.assertIn("| current=CARD-001:ready", workflows_result.assistant_text)

    def test_workflows_surface_scheduler_budget_block_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _RuntimeStub(Path(tmpdir))
            create_result = run_command_text_result(runtime, f"/orchestrate {READ_ONLY_MARKDOWN}")
            run_id = _line_value(create_result.assistant_text, "run_id")
            self.assertTrue(run_id.startswith("run_"))
            services = taskbook_runtime_service.runtime_services(runtime)
            run = services.storage.read_run(run_id)
            assert run is not None
            run.status = ComplexTaskRunStatus.BLOCKED
            run.current_phase = "card_scheduling"
            run.ready_card_ids = []
            run.blocked_card_ids = ["CARD-001"]
            services.storage.save_run(run)
            state = services.storage.read_card_state(run_id, "CARD-001")
            assert state is not None
            state.status = TaskCardStatus.BLOCKED
            state.last_scheduler_decision = "workspace_write_budget_exhausted"
            services.storage.save_card_state(run_id, state)

            workflows_result = run_command_text_result(runtime, "/workflows --limit 5")

            self.assertIn(f"- orchestration | {run_id} | blocked", workflows_result.assistant_text)
            self.assertIn("| blocker=CARD-001:workspace_write_budget_exhausted", workflows_result.assistant_text)
            self.assertIn("| current=CARD-001:blocked", workflows_result.assistant_text)

    def test_orchestrate_dispatch_command_updates_running_card_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _RuntimeStub(Path(tmpdir))
            create_result = run_command_text_result(runtime, f"/orchestrate {READ_ONLY_MARKDOWN}")
            run_id = _line_value(create_result.assistant_text, "run_id")

            dispatch_result = run_command_text_result(runtime, f"/orchestrate_dispatch {run_id}")
            self.assertIn("orchestration dispatch submitted", dispatch_result.assistant_text)
            self.assertIn(f"run_id={run_id}", dispatch_result.assistant_text)
            self.assertIn("status=running", dispatch_result.assistant_text)
            self.assertIn("selected_cards=CARD-001", dispatch_result.assistant_text)
            self.assertIn("dispatched_cards=CARD-001", dispatch_result.assistant_text)
            self.assertIn("dispatch_refs=CARD-001:delegated_subagent:ag_orch_001", dispatch_result.assistant_text)

            workflows_result = run_command_text_result(runtime, "/workflows --limit 5")
            self.assertIn(f"- orchestration | {run_id} | running", workflows_result.assistant_text)
            self.assertIn("| phase=cards_dispatched", workflows_result.assistant_text)
            self.assertIn("| running=1", workflows_result.assistant_text)
            self.assertIn("| current=CARD-001:running", workflows_result.assistant_text)

    def test_orchestrate_progress_command_accepts_terminal_card_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _RuntimeStub(Path(tmpdir))
            create_result = run_command_text_result(runtime, f"/orchestrate {READ_ONLY_MARKDOWN}")
            run_id = _line_value(create_result.assistant_text, "run_id")
            run_command_text_result(runtime, f"/orchestrate_dispatch {run_id}")
            runtime._delegated_agent_state_snapshot = lambda: [
                {
                    "agent_id": "ag_orch_001",
                    "status": "completed",
                    "updated_at": "2026-04-06T13:00:00Z",
                    "completion_state": "adopted",
                    "terminal_state": "completed",
                    "result_contract": {
                        "status": "completed",
                        "summary": "captured findings",
                        "next_action": "already_adopted",
                        "touched_scope": [],
                    },
                }
            ]

            progress_result = run_command_text_result(runtime, f"/orchestrate_progress {run_id}")

            self.assertIn("orchestration progress updated", progress_result.assistant_text)
            self.assertIn(f"run_id={run_id}", progress_result.assistant_text)
            self.assertIn("synced_cards=CARD-001", progress_result.assistant_text)
            self.assertIn("accepted_cards=CARD-001", progress_result.assistant_text)
            self.assertIn("completed_cards=1", progress_result.assistant_text)

            workflows_result = run_command_text_result(runtime, "/workflows --limit 5")
            self.assertIn(f"- orchestration | {run_id} | completed", workflows_result.assistant_text)
            self.assertIn("| phase=taskbook_completed", workflows_result.assistant_text)
            self.assertIn("delegated_result_returned=0", workflows_result.assistant_text)
            self.assertIn("delegated_result_adopted=1", workflows_result.assistant_text)
            self.assertIn("delegated_result_pending_review=0", workflows_result.assistant_text)
            self.assertIn("background_result_pending_review=0", workflows_result.assistant_text)
            self.assertIn("latest_acceptance=CARD-001:accept", workflows_result.assistant_text)

    def test_orchestrate_continue_command_runs_until_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _RuntimeStub(Path(tmpdir))
            create_result = run_command_text_result(runtime, f"/orchestrate {READ_ONLY_CHAIN_MARKDOWN}")
            run_id = _line_value(create_result.assistant_text, "run_id")
            run_command_text_result(runtime, f"/orchestrate_dispatch {run_id}")

            def _snapshot():
                items: list[dict[str, object]] = []
                for index in range(1, runtime._spawn_count + 1):
                    items.append(
                        {
                            "agent_id": f"ag_orch_{index:03d}",
                            "status": "completed",
                            "updated_at": f"2026-04-06T14:0{index}:00Z",
                            "completion_state": "adopted",
                            "terminal_state": "completed",
                            "result_contract": {
                                "status": "completed",
                                "summary": f"card_{index}_done",
                                "next_action": "already_adopted",
                                "touched_scope": [],
                            },
                        }
                    )
                return items

            runtime._delegated_agent_state_snapshot = _snapshot
            continue_result = run_command_text_result(runtime, f"/orchestrate_continue {run_id} --max-passes 4")

            self.assertIn("orchestration continue finished", continue_result.assistant_text)
            self.assertIn(f"run_id={run_id}", continue_result.assistant_text)
            self.assertIn("passes=2", continue_result.assistant_text)
            self.assertIn("max_passes=4", continue_result.assistant_text)
            self.assertIn("stop_pass=2", continue_result.assistant_text)
            self.assertIn("mutated_passes=2", continue_result.assistant_text)
            self.assertIn("last_mutated_pass=2", continue_result.assistant_text)
            self.assertIn("stopped_reason=terminal:completed", continue_result.assistant_text)
            self.assertIn(
                "pass_summaries=1:running/cards_running:mutated;2:completed/taskbook_completed:mutated:terminal:completed",
                continue_result.assistant_text,
            )
            self.assertIn("accepted_cards=CARD-001,CARD-002", continue_result.assistant_text)
            self.assertIn("dispatched_cards=CARD-002", continue_result.assistant_text)

    def test_orchestrate_apply_command_applies_staged_background_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _RuntimeStub(Path(tmpdir))
            services = taskbook_runtime_service.runtime_services(runtime)
            run = ComplexTaskRun(
                run_id="run_apply_cmd",
                thread_id=runtime.thread_id,
                objective="apply staged patch",
                status=ComplexTaskRunStatus.BLOCKED,
                current_phase="card_review_pending",
                blocked_card_ids=["CARD-010"],
            )
            card = TaskCard(
                card_id="CARD-010",
                taskbook_version=1,
                title="Patch runtime",
                goal="modify runtime wiring",
                kind=TaskCardKind.WORKSPACE_MUTATING,
                execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
                owned_files=["cli/agent_cli/runtime.py"],
                acceptance_criteria=["runtime wiring updated"],
            )
            state = TaskCardState(
                card_id="CARD-010",
                status=TaskCardStatus.BLOCKED,
                dependency_status=TaskCardDependencyStatus.SATISFIED,
                execution_refs=[ExecutionRef(kind=ExecutionRefKind.BACKGROUND_TASK, task_id="bg_010")],
                last_scheduler_decision="blocked_by_acceptance",
            )
            services.storage.save_run(run)
            services.storage.save_card_spec(run.run_id, card)
            services.storage.save_card_state(run.run_id, state)

            class _Adapter:
                def __init__(self) -> None:
                    self.payload = {
                        "task_id": "bg_010",
                        "status": "completed",
                        "summary": "teammate staged changes ready for final apply",
                        "artifact": {
                            "staged_workspace": True,
                            "final_apply_pending": True,
                            "final_apply_state": "pending",
                            "modified_files": ["cli/agent_cli/runtime.py"],
                            "review_commands": ["/background_task_apply bg_010"],
                            "terminal_state": "completed",
                        },
                    }

                def get_status(self, task_id: str) -> dict[str, object]:
                    assert task_id == "bg_010"
                    return self.payload

                def apply_staged_changes(self, task_id: str) -> dict[str, object]:
                    assert task_id == "bg_010"
                    self.payload["summary"] = "background teammate changes applied to live workspace"
                    artifact = dict(self.payload["artifact"])
                    artifact["final_apply_pending"] = False
                    artifact["final_apply_state"] = "applied"
                    artifact["applied_files"] = ["cli/agent_cli/runtime.py"]
                    artifact["review_commands"] = []
                    self.payload["artifact"] = artifact
                    return self.payload

            adapter = _Adapter()
            with patch("cli.agent_cli.orchestration.taskbook_runtime.build_background_task_adapter", lambda cwd=None: adapter):
                result = run_command_text_result(runtime, "/orchestrate_apply run_apply_cmd CARD-010")

            self.assertIn("orchestration staged changes applied", result.assistant_text)
            self.assertIn("run_id=run_apply_cmd", result.assistant_text)
            self.assertIn("card_id=CARD-010", result.assistant_text)
            self.assertIn("task_id=bg_010", result.assistant_text)
            self.assertIn("final_apply_state=applied", result.assistant_text)
            self.assertIn("accepted_cards=-", result.assistant_text)
            self.assertIn("status=blocked", result.assistant_text)

            workflows_result = run_command_text_result(runtime, "/workflows --limit 5")
            self.assertIn("- orchestration | run_apply_cmd | blocked", workflows_result.assistant_text)
            self.assertIn("latest_acceptance=CARD-010:block", workflows_result.assistant_text)
            self.assertIn("review_reason=CARD-010:", workflows_result.assistant_text)
            self.assertIn("current_result=CARD-010:completed", workflows_result.assistant_text)

    def test_orchestrate_reject_command_keeps_card_unaccepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _RuntimeStub(Path(tmpdir))
            services = taskbook_runtime_service.runtime_services(runtime)
            run = ComplexTaskRun(
                run_id="run_reject_cmd",
                thread_id=runtime.thread_id,
                objective="reject staged patch",
                status=ComplexTaskRunStatus.BLOCKED,
                current_phase="card_review_pending",
                blocked_card_ids=["CARD-010"],
            )
            card = TaskCard(
                card_id="CARD-010",
                taskbook_version=1,
                title="Patch runtime",
                goal="modify runtime wiring",
                kind=TaskCardKind.WORKSPACE_MUTATING,
                execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
                owned_files=["cli/agent_cli/runtime.py"],
                acceptance_criteria=["runtime wiring updated"],
            )
            state = TaskCardState(
                card_id="CARD-010",
                status=TaskCardStatus.BLOCKED,
                dependency_status=TaskCardDependencyStatus.SATISFIED,
                execution_refs=[ExecutionRef(kind=ExecutionRefKind.BACKGROUND_TASK, task_id="bg_010")],
                last_scheduler_decision="blocked_by_acceptance",
            )
            services.storage.save_run(run)
            services.storage.save_card_spec(run.run_id, card)
            services.storage.save_card_state(run.run_id, state)

            class _Adapter:
                def __init__(self) -> None:
                    self.payload = {
                        "task_id": "bg_010",
                        "status": "completed",
                        "summary": "teammate staged changes ready for final apply",
                        "artifact": {
                            "staged_workspace": True,
                            "final_apply_pending": True,
                            "final_apply_state": "pending",
                            "modified_files": ["cli/agent_cli/runtime.py"],
                            "review_commands": ["/background_task_reject bg_010"],
                            "terminal_state": "completed",
                        },
                    }

                def get_status(self, task_id: str) -> dict[str, object]:
                    assert task_id == "bg_010"
                    return self.payload

                def reject_staged_changes(self, task_id: str) -> dict[str, object]:
                    assert task_id == "bg_010"
                    self.payload["summary"] = "background teammate staged changes rejected"
                    artifact = dict(self.payload["artifact"])
                    artifact["final_apply_pending"] = False
                    artifact["final_apply_state"] = "rejected"
                    artifact["review_commands"] = []
                    self.payload["artifact"] = artifact
                    return self.payload

            adapter = _Adapter()
            with patch("cli.agent_cli.orchestration.taskbook_runtime.build_background_task_adapter", lambda cwd=None: adapter):
                result = run_command_text_result(runtime, "/orchestrate_reject run_reject_cmd CARD-010")

            self.assertIn("orchestration staged changes rejected", result.assistant_text)
            self.assertIn("run_id=run_reject_cmd", result.assistant_text)
            self.assertIn("card_id=CARD-010", result.assistant_text)
            self.assertIn("task_id=bg_010", result.assistant_text)
            self.assertIn("final_apply_state=rejected", result.assistant_text)
            self.assertIn("accepted_cards=-", result.assistant_text)
            self.assertIn("status=ready", result.assistant_text)

