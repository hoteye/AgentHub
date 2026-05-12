import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.background_tasks import (
    BackgroundTasksConfig,
    HueyConfig,
    build_background_task_adapter,
)
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.models import AgentIntent
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli.runtime_services import (
    delegated_agent_background_state_runtime as background_state_runtime,
    delegated_agent_background_state_transition_runtime as background_state_transition_runtime,
    delegated_agent_workflow_runtime as workflow_runtime,
)


class _DelegateAgent:
    host_platform = current_host_platform()

    @staticmethod
    def provider_status():
        return {
            "provider_ready": "true",
            "provider_name": "openai",
            "provider_model": "gpt-5.4",
            "provider_reasoning_effort": "high",
            "provider_planner": "openai_responses",
            "provider_source": "test",
            "provider_label": "openai | gpt-5.4 | tool-calls",
            "model_key": "gpt_54",
            "session_line": "openai-tools",
        }

    @staticmethod
    def resolve_delegate_execution(
        role_name,
        *,
        model=None,
        provider=None,
        reasoning_effort=None,
        timeout=None,
    ):
        del model, provider, reasoning_effort, timeout
        assert role_name == "teammate"
        return SimpleNamespace(
            config=ProviderConfig(
                model="glm-5",
                api_key="sk-glm",
                provider_name="glm",
                model_key="glm_5",
                planner_kind="openai_chat",
                wire_api="openai_chat",
                base_url="https://glm.example/v1",
                reasoning_effort="medium",
                raw_model={},
            ),
            timeout=18,
            source="delegation",
        )


class _DelegatedPlanner:
    def plan(self, user_text, history, *, tool_executor=None, attachments=None, input_items=None, prompt_cache_key=None):
        del history, tool_executor, attachments, input_items, prompt_cache_key
        return AgentIntent(assistant_text=f"answer:{user_text}")


def _runtime() -> AgentCliRuntime:
    return AgentCliRuntime(
        agent=_DelegateAgent(),
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )


def _wait_completed_snapshot(runtime: AgentCliRuntime, agent_id: str):
    snapshot = None
    for _ in range(30):
        snapshot = runtime.wait_agent_result(agent_id, timeout_ms=250, wait_required=False)
        if snapshot.tool_events[0].payload["status"] == "completed":
            break
        time.sleep(0.05)
    assert snapshot is not None
    return snapshot


def test_teammate_default_background_spawn_defaults_are_stable():
    runtime = _runtime()
    with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _DelegatedPlanner()):
        spawned = runtime.spawn_agent_result(task="后台总结仓库", role="teammate")

    payload = spawned.tool_events[0].payload
    assert spawned.tool_events[0].summary == "spawn_agent started"
    assert payload["async"] is True
    assert payload["delegation_mode"] == "background"
    assert payload["wait_required"] is False
    assert payload["completion_policy"] == "suggest_adopt"
    assert payload["background_priority"] == "low"
    assert payload["completion_state"] in {"pending", "ready_to_adopt"}


def test_completed_background_snapshot_surfaces_ready_to_adopt_consistently():
    runtime = _runtime()
    with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _DelegatedPlanner()):
        spawned = runtime.spawn_agent_result(task="后台总结仓库", role="teammate")
        agent_id = spawned.tool_events[0].payload["agent_id"]
        snapshot = _wait_completed_snapshot(runtime, agent_id)
        session_snapshot = runtime._snapshot_delegated_agent_session(runtime._delegated_agents[agent_id])

    payload = snapshot.tool_events[0].payload
    assert payload["status"] == "completed"
    assert payload["adopted"] is False
    assert payload["completion_state"] == "ready_to_adopt"
    assert payload["result_state"] == "pending_review"
    assert session_snapshot["completion_state"] == "ready_to_adopt"
    assert session_snapshot["result_state"] == "pending_review"
    assert session_snapshot["live_snapshot_version"] == 1
    assert session_snapshot["live_has_active_input"] is False


def test_background_store_mirror_matches_wait_state_transitions():
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime()
        runtime.set_cwd(temp_dir)
        adapter = build_background_task_adapter(
            config=BackgroundTasksConfig(
                enabled=True,
                provider="huey",
                huey=HueyConfig(
                    backend="sqlite",
                    path=Path(temp_dir) / "background_tasks.sqlite3",
                    results_dir=Path(temp_dir) / "results",
                    worker_count=1,
                    immediate=True,
                ),
            )
        )
        runtime._background_task_adapter_cache = adapter
        runtime._background_task_adapter_cwd = str(runtime.cwd or "").strip()
        with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _DelegatedPlanner()):
            spawned = runtime.spawn_agent_result(
                task="后台总结仓库",
                role="teammate",
                async_mode=True,
                mode="background",
                wait_required=False,
            )
            agent_id = spawned.tool_events[0].payload["agent_id"]
            ready_snapshot = _wait_completed_snapshot(runtime, agent_id)
            ready_payload = ready_snapshot.tool_events[0].payload

            stored_ready = None
            for _ in range(30):
                stored_ready = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                if stored_ready is not None and (stored_ready.artifact or {}).get("notification_state") == "ready":
                    break
                time.sleep(0.05)
            assert stored_ready is not None
            assert stored_ready.artifact["notification_state"] == "ready"
            ready_snapshot_path = Path(stored_ready.artifact["snapshot_path"])
            mirrored_ready_payload = json.loads(ready_snapshot_path.read_text(encoding="utf-8"))
            assert mirrored_ready_payload["delegated_agent"]["completion_state"] == ready_payload["completion_state"]
            assert mirrored_ready_payload["delegated_agent"]["result_state"] == ready_payload["result_state"]

            adopted = runtime.wait_agent_result(agent_id, timeout_ms=1000)
            adopted_payload = adopted.tool_events[0].payload

        stored_adopted = None
        for _ in range(30):
            stored_adopted = adapter.storage.get_result(f"bg_delegate_{agent_id}")
            if stored_adopted is not None and (stored_adopted.artifact or {}).get("notification_state") == "foreground_adopted":
                break
            time.sleep(0.05)
        assert stored_adopted is not None
        assert stored_adopted.artifact["notification_state"] == "foreground_adopted"
        assert stored_adopted.artifact["foreground_taken_over_at"] == adopted_payload["adopted_at"]
        adopted_snapshot_path = Path(stored_adopted.artifact["snapshot_path"])
        mirrored_adopted_payload = json.loads(adopted_snapshot_path.read_text(encoding="utf-8"))
        assert mirrored_adopted_payload["delegated_agent"]["completion_state"] == adopted_payload["completion_state"]
        assert mirrored_adopted_payload["delegated_agent"]["result_state"] == adopted_payload["result_state"]


def test_session_override_and_wait_required_states_stay_consistent():
    runtime = _runtime()
    with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _DelegatedPlanner()):
        spawned = runtime.spawn_agent_result(
            task="必须 join 的后台验证",
            role="teammate",
            async_mode=True,
            mode="background",
            wait_required=True,
        )
        agent_id = spawned.tool_events[0].payload["agent_id"]
        snapshot = _wait_completed_snapshot(runtime, agent_id)
        adopted = runtime.wait_agent_result(agent_id, timeout_ms=1000, reason="wait_for_child_result")

    snapshot_payload = snapshot.tool_events[0].payload
    adopted_payload = adopted.tool_events[0].payload
    assert snapshot_payload["completion_policy"] == "must_join"
    assert snapshot_payload["completion_state"] == "awaiting_join"
    assert snapshot_payload["adoption_expectation"] == "wait_agent_to_adopt"
    assert adopted_payload["completion_state"] == "adopted"
    assert adopted_payload["adoption_expectation"] == "already_adopted"

    restore_runtime = SimpleNamespace(
        _delegated_background_priority=lambda **kwargs: workflow_runtime.delegated_background_priority(
            role=kwargs.get("role"),
            delegation_mode=kwargs.get("delegation_mode"),
            wait_required=kwargs.get("wait_required"),
        ),
        _delegated_parallel_group=lambda task_shape: workflow_runtime.delegated_parallel_group(task_shape),
        _normalized_planner_input_item=lambda item: item if isinstance(item, dict) else None,
        _normalized_history_item=lambda item: item if isinstance(item, dict) else None,
        _restored_delegated_status=lambda **kwargs: background_state_transition_runtime.restored_delegated_status(
            status=kwargs.get("status"),
            queued_inputs=kwargs.get("queued_inputs") or [],
            close_requested=bool(kwargs.get("close_requested")),
            closed=bool(kwargs.get("closed")),
            assistant_text=str(kwargs.get("assistant_text") or ""),
            error=str(kwargs.get("error") or ""),
        ),
    )
    restored = background_state_runtime.restored_session_kwargs(
        restore_runtime,
        {
            "status": "completed",
            "delegation_mode": "background",
            "wait_required": "true",
            "close_requested": "false",
            "closed": "false",
            "adopted": "false",
            "last_wait_timed_out": "false",
            "text": "answer:必须 join 的后台验证",
            "created_at": "2026-04-06T00:00:00+00:00",
            "updated_at": "2026-04-06T00:00:01+00:00",
        },
        agent_id="agent_restore",
        role="teammate",
        config=SimpleNamespace(),
        resolution=SimpleNamespace(source="delegation"),
        timeout=18,
        queued_inputs=[],
        raw_status="completed",
        active_input=None,
        now_iso_fn=lambda: "2026-04-06T00:00:02+00:00",
    )
    assert restored["wait_required"] is True
    assert restored["background_priority"] == "normal"
    assert restored["close_requested"] is False
    assert restored["closed"] is False
    assert restored["adopted"] is False
    assert restored["last_wait_timed_out"] is False
