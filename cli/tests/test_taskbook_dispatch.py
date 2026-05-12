from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.background_tasks.models import BackgroundTaskType
from cli.agent_cli.orchestration.taskbook_dispatch import (
    build_teammate_task_text,
    dispatch_task_card,
)
from cli.agent_cli.orchestration.taskbook_models import ComplexTaskRun, TaskCard, TaskCardState
from cli.agent_cli.orchestration.taskbook_state import (
    ExecutionRefKind,
    TaskCardExecutionMode,
    TaskCardKind,
    TaskCardStatus,
)


def test_dispatch_read_only_card_uses_background_subagent_runtime() -> None:
    seen: dict[str, object] = {}

    class _FakeRuntime:
        def spawn_agent_result(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                tool_events=[
                    SimpleNamespace(
                        payload={
                            "agent_id": "agent_123",
                            "provider_name": "openai",
                            "model": "gpt-5.4",
                        }
                    )
                ]
            )

    run = ComplexTaskRun(run_id="ctrun_dispatch_1", thread_id="thread_1")
    card = TaskCard(
        card_id="CARD-001",
        taskbook_version=1,
        title="Read code",
        goal="Inspect code paths",
        kind=TaskCardKind.READ_ONLY,
        acceptance_criteria=["notes produced"],
    )
    state = TaskCardState(card_id="CARD-001", status=TaskCardStatus.QUEUED)

    result = dispatch_task_card(
        run, card, state, runtime=_FakeRuntime(), provider="openai", model="gpt-5.4"
    )

    assert seen["role"] == "subagent"
    assert seen["async_mode"] is True
    assert result.execution_ref.kind is ExecutionRefKind.DELEGATED_SUBAGENT
    assert result.execution_ref.agent_id == "agent_123"
    assert result.state.status is TaskCardStatus.RUNNING


def test_dispatch_visible_child_tab_card_uses_visible_backend() -> None:
    seen: dict[str, object] = {}

    class _Backend:
        active_tab_id = "main"

        def dispatch_visible_child_task(self, **kwargs):
            seen.update(kwargs)
            return {
                "tab_id": "tab-1",
                "task_id": "run_visible:CARD-001:0",
                "provider_name": "openai",
                "model": "gpt-5.4",
            }

    runtime = SimpleNamespace(
        visible_child_tab_backend=_Backend(),
        visible_child_parent_tab_id="main",
    )
    run = ComplexTaskRun(run_id="run_visible", thread_id="thread_1")
    card = TaskCard(
        card_id="CARD-001",
        taskbook_version=1,
        title="Visible child",
        goal="Inspect visible child path",
        kind=TaskCardKind.READ_ONLY,
        execution_mode=TaskCardExecutionMode.VISIBLE_CHILD_TAB,
        owned_files=["docs/visible.md"],
        acceptance_criteria=["result reported"],
    )
    state = TaskCardState(card_id="CARD-001", status=TaskCardStatus.QUEUED)

    result = dispatch_task_card(run, card, state, runtime=runtime)

    assert seen["parent_tab_id"] == "main"
    assert "Execution contract:" in seen["task_text"]
    assert seen["metadata"] == {"run_id": "run_visible", "card_id": "CARD-001", "attempt": 0}
    assert result.backend == "visible_child_tab"
    assert result.execution_ref.kind is ExecutionRefKind.VISIBLE_CHILD_TAB
    assert result.execution_ref.agent_id == "tab-1"
    assert result.execution_ref.task_id == "run_visible:CARD-001:0"
    assert result.state.status is TaskCardStatus.RUNNING
    assert result.state.last_scheduler_decision == "dispatched_via_visible_child_tab"


def test_dispatch_workspace_mutating_card_enqueues_background_teammate() -> None:
    seen: dict[str, object] = {}

    def _fake_enqueue_background_task(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(task_id="bg_123", status="queued")

    run = ComplexTaskRun(run_id="ctrun_dispatch_2", thread_id="thread_2")
    card = TaskCard(
        card_id="CARD-002",
        taskbook_version=1,
        title="Patch files",
        goal="Modify implementation",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["src/app.py"],
        allowed_paths=["src/**"],
        blocked_paths=["README.md"],
        acceptance_criteria=["tests pass"],
    )
    state = TaskCardState(card_id="CARD-002", status=TaskCardStatus.QUEUED)

    result = dispatch_task_card(
        run,
        card,
        state,
        enqueue_background_task_fn=_fake_enqueue_background_task,
        provider="glm",
        model="glm_5",
        reasoning_effort="medium",
        cwd="/tmp/demo",
    )

    assert seen["task_type"] is BackgroundTaskType.TEAMMATE
    assert seen["payload"]["sandbox_mode"] == "workspace-write"
    assert seen["payload"]["allowed_paths"] == ["src/**"]
    assert seen["payload"]["blocked_paths"] == ["README.md"]
    assert seen["payload"]["task"]
    assert "Execution contract:" in seen["payload"]["task"]
    assert "current working directory as the isolated workspace root" in seen["payload"]["task"]
    assert "Owned files: src/app.py" in seen["payload"]["task"]
    assert "Allowed paths: src/**" in seen["payload"]["task"]
    assert "Blocked paths: README.md" in seen["payload"]["task"]
    assert result.execution_ref.kind is ExecutionRefKind.BACKGROUND_TASK
    assert result.execution_ref.task_id == "bg_123"


def test_dispatch_background_task_card_can_target_benchmark() -> None:
    seen: dict[str, object] = {}

    def _fake_enqueue_background_task(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(task_id="bg_bench_1", status="queued")

    run = ComplexTaskRun(run_id="ctrun_dispatch_3")
    card = TaskCard(
        card_id="CARD-003",
        taskbook_version=1,
        title="Benchmark providers",
        goal="Run benchmark across providers",
        kind=TaskCardKind.LONG_RUNNING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TASK,
        acceptance_criteria=["latency captured"],
    )
    state = TaskCardState(card_id="CARD-003", status=TaskCardStatus.QUEUED)

    result = dispatch_task_card(
        run, card, state, enqueue_background_task_fn=_fake_enqueue_background_task
    )

    assert seen["task_type"] is BackgroundTaskType.BENCHMARK
    assert seen["payload"]["case"] == "Run benchmark across providers"
    assert result.backend == "benchmark"


def test_build_teammate_task_text_dedupes_inline_structured_goal_fields() -> None:
    card = TaskCard(
        card_id="CARD-004",
        taskbook_version=1,
        title="background teammate update orchestration status rendering",
        goal=(
            "background teammate update orchestration status rendering\n"
            "owned_files: cli/agent_cli/runtime_core/orchestration_commands.py\n"
            "acceptance_criteria: runtime wiring updated"
        ),
        kind=TaskCardKind.WORKSPACE_MUTATING,
        execution_mode=TaskCardExecutionMode.BACKGROUND_TEAMMATE,
        owned_files=["cli/agent_cli/runtime_core/orchestration_commands.py"],
        acceptance_criteria=["runtime wiring updated"],
    )

    task_text = build_teammate_task_text(card)

    assert "owned_files:" not in task_text
    assert "acceptance_criteria:" not in task_text
    assert task_text.count("Owned files: cli/agent_cli/runtime_core/orchestration_commands.py") == 1
    assert (
        task_text.count("Allowed paths: cli/agent_cli/runtime_core/orchestration_commands.py") == 1
    )
    assert task_text.count("Acceptance criteria: runtime wiring updated") == 1
