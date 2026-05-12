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


def _adapter(temp_dir: str):
    return build_background_task_adapter(
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


def _wait_completed_snapshot(runtime: AgentCliRuntime, agent_id: str):
    snapshot = None
    for _ in range(40):
        snapshot = runtime.wait_agent_result(agent_id, timeout_ms=250, wait_required=False)
        if snapshot.tool_events[0].payload["status"] == "completed":
            break
        time.sleep(0.05)
    assert snapshot is not None
    assert snapshot.tool_events[0].payload["status"] == "completed"
    return snapshot


def _wait_stored_result(adapter, task_id: str, *, notification_state: str):
    stored = None
    for _ in range(40):
        stored = adapter.storage.get_result(task_id)
        if stored is not None and (stored.artifact or {}).get("notification_state") == notification_state:
            return stored
        time.sleep(0.05)
    assert stored is not None
    return stored


def _spawn_background_teammate(runtime: AgentCliRuntime, *, task: str) -> str:
    spawned = runtime.spawn_agent_result(
        task=task,
        role="teammate",
        async_mode=True,
        mode="background",
        wait_required=False,
    )
    return spawned.tool_events[0].payload["agent_id"]


def test_background_adapter_patch_is_used_for_teammate_background_sync():
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime()
        runtime.set_cwd(temp_dir)
        adapter = _adapter(temp_dir)
        with patch("cli.agent_cli.runtime.build_background_task_adapter", autospec=True, return_value=adapter) as patched_builder:
            with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _DelegatedPlanner()):
                agent_id = _spawn_background_teammate(runtime, task="dynamic adapter patch")
                _wait_completed_snapshot(runtime, agent_id)
                stored = _wait_stored_result(adapter, f"bg_delegate_{agent_id}", notification_state="ready")

        assert patched_builder.call_count >= 1
        assert patched_builder.call_args.kwargs.get("cwd") == runtime.cwd
        assert stored.status.value == "completed"


def test_teammate_background_store_sync_ready_then_foreground_adopted():
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime()
        runtime.set_cwd(temp_dir)
        adapter = _adapter(temp_dir)
        with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
            with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _DelegatedPlanner()):
                agent_id = _spawn_background_teammate(runtime, task="background store sync")
                ready = _wait_completed_snapshot(runtime, agent_id)
                ready_payload = ready.tool_events[0].payload

                stored_ready = _wait_stored_result(adapter, f"bg_delegate_{agent_id}", notification_state="ready")
                ready_snapshot_payload = json.loads(Path(stored_ready.artifact["snapshot_path"]).read_text(encoding="utf-8"))
                assert ready_snapshot_payload["delegated_agent"]["completion_state"] == ready_payload["completion_state"]
                assert ready_snapshot_payload["delegated_agent"]["result_state"] == ready_payload["result_state"]

                adopted = runtime.wait_agent_result(agent_id, timeout_ms=1000)
                adopted_payload = adopted.tool_events[0].payload

                stored_adopted = _wait_stored_result(
                    adapter,
                    f"bg_delegate_{agent_id}",
                    notification_state="foreground_adopted",
                )

        adopted_snapshot_payload = json.loads(Path(stored_adopted.artifact["snapshot_path"]).read_text(encoding="utf-8"))
        assert stored_adopted.artifact["foreground_taken_over_at"] == adopted_payload["adopted_at"]
        assert adopted_snapshot_payload["delegated_agent"]["completion_state"] == adopted_payload["completion_state"]
        assert adopted_snapshot_payload["delegated_agent"]["result_state"] == adopted_payload["result_state"]


def test_teammate_background_checkpoint_persistence_in_snapshot_and_artifact():
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime()
        runtime.set_cwd(temp_dir)
        adapter = _adapter(temp_dir)
        with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
            with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _DelegatedPlanner()):
                agent_id = _spawn_background_teammate(runtime, task="checkpoint persistence")
                _wait_completed_snapshot(runtime, agent_id)
                stored = _wait_stored_result(adapter, f"bg_delegate_{agent_id}", notification_state="ready")

        snapshot_payload = json.loads(Path(stored.artifact["snapshot_path"]).read_text(encoding="utf-8"))
        checkpoints = list(snapshot_payload.get("checkpoints") or [])

        assert checkpoints
        assert isinstance(checkpoints[-1], dict)
        assert str(checkpoints[-1].get("checkpoint_id") or "").strip()
        assert snapshot_payload["checkpoint_count"] == len(checkpoints)
        assert stored.artifact["checkpoint_count"] == len(checkpoints)
        assert isinstance(stored.artifact.get("latest_checkpoint"), dict)
