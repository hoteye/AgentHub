from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace

from cli.agent_cli.providers.config_catalog import ProviderConfig  # noqa: E402
from cli.agent_cli.models import ReferenceContextItem  # noqa: E402
from cli.agent_cli.runtime_services import prompt_turn_context_runtime  # noqa: E402

class _AgentStub:
    @staticmethod
    def provider_status():
        return {"provider_model": "gpt-test"}

class _RuntimeStub:
    def __init__(self) -> None:
        self.cwd = "/tmp/work"
        self.agent = _AgentStub()
        self.runtime_policy = SimpleNamespace(
            approval_policy="never",
            sandbox_mode="danger-full-access",
            network_access_enabled=True,
        )
        self.reference_context_items = []
        self._environment_context_history = []
        self._context_update_history = []
        self._environment_context_snapshot = {}
        self._workspace_context_snapshot = {}

    @staticmethod
    def _normalized_history_item(item):
        if not isinstance(item, dict):
            return None
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant", "system", "developer"} or not content:
            return None
        return {"role": role, "content": content}

    @staticmethod
    def _planner_message_history_input_items(history):
        items = []
        for entry in list(history or []):
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "system").strip().lower() or "system"
            content = str(entry.get("content") or "").strip()
            if not content:
                continue
            items.append(
                {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text", "text": content}],
                }
            )
        return items

class PromptTurnContextRuntimeTests(unittest.TestCase):
    def test_turn_context_rollout_items_returns_empty_without_context_payload(self) -> None:
        runtime = _RuntimeStub()

        items = prompt_turn_context_runtime.turn_context_rollout_items(
            runtime,
            pending_environment_messages=[],
            pending_context_messages=[],
            pending_context_items=[],
            next_environment_snapshot={},
            next_workspace_snapshot={},
        )

        self.assertEqual(items, [])

    def test_turn_context_rollout_items_include_environment_and_reference_context(self) -> None:
        runtime = _RuntimeStub()

        items = prompt_turn_context_runtime.turn_context_rollout_items(
            runtime,
            pending_environment_messages=[{"role": "system", "content": "env snapshot"}],
            pending_context_messages=[{"role": "system", "content": "workspace note"}],
            pending_context_items=[
                ReferenceContextItem(
                    item_type="file",
                    source="tool:file_read",
                    label="status.txt",
                    path="/tmp/work/status.txt",
                    description="current repo state",
                    metadata={"state": "dirty"},
                )
            ],
            next_environment_snapshot={
                "shell": "bash",
                "current_date": "2026-04-05",
                "timezone": "Asia/Shanghai",
            },
            next_workspace_snapshot={"project": "AgentHub"},
        )

        self.assertEqual(len(items), 1)
        turn_context = dict(items[0])
        self.assertEqual(turn_context.get("model"), "gpt-test")
        self.assertEqual(turn_context.get("shell"), "bash")
        self.assertEqual(
            [item.get("source") for item in list(turn_context.get("items") or [])],
            ["environment_context"],
        )
        self.assertEqual(
            turn_context.get("state"),
            {
                "environment_context_snapshot": {
                    "shell": "bash",
                    "current_date": "2026-04-05",
                    "timezone": "Asia/Shanghai",
                },
                "workspace_context_snapshot": {"project": "AgentHub"},
            },
        )
        self.assertEqual(len(list(turn_context.get("reference_context_items") or [])), 1)

    def test_turn_context_rollout_items_persist_effective_codex_headless_policy(self) -> None:
        runtime = _RuntimeStub()
        runtime.runtime_policy = SimpleNamespace(
            approval_policy="on-request",
            sandbox_mode="read-only",
            network_access_enabled=True,
        )
        runtime._agenthub_headless_mode = "prompt"
        runtime.agent._planner = SimpleNamespace(
            config=ProviderConfig(
                model="gpt-5.4",
                api_key="test-key",
                interaction_profile="codex_openai",
                interaction_profile_source="test",
            )
        )

        items = prompt_turn_context_runtime.turn_context_rollout_items(
            runtime,
            pending_environment_messages=[{"role": "system", "content": "env snapshot"}],
            pending_context_messages=[],
            pending_context_items=[],
            next_environment_snapshot={
                "shell": "bash",
                "current_date": "2026-04-05",
                "timezone": "Asia/Shanghai",
            },
            next_workspace_snapshot={"project": "AgentHub"},
        )

        self.assertEqual(len(items), 1)
        turn_context = dict(items[0])
        self.assertEqual(turn_context.get("approval_policy"), "never")
        self.assertEqual(turn_context.get("sandbox_mode"), "read-only")

    def test_apply_turn_context_updates_persists_history_reference_items_and_snapshots(self) -> None:
        runtime = _RuntimeStub()
        pending_context_item = ReferenceContextItem(
            item_type="file",
            source="tool:file_read",
            label="status.txt",
            path="/tmp/work/status.txt",
            description="current repo state",
            metadata={"state": "dirty"},
        )

        prompt_turn_context_runtime.apply_turn_context_updates(
            runtime,
            pending_environment_messages=[
                {"role": "system", "content": "env snapshot"},
                {"role": "system", "content": "env snapshot"},
            ],
            pending_context_messages=[{"role": "system", "content": "workspace note"}],
            pending_context_items=[pending_context_item],
            next_environment_snapshot={"shell": "bash"},
            next_workspace_snapshot={"project": "AgentHub"},
        )

        self.assertEqual(runtime._environment_context_history, [{"role": "system", "content": "env snapshot"}])
        self.assertEqual(runtime._context_update_history, [{"role": "system", "content": "workspace note"}])
        self.assertEqual(runtime.reference_context_items, [pending_context_item.to_dict()])
        self.assertEqual(runtime._environment_context_snapshot, {"shell": "bash"})
        self.assertEqual(runtime._workspace_context_snapshot, {"project": "AgentHub"})
