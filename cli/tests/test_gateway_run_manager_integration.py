from __future__ import annotations

from cli.agent_cli.gateway_core import TriggerRegistration, create_gateway_event, create_workflow_run
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_runs import RunStatus


class _GatewayFakeAgent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "provider_model": "test-model",
        }

    @staticmethod
    def plan(text, history=None, *, tool_executor=None, attachments=None):
        raise AssertionError("planner should not be used in gateway run-manager tests")


def _trigger() -> TriggerRegistration:
    return TriggerRegistration(
        trigger_key="demo_trigger",
        plugin_name="demo_plugin",
        trigger_kind="event",
        connector_key="demo_webhook",
        event_types=["demo.event"],
        workflow_name="handle_demo_event",
    )


def _event():
    return create_gateway_event(
        event_type="demo.event",
        source_kind="manual",
        source_id="cli",
    )


def test_save_gateway_workflow_run_backfills_run_id_and_syncs_run_manager() -> None:
    runtime = AgentCliRuntime(agent=_GatewayFakeAgent())
    workflow_run = create_workflow_run(
        trigger=_trigger(),
        event=_event(),
        status="pending",
        current_step="routed",
    )

    saved = runtime.save_gateway_workflow_run(workflow_run)

    assert str(saved.run_id or "").strip()
    run_record = runtime.run_manager.get(saved.run_id)
    assert run_record is not None
    assert run_record.status is RunStatus.CREATED
    assert run_record.payload["workflow_run_id"] == saved.workflow_run_id
    assert run_record.payload["status"] == "pending"


def test_update_workflow_run_state_syncs_run_manager_status_mapping() -> None:
    runtime = AgentCliRuntime(agent=_GatewayFakeAgent())
    workflow_run = create_workflow_run(
        trigger=_trigger(),
        event=_event(),
        status="pending",
        current_step="routed",
    )
    saved = runtime.save_gateway_workflow_run(workflow_run)
    assert str(saved.run_id or "").strip()

    runtime.update_workflow_run_state(saved.workflow_run_id, status="running")
    assert runtime.run_manager.get(saved.run_id).status is RunStatus.RUNNING  # type: ignore[union-attr]

    runtime.update_workflow_run_state(saved.workflow_run_id, status="completed", finished=True)
    assert runtime.run_manager.get(saved.run_id).status is RunStatus.COMPLETED  # type: ignore[union-attr]

    runtime.update_workflow_run_state(saved.workflow_run_id, status="failed", finished=True)
    assert runtime.run_manager.get(saved.run_id).status is RunStatus.FAILED  # type: ignore[union-attr]

    runtime.update_workflow_run_state(saved.workflow_run_id, status="cancelled", finished=True)
    assert runtime.run_manager.get(saved.run_id).status is RunStatus.CANCELLED  # type: ignore[union-attr]

    runtime.update_workflow_run_state(saved.workflow_run_id, status="pending")
    assert runtime.run_manager.get(saved.run_id).status is RunStatus.CREATED  # type: ignore[union-attr]


def test_save_gateway_workflow_run_propagates_parent_run_id() -> None:
    runtime = AgentCliRuntime(agent=_GatewayFakeAgent())
    workflow_run = create_workflow_run(
        trigger=_trigger(),
        event=_event(),
        status="pending",
        parent_run_id="run_parent_1",
    )

    saved = runtime.save_gateway_workflow_run(workflow_run)
    run_record = runtime.run_manager.get(saved.run_id)

    assert saved.parent_run_id == "run_parent_1"
    assert run_record is not None
    assert run_record.parent_run_id == "run_parent_1"


def test_update_workflow_run_state_maps_timed_out_status() -> None:
    runtime = AgentCliRuntime(agent=_GatewayFakeAgent())
    workflow_run = create_workflow_run(
        trigger=_trigger(),
        event=_event(),
        status="pending",
        current_step="routed",
    )
    saved = runtime.save_gateway_workflow_run(workflow_run)
    assert str(saved.run_id or "").strip()

    runtime.update_workflow_run_state(saved.workflow_run_id, status="timed_out", finished=True)

    run_record = runtime.run_manager.get(saved.run_id)
    assert run_record is not None
    assert run_record.status is RunStatus.TIMED_OUT
