from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.orchestration import taskbook_runtime as taskbook_runtime_service
from cli.agent_cli.orchestration import (
    taskbook_runtime_results_helper_runtime,
    taskbook_runtime_results_runtime,
)
from cli.agent_cli.orchestration.taskbook_models import (
    CardResult,
    ComplexTaskRun,
    ExecutionRef,
    TaskCard,
    TaskCardState,
)
from cli.agent_cli.orchestration.taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    ComplexTaskRunStatus,
    ExecutionRefKind,
    TaskCardDependencyStatus,
    TaskCardExecutionMode,
    TaskCardKind,
    TaskCardStatus,
)

READ_ONLY_CHAIN_MARKDOWN = """# Progress orchestration

### CARD-001: Research workflow
- goal: research the current workflow surface
- owned_files: docs/research_progress.md
- acceptance_criteria: capture research findings

### CARD-002: Summarize next step
- goal: summarize the next step after research
- owned_files: docs/research_progress_next.md
- acceptance_criteria: next step summary captured
- depends_on: CARD-001
"""


class _RuntimeStub:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "openai",
                "provider_model": "gpt-5.4",
                "provider_reasoning_effort": "medium",
            }

    def __init__(self, root: Path) -> None:
        self.cwd = Path(root)
        self.thread_id = "thread_progress"
        self.agent = self._Agent()
        self._orchestration_runtime_services_cache = None
        self._orchestration_runtime_services_cwd = ""
        self._spawn_count = 0
        self._delegated_snapshots: list[dict[str, object]] = []

    def _delegated_agent_state_snapshot(self):
        return list(self._delegated_snapshots)

    def spawn_agent_result(self, **kwargs) -> CommandExecutionResult:
        self._spawn_count += 1
        agent_id = f"ag_orch_{self._spawn_count:03d}"
        tool_event = ToolEvent(
            name="spawn_agent",
            ok=True,
            summary="spawned orchestration card",
            payload={
                "agent_id": agent_id,
                "provider_name": str(kwargs.get("provider") or "openai"),
                "model": str(kwargs.get("model") or "gpt-5.4"),
            },
        )
        return CommandExecutionResult(
            assistant_text="spawned orchestration card",
            tool_events=[tool_event],
            item_events=[],
            turn_events=[],
        )


def test_progress_accepts_terminal_read_only_result_and_dispatches_unlocked_card(
    tmp_path: Path,
) -> None:
    runtime = _RuntimeStub(tmp_path)

    created = taskbook_runtime_service.create_orchestration_run(runtime, READ_ONLY_CHAIN_MARKDOWN)
    run_id = str(created["run_id"])
    dispatched = taskbook_runtime_service.dispatch_orchestration_run(runtime, run_id)

    assert dispatched["dispatched_card_ids"] == ["CARD-001"]

    runtime._delegated_snapshots = [
        {
            "agent_id": "ag_orch_001",
            "status": "completed",
            "updated_at": "2026-04-06T12:00:00Z",
            "completion_state": "adopted",
            "terminal_state": "completed",
            "result_contract": {
                "status": "completed",
                "summary": "research captured",
                "next_action": "already_adopted",
                "touched_scope": [],
            },
            "last_tool_events": [
                {
                    "name": "exec_command",
                    "payload": {"command": "pytest -q cli/tests/test_taskbook_progress.py"},
                }
            ],
        }
    ]

    progress = taskbook_runtime_service.progress_orchestration_run(runtime, run_id)

    assert progress["synced_card_ids"] == ["CARD-001"]
    assert progress["accepted_card_ids"] == ["CARD-001"]
    assert progress["unlocked_card_ids"] == ["CARD-002"]
    assert progress["selected_card_ids"] == ["CARD-002"]
    assert progress["dispatched_card_ids"] == ["CARD-002"]
    assert progress["dispatch_refs"] == ["CARD-002:delegated_subagent:ag_orch_002"]
    assert progress["status"] == "running"

    bundle = taskbook_runtime_service.runtime_services(runtime).storage.load_run_bundle(run_id)
    accepted = bundle["card_acceptance"]["CARD-001"][-1]
    assert accepted.decision is CardAcceptanceDecision.ACCEPT
    assert bundle["card_states"]["CARD-001"].status is TaskCardStatus.ACCEPTED
    assert bundle["card_states"]["CARD-002"].status is TaskCardStatus.RUNNING
    assert bundle["run"].status is ComplexTaskRunStatus.RUNNING


def test_continue_progresses_multiple_passes_until_completed(tmp_path: Path) -> None:
    runtime = _RuntimeStub(tmp_path)
    created = taskbook_runtime_service.create_orchestration_run(runtime, READ_ONLY_CHAIN_MARKDOWN)
    run_id = str(created["run_id"])
    taskbook_runtime_service.dispatch_orchestration_run(runtime, run_id)

    def _snapshot():
        items: list[dict[str, object]] = []
        for index in range(1, runtime._spawn_count + 1):
            items.append(
                {
                    "agent_id": f"ag_orch_{index:03d}",
                    "status": "completed",
                    "updated_at": f"2026-04-06T12:0{index}:00Z",
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
    result = taskbook_runtime_service.continue_orchestration_run(runtime, run_id, max_passes=4)

    assert result["status"] == "completed"
    assert result["current_phase"] == "taskbook_completed"
    assert result["max_passes"] == 4
    assert result["pass_count"] == 2
    assert result["passes_executed"] == 2
    assert result["stop_pass"] == 2
    assert result["mutated_pass_count"] == 2
    assert result["last_mutated_pass"] == 2
    assert result["stopped_reason"] == "terminal:completed"
    assert result["accepted_card_ids"] == ["CARD-001", "CARD-002"]
    assert result["dispatched_card_ids"] == ["CARD-002"]
    pass_summaries = list(result["pass_summaries"])
    assert len(pass_summaries) == 2
    assert pass_summaries[0]["pass"] == 1
    assert pass_summaries[0]["status"] == "running"
    assert pass_summaries[0]["mutated"] is True
    assert pass_summaries[0]["stop_candidate"] == "continue"
    assert pass_summaries[1]["pass"] == 2
    assert pass_summaries[1]["status"] == "completed"
    assert pass_summaries[1]["mutated"] is True
    assert pass_summaries[1]["stop_candidate"] == "terminal:completed"

    bundle = taskbook_runtime_service.runtime_services(runtime).storage.load_run_bundle(run_id)
    assert bundle["run"].status is ComplexTaskRunStatus.COMPLETED
    assert bundle["card_states"]["CARD-001"].status is TaskCardStatus.ACCEPTED
    assert bundle["card_states"]["CARD-002"].status is TaskCardStatus.ACCEPTED


def test_continue_stops_with_stable_noop_and_reports_pass_summary(tmp_path: Path) -> None:
    runtime = _RuntimeStub(tmp_path)
    created = taskbook_runtime_service.create_orchestration_run(runtime, READ_ONLY_CHAIN_MARKDOWN)
    run_id = str(created["run_id"])
    taskbook_runtime_service.dispatch_orchestration_run(runtime, run_id)
    runtime._delegated_agent_state_snapshot = lambda: []

    result = taskbook_runtime_service.continue_orchestration_run(
        runtime, run_id, max_passes=3, dispatch_ready=False
    )

    assert result["status"] == "running"
    assert result["pass_count"] == 1
    assert result["stop_pass"] == 1
    assert result["stopped_reason"] == "waiting_on_running_cards"
    assert result["mutated_pass_count"] == 0
    assert result["last_mutated_pass"] == 0
    pass_summaries = list(result["pass_summaries"])
    assert len(pass_summaries) == 1
    assert pass_summaries[0]["pass"] == 1
    assert pass_summaries[0]["mutated"] is False
    assert pass_summaries[0]["stop_candidate"] == "waiting_on_running_cards"


def test_continue_reports_waiting_on_ready_cards_for_noop_ready_state(tmp_path: Path) -> None:
    runtime = _RuntimeStub(tmp_path)
    created = taskbook_runtime_service.create_orchestration_run(runtime, READ_ONLY_CHAIN_MARKDOWN)
    run_id = str(created["run_id"])

    result = taskbook_runtime_service.continue_orchestration_run(
        runtime, run_id, max_passes=1, dispatch_ready=False
    )

    assert result["status"] == "ready"
    assert result["stopped_reason"] == "waiting_on_ready_cards"
    assert result["pass_summaries"][0]["stop_candidate"] == "waiting_on_ready_cards"


def test_progress_blocks_background_teammate_result_when_staged_review_pending(
    monkeypatch, tmp_path: Path
) -> None:
    runtime = _RuntimeStub(tmp_path)
    services = taskbook_runtime_service.runtime_services(runtime)

    run = ComplexTaskRun(
        run_id="run_progress_bg",
        thread_id=runtime.thread_id,
        objective="apply teammate patch",
        status=ComplexTaskRunStatus.RUNNING,
        current_phase="cards_running",
        ready_card_ids=[],
        running_card_ids=["CARD-010"],
        blocked_card_ids=[],
        completed_card_ids=[],
    )
    card = TaskCard(
        card_id="CARD-010",
        taskbook_version=1,
        title="Patch runtime",
        goal="modify runtime wiring",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
        acceptance_criteria=["runtime wiring updated"],
    )
    state = TaskCardState(
        card_id="CARD-010",
        status=TaskCardStatus.RUNNING,
        execution_refs=[ExecutionRef(kind=ExecutionRefKind.BACKGROUND_TASK, task_id="bg_010")],
        last_scheduler_decision="dispatched_via_teammate",
    )
    services.storage.save_run(run)
    services.storage.save_card_spec(run.run_id, card)
    services.storage.save_card_state(run.run_id, state)

    fake_adapter = SimpleNamespace(
        get_status=lambda task_id: {
            "task_id": task_id,
            "status": "completed",
            "summary": "teammate staged changes ready for final apply",
            "error": "",
            "artifact": {
                "snapshot_path": str(tmp_path / "bg_010_snapshot.json"),
                "modified_files": ["src/runtime.py"],
                "commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                "test_commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                "staged_workspace": True,
                "final_apply_pending": True,
                "final_apply_state": "pending",
                "review_commands": ["/background_task_apply bg_010"],
                "terminal_state": "completed",
            },
            "result": {"finished_at": "2026-04-06T12:30:00Z"},
        }
    )
    monkeypatch.setattr(
        "cli.agent_cli.orchestration.taskbook_runtime.build_background_task_adapter",
        lambda cwd=None: fake_adapter,
    )

    progress = taskbook_runtime_service.progress_orchestration_run(
        runtime, run.run_id, dispatch_ready=False
    )

    assert progress["synced_card_ids"] == ["CARD-010"]
    assert progress["accepted_card_ids"] == []
    assert progress["status"] == "blocked"
    assert progress["blocked_card_ids"] == ["CARD-010"]

    bundle = services.storage.load_run_bundle(run.run_id)
    result = bundle["card_results"]["CARD-010"][-1]
    acceptance = bundle["card_acceptance"]["CARD-010"][-1]
    assert result.needs_review is True
    assert acceptance.decision is CardAcceptanceDecision.BLOCK
    assert bundle["card_states"]["CARD-010"].status is TaskCardStatus.BLOCKED


def test_progress_does_not_redispatch_blocked_review_card(monkeypatch, tmp_path: Path) -> None:
    runtime = _RuntimeStub(tmp_path)
    services = taskbook_runtime_service.runtime_services(runtime)

    run = ComplexTaskRun(
        run_id="run_progress_bg_blocked",
        thread_id=runtime.thread_id,
        objective="apply teammate patch",
        status=ComplexTaskRunStatus.RUNNING,
        current_phase="cards_running",
        ready_card_ids=[],
        running_card_ids=["CARD-010"],
        blocked_card_ids=[],
        completed_card_ids=[],
    )
    card = TaskCard(
        card_id="CARD-010",
        taskbook_version=1,
        title="Patch runtime",
        goal="modify runtime wiring",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
        acceptance_criteria=["runtime wiring updated"],
    )
    state = TaskCardState(
        card_id="CARD-010",
        status=TaskCardStatus.RUNNING,
        execution_refs=[ExecutionRef(kind=ExecutionRefKind.BACKGROUND_TASK, task_id="bg_010")],
        last_scheduler_decision="dispatched_via_teammate",
    )
    services.storage.save_run(run)
    services.storage.save_card_spec(run.run_id, card)
    services.storage.save_card_state(run.run_id, state)

    fake_adapter = SimpleNamespace(
        get_status=lambda task_id: {
            "task_id": task_id,
            "status": "completed",
            "summary": "teammate staged changes ready for final apply",
            "error": "",
            "artifact": {
                "snapshot_path": str(tmp_path / "bg_010_snapshot.json"),
                "modified_files": ["src/runtime.py"],
                "commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                "test_commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                "staged_workspace": True,
                "final_apply_pending": True,
                "final_apply_state": "pending",
                "review_commands": ["/background_task_apply bg_010"],
                "terminal_state": "completed",
            },
            "result": {"finished_at": "2026-04-06T12:30:00Z"},
        }
    )
    monkeypatch.setattr(
        "cli.agent_cli.orchestration.taskbook_runtime.build_background_task_adapter",
        lambda cwd=None: fake_adapter,
    )

    progress = taskbook_runtime_service.progress_orchestration_run(runtime, run.run_id)

    assert progress["synced_card_ids"] == ["CARD-010"]
    assert progress["accepted_card_ids"] == []
    assert progress["selected_card_ids"] == []
    assert progress["dispatched_card_ids"] == []
    assert progress["dispatch_refs"] == []
    assert progress["status"] == "blocked"
    assert progress["blocked_card_ids"] == ["CARD-010"]


def test_progress_defers_auto_redispatch_for_rework_and_keeps_explicit_dispatch(
    tmp_path: Path,
) -> None:
    runtime = _RuntimeStub(tmp_path)
    services = taskbook_runtime_service.runtime_services(runtime)

    run = ComplexTaskRun(
        run_id="run_progress_rework_defer",
        thread_id=runtime.thread_id,
        objective="retry read-only card",
        status=ComplexTaskRunStatus.RUNNING,
        current_phase="cards_running",
        ready_card_ids=[],
        running_card_ids=["CARD-001"],
        blocked_card_ids=[],
        completed_card_ids=[],
    )
    card = TaskCard(
        card_id="CARD-001",
        taskbook_version=1,
        title="Research runtime behavior",
        goal="collect findings",
        kind=TaskCardKind.READ_ONLY,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["docs/research_runtime.md"],
        acceptance_criteria=["findings captured"],
    )
    state = TaskCardState(
        card_id="CARD-001",
        status=TaskCardStatus.RUNNING,
        execution_refs=[ExecutionRef(kind=ExecutionRefKind.DELEGATED_SUBAGENT, agent_id="ag_001")],
        last_scheduler_decision="dispatched_via_delegated_subagent",
    )
    services.storage.save_run(run)
    services.storage.save_card_spec(run.run_id, card)
    services.storage.save_card_state(run.run_id, state)

    runtime._delegated_snapshots = [
        {
            "agent_id": "ag_001",
            "status": "failed",
            "updated_at": "2026-04-06T12:00:00Z",
            "completion_state": "adopted",
            "terminal_state": "failed",
            "result_contract": {
                "status": "failed",
                "summary": "need another attempt",
                "next_action": "execution_failed_retry_recommended",
                "touched_scope": [],
            },
            "last_tool_events": [],
        }
    ]

    progress = taskbook_runtime_service.progress_orchestration_run(runtime, run.run_id)

    assert progress["synced_card_ids"] == ["CARD-001"]
    assert progress["accepted_card_ids"] == []
    assert progress["selected_card_ids"] == []
    assert progress["dispatched_card_ids"] == []
    assert progress["dispatch_refs"] == []
    assert progress["status"] == "ready"
    assert progress["ready_card_ids"] == ["CARD-001"]

    bundle = services.storage.load_run_bundle(run.run_id)
    updated_state = bundle["card_states"]["CARD-001"]
    assert updated_state.status is TaskCardStatus.READY
    assert updated_state.last_scheduler_decision == "deferred_after_progress_acceptance"
    assert len(updated_state.execution_refs) == 1
    assert updated_state.execution_refs[-1].agent_id == "ag_001"

    dispatched = taskbook_runtime_service.dispatch_orchestration_run(runtime, run.run_id)

    assert dispatched["selected_card_ids"] == ["CARD-001"]
    assert dispatched["dispatched_card_ids"] == ["CARD-001"]
    assert dispatched["dispatch_refs"] == ["CARD-001:delegated_subagent:ag_orch_001"]
    bundle_after_dispatch = services.storage.load_run_bundle(run.run_id)
    assert len(bundle_after_dispatch["card_states"]["CARD-001"].execution_refs) == 2


def test_progress_persists_replan_followup_actions_for_escalated_rework_block(
    tmp_path: Path,
) -> None:
    runtime = _RuntimeStub(tmp_path)
    services = taskbook_runtime_service.runtime_services(runtime)

    run = ComplexTaskRun(
        run_id="run_progress_replan_followup",
        thread_id=runtime.thread_id,
        objective="surface replan followup actions",
        status=ComplexTaskRunStatus.RUNNING,
        current_phase="cards_running",
        ready_card_ids=[],
        running_card_ids=["CARD-009"],
        blocked_card_ids=[],
        completed_card_ids=[],
    )
    card = TaskCard(
        card_id="CARD-009",
        taskbook_version=1,
        title="Escalated retry card",
        goal="trigger replan candidate from progress acceptance",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/retry.sh"],
        acceptance_criteria=["replan candidate captured"],
    )
    state = TaskCardState(
        card_id="CARD-009",
        status=TaskCardStatus.RUNNING,
        attempt=2,
        execution_refs=[ExecutionRef(kind=ExecutionRefKind.DELEGATED_SUBAGENT, agent_id="ag_009")],
        last_scheduler_decision="dispatched_via_delegated_subagent",
    )
    services.storage.save_run(run)
    services.storage.save_card_spec(run.run_id, card)
    services.storage.save_card_state(run.run_id, state)

    runtime._delegated_snapshots = [
        {
            "agent_id": "ag_009",
            "status": "failed",
            "updated_at": "2026-04-07T15:00:00Z",
            "completion_state": "adopted",
            "terminal_state": "failed",
            "result_contract": {
                "status": "failed",
                "summary": "failed repeatedly",
                "next_action": "execution_failed_retry_recommended",
                "touched_scope": [],
            },
            "last_tool_events": [],
        }
    ]

    progress = taskbook_runtime_service.progress_orchestration_run(
        runtime, run.run_id, dispatch_ready=False
    )

    assert progress["synced_card_ids"] == ["CARD-009"]
    assert progress["accepted_card_ids"] == []
    assert progress["blocked_card_ids"] == ["CARD-009"]
    assert len(progress["replan_candidates"]) == 1
    assert progress["replan_candidates"][0]["action"] == "replan_candidate"
    assert progress["replan_candidates"][0]["card_id"] == "CARD-009"
    assert len(progress["replan_pending"]) == 1
    assert progress["replan_pending"][0]["pending_state"] == "awaiting_operator_action"
    assert (
        progress["replan_pending"][0]["pending_reason"]
        == "execution_failed_retry_recommended_escalated_after_retries"
    )
    assert progress["replan_pending_card_ids"] == ["CARD-009"]
    assert progress["replan_contract_version"] == 1
    assert len(progress["replan_operator_action_ids"]) == 1
    assert len(progress["operator_actions"]) == 1
    assert progress["operator_actions"][0]["action"] == "replan_taskbook"
    assert progress["operator_actions"][0]["action_id"] == progress["replan_operator_action_ids"][0]
    assert progress["operator_actions"][0]["status"] == "pending"
    assert progress["operator_actions"][0]["card_id"] == "CARD-009"
    assert progress["operator_actions"][0]["command_name"] == "/orchestrate_confirm"
    assert progress["operator_actions"][0]["command_args"] == ["<updated taskbook markdown>"]
    assert (
        progress["operator_actions"][0]["command"]
        == "/orchestrate_confirm <updated taskbook markdown>"
    )
    assert progress["replan_followup_summary"]["contract_version"] == 1
    assert progress["replan_followup_summary"]["has_replan_followup"] is True
    assert progress["replan_followup_summary"]["candidate_count"] == 1
    assert progress["replan_followup_summary"]["pending_count"] == 1
    assert progress["replan_followup_summary"]["pending_card_count"] == 1
    assert progress["replan_followup_summary"]["operator_action_count"] == 1
    assert progress["replan_followup_summary"]["scopes"] == ["card"]
    assert progress["replan_followup_summary"]["triggers"] == ["rework_escalated_after_retries"]
    assert progress["replan_followup_summary"]["pending_reasons"] == [
        "execution_failed_retry_recommended_escalated_after_retries"
    ]
    assert (
        progress["replan_followup_summary"]["next_operator_command"]
        == "/orchestrate_confirm <updated taskbook markdown>"
    )
    assert progress["replan_followup_summary"]["candidate_count"] == len(
        progress["replan_candidates"]
    )
    assert progress["replan_followup_summary"]["pending_count"] == len(progress["replan_pending"])
    assert progress["replan_followup_summary"]["operator_action_count"] == len(
        progress["operator_actions"]
    )
    assert progress["replan_followup_summary"]["pending_card_count"] == len(
        progress["replan_pending_card_ids"]
    )
    assert progress["replan_followup_summary"]["has_replan_followup"] is bool(
        progress["replan_candidates"] or progress["replan_pending"] or progress["operator_actions"]
    )
    assert progress["status"] == "blocked"

    bundle = services.storage.load_run_bundle(run.run_id)
    acceptance = bundle["card_acceptance"]["CARD-009"][-1]
    assert acceptance.decision is CardAcceptanceDecision.BLOCK
    assert acceptance.reason.endswith("_escalated_after_retries")
    assert len(acceptance.followup_actions) == 1
    assert acceptance.followup_actions[0]["action"] == "replan_candidate"
    assert acceptance.followup_actions[0]["scope"] == "card"
    assert acceptance.followup_actions[0]["trigger"] == "rework_escalated_after_retries"


def test_replan_followup_summary_contract_keys_stable() -> None:
    summary = taskbook_runtime_results_runtime._replan_followup_progress_summary(
        contract_version=1,
        candidates=[
            {
                "scope": "card",
                "trigger": "rework_escalated_after_retries",
            }
        ],
        pending=[
            {
                "pending_reason": "execution_failed_retry_recommended_escalated_after_retries",
            }
        ],
        pending_card_ids=["CARD-009"],
        operator_actions=[
            {
                "command": "/orchestrate_confirm <updated taskbook markdown>",
            }
        ],
    )
    assert summary["contract_version"] == 1
    assert summary["has_replan_followup"] is True
    assert summary["candidate_count"] == 1
    assert summary["pending_count"] == 1
    assert summary["pending_card_count"] == 1
    assert summary["operator_action_count"] == 1
    assert summary["scopes"] == ["card"]
    assert summary["triggers"] == ["rework_escalated_after_retries"]
    assert summary["pending_reasons"] == [
        "execution_failed_retry_recommended_escalated_after_retries"
    ]
    assert summary["next_operator_command"] == "/orchestrate_confirm <updated taskbook markdown>"


def test_orchestrate_apply_accepts_staged_background_result(monkeypatch, tmp_path: Path) -> None:
    runtime = _RuntimeStub(tmp_path)
    services = taskbook_runtime_service.runtime_services(runtime)

    run = ComplexTaskRun(
        run_id="run_progress_apply",
        thread_id=runtime.thread_id,
        objective="apply teammate patch",
        status=ComplexTaskRunStatus.BLOCKED,
        current_phase="card_review_pending",
        ready_card_ids=[],
        running_card_ids=[],
        blocked_card_ids=["CARD-010"],
        completed_card_ids=[],
    )
    card = TaskCard(
        card_id="CARD-010",
        taskbook_version=1,
        title="Patch runtime",
        goal="modify runtime wiring",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
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
                "error": "",
                "artifact": {
                    "snapshot_path": str(tmp_path / "bg_010_snapshot.json"),
                    "modified_files": ["src/runtime.py"],
                    "commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                    "test_commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                    "staged_workspace": True,
                    "final_apply_pending": True,
                    "final_apply_state": "pending",
                    "review_commands": ["/background_task_apply bg_010"],
                    "terminal_state": "completed",
                },
                "result": {"finished_at": "2026-04-06T12:30:00Z"},
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
            artifact["applied_files"] = ["src/runtime.py"]
            artifact["review_commands"] = []
            self.payload["artifact"] = artifact
            return self.payload

    adapter = _Adapter()
    monkeypatch.setattr(
        "cli.agent_cli.orchestration.taskbook_runtime.build_background_task_adapter",
        lambda cwd=None: adapter,
    )

    payload = taskbook_runtime_service.apply_orchestration_card(runtime, run.run_id, "CARD-010")

    assert payload["card_id"] == "CARD-010"
    assert payload["task_id"] == "bg_010"
    assert payload["final_apply_state"] == "applied"
    assert payload["task_status"] == "completed"
    assert payload["synced_card_ids"] == ["CARD-010"]
    assert payload["accepted_card_ids"] == ["CARD-010"]
    assert payload["status"] == "completed"

    bundle = services.storage.load_run_bundle(run.run_id)
    acceptance = bundle["card_acceptance"]["CARD-010"][-1]
    assert acceptance.decision is CardAcceptanceDecision.ACCEPT
    assert bundle["card_states"]["CARD-010"].status is TaskCardStatus.ACCEPTED
    assert bundle["run"].status is ComplexTaskRunStatus.COMPLETED


def test_orchestrate_apply_accepts_after_prior_blocked_review(monkeypatch, tmp_path: Path) -> None:
    runtime = _RuntimeStub(tmp_path)
    services = taskbook_runtime_service.runtime_services(runtime)

    run = ComplexTaskRun(
        run_id="run_progress_apply_after_block",
        thread_id=runtime.thread_id,
        objective="apply teammate patch",
        status=ComplexTaskRunStatus.RUNNING,
        current_phase="cards_running",
        ready_card_ids=[],
        running_card_ids=["CARD-010"],
        blocked_card_ids=[],
        completed_card_ids=[],
    )
    card = TaskCard(
        card_id="CARD-010",
        taskbook_version=1,
        title="Patch runtime",
        goal="modify runtime wiring",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
        acceptance_criteria=["runtime wiring updated"],
    )
    state = TaskCardState(
        card_id="CARD-010",
        status=TaskCardStatus.RUNNING,
        execution_refs=[ExecutionRef(kind=ExecutionRefKind.BACKGROUND_TASK, task_id="bg_010")],
        last_scheduler_decision="dispatched_via_teammate",
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
                "error": "",
                "artifact": {
                    "snapshot_path": str(tmp_path / "bg_010_snapshot.json"),
                    "modified_files": ["src/runtime.py"],
                    "commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                    "test_commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                    "staged_workspace": True,
                    "final_apply_pending": True,
                    "final_apply_state": "pending",
                    "review_commands": ["/background_task_apply bg_010"],
                    "terminal_state": "completed",
                },
                "result": {"finished_at": "2026-04-06T12:30:00Z"},
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
            artifact["applied_files"] = ["src/runtime.py"]
            artifact["review_commands"] = []
            self.payload["artifact"] = artifact
            return self.payload

    adapter = _Adapter()
    monkeypatch.setattr(
        "cli.agent_cli.orchestration.taskbook_runtime.build_background_task_adapter",
        lambda cwd=None: adapter,
    )

    blocked = taskbook_runtime_service.progress_orchestration_run(runtime, run.run_id)
    assert blocked["status"] == "blocked"
    assert blocked["blocked_card_ids"] == ["CARD-010"]

    applied = taskbook_runtime_service.apply_orchestration_card(runtime, run.run_id, "CARD-010")

    assert applied["final_apply_state"] == "applied"
    assert applied["accepted_card_ids"] == ["CARD-010"]
    assert applied["status"] == "completed"

    bundle = services.storage.load_run_bundle(run.run_id)
    acceptances = bundle["card_acceptance"]["CARD-010"]
    assert [item.decision for item in acceptances] == [
        CardAcceptanceDecision.BLOCK,
        CardAcceptanceDecision.ACCEPT,
    ]
    assert bundle["card_states"]["CARD-010"].status is TaskCardStatus.ACCEPTED
    assert bundle["run"].status is ComplexTaskRunStatus.COMPLETED


def test_orchestrate_reject_keeps_background_card_unaccepted(monkeypatch, tmp_path: Path) -> None:
    runtime = _RuntimeStub(tmp_path)
    services = taskbook_runtime_service.runtime_services(runtime)

    run = ComplexTaskRun(
        run_id="run_progress_reject",
        thread_id=runtime.thread_id,
        objective="review teammate patch",
        status=ComplexTaskRunStatus.BLOCKED,
        current_phase="card_review_pending",
        ready_card_ids=[],
        running_card_ids=[],
        blocked_card_ids=["CARD-010"],
        completed_card_ids=[],
    )
    card = TaskCard(
        card_id="CARD-010",
        taskbook_version=1,
        title="Patch runtime",
        goal="modify runtime wiring",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
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
                "error": "",
                "artifact": {
                    "snapshot_path": str(tmp_path / "bg_010_snapshot.json"),
                    "modified_files": ["src/runtime.py"],
                    "commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                    "test_commands": ["pytest -q cli/tests/test_taskbook_progress.py"],
                    "staged_workspace": True,
                    "final_apply_pending": True,
                    "final_apply_state": "pending",
                    "review_commands": ["/background_task_reject bg_010"],
                    "terminal_state": "completed",
                },
                "result": {"finished_at": "2026-04-06T12:30:00Z"},
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
    monkeypatch.setattr(
        "cli.agent_cli.orchestration.taskbook_runtime.build_background_task_adapter",
        lambda cwd=None: adapter,
    )

    payload = taskbook_runtime_service.reject_orchestration_card(runtime, run.run_id, "CARD-010")

    assert payload["card_id"] == "CARD-010"
    assert payload["task_id"] == "bg_010"
    assert payload["final_apply_state"] == "rejected"
    assert payload["task_status"] == "completed"
    assert payload["synced_card_ids"] == ["CARD-010"]
    assert payload["accepted_card_ids"] == []
    assert payload["selected_card_ids"] == []
    assert payload["dispatched_card_ids"] == []
    assert payload["status"] == "ready"
    assert payload["ready_card_ids"] == ["CARD-010"]

    bundle = services.storage.load_run_bundle(run.run_id)
    acceptance = bundle["card_acceptance"]["CARD-010"][-1]
    assert acceptance.decision is CardAcceptanceDecision.REJECT
    assert bundle["card_states"]["CARD-010"].status is TaskCardStatus.READY
    assert bundle["run"].status is ComplexTaskRunStatus.READY


def test_auto_acceptance_policy_accepts_clean_read_only_result() -> None:
    card = TaskCard(
        card_id="CARD-RO-001",
        taskbook_version=1,
        title="Research docs",
        goal="collect findings",
        kind=TaskCardKind.READ_ONLY,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["docs/research.md"],
        acceptance_criteria=["research complete"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW)
    result = CardResult(
        result_id="result_ro_ok",
        run_id="run_ro",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="research done",
        modified_files=[],
        commands=["rg -n TODO docs"],
        test_commands=[],
        blockers=[],
        risks=[],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
        )
    )

    assert decision is CardAcceptanceDecision.ACCEPT
    assert reason == "auto_accept_read_only_clean_result"
    assert accepted_facts == [f"{card.card_id}:accepted"]


def test_auto_acceptance_policy_blocks_workspace_change_without_test_evidence() -> None:
    card = TaskCard(
        card_id="CARD-WS-001",
        taskbook_version=1,
        title="Patch runtime",
        goal="apply patch",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
        acceptance_criteria=["runtime updated"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW)
    result = CardResult(
        result_id="result_ws_no_tests",
        run_id="run_ws",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="patch ready",
        modified_files=["src/runtime.py"],
        commands=["python -m cli.agent_cli --headless"],
        test_commands=[],
        blockers=[],
        risks=[],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "workspace_change_missing_test_evidence"
    assert accepted_facts == []


def test_auto_acceptance_policy_marks_failed_rework_with_explicit_reason() -> None:
    card = TaskCard(
        card_id="CARD-RW-001",
        taskbook_version=1,
        title="Retry flaky command",
        goal="stabilize command",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/retry.sh"],
        acceptance_criteria=["retry strategy documented"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW)
    result = CardResult(
        result_id="result_failed_retry",
        run_id="run_rw",
        card_id=card.card_id,
        status=CardResultStatus.FAILED,
        summary="command failed with transient issue",
        modified_files=[],
        commands=["bash scripts/retry.sh"],
        test_commands=[],
        blockers=[],
        risks=[],
        needs_review=True,
        rework_required=True,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
        )
    )

    assert decision is CardAcceptanceDecision.REWORK
    assert reason == "execution_failed_retry_recommended"
    assert accepted_facts == []


def test_auto_acceptance_policy_escalates_failed_rework_after_retries() -> None:
    card = TaskCard(
        card_id="CARD-RW-002",
        taskbook_version=1,
        title="Retry flaky command until escalation",
        goal="stabilize command",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/retry.sh"],
        acceptance_criteria=["retry strategy documented"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=2)
    result = CardResult(
        result_id="result_failed_retry_escalated",
        run_id="run_rw_escalated",
        card_id=card.card_id,
        attempt=2,
        status=CardResultStatus.FAILED,
        summary="command failed repeatedly",
        modified_files=[],
        commands=["bash scripts/retry.sh"],
        test_commands=[],
        blockers=[],
        risks=[],
        needs_review=True,
        rework_required=True,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "execution_failed_retry_recommended_escalated_after_retries"
    assert accepted_facts == []


def test_auto_acceptance_policy_escalates_completed_rework_after_retries() -> None:
    card = TaskCard(
        card_id="CARD-RW-003",
        taskbook_version=1,
        title="Completed with unresolved rework",
        goal="return deterministic result",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["src/runtime.py"],
        acceptance_criteria=["runtime updated"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=3)
    result = CardResult(
        result_id="result_completed_rework_escalated",
        run_id="run_rw_completed_escalated",
        card_id=card.card_id,
        attempt=3,
        status=CardResultStatus.COMPLETED,
        summary="result still requires manual rework",
        modified_files=["src/runtime.py"],
        commands=["python -m pytest"],
        test_commands=["python -m pytest"],
        blockers=[],
        risks=[],
        needs_review=False,
        rework_required=True,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "completed_result_marked_rework_escalated_after_retries"
    assert accepted_facts == []


def test_auto_acceptance_policy_uses_staged_workspace_review_reason() -> None:
    card = TaskCard(
        card_id="CARD-RISK-001",
        taskbook_version=1,
        title="Review staged workspace apply command",
        goal="validate staged diff review",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
        acceptance_criteria=["review command captured"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_staged_review",
        run_id="run_risk",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="staged review command present",
        modified_files=[],
        commands=[],
        test_commands=[],
        blockers=[],
        risks=["/background_task_apply bg_010"],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "staged_workspace_review_required"
    assert accepted_facts == []


def test_auto_acceptance_policy_respects_workspace_change_review_override() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-001",
        taskbook_version=1,
        title="Workspace change with tests",
        goal="apply patch and tests",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
        acceptance_criteria=["patch verified"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW)
    result = CardResult(
        result_id="result_policy_workspace",
        run_id="run_policy_workspace",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="workspace change with tests",
        modified_files=["src/runtime.py"],
        commands=["python -m pytest cli/tests/test_runtime_core_modules.py"],
        test_commands=["python -m pytest cli/tests/test_runtime_core_modules.py"],
        blockers=[],
        risks=[],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"workspace_change_requires_review": True},
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "reviewer_policy_workspace_change_requires_review"
    assert accepted_facts == []


def test_auto_acceptance_policy_respects_rework_escalation_threshold_override() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-002",
        taskbook_version=1,
        title="Escalate failed retry earlier",
        goal="surface failure sooner",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/retry.sh"],
        acceptance_criteria=["failure reason is deterministic"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_retry",
        run_id="run_policy_retry",
        card_id=card.card_id,
        attempt=1,
        status=CardResultStatus.FAILED,
        summary="failed once",
        modified_files=[],
        commands=["bash scripts/retry.sh"],
        test_commands=[],
        blockers=[],
        risks=[],
        needs_review=True,
        rework_required=True,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"rework_escalation_min_attempts": 1},
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "execution_failed_retry_recommended_escalated_after_retries"
    assert accepted_facts == []


def test_auto_acceptance_policy_allows_read_only_risk_when_policy_disables_read_only_risk_block() -> (
    None
):
    card = TaskCard(
        card_id="CARD-POLICY-003",
        taskbook_version=1,
        title="Read-only scan with non-blocking warning",
        goal="report findings",
        kind=TaskCardKind.READ_ONLY,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["docs/findings.md"],
        acceptance_criteria=["findings captured"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_read_only_risk",
        run_id="run_policy_read_only_risk",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="read-only scan done with warning",
        modified_files=[],
        commands=["rg -n TODO docs"],
        test_commands=[],
        blockers=[],
        risks=["minor_warning_only"],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"risk_requires_review_by_kind": {"read_only": False}},
        )
    )

    assert decision is CardAcceptanceDecision.ACCEPT
    assert reason == "auto_accept_read_only_clean_result"
    assert accepted_facts == [f"{card.card_id}:accepted"]


def test_auto_acceptance_policy_uses_risk_keyword_reason_override() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-004",
        taskbook_version=1,
        title="Workspace card with keyword risk",
        goal="validate keyword risk routing",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
        acceptance_criteria=["risk keyword is classified"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_risk_keyword",
        run_id="run_policy_risk_keyword",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="keyword risk captured",
        modified_files=[],
        commands=[],
        test_commands=[],
        blockers=[],
        risks=["security_sensitive_path_detected"],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"risk_block_keywords": ["security_sensitive"]},
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "reviewer_policy_risk_keyword:security_sensitive"
    assert accepted_facts == []


def test_auto_acceptance_policy_uses_rework_escalation_threshold_by_kind() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-005",
        taskbook_version=1,
        title="Long-running retry with stricter escalation",
        goal="escalate long-running retry faster",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/retry.sh"],
        acceptance_criteria=["escalation happens on first retry"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_rework_by_kind",
        run_id="run_policy_rework_by_kind",
        card_id=card.card_id,
        attempt=1,
        status=CardResultStatus.FAILED,
        summary="long-running retry failed once",
        modified_files=[],
        commands=["bash scripts/retry.sh"],
        test_commands=[],
        blockers=[],
        risks=[],
        needs_review=True,
        rework_required=True,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"rework_escalation_min_attempts_by_kind": {"long_running": 1}},
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "execution_failed_retry_recommended_escalated_after_retries"
    assert accepted_facts == []


def test_auto_acceptance_policy_allows_failure_retry_rework_by_kind_policy() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-007",
        taskbook_version=1,
        title="Long-running failed result with retry policy",
        goal="prefer rework before reject",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/retry.sh"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_retry_by_kind",
        run_id="run_policy_retry_by_kind",
        card_id=card.card_id,
        attempt=1,
        status=CardResultStatus.FAILED,
        summary="failed once",
        suggested_next_action="execution_failed_retry_recommended",
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"retry_failed_requires_rework_by_kind": {"long_running": True}},
        )
    )

    assert decision is CardAcceptanceDecision.REWORK
    assert reason == "execution_failed_retry_recommended"
    assert accepted_facts == []


def test_auto_acceptance_policy_keeps_failure_reject_when_retry_kind_policy_does_not_match() -> (
    None
):
    card = TaskCard(
        card_id="CARD-POLICY-008",
        taskbook_version=1,
        title="Read-only failed result",
        goal="counterexample for retry by kind",
        kind=TaskCardKind.READ_ONLY,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["docs/status.md"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_retry_kind_miss",
        run_id="run_policy_retry_kind_miss",
        card_id=card.card_id,
        attempt=1,
        status=CardResultStatus.FAILED,
        summary="failed once",
        suggested_next_action="execution_failed_retry_recommended",
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"retry_failed_requires_rework_by_kind": {"long_running": True}},
        )
    )

    assert decision is CardAcceptanceDecision.REJECT
    assert reason == "execution_failed_retry_recommended"
    assert accepted_facts == []


def test_auto_acceptance_policy_allows_failed_retry_rework_by_kind_reason_keywords() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-011",
        taskbook_version=1,
        title="Long-running failure by keyword",
        goal="retry by kind keywords should trigger rework",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/retry.sh"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_retry_kw_by_kind",
        run_id="run_policy_retry_kw_by_kind",
        card_id=card.card_id,
        attempt=1,
        status=CardResultStatus.FAILED,
        summary="transient backend issue",
        suggested_next_action="transient_backend_error_retry",
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={
                "retry_failed_reason_keywords_by_kind": {
                    "long_running": ["transient_backend"],
                }
            },
        )
    )

    assert decision is CardAcceptanceDecision.REWORK
    assert reason == "transient_backend_error_retry"
    assert accepted_facts == []


def test_auto_acceptance_policy_allows_timeout_retry_rework_by_kind_reason_keywords() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-012",
        taskbook_version=1,
        title="Long-running timeout by keyword",
        goal="timeout retry by kind keywords should trigger rework",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/retry.sh"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_timeout_kw_by_kind",
        run_id="run_policy_timeout_kw_by_kind",
        card_id=card.card_id,
        attempt=1,
        status=CardResultStatus.TIMED_OUT,
        summary="timeout on provider call",
        suggested_next_action="timeout_budget_exceeded_retry",
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={
                "retry_timeout_reason_keywords_by_kind": {
                    "long_running": "timeout_budget",
                }
            },
        )
    )

    assert decision is CardAcceptanceDecision.REWORK
    assert reason == "timeout_budget_exceeded_retry"
    assert accepted_facts == []


def test_auto_acceptance_policy_keeps_timeout_reject_when_retry_keyword_kind_miss() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-013",
        taskbook_version=1,
        title="Read-only timeout",
        goal="counterexample for timeout retry keywords by kind",
        kind=TaskCardKind.READ_ONLY,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["docs/status.md"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_timeout_kw_kind_miss",
        run_id="run_policy_timeout_kw_kind_miss",
        card_id=card.card_id,
        attempt=1,
        status=CardResultStatus.TIMED_OUT,
        summary="timeout once",
        suggested_next_action="timeout_budget_exceeded_retry",
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={
                "retry_timeout_reason_keywords_by_kind": {
                    "long_running": "timeout_budget",
                }
            },
        )
    )

    assert decision is CardAcceptanceDecision.REJECT
    assert reason == "timeout_budget_exceeded_retry"
    assert accepted_facts == []


def test_auto_acceptance_policy_requires_test_evidence_only_for_selected_kinds() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-006",
        taskbook_version=1,
        title="Long-running with workspace change but no tests",
        goal="allow no-test completion for selected kind policy",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/sync_data.sh"],
        acceptance_criteria=["sync script updated"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_tests_by_kind",
        run_id="run_policy_tests_by_kind",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="long-running card completed without tests",
        modified_files=["scripts/sync_data.sh"],
        commands=["bash scripts/sync_data.sh --dry-run"],
        test_commands=[],
        blockers=[],
        risks=[],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"require_tests_for_card_kinds": ["workspace_mutating"]},
        )
    )

    assert decision is CardAcceptanceDecision.ACCEPT
    assert reason == "auto_accept_workspace_change_with_test_evidence"
    assert accepted_facts == [f"{card.card_id}:accepted"]


def test_auto_acceptance_policy_can_reject_risk_by_keyword_policy() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-009",
        taskbook_version=1,
        title="Reject critical risk keyword",
        goal="force reject on critical risk",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_risk_reject",
        run_id="run_policy_risk_reject",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="critical risk detected",
        risks=["critical_security_gate_failed"],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"risk_reject_keywords": ["critical_security"]},
        )
    )

    assert decision is CardAcceptanceDecision.REJECT
    assert reason == "reviewer_policy_risk_reject_keyword:critical_security"
    assert accepted_facts == []


def test_auto_acceptance_policy_keeps_block_for_non_matching_risk_reject_keyword() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-010",
        taskbook_version=1,
        title="Block risk when reject keyword does not match",
        goal="counterexample for risk reject keyword",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_risk_reject_miss",
        run_id="run_policy_risk_reject_miss",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="security risk captured",
        risks=["security_sensitive_path_detected"],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={"risk_reject_keywords": ["critical_security"]},
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "completed_result_risk_review_required"
    assert accepted_facts == []


def test_auto_acceptance_policy_can_reject_risk_by_keyword_policy_by_kind() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-014",
        taskbook_version=1,
        title="Reject risk by kind keyword",
        goal="kind-specific risk reject should work",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_risk_reject_by_kind",
        run_id="run_policy_risk_reject_by_kind",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="critical path risk detected",
        risks=["critical_workspace_violation_detected"],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={
                "risk_reject_keywords_by_kind": {
                    "workspace_mutating": ["critical_workspace"],
                }
            },
        )
    )

    assert decision is CardAcceptanceDecision.REJECT
    assert reason == "reviewer_policy_risk_reject_keyword:critical_workspace"
    assert accepted_facts == []


def test_auto_acceptance_policy_keeps_block_for_non_matching_risk_reject_keyword_by_kind() -> None:
    card = TaskCard(
        card_id="CARD-POLICY-015",
        taskbook_version=1,
        title="Block risk when reject-by-kind misses",
        goal="kind-specific reject keyword counterexample",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_policy_risk_reject_by_kind_miss",
        run_id="run_policy_risk_reject_by_kind_miss",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="security risk",
        risks=["security_sensitive_path_detected"],
        needs_review=False,
        rework_required=False,
    )

    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy={
                "risk_reject_keywords_by_kind": {
                    "workspace_mutating": ["critical_workspace"],
                }
            },
        )
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "completed_result_risk_review_required"
    assert accepted_facts == []


def test_replan_followup_actions_suggests_card_replan_on_escalated_rework_block() -> None:
    card = TaskCard(
        card_id="CARD-REPLAN-001",
        taskbook_version=1,
        title="Escalated failed retry",
        goal="surface card-level replan trigger",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.DELEGATED_SUBAGENT,
        owned_files=["scripts/retry.sh"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=2)
    result = CardResult(
        result_id="result_replan_escalated",
        run_id="run_replan_escalated",
        card_id=card.card_id,
        attempt=2,
        status=CardResultStatus.FAILED,
        summary="failed repeatedly",
        rework_required=True,
    )
    decision, reason, _ = taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
        result,
        card=card,
        state=state,
    )

    actions = taskbook_runtime_results_helper_runtime.replan_followup_actions(
        result=result,
        decision=decision,
        reason=reason,
        card=card,
        state=state,
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason.endswith("_escalated_after_retries")
    assert len(actions) == 1
    assert actions[0]["action"] == "replan_candidate"
    assert actions[0]["scope"] == "card"
    assert actions[0]["trigger"] == "rework_escalated_after_retries"
    assert actions[0]["card_id"] == card.card_id


def test_replan_followup_actions_suggests_run_replan_on_terminal_reject() -> None:
    card = TaskCard(
        card_id="CARD-REPLAN-002",
        taskbook_version=1,
        title="Terminal failure",
        goal="surface run-level replan trigger",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_replan_reject",
        run_id="run_replan_reject",
        card_id=card.card_id,
        status=CardResultStatus.FAILED,
        summary="execution failed",
        rework_required=False,
    )
    decision, reason, _ = taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
        result,
        card=card,
        state=state,
    )

    actions = taskbook_runtime_results_helper_runtime.replan_followup_actions(
        result=result,
        decision=decision,
        reason=reason,
        card=card,
        state=state,
    )

    assert decision is CardAcceptanceDecision.REJECT
    assert reason == "execution_failed"
    assert len(actions) == 1
    assert actions[0]["scope"] == "run"
    assert actions[0]["trigger"] == "terminal_reject"
    assert actions[0]["card_id"] == card.card_id


def test_replan_followup_actions_skips_manual_review_only_block_reason() -> None:
    card = TaskCard(
        card_id="CARD-REPLAN-003",
        taskbook_version=1,
        title="Workspace change without tests",
        goal="manual review should not auto-trigger replan",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/runtime.py"],
    )
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.REVIEW, attempt=1)
    result = CardResult(
        result_id="result_replan_manual_review",
        run_id="run_replan_manual_review",
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="workspace change with missing test evidence",
        modified_files=["src/runtime.py"],
        test_commands=[],
        needs_review=False,
    )
    decision, reason, _ = taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
        result,
        card=card,
        state=state,
    )

    actions = taskbook_runtime_results_helper_runtime.replan_followup_actions(
        result=result,
        decision=decision,
        reason=reason,
        card=card,
        state=state,
    )

    assert decision is CardAcceptanceDecision.BLOCK
    assert reason == "workspace_change_missing_test_evidence"
    assert actions == []


def test_build_acceptance_supports_replan_followup_actions_payload() -> None:
    acceptance = taskbook_runtime_results_helper_runtime.build_acceptance(
        acceptance_id_value="accept_replan_001",
        run_id="run_replan",
        card_id="CARD-REPLAN-004",
        result_id="result_replan_001",
        decision=CardAcceptanceDecision.BLOCK,
        reason="execution_failed_retry_recommended_escalated_after_retries",
        accepted_facts_delta=[],
        reviewer_provider="openai",
        reviewer_model="gpt-5.4",
        followup_actions=[
            {
                "action": "replan_candidate",
                "scope": "card",
                "trigger": "rework_escalated_after_retries",
            }
        ],
    )

    assert len(acceptance.followup_actions) == 1
    assert acceptance.followup_actions[0]["action"] == "replan_candidate"


def test_reviewer_smoke_profile_contract_points_to_existing_tests() -> None:
    profile_cases = {
        "reviewer_risk_reject_matrix": [
            "test_auto_acceptance_policy_can_reject_risk_by_keyword_policy",
            "test_auto_acceptance_policy_keeps_block_for_non_matching_risk_reject_keyword",
            "test_auto_acceptance_policy_can_reject_risk_by_keyword_policy_by_kind",
            "test_auto_acceptance_policy_keeps_block_for_non_matching_risk_reject_keyword_by_kind",
        ],
        "reviewer_retry_rework_matrix": [
            "test_auto_acceptance_policy_allows_failure_retry_rework_by_kind_policy",
            "test_auto_acceptance_policy_allows_failed_retry_rework_by_kind_reason_keywords",
            "test_auto_acceptance_policy_allows_timeout_retry_rework_by_kind_reason_keywords",
        ],
        "reviewer_counterexample_guardrails": [
            "test_auto_acceptance_policy_keeps_failure_reject_when_retry_kind_policy_does_not_match",
            "test_auto_acceptance_policy_keeps_timeout_reject_when_retry_keyword_kind_miss",
            "test_auto_acceptance_policy_keeps_block_for_non_matching_risk_reject_keyword",
            "test_auto_acceptance_policy_keeps_block_for_non_matching_risk_reject_keyword_by_kind",
        ],
    }

    for profile, case_names in profile_cases.items():
        assert case_names, profile
        for case_name in case_names:
            case_obj = globals().get(case_name)
            assert callable(case_obj), f"{profile} missing {case_name}"


def test_sync_card_terminal_result_ingests_visible_child_tab_task_run(tmp_path: Path) -> None:
    runtime = _RuntimeStub(tmp_path)
    services = taskbook_runtime_service.runtime_services(runtime)
    run = ComplexTaskRun(run_id="run_visible_progress", thread_id=runtime.thread_id)
    card = TaskCard(
        card_id="CARD-VC-001",
        taskbook_version=1,
        title="Visible child research",
        goal="research through visible child tab",
        kind=TaskCardKind.READ_ONLY,
        execution_mode=TaskCardExecutionMode.VISIBLE_CHILD_TAB,
        owned_files=["docs/visible.md"],
        acceptance_criteria=["summary reported"],
    )
    state = TaskCardState(
        card_id=card.card_id,
        status=TaskCardStatus.RUNNING,
        execution_refs=[
            ExecutionRef(
                kind=ExecutionRefKind.VISIBLE_CHILD_TAB,
                agent_id="tab-1",
                task_id="run_visible_progress:CARD-VC-001:0",
            )
        ],
    )
    runtime.visible_child_parent_tab_id = "main"
    runtime.visible_child_tab_backend = SimpleNamespace(
        visible_child_task_run_snapshots=lambda parent_tab_id: [
            {
                "run_id": "tab-1-run-1",
                "tab_id": "tab-1",
                "parent_tab_id": parent_tab_id,
                "state": "completed",
                "terminal_state": "completed",
                "terminal_reason": "provider_completed",
                "objective_state": "claimed_done",
                "summary": "visible child completed the research",
                "finished_at": "2026-04-06T12:00:00Z",
                "assignment_ref": {
                    "run_id": "run_visible_progress",
                    "card_id": "CARD-VC-001",
                    "attempt": 0,
                },
            }
        ]
    )

    result = taskbook_runtime_results_runtime.sync_card_terminal_result(
        runtime,
        services=services,
        run=run,
        card=card,
        state=state,
        delegated_index={},
        background_adapter=None,
        delegated_terminal_result_status_fn=lambda *_args, **_kwargs: None,
    )

    assert result is not None
    assert result.status is CardResultStatus.COMPLETED
    assert result.summary == "visible child completed the research"
    assert result.needs_review is False
    assert result.execution_ref is state.execution_refs[0]
    assert services.storage.latest_card_result(run.run_id, card.card_id) == result
