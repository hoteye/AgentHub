from __future__ import annotations

from cli.agent_cli.background_tasks.models import BackgroundTaskType, TaskEnvelope
from cli.agent_cli.gateway_core.models import workflow_run_from_mapping


def test_task_envelope_run_projection_fields_roundtrip() -> None:
    envelope = TaskEnvelope(
        task_id="bg_1",
        task_type=BackgroundTaskType.TEAMMATE,
        thread_id="thread_1",
        parent_agent_id="agent_1",
        run_id="run_1",
        parent_run_id="run_parent_1",
    )
    payload = envelope.to_dict()
    restored = TaskEnvelope.from_dict(payload)

    assert payload["run_id"] == "run_1"
    assert payload["parent_run_id"] == "run_parent_1"
    assert restored.run_id == "run_1"
    assert restored.parent_run_id == "run_parent_1"


def test_run_projection_fields_are_backward_compatible_for_missing_payload_keys() -> None:
    legacy_envelope_payload = {
        "task_id": "bg_legacy",
        "task_type": "teammate",
        "thread_id": "thread_legacy",
    }
    restored_envelope = TaskEnvelope.from_dict(legacy_envelope_payload)
    assert restored_envelope.run_id == ""
    assert restored_envelope.parent_run_id == ""

    workflow = workflow_run_from_mapping(
        {
            "workflow_run_id": "wf_legacy",
            "workflow_name": "legacy_workflow",
            "plugin_name": "plugin_x",
            "trace_id": "trace_legacy",
            "status": "running",
            "started_at": "2026-04-07T00:00:00+00:00",
            "updated_at": "2026-04-07T00:00:01+00:00",
        }
    )
    assert workflow.run_id is None
    assert workflow.parent_run_id is None


def test_run_projection_fields_prefer_canonical_keys_when_live_aliases_exist() -> None:
    restored_envelope = TaskEnvelope.from_dict(
        {
            "task_id": "bg_alias",
            "task_type": "teammate",
            "thread_id": "thread_alias",
            "run_id": "run_canonical",
            "parent_run_id": "parent_canonical",
            "live_run_id": "run_alias",
            "live_parent_run_id": "parent_alias",
            "live_thread_id": "thread_alias_live",
        }
    )
    assert restored_envelope.run_id == "run_canonical"
    assert restored_envelope.parent_run_id == "parent_canonical"

    workflow = workflow_run_from_mapping(
        {
            "workflow_run_id": "wf_alias",
            "workflow_name": "alias_workflow",
            "plugin_name": "plugin_x",
            "trace_id": "trace_alias",
            "status": "running",
            "started_at": "2026-04-07T00:00:00+00:00",
            "updated_at": "2026-04-07T00:00:01+00:00",
            "run_id": "run_canonical",
            "parent_run_id": "parent_canonical",
            "live_run_id": "run_alias",
            "live_parent_run_id": "parent_alias",
            "live_thread_id": "thread_alias_live",
        }
    )
    assert workflow.run_id == "run_canonical"
    assert workflow.parent_run_id == "parent_canonical"


def test_run_projection_fields_ignore_command_policy_surface_noise() -> None:
    workflow = workflow_run_from_mapping(
        {
            "workflow_run_id": "wf_policy",
            "workflow_name": "policy_workflow",
            "plugin_name": "plugin_x",
            "trace_id": "trace_policy",
            "status": "running",
            "started_at": "2026-04-07T00:00:00+00:00",
            "updated_at": "2026-04-07T00:00:01+00:00",
            "run_id": "run_policy",
            "parent_run_id": "parent_policy",
            "command_policies_count": 2,
            "command_policy_surface": "denied:1,rewrite:1,checked:0",
            "command_policy_denied_count": 1,
        }
    )
    assert workflow.run_id == "run_policy"
    assert workflow.parent_run_id == "parent_policy"
